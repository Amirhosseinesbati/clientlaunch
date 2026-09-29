"""Initial ClientLaunch business schema.

Revision ID: 0001_initial
Revises:
"""

from alembic import op

from apps.api.database import Base
from apps.api import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

INITIAL_TABLES = (
    "workspaces", "users", "user_sessions", "clients", "won_deals", "event_receipts",
    "onboarding_templates", "onboardings", "plan_revisions", "approvals", "checklist_items",
    "assets", "intake_submissions", "portal_invites", "client_sessions",
    "provisioning_operations", "external_resources", "sim_resources", "outbox_emails",
    "reminder_tasks", "handoff_summaries", "timeline_events", "workflow_dispatches",
    "workflow_exceptions",
)


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in INITIAL_TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in INITIAL_TABLES])
