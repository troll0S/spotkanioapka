"""Archiwum sesji — dostęp ponad sesjami, więc za osobnym logowaniem."""

import pytest
from fastapi.testclient import TestClient

from app import admin_auth, ratelimit
from app.db import engine
from app.main import app
from app.models import Base

LOGIN = "admin"
HASLO = "Test-Haslo1!"


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    admin_auth.clear()
    ratelimit.failed_auth.clear()
    ratelimit.joins.clear()
    yield TestClient(app)
    Base.metadata.drop_all(engine)
    admin_auth.clear()
    ratelimit.failed_auth.clear()


@pytest.fixture()
def naglowki(client):
    res = client.post("/api/admin/login", json={"login": LOGIN, "password": HASLO})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _sesja(client, nazwa="Wakacje"):
    host = client.post("/api/session", json={"name": nazwa, "login": LOGIN, "password": HASLO}).json()
    client.post(f"/api/session/{host['code']}/join", json={"display_name": "Ania"})
    return host


# ── logowanie ───────────────────────────────────────────────────────────────


def test_zle_haslo_nie_daje_tokenu(client):
    res = client.post("/api/admin/login", json={"login": LOGIN, "password": "nie-to"})
    assert res.status_code == 401


def test_archiwum_wymaga_logowania(client):
    """Lista wszystkich spotkań to jedyne miejsce widoczne spoza sesji —
    przez publiczny adres tunelu wyciekłoby komuś bez żadnego kodu."""
    assert client.get("/api/admin/sessions").status_code == 401


def test_zmyslony_token_nie_dziala(client):
    res = client.get("/api/admin/sessions", headers={"Authorization": "Bearer bzdura"})
    assert res.status_code == 401


def test_wylogowanie_uniewaznia_token(client, naglowki):
    assert client.get("/api/admin/sessions", headers=naglowki).status_code == 200
    assert client.post("/api/admin/logout", headers=naglowki).status_code == 200
    assert client.get("/api/admin/sessions", headers=naglowki).status_code == 401


def test_zgadywanie_hasla_do_archiwum_jest_limitowane(client):
    for _ in range(ratelimit.failed_auth.limit):
        client.post("/api/admin/login", json={"login": LOGIN, "password": "zle"})

    res = client.post("/api/admin/login", json={"login": LOGIN, "password": "zle"})
    assert res.status_code == 429


# ── lista ───────────────────────────────────────────────────────────────────


def test_lista_zawiera_sesje_z_licznikami(client, naglowki):
    host = _sesja(client, "Plany na wiosnę")

    lista = client.get("/api/admin/sessions", headers=naglowki).json()
    wpis = next(s for s in lista if s["code"] == host["code"])

    assert wpis["name"] == "Plany na wiosnę"
    assert wpis["participants"] == 1, "host nie liczy się jako uczestnik"
    assert wpis["isActive"] is True


def test_najnowsze_sesje_na_gorze(client, naglowki):
    _sesja(client, "Pierwsza")
    druga = _sesja(client, "Druga")

    lista = client.get("/api/admin/sessions", headers=naglowki).json()
    assert lista[0]["code"] == druga["code"]


# ── podgląd ─────────────────────────────────────────────────────────────────


def test_podglad_pokazuje_zawartosc_sesji(client, naglowki):
    host = _sesja(client)
    with client.websocket_connect(
        f"/ws/session/{host['code']}?token={host['token']}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "host.advance"})
        ws.receive_json()

    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Bartek"}
    ).json()
    with client.websocket_connect(
        f"/ws/session/{host['code']}?token={gosc['token']}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "idea.create", "payload": {"title": "Kajaki"}})
        ws.receive_json()

    szczegoly = client.get(f"/api/admin/sessions/{host['code']}", headers=naglowki).json()

    assert szczegoly["name"] == "Wakacje"
    assert [i["title"] for i in szczegoly["ideas"]] == ["Kajaki"]
    assert szczegoly["ideas"][0]["author"] == "Bartek"
    assert szczegoly["canExport"] is False, "sesja wciąż trwa"


def test_podglad_nieistniejacej_sesji(client, naglowki):
    assert client.get("/api/admin/sessions/ZZZZZZ", headers=naglowki).status_code == 404


def test_podglad_wymaga_logowania(client):
    host = _sesja(client)
    assert client.get(f"/api/admin/sessions/{host['code']}").status_code == 401


def test_zamknieta_sesja_pozwala_pobrac(client, naglowki):
    host = _sesja(client)
    with client.websocket_connect(
        f"/ws/session/{host['code']}?token={host['token']}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "host.abort"})
        ws.receive_json()

    szczegoly = client.get(f"/api/admin/sessions/{host['code']}", headers=naglowki).json()

    assert szczegoly["isActive"] is False
    assert szczegoly["canExport"] is True
    assert szczegoly["exportBase"].endswith("/export")


# ── usuwanie ────────────────────────────────────────────────────────────────


def test_usuniecie_sesji_zabiera_wszystko(client, naglowki):
    host = _sesja(client)

    res = client.delete(f"/api/admin/sessions/{host['code']}", headers=naglowki)
    assert res.status_code == 204

    assert client.get(f"/api/session/{host['code']}").status_code == 404
    lista = client.get("/api/admin/sessions", headers=naglowki).json()
    assert all(s["code"] != host["code"] for s in lista)


def test_usuniecie_wymaga_logowania(client):
    host = _sesja(client)
    assert client.delete(f"/api/admin/sessions/{host['code']}").status_code == 401
    assert client.get(f"/api/session/{host['code']}").status_code == 200
