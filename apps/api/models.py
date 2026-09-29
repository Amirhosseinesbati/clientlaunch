from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    workspace: Mapped[Workspace] = relationship()


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))


class WonDeal(Base):
    __tablename__ = "won_deals"
    __table_args__ = (UniqueConstraint("workspace_id", "external_deal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    external_deal_id: Mapped[str] = mapped_column(String(160))
    business_hash: Mapped[str] = mapped_column(String(64))
    services: Mapped[list] = mapped_column(JSON)
    approved_scope: Mapped[str] = mapped_column(Text)
    proposal_text: Mapped[str] = mapped_column(Text)
    timeline: Mapped[dict] = mapped_column(JSON)
    account_owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    client: Mapped[Client] = relationship()
    account_owner: Mapped[User] = relationship()


class EventReceipt(Base):
    __tablename__ = "event_receipts"
    __table_args__ = (UniqueConstraint("workspace_id", "event_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(160))
    payload_hash: Mapped[str] = mapped_column(String(64))
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OnboardingTemplateVersion(Base):
    __tablename__ = "onboarding_templates"
    __table_args__ = (UniqueConstraint("workspace_id", "service_code", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    service_code: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    checklist: Mapped[list] = mapped_column(JSON)
    folder_blueprint: Mapped[list] = mapped_column(JSON)
    board_blueprint: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Onboarding(Base):
    __tablename__ = "onboardings"
    __table_args__ = (UniqueConstraint("workspace_id", "deal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("won_deals.id"), unique=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="received")
    substate: Mapped[str | None] = mapped_column(String(40))
    current_plan_id: Mapped[str | None] = mapped_column(ForeignKey("plan_revisions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    workspace: Mapped[Workspace] = relationship()
    deal: Mapped[WonDeal] = relationship()
    client: Mapped[Client] = relationship()
    current_plan: Mapped[PlanRevision | None] = relationship(foreign_keys=[current_plan_id])


class PlanRevision(Base):
    __tablename__ = "plan_revisions"
    __table_args__ = (UniqueConstraint("onboarding_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    proposal_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    plan: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    plan_revision_id: Mapped[str] = mapped_column(ForeignKey("plan_revisions.id"), unique=True)
    proposal_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    __table_args__ = (UniqueConstraint("onboarding_id", "item_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    item_key: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_name: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(24))
    client_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    checklist_item_id: Mapped[str | None] = mapped_column(ForeignKey("checklist_items.id"))
    original_name: Mapped[str] = mapped_column(String(240))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntakeSubmission(Base):
    __tablename__ = "intake_submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    answers: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PortalInvite(Base):
    __tablename__ = "portal_invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientSession(Base):
    __tablename__ = "client_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProvisioningOperation(Base):
    __tablename__ = "provisioning_operations"
    __table_args__ = (UniqueConstraint("onboarding_id", "operation_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    operation_key: Mapped[str] = mapped_column(String(160))
    system: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(24), default="claimed")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_payload: Mapped[dict] = mapped_column(JSON)
    response_payload: Mapped[dict | None] = mapped_column(JSON)
    external_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalResource(Base):
    __tablename__ = "external_resources"
    __table_args__ = (UniqueConstraint("onboarding_id", "system", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    system: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(200))
    preview: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectFolder(Base):
    """Approved, immutable per-service Drive folder plan and its provider outcome."""

    __tablename__ = "project_folders"
    __table_args__ = (UniqueConstraint("onboarding_id", "service_code", "folder_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    template_version_id: Mapped[str] = mapped_column(ForeignKey("onboarding_templates.id"))
    service_code: Mapped[str] = mapped_column(String(80))
    folder_key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(240))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("project_folders.id"))
    sort_order: Mapped[int] = mapped_column(Integer)
    external_id: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000))


class TaskCard(Base):
    __tablename__ = "task_cards"
    __table_args__ = (UniqueConstraint("checklist_item_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    checklist_item_id: Mapped[str] = mapped_column(ForeignKey("checklist_items.id"), index=True)
    board_external_id: Mapped[str] = mapped_column(String(200))
    external_card_id: Mapped[str | None] = mapped_column(String(200))
    desired_status: Mapped[str] = mapped_column(String(24))
    synced_status: Mapped[str | None] = mapped_column(String(24))
    sync_state: Mapped[str] = mapped_column(String(24), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class SimResource(Base):
    __tablename__ = "sim_resources"
    __table_args__ = (UniqueConstraint("system", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    system: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEmail(Base):
    __tablename__ = "outbox_emails"
    __table_args__ = (UniqueConstraint("onboarding_id", "kind", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(160))
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="simulated_sent")
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReminderTask(Base):
    __tablename__ = "reminder_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    checklist_item_id: Mapped[str] = mapped_column(ForeignKey("checklist_items.id"))
    status: Mapped[str] = mapped_column(String(24), default="drafted")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandoffSummary(Base):
    __tablename__ = "handoff_summaries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), unique=True)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowDispatch(Base):
    __tablename__ = "workflow_dispatches"
    __table_args__ = (UniqueConstraint("kind", "dedupe_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str] = mapped_column(ForeignKey("onboardings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowException(Base):
    __tablename__ = "workflow_exceptions"
    __table_args__ = (UniqueConstraint("workflow_id", "execution_id", "node"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    onboarding_id: Mapped[str | None] = mapped_column(ForeignKey("onboardings.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(160))
    execution_id: Mapped[str] = mapped_column(String(160))
    node: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
