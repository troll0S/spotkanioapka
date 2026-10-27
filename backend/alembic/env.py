"""Konfiguracja Alembica.

Adres bazy bierzemy z aplikacji, a nie z alembic.ini — dzięki temu migracje
i serwer zawsze patrzą na ten sam plik, także w kontenerze.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import DATABASE_URL
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    # disable_existing_loggers=False jest tu kluczowe. Domyślnie fileConfig
    # wycisza wszystkie loggery skonfigurowane wcześniej — a migracje biegną
    # przy starcie aplikacji, więc uvicorn i logi aplikacji milkną na dobre.
    # Przy diagnozowaniu problemu z przeglądarką brak logów dostępu boli.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite nie umie ALTER TABLE w pełnym zakresie — batch mode
            # przepisuje tabelę. Bez tego zmiana kolumny w K2+ się wywali.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
