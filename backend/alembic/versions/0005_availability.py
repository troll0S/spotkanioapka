"""K5: deklaracje dostępności

Revision ID: 0005
Revises: 0004
Create Date: K5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "availabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idea_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.String(length=16), nullable=False),
        # Wypełniane dopiero przy korekcie z panelu admina (K8) — żeby dało się
        # odróżnić głos uczestnika od poprawki.
        sa.Column("original_answer", sa.String(length=16), nullable=True),
        sa.Column("edited_by_admin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Sam wiersz jest blokadą: jedna odpowiedź na wydarzenie.
        sa.UniqueConstraint("idea_id", "participant_id", name="uq_availability_once"),
    )
    op.create_index("ix_availabilities_idea_id", "availabilities", ["idea_id"])
    op.create_index("ix_availabilities_participant_id", "availabilities", ["participant_id"])

    # SQLite nie umie pełnego ALTER TABLE — batch_alter_table przepisuje tabelę.
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("availability_order", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("availability_index", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("availability_index")
        batch.drop_column("availability_order")

    op.drop_index("ix_availabilities_participant_id", table_name="availabilities")
    op.drop_index("ix_availabilities_idea_id", table_name="availabilities")
    op.drop_table("availabilities")
