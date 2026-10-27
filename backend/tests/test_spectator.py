"""Widok widza — podgląd tylko do odczytu, bez tokenu.

Istnieje dla trybu zdalnego: etapy 2, 3 i 5 dzieją się na ekranie hosta,
którego nikt poza laptopem nie widzi.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app
from app.models import Base

LOGIN = "admin"
HASLO = "Test-Haslo1!"


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    yield TestClient(app)
    Base.metadata.drop_all(engine)


@pytest.fixture()
def sesja(client):
    host = client.post("/api/session", json={"name": "Wakacje", "login": LOGIN, "password": HASLO}).json()
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Ania"}
    ).json()
    return host, gosc


def _sciezka(code: str) -> str:
    return f"/ws/session/{code}?spectator=true"


def test_widz_laczy_sie_bez_tokenu(client, sesja):
    host, _ = sesja

    with client.websocket_connect(_sciezka(host["code"])) as ws:
        wiadomosc = ws.receive_json()

    assert wiadomosc["type"] == "state"
    assert wiadomosc["payload"]["session"]["status"] == "LOBBY"


def test_widz_nie_ma_tozsamosci_ani_sterowania(client, sesja):
    host, _ = sesja

    with client.websocket_connect(_sciezka(host["code"])) as ws:
        snap = ws.receive_json()["payload"]

    assert snap["you"] is None
    assert "host" not in snap, "widz nie może dostać sekcji sterującej"


def test_widz_nie_moze_nic_zrobic(client, sesja):
    """Nie chodzi o ukryte przyciski — pętla widza nie przyjmuje poleceń."""
    host, _ = sesja

    with client.websocket_connect(_sciezka(host["code"])) as ws:
        ws.receive_json()
        ws.send_json({"type": "host.advance"})
        odpowiedz = ws.receive_json()

    assert odpowiedz["type"] == "error"
    assert "tylko do odczytu" in odpowiedz["payload"]["text"]

    assert client.get(f"/api/session/{host['code']}").json()["status"] == "LOBBY"


def test_widz_nie_dodaje_pomyslow(client, sesja):
    host, _ = sesja

    with client.websocket_connect(_sciezka(host["code"])) as ws:
        ws.receive_json()
        ws.send_json({"type": "idea.create", "payload": {"title": "Podstęp"}})
        odpowiedz = ws.receive_json()

    assert odpowiedz["type"] == "error"


def test_widz_widzi_przebieg_sesji_na_zywo(client, sesja):
    """Sedno widoku: to, co dzieje się u hosta, dociera do widza."""
    host, _ = sesja

    with client.websocket_connect(_sciezka(host["code"])) as ws_widz:
        ws_widz.receive_json()

        with client.websocket_connect(
            f"/ws/session/{host['code']}?token={host['token']}"
        ) as ws_host:
            ws_host.receive_json()
            ws_host.send_json({"type": "host.advance"})
            ws_host.receive_json()

            snap = _stan_gdy(ws_widz, lambda p: p["session"]["status"] == "COLLECTING")

    assert snap["session"]["statusLabel"].startswith("Etap 1")


def test_widz_nie_liczy_sie_do_glosujacych(client, sesja):
    """Widz nie jest uczestnikiem — nie może przesuwać mianownika liczników."""
    host, _ = sesja

    with client.websocket_connect(
        f"/ws/session/{host['code']}?token={host['token']}"
    ) as ws_host:
        snap = ws_host.receive_json()["payload"]
        przed = snap["counts"]

        with client.websocket_connect(_sciezka(host["code"])) as ws_widz:
            ws_widz.receive_json()
            snap = _stan_gdy(ws_host, lambda p: p["counts"]["spectators"] == 1)

    assert snap["counts"]["voting"] == przed["voting"]
    assert snap["counts"]["total"] == przed["total"]
    assert snap["counts"]["spectators"] == 1


def test_zamknieta_sesja_nie_jest_pokazywana_anonimowo(client, sesja):
    """Adres tunelu bywa aktywny dłużej niż spotkanie."""
    host, _ = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.abort"})
        _stan_gdy(ws, lambda p: p["session"]["status"] == "CLOSED")

    with pytest.raises(Exception):
        with client.websocket_connect(_sciezka(host["code"])) as ws:
            ws.receive_json()


def test_uczestnik_z_tokenem_wciaz_widzi_zamknieta_sesje(client, sesja):
    """Zamknięcie odcina anonimowy podgląd, ale nie tych, którzy tam byli."""
    host, gosc = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.abort"})
        _stan_gdy(ws, lambda p: p["session"]["status"] == "CLOSED")

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        snap = ws.receive_json()["payload"]

    assert snap["session"]["status"] == "CLOSED"


def test_nieistniejaca_sesja_zamyka_podglad(client):
    with pytest.raises(Exception):
        with client.websocket_connect(_sciezka("ZZZZZZ")) as ws:
            ws.receive_json()


def _stan_gdy(ws, warunek, proby: int = 8) -> dict:
    for _ in range(proby):
        wiadomosc = ws.receive_json()
        if wiadomosc["type"] == "state" and warunek(wiadomosc["payload"]):
            return wiadomosc["payload"]
    raise AssertionError("nie doczekano się snapshotu spełniającego warunek")
