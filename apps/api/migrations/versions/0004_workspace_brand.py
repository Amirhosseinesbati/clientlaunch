"""Workspace-scoped client portal branding; additive and reversible."""
from alembic import op
from apps.api.models import WorkspaceBrand

revision = "0004_workspace_brand"
down_revision = "0003_project_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    WorkspaceBrand.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    WorkspaceBrand.__table__.drop(bind=op.get_bind())
