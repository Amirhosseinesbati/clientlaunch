"""Reproducible synthetic ClientLaunch demo data.

Run after migrations: python -m scripts.seed --mode full
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
import zlib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from apps.api.database import Base, SessionLocal, engine
from apps.api.models import (
    Approval, Asset, ChecklistItem, Client, EventReceipt, ExternalResource, HandoffSummary,
    IntakeSubmission, Onboarding, OnboardingTemplateVersion, OutboxEmail, PlanRevision,
    PortalInvite, ProvisioningOperation, ReminderTask, SimResource, TaskCard, TimelineEvent, User,
    WonDeal, Workspace,
)
from apps.api.security import digest, hash_password, portal_token_for
from apps.api.services import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_PATH = ROOT / "apps" / "api" / "templates.json"
FIRST = ["Juniper", "Aster", "Cedar", "Lumen", "Morrow", "Harbor", "Olive", "Spruce", "Meadow", "Birch", "Rowan", "Willow", "Ember", "Pine", "Mosaic"]
SECOND = ["Studio", "Works", "Collective", "Goods", "Labs", "Atelier", "Supply", "Cooperative"]


def png_placeholder(seed: int) -> bytes:
    rng = random.Random(seed)
    color = tuple(rng.randint(50, 190) for _ in range(3))
    accent = tuple(min(255, x + 45) for x in color)
    raw = bytearray()
    for y in range(64):
        raw.append(0)
        for x in range(64):
            raw.extend(accent if (x - 32) ** 2 + (y - 32) ** 2 < 20 ** 2 else color)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def load_templates() -> list[dict]:
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def ensure_workspace(db, slug: str, name: str) -> Workspace:
    row = db.scalar(select(Workspace).where(Workspace.slug == slug))
    if not row:
        row = Workspace(slug=slug, name=name, is_demo=True)
        db.add(row)
        db.flush()
    return row


def ensure_user(db, workspace: Workspace, local: str, role: str, password_hash: str) -> User:
    email = f"{local}@{workspace.slug}.example.com"
    row = db.scalar(select(User).where(User.workspace_id == workspace.id, User.email == email))
    if not row:
        row = User(workspace_id=workspace.id, email=email, name=f"{local.title()} {workspace.name}", password_hash=password_hash, role=role)
        db.add(row)
        db.flush()
    return row


def ensure_templates(db, workspace: Workspace, templates: list[dict]) -> None:
    for entry in templates:
        existing = db.scalar(select(OnboardingTemplateVersion).where(OnboardingTemplateVersion.workspace_id == workspace.id, OnboardingTemplateVersion.service_code == entry["service_code"], OnboardingTemplateVersion.version == 1))
        if not existing:
            db.add(OnboardingTemplateVersion(workspace_id=workspace.id, service_code=entry["service_code"], version=1, name=entry["name"], description=f"Deterministic {entry['name'].lower()} onboarding template.", checklist=[{**task, "client_visible": True, "description": f"Needed for {entry['name'].lower()}."} for task in entry["tasks"]], folder_blueprint=entry["folders"], board_blueprint=["To do", "Waiting for client", "In review", "Done"]))
    db.flush()


def ensure_client(db, workspace: Workspace, index: int) -> Client:
    email = f"client{index + 1:03d}@{workspace.slug}.example.com"
    row = db.scalar(select(Client).where(Client.workspace_id == workspace.id, Client.email == email))
    if not row:
        name = f"{FIRST[index % len(FIRST)]} {SECOND[(index // len(FIRST)) % len(SECOND)]}"
        row = Client(workspace_id=workspace.id, name=name, email=email)
        db.add(row)
        db.flush()
    return row


def generated_plan(templates: list[dict], service_codes: list[str], item_count: int, approved_scope: str, client_name: str) -> dict:
    by_code = {entry["service_code"]: entry for entry in templates}
    checklist = []
    for code in service_codes:
        for item in by_code[code]["tasks"]:
            checklist.append({"key": item["key"], "title": item["title"], "description": "", "required": item["required"], "source": "template", "service_code": code, "evidence": None, "client_visible": True, "due_date": None, "owner": None})
    extra = 1
    while len(checklist) < item_count:
        evidence = f"Client input {extra} for the approved project"
        checklist.append({"key": f"scope_input_{extra:02d}", "title": f"Provide project input {extra}", "description": evidence, "required": True, "source": "scope", "service_code": service_codes[0], "evidence": evidence, "client_visible": True, "due_date": None, "owner": None})
        extra += 1
    return {"checklist": checklist[:item_count], "deliverables": [f"{by_code[code]['name']} delivery" for code in service_codes], "risks": ["Access may arrive after kickoff"], "missing_inputs": [item["title"] for item in checklist[:3]], "welcome_draft": f"Hello {client_name}, welcome to your project. We are ready to begin once your intake checklist is complete.", "summary": f"Onboard {client_name} for {', '.join(service_codes)}.", "suggestions": []}


def ensure_deal(db, workspace: Workspace, owner: User, client: Client, global_index: int, service_codes: list[str], approved_scope: str, ref: date) -> Onboarding:
    external_id = f"SYN-DEAL-{global_index + 1:03d}"
    existing = db.scalar(select(WonDeal).where(WonDeal.workspace_id == workspace.id, WonDeal.external_deal_id == external_id))
    if existing:
        return db.scalar(select(Onboarding).where(Onboarding.deal_id == existing.id))
    timeline = {"start_date": (ref - timedelta(days=global_index % 10)).isoformat(), "target_date": (ref + timedelta(days=20 + global_index % 40)).isoformat()}
    if global_index % 17 == 0 and global_index:
        timeline["target_date"] = (ref - timedelta(days=3)).isoformat()
    business_payload = {"workspace_slug": workspace.slug, "external_deal_id": external_id, "client": {"name": client.name, "email": client.email}, "services": service_codes, "approved_scope": approved_scope, "proposal_text": approved_scope, "timeline": timeline, "account_owner_email": owner.email}
    deal = WonDeal(workspace_id=workspace.id, client_id=client.id, external_deal_id=external_id, business_hash=canonical_hash(business_payload), services=service_codes, approved_scope=approved_scope, proposal_text=approved_scope, timeline=timeline, account_owner_id=owner.id)
    db.add(deal)
    db.flush()
    onboarding = Onboarding(workspace_id=workspace.id, deal_id=deal.id, client_id=client.id)
    db.add(onboarding)
    db.flush()
    db.add(EventReceipt(workspace_id=workspace.id, event_id=f"SYN-EVENT-{global_index + 1:03d}", payload_hash=canonical_hash({**business_payload, "event_id": f"SYN-EVENT-{global_index + 1:03d}"}), onboarding_id=onboarding.id))
    db.add(TimelineEvent(onboarding_id=onboarding.id, kind="received", message="Synthetic won deal received", data={"synthetic": True}))
    return onboarding


def ensure_plan(db, onboarding: Onboarding, templates: list[dict], item_count: int, ref: date) -> None:
    if onboarding.current_plan_id:
        return
    content = generated_plan(templates, onboarding.deal.services, item_count, onboarding.deal.approved_scope, onboarding.client.name)
    plan = PlanRevision(onboarding_id=onboarding.id, revision=1, proposal_hash=canonical_hash(content), status="pending" if item_count == 0 else "approved", plan=content)
    db.add(plan)
    db.flush()
    onboarding.current_plan_id = plan.id
    onboarding.status = "awaiting_approval" if item_count == 0 else "provisioning"
    approval = Approval(onboarding_id=onboarding.id, plan_revision_id=plan.id, proposal_hash=plan.proposal_hash, status="pending" if item_count == 0 else "approved", expires_at=datetime.combine(ref + timedelta(days=30), time(0, 0), tzinfo=timezone.utc), decided_at=None if item_count == 0 else datetime.combine(ref - timedelta(days=2), time(12, 0), tzinfo=timezone.utc))
    db.add(approval)
    if item_count:
        token = portal_token_for(onboarding.id, plan.id)
        db.add(PortalInvite(onboarding_id=onboarding.id, token_hash=digest(token), expires_at=datetime.combine(ref + timedelta(days=30), time(0, 0), tzinfo=timezone.utc)))


def ensure_checklist(db, onboarding: Onboarding, item_count: int, ref: date) -> list[ChecklistItem]:
    plan = onboarding.current_plan
    existing = {item.item_key: item for item in db.scalars(select(ChecklistItem).where(ChecklistItem.onboarding_id == onboarding.id)).all()}
    result = []
    for position, item in enumerate(plan.plan["checklist"][:item_count]):
        key = f"{item['service_code']}:{item['key']}"
        row = existing.get(key)
        if not row:
            due = datetime.combine(ref + timedelta(days=(position % 8) - 3), time(17, 0), tzinfo=timezone.utc)
            row = ChecklistItem(onboarding_id=onboarding.id, item_key=key, title=item["title"], description=item.get("description") or "", required=True, status="open", due_at=due, owner_name=onboarding.deal.account_owner.name if position % 4 == 0 else onboarding.client.name, source=item["source"], client_visible=True)
            db.add(row)
            db.flush()
        result.append(row)
    return result


def ensure_operation(db, onboarding: Onboarding, system: str, successful: bool, uncertain: bool = False) -> None:
    action = "create_folder" if system == "drive" else "create_board"
    key = f"{system}:{action}"
    operation = db.scalar(select(ProvisioningOperation).where(ProvisioningOperation.onboarding_id == onboarding.id, ProvisioningOperation.operation_key == key))
    if operation:
        if system == "trello" and successful:
            sim = db.scalar(select(SimResource).where(SimResource.system == "trello", SimResource.idempotency_key == operation.idempotency_key))
            board = db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == "trello", ExternalResource.kind == "board"))
            if sim and not sim.payload.get("todo_list_id"):
                sim.payload = {**sim.payload, "todo_list_id": f"sim-list-{onboarding.id}"}
            if board and not board.preview.get("todo_list_id"):
                board.preview = {**board.preview, "todo_list_id": f"sim-list-{onboarding.id}"}
        return
    idempotency_key = f"clientlaunch:{onboarding.id}:{key}"
    name = onboarding.client.name + (" Project" if system == "drive" else " Onboarding")
    status = "succeeded" if successful else "unknown" if uncertain else "failed"
    resource = None
    if successful or uncertain:
        resource = SimResource(system=system, kind="folder" if system == "drive" else "board", idempotency_key=idempotency_key, payload={"name": name, "url": f"https://{system}.example.test/{onboarding.id}", "onboarding_id": onboarding.id, "todo_list_id": f"sim-list-{onboarding.id}" if system == "trello" else None})
        db.add(resource)
        db.flush()
    operation = ProvisioningOperation(onboarding_id=onboarding.id, operation_key=key, system=system, action=action, status=status, idempotency_key=idempotency_key, request_payload={"name": name}, response_payload={"synthetic": True} if successful else None, external_id=resource.id if successful else None, error="Synthetic ambiguous response" if uncertain else "Synthetic connector failure" if not successful else None, attempt_count=1)
    db.add(operation)
    if successful:
        db.add(ExternalResource(onboarding_id=onboarding.id, system=system, kind="folder" if system == "drive" else "board", external_id=resource.id, preview={"url": resource.payload["url"], "name": name, "todo_list_id": resource.payload.get("todo_list_id")}))


def ensure_task_cards(db, onboarding: Onboarding, items: list[ChecklistItem]) -> None:
    board = db.scalar(select(ExternalResource).where(ExternalResource.onboarding_id == onboarding.id, ExternalResource.system == "trello", ExternalResource.kind == "board"))
    if not board:
        return
    task_preview = []
    for item in items:
        existing = db.scalar(select(TaskCard).where(TaskCard.checklist_item_id == item.id))
        if not existing:
            key = f"clientlaunch:{onboarding.id}:trello:card:{item.id}"
            sim = SimResource(system="trello", kind="card", idempotency_key=key, payload={"board_id": board.external_id, "name": item.title, "description": item.description, "status": item.status, "checklist_item_id": item.id, "url": f"https://trello.example.test/card/{item.id}"})
            db.add(sim)
            db.flush()
            existing = TaskCard(onboarding_id=onboarding.id, checklist_item_id=item.id, board_external_id=board.external_id, external_card_id=sim.id, desired_status=item.status, synced_status=item.status, sync_state="synced", idempotency_key=key)
            db.add(existing)
        task_preview.append({"checklist_item_id": item.id, "external_card_id": existing.external_card_id, "title": item.title, "status": item.status})
    board.preview = {**board.preview, "tasks": task_preview}


def ensure_asset(db, onboarding: Onboarding, item: ChecklistItem, asset_index: int, storage: Path) -> None:
    filename = f"synthetic-brand-{asset_index + 1:03d}.png"
    existing = db.scalar(select(Asset).where(Asset.onboarding_id == onboarding.id, Asset.original_name == filename))
    if existing:
        return
    data = png_placeholder(asset_index)
    asset = Asset(workspace_id=onboarding.workspace_id, onboarding_id=onboarding.id, checklist_item_id=item.id, original_name=filename, content_type="image/png", size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_path="")
    db.add(asset)
    db.flush()
    relative = Path(onboarding.workspace_id) / onboarding.id / f"{asset.id}.png"
    destination = storage / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    asset.storage_path = str(relative)
    item.status = "completed"
    item.completed_at = datetime.now(timezone.utc)


def ensure_submission(db, onboarding: Onboarding, item: ChecklistItem, ordinal: int) -> None:
    records = db.scalars(select(IntakeSubmission).where(IntakeSubmission.onboarding_id == onboarding.id)).all()
    if len(records) > ordinal:
        return
    answer = {"checklist_item_id": item.id, "value": f"Synthetic approved answer {ordinal + 1} for {onboarding.client.name}."}
    db.add(IntakeSubmission(onboarding_id=onboarding.id, answers=[answer]))
    item.status = "completed"
    item.completed_at = datetime.now(timezone.utc)


def seed(mode: str, seed_value: int, reference_date: date) -> dict:
    password = os.getenv("DEMO_ADMIN_PASSWORD")
    if not password or len(password) < 12:
        raise SystemExit("Set DEMO_ADMIN_PASSWORD to at least 12 characters before seeding")
    rng = random.Random(seed_value)
    templates = load_templates()
    codes = [entry["service_code"] for entry in templates]
    client_target, deal_target = (60, 90) if mode == "full" else (8, 8)
    storage = Path(os.getenv("ASSET_STORAGE_DIR", ROOT / "data" / "assets")).resolve()
    with SessionLocal() as db:
        workspaces = [ensure_workspace(db, "northstar", "Northstar Creative"), ensure_workspace(db, "cedar", "Cedar & Co")]
        hashed = hash_password(password)
        owners = {}
        for workspace in workspaces:
            owners[workspace.id] = ensure_user(db, workspace, "operator", "operator", hashed)
            ensure_user(db, workspace, "admin", "admin", hashed)
            ensure_user(db, workspace, "viewer", "viewer", hashed)
            ensure_templates(db, workspace, templates)
        clients = []
        for global_index in range(client_target):
            workspace = workspaces[0 if global_index < (client_target // 2) else 1]
            local_index = global_index if workspace is workspaces[0] else global_index - client_target // 2
            clients.append(ensure_client(db, workspace, local_index))
        db.flush()
        selected_indices = range(deal_target) if mode == "full" else [0, 1, 2, 31, 33, 39, 51, 55]
        for index in selected_indices:
            workspace = workspaces[0 if index < 45 else 1]
            if mode == "fast":
                group_start = 0 if workspace is workspaces[0] else client_target // 2
                client = clients[group_start + (index % (client_target // 2))]
            else:
                group_start = 0 if workspace is workspaces[0] else client_target // 2
                client = clients[group_start + (index % (client_target // 2))]
            services = ["website"] if index == 0 else [codes[index % len(codes)]] + ([codes[(index + 3) % len(codes)]] if index % 4 == 0 else [])
            item_target = 0 if index == 0 else 12 if index <= 21 else 11
            extra_count = max(0, item_target - sum(len(next(entry for entry in templates if entry["service_code"] == code)["tasks"]) for code in services))
            scope = f"Approved {', '.join(services)} project for {client.name}. " + " ".join(f"Client input {number} for the approved project." for number in range(1, extra_count + 1))
            onboarding = ensure_deal(db, workspace, owners[workspace.id], client, index, services, scope, reference_date)
            ensure_plan(db, onboarding, templates, item_target, reference_date)
            if item_target == 0:
                continue
            items = ensure_checklist(db, onboarding, item_target, reference_date)
            if index <= 30:
                ensure_operation(db, onboarding, "drive", True)
                ensure_operation(db, onboarding, "trello", False, uncertain=index % 2 == 0)
                onboarding.status = "provisioning"
                onboarding.substate = "uncertain" if index % 2 == 0 else "failed"
                continue
            ensure_operation(db, onboarding, "drive", True)
            ensure_operation(db, onboarding, "trello", True)
            onboarding.status = "waiting_for_client"
            onboarding.substate = None
            email = db.scalar(select(OutboxEmail).where(OutboxEmail.onboarding_id == onboarding.id, OutboxEmail.kind == "welcome"))
            portal_link = f"{os.getenv('WEB_BASE_URL', 'http://localhost:5173').rstrip('/')}/client?token={portal_token_for(onboarding.id, onboarding.current_plan_id)}"
            requested = "\n".join(f"- {item.title}" for item in items if item.status != "completed")
            welcome_body = onboarding.current_plan.plan["welcome_draft"] + f"\n\nYour secure intake portal: {portal_link}\n\nWhat we need from you next:\n{requested}\n\nAccount owner: {onboarding.deal.account_owner.name}\nPlease share your kickoff availability in the portal."
            if not email:
                db.add(OutboxEmail(onboarding_id=onboarding.id, kind="welcome", dedupe_key=onboarding.current_plan_id, recipient=client.email, subject="Welcome to your project", body=welcome_body, status="simulated_sent"))
            elif email.body == onboarding.current_plan.plan["welcome_draft"]:
                email.body = welcome_body
            if mode == "full":
                asset_target = 4 + (1 if index <= 44 else 0)
                submission_target = 3 + (1 if index <= 33 else 0)
            else:
                asset_target = 1
                submission_target = 1
            for ordinal in range(asset_target):
                ensure_asset(db, onboarding, items[ordinal % len(items)], index * 10 + ordinal, storage)
            for ordinal in range(submission_target):
                ensure_submission(db, onboarding, items[ordinal % len(items)], ordinal)
            if index % 13 == 0:
                for item in items:
                    item.status = "completed"
                onboarding.status = "handed_off"
                if not db.scalar(select(HandoffSummary).where(HandoffSummary.onboarding_id == onboarding.id)):
                    db.add(HandoffSummary(onboarding_id=onboarding.id, summary=f"Synthetic delivery handoff for {client.name}, linked to intake and assets.", evidence={"synthetic": True}))
            elif index % 11 == 0:
                for item in items:
                    item.status = "completed"
                onboarding.status = "ready"
            elif index % 17 == 0:
                onboarding.status = "paused"
            ensure_task_cards(db, onboarding, items)
            if onboarding.status == "waiting_for_client" and index % 5 == 0:
                db.add(ReminderTask(onboarding_id=onboarding.id, checklist_item_id=items[-1].id, status="drafted", due_at=items[-1].due_at))
        db.commit()
        counts = {table: db.scalar(select(func.count()).select_from(model)) for table, model in {
            "workspaces": Workspace, "clients": Client, "won_deals": WonDeal,
            "service_templates": OnboardingTemplateVersion, "checklist_items": ChecklistItem,
            "assets": Asset, "intake_submissions": IntakeSubmission,
            "task_cards": TaskCard,
            "partial_failures": ProvisioningOperation,
        }.items()}
        counts["partial_failures"] = db.scalar(select(func.count()).select_from(ProvisioningOperation).where(ProvisioningOperation.status.in_(["failed", "unknown"])))
        return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fast", "full"], default="fast")
    parser.add_argument("--seed", type=int, default=int(os.getenv("DEMO_SEED", "20260928")))
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date.fromisoformat(os.getenv("DEMO_REFERENCE_DATE", "2026-09-28")))
    args = parser.parse_args()
    print(json.dumps({"mode": args.mode, "seed": args.seed, "reference_date": args.reference_date.isoformat(), "counts": seed(args.mode, args.seed, args.reference_date)}, indent=2))


if __name__ == "__main__":
    main()
