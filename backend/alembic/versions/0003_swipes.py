"""K3: głosy uczestników i rozstrzygnięcia hosta

Revision ID: 0003
Revises: 0002
Create Date: K3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "swipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idea_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Jeden głos na pomysł. Nawet gdyby dwa żądania przyszły równocześnie,
        # baza nie wpuści drugiego.
        sa.UniqueConstraint("idea_id", "participant_id", name="uq_swipe_once"),
    )
    op.create_index("ix_swipes_idea_id", "swipes", ["idea_id"])
    op.create_index("ix_swipes_participant_id", "swipes", ["participant_id"])

    op.create_table(
        "host_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idea_id", sa.Integer(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_host_decisions_idea_id", "host_decisions", ["idea_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_host_decisions_idea_id", table_name="host_decisions")
    op.drop_table("host_decisions")
    op.drop_index("ix_swipes_participant_id", table_name="swipes")
    op.drop_index("ix_swipes_idea_id", table_name="swipes")
    op.drop_table("swipes")
