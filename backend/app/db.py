"""Połączenie z bazą.

SQLite jest tu świadomym wyborem: jeden host, maks. 30 telefonów, brak zapisów
z wielu procesów. Postgres byłby narzutem bez korzyści. Dostęp idzie przez
SQLAlchemy, więc przeniesienie do chmury to w razie czego zmiana adresu.

Zapytania wykonujemy synchronicznie także w obsłudze WebSocketów. Przy tej
skali pojedyncze zapytanie to ułamek milisekundy — blokada pętli zdarzeń jest
nieodczuwalna, a kod pozostaje czytelny i łatwy do debugowania.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import config

config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{config.DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    # SQLite domyślnie zabrania użycia połączenia w innym wątku niż utworzone,
    # a uvicorn obsługuje żądania w puli wątków.
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL: czytanie nie blokuje pisania. Przy telefonach odpytujących stan
    # równolegle z zapisami hosta to zauważalna różnica.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[DbSession]:
    """Zależność FastAPI — sesja bazy na czas jednego żądania."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
