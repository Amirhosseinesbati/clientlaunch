"""Store the approved per-service Drive folder tree.

Revision ID: 0003_project_folders
Revises: 0002_task_cards
"""

from alembic import op

from apps.api.models import ProjectFolder

revision = "0003_project_folders"
down_revision = "0002_task_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ProjectFolder.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    ProjectFolder.__table__.drop(bind=op.get_bind())
