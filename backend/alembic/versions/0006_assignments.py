"""K6a: etap 5 — przydział wykonawców i zatwierdzanie wydarzeń

Revision ID: 0006
Revises: 0005
Create Date: K6a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idea_id", sa.Integer(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_plans_idea_id", "event_plans", ["idea_id"], unique=True)

    op.create_table(
        "event_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idea_id", sa.Integer(), nullable=False),
        # Puste dla osób spoza sesji — „Marek z pracy", „tata".
        sa.Column("participant_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idea_id", "name", name="uq_assignment_name"),
    )
    op.create_index("ix_event_assignments_idea_id", "event_assignments", ["idea_id"])

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(
            sa.Column("assignment_index", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("assignment_index")

    op.drop_index("ix_event_assignments_idea_id", table_name="event_assignments")
    op.drop_table("event_assignments")
    op.drop_index("ix_event_plans_idea_id", table_name="event_plans")
    op.drop_table("event_plans")
