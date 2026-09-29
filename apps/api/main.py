"""ClientLaunch business API. n8n owns workflow orchestration; this service owns durable state."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import (
    Approval, Asset, ChecklistItem, Client, ClientSession, EventReceipt, ExternalResource,
    HandoffSummary, IntakeSubmission, Onboarding, OnboardingTemplateVersion, OutboxEmail,
    PlanRevision, PortalInvite, ProjectFolder, ProvisioningOperation, ReminderTask, SimResource, TimelineEvent,
    TaskCard, User, UserSession, WonDeal, WorkflowDispatch, WorkflowException, Workspace, utcnow,
)
from .schemas import (
    ApprovalDecision, ChecklistEdit, HandoffRequest, IntakeRequest, LifecycleAction, LoginRequest, PlanDraft,
    OutboxAck, PortalExchange, ProvisionClaim, ProvisionComplete, RecoverRequest, ReminderApproval, TaskCardAck, TaskCardReconcile,
    ReminderDispatch, ReminderEvaluate, SimCardCreate, SimCardUpdate, SimCreate, SimFaultRequest, SimMail, TaskCardClaim, WelcomeRequest, WonDealEvent, WorkflowErrorReport,
)
from .security import (
    APP_MODE, COOKIE_SECURE, INTERNAL_KEY, OperatorActor, aware, client_onboarding,
    csrf_for_session, digest, fresh_session_expiry, generate_token, internal_service,
    operator_actor, operator_writer, portal_token_for, verify_password, verify_webhook,
)
from .services import (
    add_event, canonical_hash, client_detail, detail, evaluate_reminders, iso, list_item,
    progress, refresh_readiness, require_onboarding,
)


app = FastAPI(title="ClientLaunch Business API", version="0.1.0")
allowed_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Internal-Key", "X-ClientLaunch-Signature", "Idempotency-Key"])


@app.on_event("startup")
def create_demo_schema() -> None:
    if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
        Base.metadata.create_all(engine)


def _user_json(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "workspace_id": user.workspace_id, "workspace_name": user.workspace.name}


def _operator_or_internal(request: Request, db: Session) -> OperatorActor | None:
    key = request.headers.get("x-internal-key")
    if key and hmac.compare_digest(key, INTERNAL_KEY):
        return None
    return operator_actor(request, db)


def _require_demo_simulator() -> None:
    if os.getenv("CONNECTOR_MODE", "demo").lower() != "demo":
        raise HTTPException(status_code=403, detail="Local connector simulator disabled in connected mode")


def _ensure_task_cards(db: Session, onboarding_id: str, board_external_id: str) -> None:
    for item in db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding_id)).all():
        if not db.scalar(select(TaskCard).where(TaskCard.checklist_item_id == item.id)):
            db.add(TaskCard(onboarding_id=onboarding_id, checklist_item_id=item.id, board_external_id=board_external_id, desired_status=item.status, sync_state="pending", idempotency_key=f"clientlaunch:{onboarding_id}:trello:card:{item.id}"))


def _freeze_folder_plan(db: Session, onboarding: Onboarding) -> None:
    """Snapshot the purchased template folders when a plan is approved."""
    if db.scalar(select(ProjectFolder.id).where(ProjectFolder.onboarding_id == onboarding.id).limit(1)):
        return
    saved_blueprints = (onboarding.current_plan.plan.get("folder_blueprints") if onboarding.current_plan else None) or {}
    for service_code in sorted(onboarding.deal.services):
        saved = saved_blueprints.get(service_code)
        if saved:
            template = db.get(OnboardingTemplateVersion, saved["template_version_id"])
            if template and (template.workspace_id != onboarding.workspace_id or template.service_code != service_code):
                raise HTTPException(status_code=409, detail="Folder template scope mismatch")
        else:
            template = db.scalar(select(OnboardingTemplateVersion).where(
                OnboardingTemplateVersion.workspace_id == onboarding.workspace_id,
                OnboardingTemplateVersion.service_code == service_code,
                OnboardingTemplateVersion.active.is_(True),
            ).order_by(OnboardingTemplateVersion.version.desc()))
        if template is None:
            raise HTTPException(status_code=422, detail=f"No folder template for {service_code}")
        service_name = saved["name"] if saved else template.name
        folder_names = saved["folders"] if saved else template.folder_blueprint
        service_folder = ProjectFolder(
            onboarding_id=onboarding.id, template_version_id=template.id,
            service_code=service_code, folder_key="service", name=service_name,
            parent_id=None, sort_order=0,
        )
        db.add(service_folder)
        db.flush()
        for index, raw_name in enumerate(folder_names):
            name = str(raw_name).strip()
            if not name or len(name) > 240:
                raise HTTPException(status_code=422, detail=f"Invalid folder blueprint for {service_code}")
            db.add(ProjectFolder(
                onboarding_id=onboarding.id, template_version_id=template.id,
                service_code=service_code, folder_key=f"item:{index}", name=name,
                parent_id=service_folder.id, sort_order=index + 1,
            ))


def _root_folder(db: Session, onboarding_id: str) -> ExternalResource | None:
    return db.scalar(select(ExternalResource).where(
        ExternalResource.onboarding_id == onboarding_id,
        ExternalResource.system == "drive", ExternalResource.kind == "folder",
    ))


def _folder_parent_external_id(db: Session, folder: ProjectFolder) -> str | None:
    if folder.parent_id:
        parent = db.get(ProjectFolder, folder.parent_id)
        return parent.external_id if parent else None
    root = _root_folder(db, folder.onboarding_id)
    return root.external_id if root else None


def _provisioning_complete(db: Session, onboarding: Onboarding) -> bool:
    systems = set(db.scalars(select(ExternalResource.system).where(ExternalResource.onboarding_id == onboarding.id)).all())
    if not {"drive", "trello"}.issubset(systems):
        return False
    folders = db.scalars(select(ProjectFolder).where(ProjectFolder.onboarding_id == onboarding.id)).all()
    planned_services = {folder.service_code for folder in folders if folder.folder_key == "service"}
    return planned_services == set(onboarding.deal.services) and all(folder.external_id for folder in folders)


def _finish_provisioning_if_ready(db: Session, onboarding: Onboarding) -> None:
    if _provisioning_complete(db, onboarding) and onboarding.status == "provisioning":
        onboarding.status = "waiting_for_client"
        onboarding.substate = None
        add_event(db, onboarding.id, "provisioning_complete", "Project folders and board are ready")
        refresh_readiness(db, onboarding)


def _record_reconciled_resource(db: Session, onboarding: Onboarding, operation: ProvisioningOperation, external_id: str, preview: dict) -> None:
    if operation.action == "create_board" and not str(preview.get("todo_list_id") or "").strip():
        raise HTTPException(status_code=422, detail="Verified To Do list ID required for a reconciled board")
    if operation.action == "create_child_folder":
        folder = db.get(ProjectFolder, operation.request_payload.get("folder_id"))
        if not folder or folder.onboarding_id != onboarding.id:
            raise HTTPException(status_code=409, detail="Operation folder is missing")
        if folder.external_id and folder.external_id != external_id:
            raise HTTPException(status_code=409, detail="Different child folder already recorded")
        folder.external_id = external_id
        folder.url = preview.get("url")
    else:
        kind = "folder" if operation.system == "drive" else "board"
        existing = db.scalar(select(ExternalResource).where(
            ExternalResource.onboarding_id == onboarding.id,
            ExternalResource.system == operation.system, ExternalResource.kind == kind,
        ))
        if existing and existing.external_id != external_id:
            raise HTTPException(status_code=409, detail="Different external resource already recorded")
        if not existing:
            db.add(ExternalResource(onboarding_id=onboarding.id, system=operation.system,
                                    kind=kind, external_id=external_id, preview=preview))
        if operation.system == "trello":
            _ensure_task_cards(db, onboarding.id, external_id)
    operation.external_id = external_id
    operation.status = "succeeded"
    operation.error = None
    db.flush()
    _finish_provisioning_if_ready(db, onboarding)


def _mark_card_desired(db: Session, item: ChecklistItem, source_id: str) -> None:
    card = db.scalar(select(TaskCard).where(TaskCard.checklist_item_id == item.id))
    if card and card.desired_status != item.status:
        card.desired_status = item.status
        # Preserve an in-flight or uncertain write and its provider key until its
        # observed outcome is recorded. That outcome schedules the newer status.
        if card.synced_status != card.desired_status and card.sync_state not in {"claimed", "unknown"}:
            card.sync_state = "pending"
            if card.external_card_id:
                card.idempotency_key = f"clientlaunch:{card.onboarding_id}:trello:card:{item.id}:{item.status}:{source_id}"


def _attempt_dispatch(db: Session, dispatch: WorkflowDispatch) -> None:
    url_var = {"approval": "N8N_PROVISION_WEBHOOK_URL", "submission": "N8N_SUBMISSION_WEBHOOK_URL", "recovery": "N8N_RECOVERY_WEBHOOK_URL"}.get(dispatch.kind)
    url = os.getenv(url_var or "", "") if url_var else ""
    if not url:
        return
    # The durable row is committed before this request; a failed call remains available to n8n polling.
    import httpx

    dispatch.attempt_count += 1
    try:
        response = httpx.post(url, json=dispatch.payload, headers={"X-Internal-Key": INTERNAL_KEY, "Idempotency-Key": dispatch.id}, timeout=3.0)
        response.raise_for_status()
        dispatch.status = "delivered"
        dispatch.delivered_at = utcnow()
        dispatch.last_error = None
    except httpx.HTTPError as exc:
        dispatch.last_error = str(exc)[:1000]
    db.commit()


def _dispatch_finished(db: Session, dispatch: WorkflowDispatch, onboarding: Onboarding) -> bool:
    if dispatch.kind == "submission":
        submission_id = dispatch.payload.get("submission_id")
        if not submission_id or not db.scalar(select(WorkflowDispatch.id).where(
            WorkflowDispatch.kind == "submission_process", WorkflowDispatch.dedupe_key == submission_id,
        )):
            return False
    elif not _provisioning_complete(db, onboarding):
        return False
    cards = db.scalars(select(TaskCard).where(TaskCard.onboarding_id == onboarding.id)).all()
    if any(card.sync_state != "synced" or card.synced_status != card.desired_status for card in cards):
        return False
    if dispatch.kind == "submission":
        return True
    welcome = db.scalar(select(OutboxEmail).where(
        OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome",
    ))
    return bool(welcome and welcome.status in {"simulated_sent", "dispatched"})


def _refresh_stale_dispatches(db: Session) -> None:
    # A webhook's 2xx only confirms n8n accepted the trigger. Business effects
    # may still fail before the first operation is claimed, so revisit accepted
    # deliveries after a quiet interval using the durable business state.
    cutoff = utcnow() - timedelta(minutes=5)
    stale = db.scalars(select(WorkflowDispatch).where(
        WorkflowDispatch.status == "delivered", WorkflowDispatch.delivered_at <= cutoff,
        WorkflowDispatch.kind.in_(["approval", "submission", "recovery"]),
    ).order_by(WorkflowDispatch.delivered_at)).all()
    changed = False
    for dispatch in stale:
        onboarding = db.get(Onboarding, dispatch.onboarding_id)
        if not onboarding:
            continue
        if os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
            changed = bool(_reconcile_demo_cards(db, onboarding)) or changed
        if _dispatch_finished(db, dispatch, onboarding):
            dispatch.status = "completed"
            changed = True
            continue
        if onboarding.status not in {"provisioning", "waiting_for_client", "ready"} or onboarding.substate in {"failed", "uncertain"}:
            continue
        operations = db.scalars(select(ProvisioningOperation.status).where(
            ProvisioningOperation.onboarding_id == onboarding.id,
        )).all()
        if any(status in {"claimed", "unknown", "failed", "compensation_requested"} for status in operations):
            continue
        cards = db.scalars(select(TaskCard.sync_state).where(TaskCard.onboarding_id == onboarding.id)).all()
        if any(state in {"claimed", "unknown"} for state in cards):
            continue
        # An SMTP send can have succeeded even when its acknowledgment was lost.
        # Never replay that branch while its provider outcome is uncertain.
        if db.scalar(select(OutboxEmail.id).where(
            OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome",
            OutboxEmail.status == "queued",
        ).limit(1)):
            continue
        dispatch.status = "pending"
        dispatch.delivered_at = None
        dispatch.last_error = "Accepted webhook did not reach complete business state; safe retry queued"
        add_event(db, onboarding.id, "dispatch_retry_queued", "Incomplete workflow run queued for safe replay", {"dispatch_id": dispatch.id})
        changed = True
    if changed:
        db.commit()


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.scalar(select(func.count()).select_from(Workspace))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "mode": APP_MODE, "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower()}


@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    email = str(body.email).lower()
    user = db.scalar(select(User).where(User.email == email, User.active.is_(True)))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_token()
    csrf_token = csrf_for_session(token)
    session = UserSession(user_id=user.id, token_hash=digest(token), csrf_token_hash=digest(csrf_token), expires_at=fresh_session_expiry())
    db.add(session)
    db.commit()
    response.set_cookie("clientlaunch_session", token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=8 * 60 * 60, path="/api")
    return {"csrf_token": csrf_token, "expires_at": iso(session.expires_at), "user": _user_json(user)}


@app.get("/api/auth/me")
def me(request: Request, actor: OperatorActor = Depends(operator_actor)) -> dict:
    token = request.cookies.get("clientlaunch_session")
    return {"user": _user_json(actor.user), "csrf_token": csrf_for_session(token) if token else None}


@app.post("/api/auth/logout")
def logout(response: Response, actor: OperatorActor = Depends(operator_actor), db: Session = Depends(get_db)) -> dict:
    actor.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie("clientlaunch_session", path="/api")
    return {"status": "signed_out"}


@app.post("/api/events/won-deal")
async def receive_won_deal(request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Event must be an object")
    verify_webhook(payload, request.headers.get("x-clientlaunch-signature"))
    event = WonDealEvent.model_validate(payload)
    workspace = db.scalar(select(Workspace).where(Workspace.slug == event.workspace_slug))
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    payload_hash = canonical_hash(payload)
    receipt = db.scalar(select(EventReceipt).where(EventReceipt.workspace_id == workspace.id, EventReceipt.event_id == event.event_id))
    if receipt:
        if receipt.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Event ID reused with different payload")
        onboarding = db.get(Onboarding, receipt.onboarding_id)
        return {"onboarding_id": onboarding.id, "status": onboarding.status, "duplicate": True, "event_id": event.event_id}
    service_codes = set(db.scalars(select(OnboardingTemplateVersion.service_code).where(OnboardingTemplateVersion.workspace_id == workspace.id, OnboardingTemplateVersion.active.is_(True))).all())
    if any(service not in service_codes for service in event.services):
        raise HTTPException(status_code=422, detail="Unknown purchased service")
    owner = db.scalar(select(User).where(User.workspace_id == workspace.id, User.email == str(event.account_owner_email).lower(), User.active.is_(True)))
    if not owner:
        raise HTTPException(status_code=422, detail="Account owner not found")
    business_payload = event.model_dump(mode="json", exclude={"event_id"})
    business_hash = canonical_hash(business_payload)
    existing_deal = db.scalar(select(WonDeal).where(WonDeal.workspace_id == workspace.id, WonDeal.external_deal_id == event.external_deal_id))
    if existing_deal:
        if existing_deal.business_hash != business_hash:
            raise HTTPException(status_code=409, detail="Deal scope changed; submit a reviewed revision")
        onboarding = db.scalar(select(Onboarding).where(Onboarding.deal_id == existing_deal.id))
        db.add(EventReceipt(workspace_id=workspace.id, event_id=event.event_id, payload_hash=payload_hash, onboarding_id=onboarding.id))
        db.commit()
        return {"onboarding_id": onboarding.id, "status": onboarding.status, "duplicate": True, "event_id": event.event_id}
    client = db.scalar(select(Client).where(Client.workspace_id == workspace.id, Client.email == str(event.client.email).lower()))
    if not client:
        client = Client(workspace_id=workspace.id, name=event.client.name, email=str(event.client.email).lower())
        db.add(client)
        db.flush()
    deal = WonDeal(workspace_id=workspace.id, client_id=client.id, external_deal_id=event.external_deal_id, business_hash=business_hash, services=event.services, approved_scope=event.approved_scope, proposal_text=event.proposal_text, timeline=event.timeline, account_owner_id=owner.id)
    db.add(deal)
    db.flush()
    onboarding = Onboarding(workspace_id=workspace.id, deal_id=deal.id, client_id=client.id, status="received")
    db.add(onboarding)
    db.flush()
    db.add(EventReceipt(workspace_id=workspace.id, event_id=event.event_id, payload_hash=payload_hash, onboarding_id=onboarding.id))
    add_event(db, onboarding.id, "received", "Signed won-deal event received", {"event_id": event.event_id})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent duplicate event; retry fetch") from exc
    return {"onboarding_id": onboarding.id, "status": onboarding.status, "duplicate": False, "event_id": event.event_id}


@app.get("/api/templates")
def templates(request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _operator_or_internal(request, db)
    query = select(OnboardingTemplateVersion).where(OnboardingTemplateVersion.active.is_(True))
    if actor:
        query = query.where(OnboardingTemplateVersion.workspace_id == actor.user.workspace_id)
    rows = db.scalars(query.order_by(OnboardingTemplateVersion.service_code)).all()
    return {"items": [{"id": row.id, "workspace_id": row.workspace_id, "service_code": row.service_code, "version": row.version, "name": row.name, "description": row.description, "checklist": row.checklist, "folder_blueprint": row.folder_blueprint, "board_blueprint": row.board_blueprint} for row in rows]}


@app.get("/api/onboardings")
def onboardings(actor: OperatorActor = Depends(operator_actor), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Onboarding).where(Onboarding.workspace_id == actor.user.workspace_id).order_by(Onboarding.created_at.desc())).all()
    return {"items": [list_item(db, row) for row in rows]}


@app.get("/api/onboardings/{onboarding_id}")
def onboarding_detail(onboarding_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    actor = _operator_or_internal(request, db)
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id if actor else None)
    result = detail(db, onboarding)
    if actor and actor.user.role == "viewer":
        result["onboarding"].pop("portal_link", None)
        for message in result["welcome"]:
            message["body"] = None
    return result


@app.post("/api/onboardings/{onboarding_id}/plan", dependencies=[Depends(internal_service)])
def save_plan(onboarding_id: str, body: PlanDraft, db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id)
    if onboarding.status not in {"received", "planning", "awaiting_approval"}:
        raise HTTPException(status_code=409, detail="Onboarding cannot accept a new plan in current state")
    services = set(onboarding.deal.services)
    templates: dict[str, OnboardingTemplateVersion] = {}
    template_items: dict[str, dict[str, dict]] = {}
    for service_code in sorted(services):
        template = db.scalar(select(OnboardingTemplateVersion).where(OnboardingTemplateVersion.workspace_id == onboarding.workspace_id, OnboardingTemplateVersion.service_code == service_code, OnboardingTemplateVersion.active.is_(True)).order_by(OnboardingTemplateVersion.version.desc()))
        if not template:
            raise HTTPException(status_code=422, detail=f"No template for {service_code}")
        templates[service_code] = template
        template_items[service_code] = {item["key"]: item for item in template.checklist}
    normalized: dict[str, dict] = {}
    for item in body.checklist:
        if item.service_code not in services:
            raise HTTPException(status_code=422, detail=f"Checklist item uses unpurchased service {item.service_code}")
        if item.source == "scope" and (not item.evidence or item.evidence.casefold() not in onboarding.deal.approved_scope.casefold()):
            raise HTTPException(status_code=422, detail=f"Scope evidence missing for {item.key}")
        data = item.model_dump(mode="json")
        if item.source == "template":
            service_items = template_items[item.service_code]
            raw_key = item.key
            prefix = f"{item.service_code}_"
            if raw_key not in service_items and raw_key.startswith(prefix):
                raw_key = raw_key[len(prefix):]
            if raw_key not in service_items:
                continue  # The active workspace template, not the AI draft, defines base tasks.
            canonical = service_items[raw_key]
            data.update(key=raw_key, title=canonical["title"], required=canonical.get("required", True),
                        client_visible=canonical.get("client_visible", True))
        key = f"{item.service_code}:{data['key']}"
        if key in normalized:
            if item.source == "template" and normalized[key]["source"] == "template":
                continue
            raise HTTPException(status_code=422, detail=f"Duplicate checklist key {key}")
        normalized[key] = data
    for service_code in sorted(services):
        for item in templates[service_code].checklist:
            key = f"{service_code}:{item['key']}"
            normalized.setdefault(key, {"key": item["key"], "title": item["title"], "description": item.get("description", ""), "required": item.get("required", True), "source": "template", "service_code": service_code, "evidence": None, "client_visible": item.get("client_visible", True), "due_date": item.get("due_date"), "owner": item.get("owner")})
    content = body.model_dump(mode="json")
    content["checklist"] = list(normalized.values())
    content["folder_blueprints"] = {
        code: {"template_version_id": template.id, "name": template.name, "folders": list(template.folder_blueprint)}
        for code, template in sorted(templates.items())
    }
    if not content["summary"].strip():
        content["summary"] = f"{onboarding.client.name}: onboarding for {', '.join(templates[code].name for code in sorted(services))}."
    proposal_hash = canonical_hash(content)
    previous = db.scalar(select(func.max(PlanRevision.revision)).where(PlanRevision.onboarding_id == onboarding.id)) or 0
    if onboarding.current_plan and onboarding.current_plan.proposal_hash == proposal_hash and onboarding.current_plan.status == "pending":
        return {"id": onboarding.current_plan.id, "revision": onboarding.current_plan.revision, "proposal_hash": proposal_hash, "status": "pending", "duplicate": True}
    revision = PlanRevision(onboarding_id=onboarding.id, revision=previous + 1, proposal_hash=proposal_hash, plan=content, status="pending")
    db.add(revision)
    db.flush()
    onboarding.current_plan_id = revision.id
    onboarding.status = "awaiting_approval"
    onboarding.updated_at = utcnow()
    db.add(Approval(onboarding_id=onboarding.id, plan_revision_id=revision.id, proposal_hash=proposal_hash, expires_at=utcnow() + timedelta(days=2)))
    add_event(db, onboarding.id, "plan_proposed", f"Plan revision {revision.revision} is awaiting review", {"plan_revision_id": revision.id})
    db.commit()
    return {"id": revision.id, "revision": revision.revision, "proposal_hash": proposal_hash, "status": "pending", "duplicate": False}


@app.post("/api/onboardings/{onboarding_id}/approval")
def decide_plan(onboarding_id: str, body: ApprovalDecision, actor: OperatorActor = Depends(operator_writer), db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    if onboarding.status != "awaiting_approval" or onboarding.current_plan_id != body.plan_revision_id:
        raise HTTPException(status_code=409, detail="Plan revision is no longer current")
    plan = onboarding.current_plan
    if plan is None or not hmac.compare_digest(plan.proposal_hash, body.proposal_hash):
        raise HTTPException(status_code=409, detail="Proposal hash mismatch")
    approval = db.scalar(select(Approval).where(Approval.plan_revision_id == plan.id))
    now = utcnow()
    if approval is None or approval.status != "pending" or aware(approval.expires_at) <= now:
        raise HTTPException(status_code=409, detail="Approval expired or already used")
    result = db.execute(update(Approval).where(Approval.id == approval.id, Approval.status == "pending", Approval.expires_at > now).values(status="approved" if body.decision == "approve" else "rejected", decided_at=now, decided_by_id=actor.user.id, reason=body.reason).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Approval already decided")
    plan.status = "approved" if body.decision == "approve" else "rejected"
    if body.decision == "approve":
        for item in plan.plan["checklist"]:
            due = datetime.combine(datetime.fromisoformat(item["due_date"]).date(), time(17, 0), tzinfo=timezone.utc) if item.get("due_date") else None
            db.add(ChecklistItem(onboarding_id=onboarding.id, item_key=f"{item['service_code']}:{item['key']}", title=item["title"], description=item.get("description") or "", required=item.get("required", True), status="open", due_at=due, owner_name=item.get("owner"), source=item["source"], client_visible=item.get("client_visible", True)))
        _freeze_folder_plan(db, onboarding)
        onboarding.status = "provisioning"
        portal_token = portal_token_for(onboarding.id, plan.id)
        db.add(PortalInvite(onboarding_id=onboarding.id, token_hash=digest(portal_token), expires_at=now + timedelta(days=14)))
        dispatch = WorkflowDispatch(onboarding_id=onboarding.id, kind="approval", dedupe_key=plan.id, payload={"onboarding_id": onboarding.id, "plan_revision_id": plan.id, "proposal_hash": plan.proposal_hash})
        db.add(dispatch)
        add_event(db, onboarding.id, "approved", "Plan approved for provisioning", {"plan_revision_id": plan.id})
    else:
        onboarding.status = "planning"
        add_event(db, onboarding.id, "plan_rejected", "Plan returned for revision", {"reason": body.reason or ""})
    onboarding.updated_at = now
    db.commit()
    if body.decision == "approve":
        _attempt_dispatch(db, dispatch)
    return {"id": approval.id, "status": "approved" if body.decision == "approve" else "rejected", "onboarding_status": onboarding.status, "dispatch_status": dispatch.status if body.decision == "approve" else None}


@app.get("/api/workflow-dispatches/pending", dependencies=[Depends(internal_service)])
def pending_dispatches(db: Session = Depends(get_db)) -> dict:
    _refresh_stale_dispatches(db)
    # Failed trigger attempts move behind untouched rows, so a small sweep batch
    # cannot indefinitely hide newer onboarding work.
    rows = db.scalars(select(WorkflowDispatch).where(WorkflowDispatch.status == "pending")
                      .order_by(WorkflowDispatch.attempt_count, WorkflowDispatch.created_at).limit(20)).all()
    return {"items": [{"id": row.id, "kind": row.kind, "onboarding_id": row.onboarding_id, "payload": row.payload, "attempt_count": row.attempt_count} for row in rows]}


@app.post("/api/workflow-dispatches/{dispatch_id}/attempt", dependencies=[Depends(internal_service)])
def record_dispatch_attempt(dispatch_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(WorkflowDispatch).where(WorkflowDispatch.id == dispatch_id).with_for_update())
    if not row:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if row.status != "pending":
        return {"execute": False, "id": row.id, "kind": row.kind, "payload": row.payload, "status": row.status,
                "attempt_count": row.attempt_count}
    row.attempt_count += 1
    db.commit()
    return {"execute": True, "id": row.id, "kind": row.kind, "payload": row.payload, "status": row.status,
            "attempt_count": row.attempt_count}


@app.post("/api/workflow-dispatches/{dispatch_id}/ack", dependencies=[Depends(internal_service)])
def acknowledge_dispatch(dispatch_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(WorkflowDispatch, dispatch_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    row.status = "delivered"
    row.delivered_at = utcnow()
    db.commit()
    return {"id": row.id, "status": row.status}


@app.post("/api/onboardings/{onboarding_id}/provisioning/claim", dependencies=[Depends(internal_service)])
def claim_provisioning(onboarding_id: str, body: ProvisionClaim, db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id)
    if onboarding.status not in {"provisioning", "waiting_for_client"} and onboarding.substate != "recovering":
        raise HTTPException(status_code=409, detail="Provisioning is not active")
    if (body.system, body.action) not in {("drive", "create_folder"), ("drive", "create_child_folder"), ("trello", "create_board")}:
        raise HTTPException(status_code=422, detail="Unsupported system/action pair")
    folder = None
    request_payload = body.request_payload
    if body.action == "create_child_folder":
        if not body.folder_id:
            raise HTTPException(status_code=422, detail="folder_id required for child folder")
        folder = db.get(ProjectFolder, body.folder_id)
        if not folder or folder.onboarding_id != onboarding.id:
            raise HTTPException(status_code=404, detail="Project folder not found")
        parent_external_id = _folder_parent_external_id(db, folder)
        if not parent_external_id:
            raise HTTPException(status_code=409, detail="Parent folder is not provisioned")
        request_payload = {"name": folder.name, "parent_id": parent_external_id, "onboarding_id": onboarding.id, "folder_id": folder.id}
    elif body.folder_id:
        raise HTTPException(status_code=422, detail="folder_id is only valid for a child folder")
    key = f"{body.system}:{body.action}" + (f":{folder.id}" if folder else "")
    operation = db.scalar(select(ProvisioningOperation).where(ProvisioningOperation.onboarding_id == onboarding.id, ProvisioningOperation.operation_key == key).with_for_update())
    resource = None if folder else db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == body.system))
    if folder and folder.external_id:
        return {"execute": False, "onboarding_id": onboarding.id, "operation_id": operation.id if operation else None, "idempotency_key": operation.idempotency_key if operation else None, "status": "succeeded", "external_resource": {"external_id": folder.external_id, "url": folder.url, "name": folder.name}, "request_payload": request_payload, "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower()}
    if resource:
        return {"execute": False, "onboarding_id": onboarding.id, "operation_id": operation.id if operation else None, "idempotency_key": operation.idempotency_key if operation else None, "status": "succeeded", "external_resource": {"external_id": resource.external_id, **resource.preview}, "request_payload": request_payload, "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower()}
    now = utcnow()
    if operation is None:
        operation = ProvisioningOperation(onboarding_id=onboarding.id, operation_key=key, system=body.system, action=body.action, status="claimed", idempotency_key=f"clientlaunch:{onboarding.id}:{key}", request_payload=request_payload, lease_until=now + timedelta(minutes=5), updated_at=now)
        db.add(operation)
        db.flush()
        add_event(db, onboarding.id, "provisioning_claimed", f"{body.system} {body.action} claimed", {"operation_id": operation.id})
        db.commit()
        execute = True
    elif operation.status == "retryable":
        operation.status = "claimed"
        operation.attempt_count += 1
        operation.lease_until = now + timedelta(minutes=5)
        operation.updated_at = now
        operation.request_payload = request_payload
        db.commit()
        execute = True
    else:
        # An expired claim may have reached a provider. Never issue another write until reconciliation.
        if operation.status == "claimed" and operation.lease_until and aware(operation.lease_until) <= now:
            operation.status = "unknown"
            operation.error = "Claim expired before outcome was recorded"
            onboarding.substate = "uncertain"
            db.commit()
        execute = False
    return {"execute": execute, "onboarding_id": onboarding.id, "operation_id": operation.id, "idempotency_key": operation.idempotency_key, "status": operation.status, "external_resource": None, "request_payload": operation.request_payload, "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower()}


@app.get("/api/onboardings/{onboarding_id}/provisioning/folders/next", dependencies=[Depends(internal_service)])
def next_project_folder(onboarding_id: str, db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id)
    if not onboarding.current_plan or onboarding.current_plan.status != "approved":
        raise HTTPException(status_code=409, detail="Approved plan required")
    if onboarding.status == "paused":
        raise HTTPException(status_code=409, detail="Onboarding is paused")
    folders = db.scalars(select(ProjectFolder).where(ProjectFolder.onboarding_id == onboarding.id).order_by(ProjectFolder.service_code, ProjectFolder.sort_order)).all()
    if not folders:
        _freeze_folder_plan(db, onboarding)
        db.commit()
        folders = db.scalars(select(ProjectFolder).where(ProjectFolder.onboarding_id == onboarding.id).order_by(ProjectFolder.service_code, ProjectFolder.sort_order)).all()
    remaining = [folder for folder in folders if not folder.external_id]
    if not remaining:
        return {"done": True, "blocked": False, "remaining_count": 0, "folder": None}
    folder = next((item for item in remaining if _folder_parent_external_id(db, item)), None)
    if folder is None:
        return {"done": False, "blocked": True, "reason": "parent_missing", "remaining_count": len(remaining), "folder": None}
    operation = db.scalar(select(ProvisioningOperation).where(
        ProvisioningOperation.onboarding_id == onboarding.id,
        ProvisioningOperation.operation_key == f"drive:create_child_folder:{folder.id}",
    ))
    if operation and operation.status in {"claimed", "unknown", "failed", "compensation_requested"}:
        return {"done": False, "blocked": True, "reason": operation.status, "remaining_count": len(remaining), "folder": None}
    return {"done": False, "blocked": False, "remaining_count": len(remaining), "folder": {
        "id": folder.id, "service_code": folder.service_code, "folder_key": folder.folder_key,
        "name": folder.name, "parent_external_id": _folder_parent_external_id(db, folder),
    }}


@app.post("/api/onboardings/{onboarding_id}/provisioning/{operation_id}/complete", dependencies=[Depends(internal_service)])
def complete_provisioning(onboarding_id: str, operation_id: str, body: ProvisionComplete, db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id)
    operation = db.scalar(select(ProvisioningOperation).where(ProvisioningOperation.id == operation_id, ProvisioningOperation.onboarding_id == onboarding.id).with_for_update())
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    if operation.status == "succeeded":
        if body.outcome == "success" and body.external_id == operation.external_id:
            return {"id": operation.id, "status": "succeeded", "duplicate": True, "external_id": operation.external_id}
        raise HTTPException(status_code=409, detail="Operation already completed with a different outcome")
    if operation.status not in {"claimed", "unknown"}:
        raise HTTPException(status_code=409, detail="Operation is not claimed")
    operation.updated_at = utcnow()
    operation.response_payload = body.model_dump(mode="json")
    operation.error = body.error
    if body.outcome == "success":
        if not body.external_id:
            raise HTTPException(status_code=422, detail="external_id required for success")
        if operation.action == "create_child_folder":
            folder = db.get(ProjectFolder, operation.request_payload.get("folder_id"))
            if not folder or folder.onboarding_id != onboarding.id:
                raise HTTPException(status_code=409, detail="Operation folder is missing")
            if folder.external_id and folder.external_id != body.external_id:
                raise HTTPException(status_code=409, detail="A different child folder is already recorded")
            folder.external_id = body.external_id
            folder.url = body.url
            operation.status = "succeeded"
            operation.external_id = body.external_id
            operation.error = None
            add_event(db, onboarding.id, "project_folder_provisioned", "Service folder recorded", {"folder_id": folder.id, "external_id": body.external_id})
            db.flush()
            _finish_provisioning_if_ready(db, onboarding)
            onboarding.updated_at = utcnow()
            db.commit()
            return {"id": operation.id, "status": operation.status, "duplicate": False, "external_id": operation.external_id}
        kind = "folder" if operation.system == "drive" else "board"
        existing = db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == operation.system, ExternalResource.kind == kind))
        if existing and existing.external_id != body.external_id:
            raise HTTPException(status_code=409, detail="A different external resource is already recorded")
        sim_board = db.get(SimResource, body.external_id) if operation.system == "trello" and os.getenv("CONNECTOR_MODE", "demo").lower() == "demo" else None
        todo_list_id = body.todo_list_id or (sim_board.payload.get("todo_list_id") if sim_board else None)
        if operation.system == "trello" and not todo_list_id:
            raise HTTPException(status_code=422, detail="todo_list_id required for board task cards")
        preview = {"url": body.url, "name": body.name, "todo_list_id": todo_list_id, **body.preview}
        if not existing:
            db.add(ExternalResource(onboarding_id=onboarding.id, system=operation.system, kind=kind, external_id=body.external_id, preview=preview))
        operation.status = "succeeded"
        operation.external_id = body.external_id
        operation.error = None
        add_event(db, onboarding.id, "provisioned", f"{operation.system} {kind} recorded", {"external_id": body.external_id})
        db.flush()
        if operation.system == "trello":
            _ensure_task_cards(db, onboarding.id, body.external_id)
        _finish_provisioning_if_ready(db, onboarding)
    else:
        operation.status = "failed" if body.outcome == "failed" else "unknown"
        onboarding.substate = "failed" if body.outcome == "failed" else "uncertain"
        add_event(db, onboarding.id, "provisioning_exception", f"{operation.system} operation {operation.status}", {"error": body.error or ""})
    onboarding.updated_at = utcnow()
    db.commit()
    return {"id": operation.id, "status": operation.status, "duplicate": False, "external_id": operation.external_id}


@app.post("/api/onboardings/{onboarding_id}/welcome", dependencies=[Depends(internal_service)])
def create_welcome(onboarding_id: str, body: WelcomeRequest, db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id)
    if onboarding.status not in {"provisioning", "waiting_for_client", "ready"} or not onboarding.current_plan or onboarding.current_plan.status != "approved":
        raise HTTPException(status_code=409, detail="Approved plan required")
    recipient = str(body.recipient).lower() if body.recipient else onboarding.client.email.lower()
    subject = body.subject or f"Welcome to your {', '.join(onboarding.deal.services)} project"
    draft = onboarding.current_plan.plan["welcome_draft"].strip()
    supplied_body = body.body.strip() if body.body else draft
    if recipient != onboarding.client.email.lower():
        raise HTTPException(status_code=422, detail="Welcome recipient must be the client on this onboarding")
    if supplied_body != draft:
        raise HTTPException(status_code=422, detail="Welcome text differs from the approved draft")
    existing = db.scalar(select(OutboxEmail).where(OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome", OutboxEmail.dedupe_key == onboarding.current_plan_id))
    connector_mode = os.getenv("CONNECTOR_MODE", "demo").lower()
    sender = os.getenv("SMTP_FROM") if connector_mode == "connected" else "hello@clientlaunch.example.com"
    if not sender:
        raise HTTPException(status_code=503, detail="SMTP_FROM is required in connected mode")
    if existing:
        if existing.subject != subject:
            raise HTTPException(status_code=409, detail="Welcome already prepared with different content")
        email = existing
    else:
        link = detail(db, onboarding)["onboarding"].get("portal_link")
        if not link:
            raise HTTPException(status_code=409, detail="Portal invite missing")
        checklist = db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id, ChecklistItem.client_visible.is_(True))).all()
        requested = "\n".join(f"- {item.title}" for item in checklist if item.status != "completed")
        full_body = draft + f"\n\nYour secure intake portal: {link}\n\nWhat we need from you next:\n{requested}\n\nAccount owner: {onboarding.deal.account_owner.name}\nPlease share your kickoff availability in the portal."
        email = OutboxEmail(onboarding_id=onboarding.id, kind="welcome", dedupe_key=onboarding.current_plan_id, recipient=recipient, subject=subject, body=full_body, status="queued" if connector_mode == "connected" else "simulated_sent")
        db.add(email)
        db.flush()
        add_event(db, onboarding.id, "welcome_prepared", "Approved welcome message recorded in outbox", {"outbox_id": email.id, "status": email.status})
        refresh_readiness(db, onboarding)
        db.commit()
    return {"id": email.id, "status": email.status, "dispatch_required": email.status == "queued", "to": email.recipient, "from": sender, "subject": email.subject, "body": email.body, "message_key": email.dedupe_key}


@app.post("/api/outbox/{outbox_id}/ack", dependencies=[Depends(internal_service)])
def acknowledge_outbox(outbox_id: str, body: OutboxAck, db: Session = Depends(get_db)) -> dict:
    email = db.get(OutboxEmail, outbox_id)
    if not email:
        raise HTTPException(status_code=404, detail="Outbox message not found")
    if email.status == "dispatched":
        if email.provider_message_id != body.provider_message_id:
            raise HTTPException(status_code=409, detail="Different message ID already recorded")
        return {"id": email.id, "status": email.status, "duplicate": True}
    if email.status != "queued":
        raise HTTPException(status_code=409, detail="Message does not need an acknowledgment")
    email.status = "dispatched"
    email.provider_message_id = body.provider_message_id
    add_event(db, email.onboarding_id, "message_dispatched", "Provider message ID recorded", {"outbox_id": email.id})
    db.commit()
    return {"id": email.id, "status": email.status, "duplicate": False}


@app.post("/api/client/exchange")
def exchange_portal_token(body: PortalExchange, db: Session = Depends(get_db)) -> dict:
    invite = db.scalar(select(PortalInvite).where(PortalInvite.token_hash == digest(body.portal_token)))
    if not invite or invite.revoked_at or aware(invite.expires_at) <= utcnow():
        raise HTTPException(status_code=401, detail="Portal link expired or invalid")
    onboarding = require_onboarding(db, invite.onboarding_id)
    if onboarding.status in {"paused", "handed_off"}:
        raise HTTPException(status_code=403, detail="Portal is unavailable")
    token = generate_token()
    session = ClientSession(onboarding_id=onboarding.id, token_hash=digest(token), expires_at=fresh_session_expiry(client=True))
    db.add(session)
    db.commit()
    return {"token": token, "token_type": "bearer", "expires_at": iso(session.expires_at)}


@app.get("/api/client/onboarding")
def client_onboarding_detail(onboarding: Onboarding = Depends(client_onboarding), db: Session = Depends(get_db)) -> dict:
    return client_detail(db, onboarding)


@app.post("/api/client/submissions")
def submit_intake(body: IntakeRequest, onboarding: Onboarding = Depends(client_onboarding), db: Session = Depends(get_db)) -> dict:
    if onboarding.status not in {"waiting_for_client", "ready"} or onboarding.substate:
        raise HTTPException(status_code=409, detail="Intake is not open")
    ids = [answer.checklist_item_id for answer in body.answers]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Duplicate answer for one checklist item")
    items = {item.id: item for item in db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id, ChecklistItem.client_visible.is_(True), ChecklistItem.id.in_(ids))).all()}
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="Checklist item not available to this client")
    previous = db.scalars(select(IntakeSubmission).where(IntakeSubmission.onboarding_id == onboarding.id).order_by(IntakeSubmission.created_at.desc())).all()
    prior_values = {answer["checklist_item_id"]: answer["value"] for record in reversed(previous) for answer in record.answers}
    changed = []
    for answer in body.answers:
        item = items[answer.checklist_item_id]
        new_value = answer.value.strip()
        if answer.checklist_item_id in prior_values and prior_values[answer.checklist_item_id] != new_value:
            item.status = "needs_review"
            changed.append(item.id)
        else:
            item.status = "completed"
            item.completed_at = utcnow()
    submission = IntakeSubmission(onboarding_id=onboarding.id, answers=[answer.model_dump(mode="json") for answer in body.answers])
    db.add(submission)
    db.flush()
    for item in items.values():
        _mark_card_desired(db, item, submission.id)
    if changed:
        add_event(db, onboarding.id, "scope_change_review", "Changed client answers require operator review", {"checklist_item_ids": changed})
    else:
        add_event(db, onboarding.id, "intake_submitted", "Client answers received", {"submission_id": submission.id})
    refresh_readiness(db, onboarding)
    dispatch = WorkflowDispatch(onboarding_id=onboarding.id, kind="submission", dedupe_key=submission.id, payload={"onboarding_id": onboarding.id, "submission_id": submission.id, "changed_item_ids": changed})
    db.add(dispatch)
    db.commit()
    _attempt_dispatch(db, dispatch)
    return {"id": submission.id, "status": "review_required" if changed else "accepted", "onboarding_status": onboarding.status, "dispatch_status": dispatch.status}


def _task_sync_item(db: Session, card: TaskCard, board: ExternalResource) -> dict:
    item = db.get(ChecklistItem, card.checklist_item_id)
    return {
        "operation_id": card.id,
        "action": "create" if card.external_card_id is None else "update",
        "external_board_id": board.external_id,
        "todo_list_id": board.preview.get("todo_list_id"),
        "title": item.title,
        "description": item.description,
        "due_date": iso(item.due_at),
        "status": card.desired_status,
        "idempotency_key": card.idempotency_key,
        "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower(),
        "checklist_item_id": item.id,
        "external_card_id": card.external_card_id,
    }


def _record_card_outcome(db: Session, card: TaskCard, external_id: str, status: str) -> None:
    board = db.scalar(select(ExternalResource).where(
        ExternalResource.onboarding_id == card.onboarding_id,
        ExternalResource.system == "trello", ExternalResource.kind == "board",
    ))
    if not board or board.external_id != card.board_external_id:
        raise HTTPException(status_code=409, detail="Task board changed")
    other = db.scalar(select(TaskCard.id).where(
        TaskCard.external_card_id == external_id, TaskCard.id != card.id,
    ).limit(1))
    if other:
        raise HTTPException(status_code=409, detail="External card is already linked to another task")
    card.external_card_id = external_id
    card.synced_status = status
    card.lease_until = None
    card.error = None
    if status == card.desired_status:
        card.sync_state = "synced"
    else:
        # The client may have changed an answer while the old write was
        # uncertain. Preserve the observed outcome, then send a new update.
        card.sync_state = "pending"
        card.idempotency_key = f"clientlaunch:{card.onboarding_id}:trello:card:{card.checklist_item_id}:{card.desired_status}:reconcile:{uuid4()}"
    item = db.get(ChecklistItem, card.checklist_item_id)
    preview = dict(board.preview)
    tasks = [task for task in preview.get("tasks", []) if task["checklist_item_id"] != item.id]
    tasks.append({"checklist_item_id": item.id, "external_card_id": external_id, "title": item.title, "status": status})
    preview["tasks"] = tasks
    board.preview = preview
    add_event(db, card.onboarding_id, "task_synced", f"Board card outcome recorded: {item.title}",
              {"external_card_id": external_id, "status": status, "sync_state": card.sync_state})
    refresh_readiness(db, require_onboarding(db, card.onboarding_id))


def _reconcile_demo_cards(db: Session, onboarding: Onboarding) -> list[dict]:
    if os.getenv("CONNECTOR_MODE", "demo").lower() != "demo":
        return []
    now = utcnow()
    cards = db.scalars(select(TaskCard).where(
        TaskCard.onboarding_id == onboarding.id, TaskCard.sync_state.in_(["claimed", "unknown"]),
    ).with_for_update()).all()
    results = []
    for card in cards:
        if card.sync_state == "claimed" and (not card.lease_until or aware(card.lease_until) > now):
            continue
        sim = (db.get(SimResource, card.external_card_id) if card.external_card_id else db.scalar(select(SimResource).where(
            SimResource.system == "trello", SimResource.kind == "card", SimResource.idempotency_key == card.idempotency_key,
        )))
        if sim and sim.system == "trello" and sim.kind == "card" and sim.payload.get("board_id") == card.board_external_id and sim.payload.get("checklist_item_id") == card.checklist_item_id:
            observed = sim.payload.get("status")
            if observed in {"open", "completed", "needs_review"}:
                if card.external_card_id and observed == card.synced_status and observed != card.desired_status:
                    card.sync_state = "retryable"
                    card.lease_until = None
                    card.error = None
                    results.append({"operation_id": card.id, "result": "update_confirmed_absent"})
                else:
                    _record_card_outcome(db, card, sim.id, observed)
                    results.append({"operation_id": card.id, "result": "existing_card_found"})
                continue
        if card.external_card_id is None and sim is None:
            card.sync_state = "retryable"
            card.lease_until = None
            card.error = None
            results.append({"operation_id": card.id, "result": "simulator_confirmed_absent"})
        else:
            card.sync_state = "unknown"
            card.error = "Card provider outcome could not be verified"
            results.append({"operation_id": card.id, "result": "unverified"})
    if results:
        refresh_readiness(db, onboarding)
    return results


@app.post("/api/client-submissions/{submission_id}/process", dependencies=[Depends(internal_service)])
def process_submission(submission_id: str, db: Session = Depends(get_db)) -> dict:
    submission = db.get(IntakeSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    onboarding = require_onboarding(db, submission.onboarding_id)
    board = db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == "trello", ExternalResource.kind == "board"))
    if not board:
        raise HTTPException(status_code=409, detail="Task board has not been provisioned")
    processed = db.scalar(select(WorkflowDispatch).where(WorkflowDispatch.kind == "submission_process", WorkflowDispatch.dedupe_key == submission.id))
    duplicate = processed is not None
    if not processed:
        for answer in submission.answers:
            item = db.get(ChecklistItem, answer["checklist_item_id"])
            _mark_card_desired(db, item, submission.id)
        processed = WorkflowDispatch(onboarding_id=onboarding.id, kind="submission_process", dedupe_key=submission.id, payload={"submission_id": submission.id}, status="delivered", delivered_at=utcnow())
        db.add(processed)
        add_event(db, onboarding.id, "submission_processed", "Client answers mapped to board card updates", {"submission_id": submission.id})
        db.commit()
    return {"submission_id": submission.id, "onboarding_id": onboarding.id, "processed": True, "duplicate": duplicate, "pending_operations": task_sync_pending(onboarding.id, db)}


@app.get("/api/onboardings/{onboarding_id}/task-sync/pending", dependencies=[Depends(internal_service)])
def task_sync_pending(onboarding_id: str, db: Session = Depends(get_db)) -> list[dict]:
    onboarding = require_onboarding(db, onboarding_id)
    board = db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == "trello", ExternalResource.kind == "board"))
    if not board:
        return []
    cards = db.scalars(select(TaskCard).where(TaskCard.onboarding_id == onboarding.id, TaskCard.sync_state.in_(["pending", "retryable"]))).all()
    return [_task_sync_item(db, card, board) for card in cards]


@app.post("/api/onboardings/{onboarding_id}/task-sync/{operation_id}/claim", dependencies=[Depends(internal_service)])
def task_sync_claim(onboarding_id: str, operation_id: str, body: TaskCardClaim, db: Session = Depends(get_db)) -> dict:
    require_onboarding(db, onboarding_id)
    card = db.scalar(select(TaskCard).where(TaskCard.id == operation_id, TaskCard.onboarding_id == onboarding_id).with_for_update())
    if not card:
        raise HTTPException(status_code=404, detail="Task operation not found")
    if card.sync_state in {"pending", "retryable"} and (body.expected_status != card.desired_status or body.expected_idempotency_key != card.idempotency_key):
        return {"execute": False, "operation_id": card.id, "idempotency_key": card.idempotency_key, "status": "stale"}
    if card.sync_state in {"pending", "retryable"}:
        card.sync_state = "claimed"
        card.lease_until = utcnow() + timedelta(minutes=5)
        card.attempt_count += 1
        db.commit()
        execute = True
    else:
        if card.sync_state == "claimed" and card.lease_until and aware(card.lease_until) <= utcnow():
            card.sync_state = "unknown"
            card.error = "Card sync claim expired; reconcile provider outcome"
            db.commit()
        execute = False
    return {"execute": execute, "operation_id": card.id, "idempotency_key": card.idempotency_key, "status": card.sync_state}


@app.post("/api/onboardings/{onboarding_id}/task-sync/reconcile")
def reconcile_task_cards(onboarding_id: str, body: TaskCardReconcile, request: Request, db: Session = Depends(get_db)) -> dict:
    internal_key = request.headers.get("x-internal-key")
    is_internal = bool(internal_key and hmac.compare_digest(internal_key, INTERNAL_KEY))
    if is_internal and not body.operation_id:
        onboarding = require_onboarding(db, onboarding_id)
        results = _reconcile_demo_cards(db, onboarding)
        db.commit()
        return {"onboarding_id": onboarding.id, "results": results,
                "pending_operations": task_sync_pending(onboarding.id, db)}
    actor = operator_writer(operator_actor(request, db))
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    if not body.operation_id or (not body.external_id and not body.confirmed_absent):
        raise HTTPException(status_code=422, detail="Operation and confirmed card outcome are required")
    if body.external_id and body.confirmed_absent:
        raise HTTPException(status_code=422, detail="Choose an external card or confirmed absence")
    card = db.scalar(select(TaskCard).where(
        TaskCard.id == body.operation_id, TaskCard.onboarding_id == onboarding.id,
    ).with_for_update())
    if not card:
        raise HTTPException(status_code=404, detail="Task operation not found")
    if card.sync_state not in {"claimed", "unknown"} or (card.sync_state == "claimed" and card.lease_until and aware(card.lease_until) > utcnow()):
        raise HTTPException(status_code=409, detail="Card claim is active or does not need reconciliation")
    if body.external_id:
        if card.external_card_id and card.external_card_id != body.external_id:
            raise HTTPException(status_code=409, detail="Card external ID changed")
        observed = body.status
        if os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
            sim = db.get(SimResource, body.external_id)
            if not sim or sim.system != "trello" or sim.kind != "card" or sim.payload.get("board_id") != card.board_external_id or sim.payload.get("checklist_item_id") != card.checklist_item_id or (not card.external_card_id and sim.idempotency_key != card.idempotency_key):
                raise HTTPException(status_code=409, detail="Simulator card does not match this operation")
            if observed and observed != sim.payload.get("status"):
                raise HTTPException(status_code=409, detail="Card status differs from simulator")
            observed = sim.payload.get("status")
        if observed not in {"open", "completed", "needs_review"}:
            raise HTTPException(status_code=422, detail="Observed external card status is required")
        _record_card_outcome(db, card, body.external_id, observed)
        result = "existing_card_recorded"
    else:
        if os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
            sim = (db.get(SimResource, card.external_card_id) if card.external_card_id else db.scalar(select(SimResource).where(
                SimResource.system == "trello", SimResource.kind == "card", SimResource.idempotency_key == card.idempotency_key,
            )))
            if sim:
                raise HTTPException(status_code=409, detail="Simulator already has this card; reconcile its external ID")
        card.sync_state = "retryable"
        card.lease_until = None
        card.error = None
        add_event(db, onboarding.id, "task_reconciled_absent", "Card provider absence confirmed; retry enabled", {"operation_id": card.id})
        refresh_readiness(db, onboarding)
        result = "confirmed_absent"
    db.commit()
    return {"onboarding_id": onboarding.id, "operation_id": card.id,
            "sync_state": card.sync_state, "result": result,
            "pending_operations": task_sync_pending(onboarding.id, db)}


@app.post("/api/onboardings/{onboarding_id}/task-sync/{operation_id}/complete", dependencies=[Depends(internal_service)])
def task_sync_complete(onboarding_id: str, operation_id: str, body: TaskCardAck, db: Session = Depends(get_db)) -> dict:
    require_onboarding(db, onboarding_id)
    card = db.scalar(select(TaskCard).where(TaskCard.id == operation_id, TaskCard.onboarding_id == onboarding_id).with_for_update())
    if not card:
        raise HTTPException(status_code=404, detail="Task operation not found")
    if card.sync_state == "synced":
        if card.external_card_id == body.external_id and card.synced_status == body.status:
            return {"operation_id": card.id, "status": "synced", "duplicate": True}
        raise HTTPException(status_code=409, detail="Card already synced with a different outcome")
    if card.sync_state not in {"claimed", "unknown"}:
        raise HTTPException(status_code=409, detail="Card operation must be claimed")
    if card.external_card_id and card.external_card_id != body.external_id:
        raise HTTPException(status_code=409, detail="Card external ID changed")
    if os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
        sim_card = db.get(SimResource, body.external_id)
        if (not sim_card or sim_card.system != "trello" or sim_card.kind != "card"
                or sim_card.payload.get("board_id") != card.board_external_id
                or sim_card.payload.get("checklist_item_id") != card.checklist_item_id
                or (not card.external_card_id and sim_card.idempotency_key != card.idempotency_key)
                or sim_card.payload.get("status") != body.status):
            raise HTTPException(status_code=409, detail="Simulator card outcome not verified")
    _record_card_outcome(db, card, body.external_id, body.status)
    db.commit()
    return {"operation_id": card.id, "status": card.sync_state, "duplicate": False, "external_id": body.external_id}


_ALLOWED_FILE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "application/pdf": (b"%PDF-", ".pdf"),
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/client/assets")
async def upload_asset(file: UploadFile = File(...), checklist_item_id: str = Form(...), onboarding: Onboarding = Depends(client_onboarding), db: Session = Depends(get_db)) -> dict:
    if onboarding.status not in {"waiting_for_client", "ready"} or onboarding.substate:
        raise HTTPException(status_code=409, detail="Asset intake is not open")
    item = db.scalar(select(ChecklistItem).where(ChecklistItem.id == checklist_item_id, ChecklistItem.onboarding_id == onboarding.id, ChecklistItem.client_visible.is_(True)))
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not available to this client")
    if file.content_type not in _ALLOWED_FILE_SIGNATURES:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, and PDF assets are accepted")
    header, extension = _ALLOWED_FILE_SIGNATURES[file.content_type]
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Asset exceeds 5 MB limit")
    if not content.startswith(header):
        raise HTTPException(status_code=415, detail="File content does not match its declared type")
    asset_id = str(uuid4())
    relative_path = Path(onboarding.workspace_id) / onboarding.id / f"{asset_id}{extension}"
    base_path = Path(os.getenv("ASSET_STORAGE_DIR", "data/assets")).resolve()
    target_path = (base_path / relative_path).resolve()
    if not target_path.is_relative_to(base_path):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    asset = Asset(id=asset_id, workspace_id=onboarding.workspace_id, onboarding_id=onboarding.id, checklist_item_id=item.id, original_name=Path(file.filename or "asset").name[:240], content_type=file.content_type, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), storage_path=str(relative_path))
    db.add(asset)
    item.status = "completed"
    item.completed_at = utcnow()
    submission = IntakeSubmission(onboarding_id=onboarding.id, answers=[{"checklist_item_id": item.id, "value": f"Asset uploaded: {asset.id}"}])
    db.add(submission)
    db.flush()
    _mark_card_desired(db, item, submission.id)
    add_event(db, onboarding.id, "asset_uploaded", "Client asset received", {"asset_id": asset.id, "checklist_item_id": item.id})
    refresh_readiness(db, onboarding)
    dispatch = WorkflowDispatch(onboarding_id=onboarding.id, kind="submission", dedupe_key=submission.id, payload={"onboarding_id": onboarding.id, "submission_id": submission.id, "asset_id": asset.id})
    db.add(dispatch)
    db.commit()
    _attempt_dispatch(db, dispatch)
    return {"id": asset.id, "filename": asset.original_name, "status": "accepted", "onboarding_status": onboarding.status}


@app.get("/api/assets/{asset_id}")
def download_asset(asset_id: str, request: Request, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    key = request.headers.get("x-internal-key")
    if not (key and hmac.compare_digest(key, INTERNAL_KEY)):
        try:
            actor = operator_actor(request, db)
            if actor.user.workspace_id != asset.workspace_id:
                raise HTTPException(status_code=404, detail="Asset not found")
        except HTTPException as operator_exc:
            try:
                onboarding = client_onboarding(request, db)
            except HTTPException:
                raise operator_exc
            if onboarding.id != asset.onboarding_id:
                raise HTTPException(status_code=404, detail="Asset not found")
    base_path = Path(os.getenv("ASSET_STORAGE_DIR", "data/assets")).resolve()
    path = (base_path / asset.storage_path).resolve()
    if not path.is_relative_to(base_path) or not path.is_file():
        raise HTTPException(status_code=404, detail="Asset file unavailable")
    return FileResponse(path, media_type=asset.content_type, filename=asset.original_name)


@app.patch("/api/onboardings/{onboarding_id}/checklist/{item_id}")
def edit_checklist(onboarding_id: str, item_id: str, body: ChecklistEdit, actor: OperatorActor = Depends(operator_writer), db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    item = db.scalar(select(ChecklistItem).where(ChecklistItem.id == item_id, ChecklistItem.onboarding_id == onboarding.id))
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    item.due_at = body.due_at
    item.owner_name = body.owner_name
    add_event(db, onboarding.id, "checklist_scheduled", "Owner or due date updated", {"checklist_item_id": item.id})
    db.commit()
    return {"id": item.id, "due_at": iso(item.due_at), "owner_name": item.owner_name}


@app.post("/api/onboardings/{onboarding_id}/handoff")
def handoff(onboarding_id: str, body: HandoffRequest, actor: OperatorActor = Depends(operator_writer), db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    refresh_readiness(db, onboarding)
    if onboarding.status != "ready":
        raise HTTPException(status_code=409, detail="Required checklist or provisioning is incomplete")
    evidence = {
        "submission_ids": db.scalars(select(IntakeSubmission.id).where(IntakeSubmission.onboarding_id == onboarding.id)).all(),
        "asset_ids": db.scalars(select(Asset.id).where(Asset.onboarding_id == onboarding.id)).all(),
        "resource_ids": db.scalars(select(ExternalResource.id).where(ExternalResource.onboarding_id == onboarding.id)).all(),
    }
    summary = HandoffSummary(onboarding_id=onboarding.id, summary=body.summary, evidence=evidence)
    db.add(summary)
    onboarding.status = "handed_off"
    onboarding.updated_at = utcnow()
    add_event(db, onboarding.id, "handed_off", "Delivery handoff recorded", {"evidence": evidence})
    db.commit()
    return {"id": summary.id, "status": "handed_off", "evidence": evidence}


@app.post("/api/onboardings/{onboarding_id}/state")
def change_lifecycle(onboarding_id: str, body: LifecycleAction, actor: OperatorActor = Depends(operator_writer), db: Session = Depends(get_db)) -> dict:
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    if onboarding.status == "handed_off":
        raise HTTPException(status_code=409, detail="Handed off onboarding cannot be paused or resumed")
    if body.action == "pause":
        onboarding.status = "paused"
        onboarding.substate = None
    elif onboarding.status == "paused":
        if onboarding.current_plan and onboarding.current_plan.status == "approved":
            onboarding.status = "waiting_for_client" if _provisioning_complete(db, onboarding) else "provisioning"
            if onboarding.status == "waiting_for_client":
                refresh_readiness(db, onboarding)
        else:
            onboarding.status = "planning"
    else:
        raise HTTPException(status_code=409, detail="Onboarding is not paused")
    onboarding.updated_at = utcnow()
    add_event(db, onboarding.id, body.action, body.reason or f"Onboarding {body.action}d")
    db.commit()
    return {"id": onboarding.id, "status": onboarding.status}


@app.post("/api/reminders/evaluate", dependencies=[Depends(internal_service)])
def evaluate_due_reminders(body: ReminderEvaluate, db: Session = Depends(get_db)) -> dict:
    drafted = evaluate_reminders(db, body.reference_time or utcnow(), body.onboarding_id)
    db.commit()
    return {"drafted_count": len(drafted), "items": [{"id": item.id, "onboarding_id": item.onboarding_id, "checklist_item_id": item.checklist_item_id, "status": item.status} for item in drafted]}


@app.post("/api/onboardings/{onboarding_id}/reminder-decisions", dependencies=[Depends(internal_service)])
def evaluate_onboarding_reminders(onboarding_id: str, body: ReminderEvaluate, db: Session = Depends(get_db)) -> dict:
    require_onboarding(db, onboarding_id)
    drafted = evaluate_reminders(db, body.reference_time or utcnow(), onboarding_id)
    db.commit()
    return {"drafted_count": len(drafted), "items": [{"id": item.id, "checklist_item_id": item.checklist_item_id, "status": item.status} for item in drafted]}


@app.post("/api/reminders/{reminder_id}/approval")
def decide_reminder(reminder_id: str, body: ReminderApproval, actor: OperatorActor = Depends(operator_writer), db: Session = Depends(get_db)) -> dict:
    reminder = db.get(ReminderTask, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    onboarding = require_onboarding(db, reminder.onboarding_id, actor.user.workspace_id)
    if reminder.status != "drafted" or onboarding.status in {"paused", "handed_off", "ready"}:
        raise HTTPException(status_code=409, detail="Reminder is no longer actionable")
    reminder.status = "approved" if body.decision == "approve" else "rejected"
    reminder.approved_at = utcnow() if body.decision == "approve" else None
    add_event(db, onboarding.id, "reminder_reviewed", f"Reminder {reminder.status}", {"reminder_id": reminder.id})
    db.commit()
    return {"id": reminder.id, "status": reminder.status}


def _reminder_message(db: Session, reminder: ReminderTask) -> dict:
    onboarding = require_onboarding(db, reminder.onboarding_id)
    item = db.get(ChecklistItem, reminder.checklist_item_id)
    connector_mode = os.getenv("CONNECTOR_MODE", "demo").lower()
    sender = os.getenv("SMTP_FROM") if connector_mode == "connected" else "hello@clientlaunch.example.com"
    if not sender:
        raise HTTPException(status_code=503, detail="SMTP_FROM is required in connected mode")
    link = detail(db, onboarding)["onboarding"].get("portal_link", "")
    return {"id": reminder.id, "connector_mode": connector_mode, "to": onboarding.client.email, "from": sender, "subject": f"ClientLaunch intake reminder: {item.title}", "body": f"Hello {onboarding.client.name},\n\nWe are still waiting for: {item.title}.\n\nPlease use your secure portal: {link}\n\nThank you,\n{onboarding.deal.account_owner.name}", "message_key": f"reminder:{reminder.id}"}


@app.get("/api/reminders/approved-pending", dependencies=[Depends(internal_service)])
def approved_pending_reminders(db: Session = Depends(get_db)) -> list[dict]:
    reminders = db.scalars(select(ReminderTask).where(ReminderTask.status == "approved").order_by(ReminderTask.created_at).limit(100)).all()
    result = []
    for reminder in reminders:
        onboarding = require_onboarding(db, reminder.onboarding_id)
        item = db.get(ChecklistItem, reminder.checklist_item_id)
        if onboarding.status == "waiting_for_client" and onboarding.substate is None and item.status != "completed":
            result.append(_reminder_message(db, reminder))
    return result


@app.post("/api/reminders/{reminder_id}/dispatch", dependencies=[Depends(internal_service)])
def dispatch_reminder(reminder_id: str, body: ReminderDispatch | None = None, db: Session = Depends(get_db)) -> dict:
    reminder = db.get(ReminderTask, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.status == "dispatched":
        return {"id": reminder.id, "status": "dispatched", "duplicate": True}
    onboarding = require_onboarding(db, reminder.onboarding_id)
    item = db.get(ChecklistItem, reminder.checklist_item_id)
    if reminder.status != "approved" or onboarding.status != "waiting_for_client" or onboarding.substate or item.status == "completed":
        raise HTTPException(status_code=409, detail="Reminder is no longer dispatchable")
    message = _reminder_message(db, reminder)
    connector_mode = message["connector_mode"]
    if connector_mode == "connected" and (body is None or not body.provider_message_id):
        raise HTTPException(status_code=422, detail="Provider message ID required after SMTP delivery")
    outbox = OutboxEmail(onboarding_id=onboarding.id, kind="reminder", dedupe_key=message["message_key"], recipient=message["to"], subject=message["subject"], body=message["body"], status="dispatched" if connector_mode == "connected" else "simulated_sent", provider_message_id=body.provider_message_id if body else None)
    db.add(outbox)
    reminder.status = "dispatched"
    reminder.dispatched_at = utcnow()
    add_event(db, onboarding.id, "reminder_dispatched", "Reminder delivery recorded", {"reminder_id": reminder.id, "mode": connector_mode})
    db.commit()
    return {"id": reminder.id, "status": "dispatched", "duplicate": False, "outbox_id": outbox.id}


@app.post("/api/onboardings/{onboarding_id}/recover")
def recover_operation(onboarding_id: str, body: RecoverRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    internal_key = request.headers.get("x-internal-key")
    is_internal = bool(internal_key and hmac.compare_digest(internal_key, INTERNAL_KEY))
    if is_internal and not body.operation_id and not body.decision:
        onboarding = require_onboarding(db, onboarding_id)
        operations = db.scalars(select(ProvisioningOperation).where(ProvisioningOperation.onboarding_id == onboarding.id).with_for_update()).all()
        reconciled = []
        for operation in operations:
            if operation.status == "failed":
                operation.status = "retryable"
                reconciled.append({"operation_id": operation.id, "result": "retryable_known_failure"})
            elif operation.status in {"unknown", "claimed"} and os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
                sim = db.scalar(select(SimResource).where(SimResource.system == operation.system, SimResource.idempotency_key == operation.idempotency_key))
                if sim:
                    _record_reconciled_resource(db, onboarding, operation, sim.id, {
                        "url": sim.payload["url"], "name": sim.payload["name"],
                        "todo_list_id": sim.payload.get("todo_list_id"),
                    })
                    reconciled.append({"operation_id": operation.id, "result": "existing_resource_found"})
                elif operation.status == "unknown" or (operation.lease_until and aware(operation.lease_until) <= utcnow()):
                    operation.status = "retryable"
                    reconciled.append({"operation_id": operation.id, "result": "simulator_confirmed_absent"})
                else:
                    reconciled.append({"operation_id": operation.id, "result": "claim_still_in_flight"})
        db.flush()
        can_retry = any(op.status == "retryable" for op in operations)
        blocked = any(op.status in {"claimed", "unknown", "failed", "compensation_requested"} for op in operations)
        welcome_recorded = db.scalar(select(OutboxEmail.id).where(
            OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome",
        ).limit(1)) is not None
        cards_pending = db.scalar(select(TaskCard.id).where(
            TaskCard.onboarding_id == onboarding.id, TaskCard.sync_state.in_(["pending", "retryable"]),
        ).limit(1)) is not None
        resume_needed = (
            onboarding.status in {"provisioning", "waiting_for_client"}
            and onboarding.current_plan is not None
            and onboarding.current_plan.status == "approved"
            and not blocked
            and (can_retry or not _provisioning_complete(db, onboarding) or cards_pending or not welcome_recorded)
        )
        if _provisioning_complete(db, onboarding) and onboarding.status == "provisioning":
            onboarding.status = "waiting_for_client"
            onboarding.substate = None
        elif resume_needed and onboarding.status == "provisioning":
            onboarding.substate = "recovering"
        add_event(db, onboarding.id, "recovery_evaluated", "Operation ledger evaluated for safe resume", {"results": reconciled})
        db.commit()
        return {"onboarding_id": onboarding.id, "can_retry": can_retry, "resume_needed": resume_needed,
                "status": onboarding.status, "substate": onboarding.substate, "results": reconciled}
    if not body.operation_id or not body.decision:
        raise HTTPException(status_code=422, detail="operation_id and decision are required for operator recovery")
    actor = operator_writer(operator_actor(request, db))
    onboarding = require_onboarding(db, onboarding_id, actor.user.workspace_id)
    operation = db.scalar(select(ProvisioningOperation).where(ProvisioningOperation.id == body.operation_id, ProvisioningOperation.onboarding_id == onboarding.id).with_for_update())
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    if operation.status == "succeeded":
        raise HTTPException(status_code=409, detail="Successful external work cannot be retried or compensated automatically")
    if body.decision == "retry":
        if operation.status != "failed":
            raise HTTPException(status_code=409, detail="Uncertain outcomes require reconciliation before retry")
        operation.status = "retryable"
        onboarding.substate = "recovering"
    elif body.decision == "reconcile":
        if operation.status not in {"unknown", "failed", "claimed"}:
            raise HTTPException(status_code=409, detail="Operation does not need reconciliation")
        external_id = body.external_id
        sim_resource = None
        if os.getenv("CONNECTOR_MODE", "demo").lower() == "demo":
            sim_resource = (db.get(SimResource, external_id) if external_id else db.scalar(select(SimResource).where(
                SimResource.system == operation.system, SimResource.idempotency_key == operation.idempotency_key,
            )))
            if sim_resource and (sim_resource.system != operation.system or sim_resource.idempotency_key != operation.idempotency_key):
                raise HTTPException(status_code=409, detail="Simulator resource does not match this operation")
            if external_id and not sim_resource:
                raise HTTPException(status_code=409, detail="Simulator resource not found for this operation")
            external_id = sim_resource.id if sim_resource else None
        if external_id:
            preview = sim_resource.payload if sim_resource else {"url": body.url, "name": body.name, "todo_list_id": body.todo_list_id}
            _record_reconciled_resource(db, onboarding, operation, external_id, preview)
            add_event(db, onboarding.id, "reconciled", "External resource outcome confirmed", {"operation_id": operation.id, "external_id": external_id})
            _finish_provisioning_if_ready(db, onboarding)
        elif body.confirmed_absent:
            operation.status = "retryable"
            onboarding.substate = "recovering"
            add_event(db, onboarding.id, "reconciled_absent", "Provider confirmed resource absent; retry enabled", {"operation_id": operation.id})
        else:
            raise HTTPException(status_code=409, detail="Outcome remains uncertain; provide a confirmed external ID or explicit absence")
    else:
        operation.status = "compensation_requested"
        onboarding.substate = "recovering"
        add_event(db, onboarding.id, "compensation_requested", "Operator requested manual compensation review; no external deletion performed", {"operation_id": operation.id})
    operation.updated_at = utcnow()
    onboarding.updated_at = utcnow()
    dispatch = None
    if operation.status in {"retryable", "succeeded"} and onboarding.status in {"provisioning", "waiting_for_client"}:
        dispatch = WorkflowDispatch(onboarding_id=onboarding.id, kind="recovery", dedupe_key=f"{operation.id}:{operation.status}:{operation.attempt_count}", payload={"onboarding_id": onboarding.id})
        db.add(dispatch)
    db.commit()
    if dispatch:
        _attempt_dispatch(db, dispatch)
    return {"id": operation.id, "status": operation.status, "onboarding_status": onboarding.status, "substate": onboarding.substate, "can_retry": operation.status == "retryable", "dispatch_status": dispatch.status if dispatch else None}


@app.post("/sim/drive/folders", dependencies=[Depends(internal_service)])
def sim_drive_folder(body: SimCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    return _simulate_resource("drive", "folder", body, idempotency_key, db)


@app.post("/sim/faults/next", dependencies=[Depends(internal_service)])
def arm_simulator_fault(body: SimFaultRequest, db: Session = Depends(get_db)) -> dict:
    _require_demo_simulator()
    require_onboarding(db, body.onboarding_id)
    dedupe_key = f"{body.onboarding_id}:{body.system}"
    row = db.scalar(select(WorkflowDispatch).where(WorkflowDispatch.kind == "sim_fault", WorkflowDispatch.dedupe_key == dedupe_key).with_for_update())
    if row and row.status == "armed":
        if row.payload.get("kind") != body.kind:
            raise HTTPException(status_code=409, detail="A different fault is already armed")
        return {"id": row.id, "onboarding_id": body.onboarding_id, "system": body.system, "kind": body.kind, "status": "armed", "duplicate": True}
    if row:
        row.status = "armed"
        row.payload = body.model_dump(mode="json")
    else:
        row = WorkflowDispatch(onboarding_id=body.onboarding_id, kind="sim_fault", dedupe_key=dedupe_key, payload=body.model_dump(mode="json"), status="armed")
        db.add(row)
    db.commit()
    return {"id": row.id, "onboarding_id": body.onboarding_id, "system": body.system, "kind": body.kind, "status": "armed", "duplicate": False}


@app.post("/sim/trello/boards", dependencies=[Depends(internal_service)])
def sim_trello_board(body: SimCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    return _simulate_resource("trello", "board", body, idempotency_key, db)


def _simulate_resource(system: str, kind: str, body: SimCreate, idempotency_key: str | None, db: Session) -> dict:
    _require_demo_simulator()
    idempotency_key = idempotency_key or body.idempotency_key
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="Idempotency key required")
    parts = idempotency_key.split(":")
    inferred_onboarding_id = parts[1] if len(parts) in {4, 5} and parts[0] == "clientlaunch" else None
    onboarding_id = body.onboarding_id or inferred_onboarding_id
    if not onboarding_id or inferred_onboarding_id != onboarding_id:
        raise HTTPException(status_code=422, detail="Simulator requires a scoped server-issued idempotency key")
    onboarding = require_onboarding(db, onboarding_id)
    existing = db.scalar(select(SimResource).where(SimResource.system == system, SimResource.idempotency_key == idempotency_key))
    if existing:
        return {"external_id": existing.id, "url": existing.payload["url"], "name": existing.payload["name"], "todo_list_id": existing.payload.get("todo_list_id"), "duplicate": True}
    operation = db.scalar(select(ProvisioningOperation).where(ProvisioningOperation.onboarding_id == onboarding_id, ProvisioningOperation.idempotency_key == idempotency_key).with_for_update())
    if not operation or operation.status != "claimed":
        raise HTTPException(status_code=409, detail="Simulator write requires a claimed operation")
    if operation.action == "create_child_folder" and (body.name != operation.request_payload.get("name") or body.parent_id != operation.request_payload.get("parent_id")):
        raise HTTPException(status_code=422, detail="Child folder must use the claimed name and parent")
    fault = db.scalar(select(WorkflowDispatch).where(WorkflowDispatch.kind == "sim_fault", WorkflowDispatch.dedupe_key == f"{onboarding_id}:{system}", WorkflowDispatch.status == "armed").with_for_update())
    fault_kind = None
    if fault:
        fault_kind = fault.payload.get("kind")
        fault.status = "consumed"
        fault.delivered_at = utcnow()
        db.commit()
    if body.simulate_failure or fault_kind == "failure":
        operation.status = "failed"
        operation.error = f"Simulated {system} failure before creation"
        operation.updated_at = utcnow()
        onboarding.substate = "failed"
        add_event(db, onboarding_id, "provisioning_exception", operation.error, {"operation_id": operation.id})
        db.commit()
        raise HTTPException(status_code=503, detail=f"Simulated {system} failure before creation")
    resource = SimResource(system=system, kind=kind, idempotency_key=idempotency_key, payload={"name": body.name, "url": f"https://{system}.example.test/{kind}/{uuid4()}", "onboarding_id": onboarding_id, "parent_id": body.parent_id, "todo_list_id": str(uuid4()) if system == "trello" else None})
    db.add(resource)
    db.commit()
    if body.simulate_timeout or fault_kind == "timeout":
        operation.status = "unknown"
        operation.error = f"Simulated {system} timeout after creation"
        operation.updated_at = utcnow()
        onboarding.substate = "uncertain"
        add_event(db, onboarding_id, "provisioning_exception", operation.error, {"operation_id": operation.id})
        db.commit()
        raise HTTPException(status_code=504, detail=f"Simulated {system} timeout after creation; reconcile before retry")
    return {"external_id": resource.id, "url": resource.payload["url"], "name": resource.payload["name"], "todo_list_id": resource.payload.get("todo_list_id"), "duplicate": False}


@app.get("/sim/{system}/resources/by-key/{idempotency_key}", dependencies=[Depends(internal_service)])
def sim_lookup(system: str, idempotency_key: str, db: Session = Depends(get_db)) -> dict:
    _require_demo_simulator()
    if system not in {"drive", "trello"}:
        raise HTTPException(status_code=404, detail="Unknown simulator")
    resource = db.scalar(select(SimResource).where(SimResource.system == system, SimResource.idempotency_key == idempotency_key))
    if not resource:
        return {"found": False}
    return {"found": True, "external_id": resource.id, "url": resource.payload["url"], "name": resource.payload["name"], "parent_id": resource.payload.get("parent_id"), "todo_list_id": resource.payload.get("todo_list_id")}


@app.post("/sim/trello/cards", dependencies=[Depends(internal_service)])
def sim_create_card(body: SimCardCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    _require_demo_simulator()
    if idempotency_key and idempotency_key != body.idempotency_key:
        raise HTTPException(status_code=409, detail="Idempotency header/body mismatch")
    board = db.get(SimResource, body.board_id)
    card = db.scalar(select(TaskCard).where(TaskCard.idempotency_key == body.idempotency_key))
    if not board or board.system != "trello" or board.kind != "board" or not card or card.board_external_id != board.id:
        raise HTTPException(status_code=404, detail="Scoped board/card operation not found")
    existing = db.scalar(select(SimResource).where(SimResource.system == "trello", SimResource.kind == "card", SimResource.idempotency_key == body.idempotency_key))
    if existing:
        return {"id": existing.id, "url": existing.payload["url"], "name": existing.payload["name"], "status": existing.payload["status"], "duplicate": True}
    item = db.get(ChecklistItem, card.checklist_item_id)
    resource = SimResource(system="trello", kind="card", idempotency_key=body.idempotency_key, payload={"board_id": board.id, "name": body.name, "description": body.description, "due_date": iso(body.due_date), "status": body.status, "checklist_item_id": item.id, "url": f"https://trello.example.test/card/{uuid4()}"})
    db.add(resource)
    db.commit()
    return {"id": resource.id, "url": resource.payload["url"], "name": resource.payload["name"], "status": resource.payload["status"], "duplicate": False}


@app.patch("/sim/trello/cards/{external_card_id}", dependencies=[Depends(internal_service)])
def sim_update_card(external_card_id: str, body: SimCardUpdate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    _require_demo_simulator()
    if idempotency_key and idempotency_key != body.idempotency_key:
        raise HTTPException(status_code=409, detail="Idempotency header/body mismatch")
    resource = db.get(SimResource, external_card_id)
    card = db.scalar(select(TaskCard).where(TaskCard.external_card_id == external_card_id, TaskCard.idempotency_key == body.idempotency_key))
    if not resource or resource.kind != "card" or not card:
        raise HTTPException(status_code=404, detail="Scoped card not found")
    duplicate = resource.payload.get("status") == body.status
    payload = dict(resource.payload)
    payload["status"] = body.status
    resource.payload = payload
    db.commit()
    return {"id": resource.id, "url": resource.payload["url"], "name": resource.payload["name"], "status": body.status, "duplicate": duplicate}


@app.post("/sim/smtp/send", dependencies=[Depends(internal_service)])
def sim_smtp(body: SimMail, idempotency_key: str = Header(alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    _require_demo_simulator()
    onboarding = require_onboarding(db, body.onboarding_id)
    if str(body.recipient).lower() != onboarding.client.email.lower():
        raise HTTPException(status_code=422, detail="Simulator recipient must be the scoped client")
    existing = db.scalar(select(OutboxEmail).where(OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "simulated_smtp", OutboxEmail.dedupe_key == idempotency_key))
    if existing:
        return {"id": existing.id, "status": existing.status, "duplicate": True}
    email = OutboxEmail(onboarding_id=onboarding.id, kind="simulated_smtp", dedupe_key=idempotency_key, recipient=str(body.recipient).lower(), subject=body.subject, body=body.body, status="simulated_sent")
    db.add(email)
    db.commit()
    return {"id": email.id, "status": email.status, "duplicate": False}


@app.post("/api/workflow-errors", dependencies=[Depends(internal_service)])
def record_workflow_error(body: WorkflowErrorReport, db: Session = Depends(get_db)) -> dict:
    workflow_id = body.workflow_id or "unknown-workflow"
    execution_id = body.execution_id or f"unknown-{uuid4()}"
    node = body.node or "unknown-node"
    message = body.message or "Workflow failed without an error message"
    existing = db.scalar(select(WorkflowException).where(WorkflowException.workflow_id == workflow_id, WorkflowException.execution_id == execution_id, WorkflowException.node == node))
    if existing:
        return {"id": existing.id, "status": existing.status, "duplicate": True}
    if body.onboarding_id:
        require_onboarding(db, body.onboarding_id)
    row = WorkflowException(onboarding_id=body.onboarding_id, workflow_id=workflow_id, execution_id=execution_id, node=node, message=message)
    db.add(row)
    if body.onboarding_id:
        add_event(db, body.onboarding_id, "workflow_exception", "n8n workflow error recorded", {"node": node, "exception_id": row.id})
    db.commit()
    return {"id": row.id, "status": row.status, "duplicate": False}


@app.get("/api/exceptions")
def list_exceptions(actor: OperatorActor = Depends(operator_actor), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(WorkflowException).join(Onboarding, WorkflowException.onboarding_id == Onboarding.id).where(Onboarding.workspace_id == actor.user.workspace_id).order_by(WorkflowException.created_at.desc()).limit(100)).all()
    return {"items": [_workflow_exception_item(row) for row in rows]}


def _workflow_exception_item(row: WorkflowException) -> dict:
    return {"id": row.id, "onboarding_id": row.onboarding_id, "workflow_id": row.workflow_id,
            "execution_id": row.execution_id, "node": row.node, "message": row.message,
            "status": row.status, "created_at": iso(row.created_at)}


@app.get("/api/workflow-errors/unattributed", dependencies=[Depends(internal_service)])
def list_unattributed_workflow_errors(db: Session = Depends(get_db)) -> dict:
    """Keep shared n8n errors inspectable without exposing them across workspaces."""
    rows = db.scalars(select(WorkflowException).where(WorkflowException.onboarding_id.is_(None))
                      .order_by(WorkflowException.created_at.desc()).limit(100)).all()
    return {"items": [_workflow_exception_item(row) for row in rows]}
