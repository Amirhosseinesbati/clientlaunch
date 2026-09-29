"""Track task cards and connected sync operations.

Revision ID: 0002_task_cards
Revises: 0001_initial
"""

from alembic import op

from apps.api.models import TaskCard

revision = "0002_task_cards"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    TaskCard.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    TaskCard.__table__.drop(bind=op.get_bind())
