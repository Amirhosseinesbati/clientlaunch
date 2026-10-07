from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Approval,
    Asset,
    ChecklistItem,
    EventReceipt,
    ExternalResource,
    HandoffSummary,
    IntakeSubmission,
    Onboarding,
    OnboardingTemplateVersion,
    OutboxEmail,
    PlanRevision,
    PortalInvite,
    ProjectFolder,
    ProvisioningOperation,
    ReminderTask,
    TaskCard,
    TimelineEvent,
    WorkflowDispatch,
    Workspace,
    WorkspaceBrand,
    utcnow,
)
from .security import aware, portal_token_for


def brand_settings(db: Session, workspace_id: str) -> dict:
    brand = db.get(WorkspaceBrand, workspace_id)
    if brand:
        return {key: getattr(brand, key) for key in ("agency_name", "accent", "welcome_heading", "welcome_message", "support_email", "version")}
    workspace = db.get(Workspace, workspace_id)
    return {"agency_name": workspace.name, "accent": "#183e32", "welcome_heading": "A great project starts with a clear first step.",
            "welcome_message": "Share a few details with your project team. You can come back and finish at your own pace.",
            "support_email": None, "version": 0}


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_onboarding(db: Session, onboarding_id: str, workspace_id: str | None = None) -> Onboarding:
    onboarding = db.get(Onboarding, onboarding_id)
    if onboarding is None or (workspace_id and onboarding.workspace_id != workspace_id):
        raise HTTPException(status_code=404, detail="Onboarding not found")
    return onboarding


def add_event(db: Session, onboarding_id: str, kind: str, message: str, data: dict | None = None) -> None:
    db.add(TimelineEvent(onboarding_id=onboarding_id, kind=kind, message=message, data=data or {}))


def project_name(onboarding: Onboarding) -> str:
    services = ", ".join(onboarding.deal.services)
    return f"{onboarding.client.name} — {services}"


def progress(db: Session, onboarding_id: str) -> tuple[int, int, int]:
    items = db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding_id, ChecklistItem.required.is_(True))).all()
    total = len(items)
    complete = sum(item.status == "completed" for item in items)
    return complete, total, round(100 * complete / total) if total else 0


