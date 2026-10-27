"""K9a: konta administratorów zamiast jednego hasła

Revision ID: 0008
Revises: 0007
Create Date: K9a

Jedno wspólne hasło przestaje wystarczać, gdy spotkania prowadzi kilka osób:
zmiana dla jednej odcina wszystkie pozostałe, a po sesji nie wiadomo, kto ją
prowadził. Zamiast hasła — konta z loginem.

`sessions.admin_password_hash` znika. Trzymaliśmy tam zamrożony hash, żeby
zmiana wspólnego hasła nie odcięła dostępu do archiwum; konta rozwiązują to
lepiej, bo same w sobie są trwałe. W jego miejsce wchodzi `created_by` —
informacja, która naprawdę się przydaje.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=40), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_users_login", "admin_users", ["login"], unique=True)

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("created_by", sa.String(length=40), nullable=True))
        batch.drop_column("admin_password_hash")


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        # Sesje sprzed kont nie mają do czego wrócić — pusty hash oznacza
        # „żadne hasło nie pasuje", co jest bezpieczniejsze niż zgadywanie.
        batch.add_column(
            sa.Column("admin_password_hash", sa.String(length=255), nullable=False, server_default="")
        )
        batch.drop_column("created_by")

    op.drop_index("ix_admin_users_login", table_name="admin_users")
    op.drop_table("admin_users")
