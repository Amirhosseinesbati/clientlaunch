from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ClientPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr


class WonDealEvent(BaseModel):
    workspace_slug: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=160)
    external_deal_id: str = Field(min_length=1, max_length=160)
    client: ClientPayload
    services: list[str] = Field(min_length=1, max_length=20)
    approved_scope: str = Field(min_length=10, max_length=30000)
    proposal_text: str = Field(min_length=10, max_length=60000)
    timeline: dict[str, str | None] = Field(default_factory=dict)
    account_owner_email: EmailStr

    @field_validator("services")
    @classmethod
    def distinct_services(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("services must be unique")
        return value


class PlanChecklistItem(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=3000)
    required: bool = True
    source: Literal["template", "scope"]
    service_code: str = Field(min_length=1, max_length=80)
    evidence: str | None = Field(default=None, max_length=2000)
    client_visible: bool = True
    due_date: date | None = None
    owner: str | None = Field(default=None, max_length=160)


class PlanDraft(BaseModel):
    checklist: list[PlanChecklistItem] = Field(default_factory=list, max_length=200)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=100)
    missing_inputs: list[str] = Field(default_factory=list, max_length=100)
    welcome_draft: str = Field(min_length=1, max_length=12000)
    summary: str = Field(default="", max_length=5000)
    suggestions: list[str] = Field(default_factory=list, max_length=100)


class ApprovalDecision(BaseModel):
    plan_revision_id: str
    proposal_hash: str
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=3000)


class ProvisionClaim(BaseModel):
    system: Literal["drive", "trello"]
    action: Literal["create_folder", "create_child_folder", "create_board"]
    folder_id: str | None = None
    request_payload: dict = Field(default_factory=dict)


class ProvisionComplete(BaseModel):
    outcome: Literal["success", "failed", "unknown"] = "success"
    external_id: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, max_length=240)
    todo_list_id: str | None = Field(default=None, max_length=200)
    preview: dict = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=3000)


class WelcomeRequest(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=240)
    body: str | None = Field(default=None, min_length=1, max_length=30000)
    recipient: EmailStr | None = None


class PortalExchange(BaseModel):
    portal_token: str = Field(min_length=1)


class IntakeAnswer(BaseModel):
    checklist_item_id: str
    value: str = Field(min_length=1, max_length=10000)


class IntakeRequest(BaseModel):
    answers: list[IntakeAnswer] = Field(min_length=1, max_length=100)


class ReminderEvaluate(BaseModel):
    reference_time: datetime | None = None
    onboarding_id: str | None = None


class ReminderApproval(BaseModel):
    decision: Literal["approve", "reject"]


class ReminderDispatch(BaseModel):
    provider_message_id: str | None = Field(default=None, max_length=200)


class RecoverRequest(BaseModel):
    operation_id: str | None = None
    decision: Literal["retry", "reconcile", "compensate"] | None = None
    external_id: str | None = None
    todo_list_id: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    name: str | None = Field(default=None, max_length=240)
    confirmed_absent: bool = False


class OutboxAck(BaseModel):
    provider_message_id: str = Field(min_length=1, max_length=200)


class TaskCardAck(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    status: Literal["open", "completed", "needs_review"]


class TaskCardReconcile(BaseModel):
    operation_id: str | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["open", "completed", "needs_review"] | None = None
    confirmed_absent: bool = False


class SimCardCreate(BaseModel):
    board_id: str
    name: str = Field(min_length=1, max_length=240)
    description: str = ""
    due_date: datetime | None = None
    status: Literal["open", "completed", "needs_review"]
    idempotency_key: str


class TaskCardClaim(BaseModel):
    expected_status: Literal["open", "completed", "needs_review"]
    expected_idempotency_key: str = Field(min_length=1, max_length=200)


class SimCardUpdate(BaseModel):
    status: Literal["open", "completed", "needs_review"]
    idempotency_key: str


class SimFaultRequest(BaseModel):
    onboarding_id: str
    system: Literal["drive", "trello"]
    kind: Literal["failure", "timeout"]


class HandoffRequest(BaseModel):
    summary: str = Field(min_length=10, max_length=10000)


class ChecklistEdit(BaseModel):
    due_at: datetime | None = None
    owner_name: str | None = Field(default=None, max_length=160)


class LifecycleAction(BaseModel):
    action: Literal["pause", "resume"]
    reason: str | None = Field(default=None, max_length=1000)


class SimCreate(BaseModel):
    onboarding_id: str | None = None
    name: str = Field(min_length=1, max_length=240)
    idempotency_key: str | None = None
    parent_id: str | None = None
    simulate_failure: bool = False
    simulate_timeout: bool = False


class SimMail(BaseModel):
    onboarding_id: str
    recipient: EmailStr
    subject: str
    body: str


class WorkflowErrorReport(BaseModel):
    workflow_id: str | None = Field(default=None, max_length=160)
    execution_id: str | None = Field(default=None, max_length=160)
    node: str | None = Field(default=None, max_length=160)
    message: str | None = Field(default=None, max_length=3000)
    onboarding_id: str | None = None


class IdResponse(BaseModel):
    id: str
    status: str

    model_config = ConfigDict(from_attributes=True)