def refresh_readiness(db: Session, onboarding: Onboarding) -> None:
    if onboarding.status not in {"waiting_for_client", "ready"} or onboarding.substate in {"failed", "recovering", "uncertain"}:
        return
    complete, total, _ = progress(db, onboarding.id)
    resources = db.scalars(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id)).all()
    systems = {item.system for item in resources}
    folders = db.scalars(select(ProjectFolder).where(ProjectFolder.onboarding_id == onboarding.id)).all()
    folders_complete = {folder.service_code for folder in folders if folder.folder_key == "service"} == set(onboarding.deal.services) and all(folder.external_id for folder in folders)
    cards = db.scalars(select(TaskCard).where(TaskCard.onboarding_id == onboarding.id)).all()
    board_tasks_synced = bool(cards) and all(card.sync_state == "synced" and card.synced_status == card.desired_status for card in cards)
    welcome = db.scalar(select(OutboxEmail).where(OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome"))
    if total and complete == total and {"drive", "trello"}.issubset(systems) and folders_complete and board_tasks_synced and welcome and welcome.status in {"simulated_sent", "dispatched"}:
        if onboarding.status != "ready":
            onboarding.status = "ready"
            add_event(db, onboarding.id, "ready", "All required client inputs are complete")
    elif onboarding.status == "ready":
        onboarding.status = "waiting_for_client"
        add_event(db, onboarding.id, "reopened", "A required item needs further review")
    onboarding.updated_at = utcnow()


def iso(value: datetime | None) -> str | None:
    return aware(value).isoformat() if value else None


def list_item(db: Session, onboarding: Onboarding) -> dict:
    complete, total, percent = progress(db, onboarding.id)
    return {
        "id": onboarding.id,
        "client_name": onboarding.client.name,
        "client_email": onboarding.client.email,
        "service_names": onboarding.deal.services,
        "status": onboarding.status,
        "substate": onboarding.substate,
        "owner_name": onboarding.deal.account_owner.name,
        "progress_percent": percent,
        "required_complete": complete,
        "required_total": total,
        "created_at": iso(onboarding.created_at),
        "updated_at": iso(onboarding.updated_at),
    }


def folder_structure(db: Session, onboarding: Onboarding, resources: list[ExternalResource], operations: list[ProvisioningOperation]) -> dict:
    root = next((resource for resource in resources if resource.system == "drive" and resource.kind == "folder"), None)
    root_operation = next((operation for operation in operations if operation.operation_key == "drive:create_folder"), None)
    rows = db.scalars(select(ProjectFolder).where(ProjectFolder.onboarding_id == onboarding.id).order_by(ProjectFolder.service_code, ProjectFolder.sort_order)).all()
    operation_by_key = {operation.operation_key: operation for operation in operations}
    if rows:
        by_id = {folder.id: folder for folder in rows}
        folders = []
        for folder in rows:
            operation = operation_by_key.get(f"drive:create_child_folder:{folder.id}")
            parent = by_id.get(folder.parent_id) if folder.parent_id else None
            folders.append({
                "id": folder.id, "service_code": folder.service_code, "folder_key": folder.folder_key,
                "name": folder.name, "parent_id": folder.parent_id, "parent_folder_key": parent.folder_key if parent else "root",
                "parent_external_id": parent.external_id if parent else (root.external_id if root else None),
                "external_id": folder.external_id, "url": folder.url,
                "status": "succeeded" if folder.external_id else (operation.status if operation else "planned"),
            })
    else:
        folders = []
        saved_blueprints = (onboarding.current_plan.plan.get("folder_blueprints") if onboarding.current_plan else None) or {}
        for service_code in sorted(onboarding.deal.services):
            saved = saved_blueprints.get(service_code)
            if saved:
                service_name, folder_names = saved["name"], saved["folders"]
            else:
                template = db.scalar(select(OnboardingTemplateVersion).where(
                    OnboardingTemplateVersion.workspace_id == onboarding.workspace_id,
                    OnboardingTemplateVersion.service_code == service_code,
                    OnboardingTemplateVersion.active.is_(True),
                ).order_by(OnboardingTemplateVersion.version.desc()))
                if not template:
                    continue
                service_name, folder_names = template.name, template.folder_blueprint
            if not service_name:
                continue
            folders.append({"id": None, "service_code": service_code, "folder_key": "service", "name": service_name,
                            "parent_id": None, "parent_folder_key": "root", "parent_external_id": root.external_id if root else None,
                            "external_id": None, "url": None, "status": "planned"})
            for index, name in enumerate(folder_names):
                folders.append({"id": None, "service_code": service_code, "folder_key": f"item:{index}", "name": name,
                                "parent_id": None, "parent_folder_key": "service", "parent_external_id": None,
                                "external_id": None, "url": None, "status": "planned"})
    return {
        "root": {"name": project_name(onboarding), "external_id": root.external_id if root else None,
                 "url": root.preview.get("url") if root else None,
                 "status": "succeeded" if root else (root_operation.status if root_operation else "planned")},
        "folders": folders,
        "planned_count": len(folders),
        "complete_count": sum(bool(folder["external_id"]) for folder in folders),
        "complete": bool(root) and {folder["service_code"] for folder in folders if folder["folder_key"] == "service"} == set(onboarding.deal.services) and all(folder["external_id"] for folder in folders),
    }


def detail(db: Session, onboarding: Onboarding) -> dict:
    plan = onboarding.current_plan
    items = db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id).order_by(ChecklistItem.title)).all()
    operations = db.scalars(select(ProvisioningOperation).where(ProvisioningOperation.onboarding_id == onboarding.id).order_by(ProvisioningOperation.updated_at)).all()
    resources = db.scalars(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id)).all()
    approvals = db.scalars(select(Approval).where(Approval.onboarding_id == onboarding.id)).all()
    events = db.scalars(select(TimelineEvent).where(TimelineEvent.onboarding_id == onboarding.id).order_by(TimelineEvent.created_at)).all()
    assets = db.scalars(select(Asset).where(Asset.onboarding_id == onboarding.id)).all()
    submissions = db.scalars(select(IntakeSubmission).where(IntakeSubmission.onboarding_id == onboarding.id)).all()
    welcome = db.scalars(select(OutboxEmail).where(OutboxEmail.onboarding_id == onboarding.id)).all()
    reminders = db.scalars(select(ReminderTask).where(ReminderTask.onboarding_id == onboarding.id).order_by(ReminderTask.created_at.desc())).all()
    cards = db.scalars(select(TaskCard).where(TaskCard.onboarding_id == onboarding.id)).all()
    handoff = db.scalar(select(HandoffSummary).where(HandoffSummary.onboarding_id == onboarding.id))
    result = list_item(db, onboarding)
    result.update({
        "workspace_id": onboarding.workspace_id,
        "workspace_name": onboarding.workspace.name,
        "project_name": project_name(onboarding),
        "folder_name": project_name(onboarding),
        "board_name": project_name(onboarding) + " | Onboarding",
        "connector_mode": os.getenv("CONNECTOR_MODE", "demo").lower(),
        "reference_date": os.getenv("DEMO_REFERENCE_DATE", "2026-09-28"),
    })
    invite = db.scalar(select(PortalInvite).where(PortalInvite.onboarding_id == onboarding.id, PortalInvite.revoked_at.is_(None)).order_by(PortalInvite.expires_at.desc()))
    result["invite_status"] = "active" if invite and aware(invite.expires_at) > utcnow() else "expired" if invite else "not_created"
    result["invite_expires_at"] = iso(invite.expires_at) if invite else None
    if invite and plan and aware(invite.expires_at) > utcnow():
        base_url = os.getenv("WEB_BASE_URL", "http://localhost:5173").rstrip("/")
        result["portal_link"] = f"{base_url}/client?token={portal_token_for(onboarding.id, plan.id)}"
    return {
        "onboarding": result,
        "deal": {
            "external_deal_id": onboarding.deal.external_deal_id,
            "approved_scope": onboarding.deal.approved_scope,
            "proposal_text": onboarding.deal.proposal_text,
            "services": onboarding.deal.services,
            "timeline": onboarding.deal.timeline,
        },
        "plan": ({"id": plan.id, "revision": plan.revision, "proposal_hash": plan.proposal_hash, "status": plan.status, **plan.plan} if plan else None),
        "checklist": [{
            "id": item.id, "key": item.item_key, "title": item.title, "description": item.description,
            "required": item.required, "status": item.status, "due_at": iso(item.due_at),
            "owner_name": item.owner_name, "source": item.source, "client_visible": item.client_visible,
        } for item in items],
        "operations": [{
            "id": op.id, "system": op.system, "action": op.action, "status": op.status,
            "external_id": op.external_id, "error": op.error, "attempt_count": op.attempt_count,
            "idempotency_key": op.idempotency_key, "updated_at": iso(op.updated_at),
        } for op in operations],
        "resources": [{"id": r.id, "system": r.system, "kind": r.kind, "external_id": r.external_id, **r.preview} for r in resources],
        "folder_structure": folder_structure(db, onboarding, resources, operations),
        "approvals": [{"id": a.id, "plan_revision_id": a.plan_revision_id, "proposal_hash": a.proposal_hash, "status": a.status, "expires_at": iso(a.expires_at), "decided_at": iso(a.decided_at)} for a in approvals],
        "events": [{"id": e.id, "kind": e.kind, "message": e.message, "data": e.data, "created_at": iso(e.created_at)} for e in events],
        "assets": [{"id": a.id, "filename": a.original_name, "content_type": a.content_type, "size_bytes": a.size_bytes, "checklist_item_id": a.checklist_item_id, "created_at": iso(a.created_at)} for a in assets],
        "submissions": [{"id": s.id, "answers": s.answers, "created_at": iso(s.created_at)} for s in submissions],
        "welcome": [{"id": m.id, "recipient": m.recipient, "subject": m.subject, "body": m.body, "status": m.status, "created_at": iso(m.created_at)} for m in welcome],
        "reminders": [{"id": r.id, "checklist_item_id": r.checklist_item_id, "status": r.status, "due_at": iso(r.due_at), "created_at": iso(r.created_at), "approved_at": iso(r.approved_at), "dispatched_at": iso(r.dispatched_at)} for r in reminders],
        "task_cards": [{"id": card.id, "checklist_item_id": card.checklist_item_id, "external_card_id": card.external_card_id, "desired_status": card.desired_status, "synced_status": card.synced_status, "sync_state": card.sync_state} for card in cards],
        "handoff": {"id": handoff.id, "summary": handoff.summary, "evidence": handoff.evidence, "created_at": iso(handoff.created_at)} if handoff else None,
    }


