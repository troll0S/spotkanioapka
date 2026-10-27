"""K8: pomysł może przeżyć swojego autora

Revision ID: 0007
Revises: 0006
Create Date: K8

Panel admina pozwala usunąć uczestnika — na przykład kogoś, kto dołączył
dwa razy. Dopóki autorstwo było wymagane, usunięcie osoby zabierało ze sobą
wszystkie jej pomysły: jedno kliknięcie kasowało treść, dla której cała
sesja się odbyła.

Po tej zmianie pole autora może być puste. Samo odpięcie pomysłów robi
`admin_ops.remove_participant` tuż przed usunięciem osoby — jawnie, w kodzie,
zamiast chować tę regułę w kluczu obcym.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite nie zmienia kolumny w miejscu — batch_alter_table przepisuje
    # tabelę, odtwarzając ją z odczytanego schematu.
    with op.batch_alter_table("ideas") as batch:
        batch.alter_column("author_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Pomysły bez autora trzeba usunąć — inaczej kolumna nie może wrócić
    # do NOT NULL.
    op.execute("DELETE FROM ideas WHERE author_id IS NULL")
    with op.batch_alter_table("ideas") as batch:
        batch.alter_column("author_id", existing_type=sa.Integer(), nullable=False)
