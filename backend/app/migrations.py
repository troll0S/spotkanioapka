"""Uruchamianie migracji przy starcie aplikacji.

Dzięki temu `docker compose up` wystarcza — nie ma osobnego kroku, o którym
można zapomnieć przed sesją.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger("spotkanioapka.db")

BACKEND_DIR = Path(__file__).resolve().parent.parent


def upgrade_to_head() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    log.info("Migracje bazy: aktualne")