def client_detail(db: Session, onboarding: Onboarding) -> dict:
    source = detail(db, onboarding)
    checklist = [item for item in source["checklist"] if item["client_visible"]]
    visible_ids = {item["id"] for item in checklist}
    public_submissions = []
    for submission in source["submissions"]:
        answers = [answer for answer in submission["answers"] if answer.get("checklist_item_id") in visible_ids]
        if answers:
            public_submissions.append({**submission, "answers": answers})
    required = [item for item in checklist if item["required"]]
    completed = sum(item["status"] == "completed" for item in required)
    public_onboarding = {key: source["onboarding"][key] for key in ("id", "client_name", "service_names", "status")}
    public_onboarding.update({"required_complete": completed, "required_total": len(required),
                              "progress_percent": round(100 * completed / len(required)) if required else 0,
                              "intake_open": onboarding.status in {"waiting_for_client", "ready"} and not onboarding.substate})
    return {
        "onboarding": public_onboarding,
        "brand": brand_settings(db, onboarding.workspace_id),
        "checklist": checklist,
        "assets": source["assets"],
        "submissions": public_submissions,
        "next_actions": [item for item in checklist if item["status"] != "completed"],
    }


def evaluate_reminders(db: Session, reference_time: datetime, onboarding_id: str | None = None) -> list[ReminderTask]:
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    query = select(Onboarding).where(Onboarding.status == "waiting_for_client", Onboarding.substate.is_(None))
    if onboarding_id:
        query = query.where(Onboarding.id == onboarding_id)
    drafted: list[ReminderTask] = []
    for onboarding in db.scalars(query).all():
        items = db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id, ChecklistItem.status != "completed", ChecklistItem.client_visible.is_(True))).all()
        for item in items:
            if item.due_at and aware(item.due_at) > reference_time:
                continue
            history = db.scalars(select(ReminderTask).where(ReminderTask.checklist_item_id == item.id).order_by(ReminderTask.created_at.desc())).all()
            sent = [r for r in history if r.status == "dispatched"]
            if len(sent) >= 3 or any(r.status in {"drafted", "approved"} for r in history):
                continue
            if sent and aware(sent[0].dispatched_at or sent[0].created_at) > reference_time - timedelta(days=3):
                continue
            reminder = ReminderTask(onboarding_id=onboarding.id, checklist_item_id=item.id, due_at=item.due_at, created_at=reference_time)
            db.add(reminder)
            db.flush()
            drafted.append(reminder)
            add_event(db, onboarding.id, "reminder_drafted", f"Reminder drafted for {item.title}", {"reminder_id": reminder.id})
    return drafted
