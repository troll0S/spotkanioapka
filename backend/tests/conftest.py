import os
import tempfile
from pathlib import Path

import pytest

# Baza testowa musi być ustawiona ZANIM zaimportuje się app.db — moduł tworzy
# silnik na poziomie importu.
#
# Przypisujemy na twardo, a NIE przez setdefault: w kontenerze DB_PATH już
# istnieje i wskazuje prawdziwą bazę. Testy robią create_all/drop_all, więc
# setdefault oznaczałby kasowanie tabel z realnej sesji.
_TMP = Path(tempfile.mkdtemp(prefix="spotkanioapka-test-"))
os.environ["DB_PATH"] = str(_TMP / "test.db")
os.environ["ADMIN_PASSWORD"] = "Test-Haslo1!"

# Atrapa zbudowanego frontendu. Obraz deweloperski go nie zawiera (w trybie dev
# serwuje go Vite), a testy serwowania statyków muszą mieć co serwować.
_STATIC = _TMP / "static"
(_STATIC / "assets").mkdir(parents=True, exist_ok=True)
(_STATIC / "index.html").write_text(
    '<!doctype html><script type="module" src="/assets/index-TEST.js"></script>',
    encoding="utf-8",
)
(_STATIC / "assets" / "index-TEST.js").write_text("console.log('test')", encoding="utf-8")
os.environ["STATIC_DIR"] = str(_STATIC)

from app import ratelimit  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402

# Zwłoka po błędnym haśle jest celowa w produkcji, ale w testach dokładałaby
# kilkanaście sekund do przebiegu. Limitów to nie dotyczy — te są testowane.
ratelimit.FAILED_AUTH_DELAY = 0
from app.models import Base, Participant, Role, Session  # noqa: E402
from app.security import hash_password, new_token  # noqa: E402
from app.state_machine import SessionStatus  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def sample_session(db):
    """Sesja z hostem, adminem i dwoma gośćmi — typowy układ ról."""
    session = Session(
        code="ABCDEF",
        name="Testowa",
        status=SessionStatus.LOBBY.value,
        created_by="admin",
    )
    db.add(session)
    db.flush()

    db.add_all(
        [
            Participant(
                session_id=session.id,
                display_name="Ekran",
                token=new_token(),
                role=Role.HOST.value,
                is_voting=False,
            ),
            Participant(
                session_id=session.id,
                display_name="Admin",
                token=new_token(),
                role=Role.ADMIN.value,
                is_voting=False,
            ),
            Participant(
                session_id=session.id,
                display_name="Ania",
                token=new_token(),
                role=Role.GUEST.value,
                is_voting=True,
            ),
            Participant(
                session_id=session.id,
                display_name="Bartek",
                token=new_token(),
                role=Role.GUEST.value,
                is_voting=True,
            ),
        ]
    )
    db.commit()
    return session
