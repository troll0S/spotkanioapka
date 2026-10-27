"""WebSocket: snapshot po połączeniu i sterowanie zarezerwowane dla hosta."""

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


def test_po_polaczeniu_przychodzi_snapshot(client, sesja):
    host, _ = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        wiadomosc = ws.receive_json()

    assert wiadomosc["type"] == "state"
    assert wiadomosc["payload"]["session"]["status"] == "LOBBY"
    assert wiadomosc["payload"]["you"]["role"] == "HOST"


def test_host_przesuwa_sesje_do_nastepnego_etapu(client, sesja):
    host, _ = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.advance"})
        stan = _nastepny_stan(ws)

    assert stan["payload"]["session"]["status"] == "COLLECTING"


def test_gosc_nie_moze_sterowac_sesja(client, sesja):
    """Najważniejszy test bezpieczeństwa w K1 — uprawnienia po stronie serwera."""
    host, gosc = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.advance"})
        odpowiedz = ws.receive_json()

    assert odpowiedz["type"] == "error"

    info = client.get(f"/api/session/{host['code']}").json()
    assert info["status"] == "LOBBY", "stan sesji nie mógł się zmienić"


def test_host_przerywa_sesje_z_lobby(client, sesja):
    host, _ = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.abort"})
        stan = _nastepny_stan(ws)

    assert stan["payload"]["session"]["status"] == "CLOSED"
    assert stan["payload"]["session"]["isActive"] is False


def test_zly_token_zamyka_polaczenie(client, sesja):
    host, _ = sesja
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/session/{host['code']}?token=nieistniejacy") as ws:
            ws.receive_json()


def test_ping_dostaje_pong(client, sesja):
    """Podtrzymanie połączenia — bez tego tunel w trybie zdalnym je zamknie."""
    host, _ = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_obecnosc_widoczna_dla_hosta(client, sesja):
    host, gosc = sesja
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws_host:
        ws_host.receive_json()
        with client.websocket_connect(
            f"/ws/session/{host['code']}?token={gosc['token']}"
        ) as ws_gosc:
            ws_gosc.receive_json()
            stan = _nastepny_stan(ws_host)

    podlaczeni = {p["displayName"] for p in stan["payload"]["participants"] if p["connected"]}
    assert "Ania" in podlaczeni


def _do_etapu_1(client, host):
    """Przestawia sesję na COLLECTING przez host.advance, jak w realnym użyciu."""
    with client.websocket_connect(f"/ws/session/{host['code']}?token={host['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "host.advance"})
        _nastepny_stan(ws)


def test_gosc_dodaje_pomysl_przez_ws(client, sesja):
    host, gosc = sesja
    _do_etapu_1(client, host)

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "idea.create", "payload": {"title": "Wyjazd w góry"}})
        stan = _nastepny_stan(ws)

    assert [i["title"] for i in stan["payload"]["ideas"]] == ["Wyjazd w góry"]
    assert stan["payload"]["you"]["ideaCount"] == 1


def test_gosc_nie_przemyci_wpisu_specjalnego(client, sesja):
    """Podniesiona flaga w ładunku nie wystarczy — decyduje rola po stronie serwera."""
    host, gosc = sesja
    _do_etapu_1(client, host)

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "idea.create", "payload": {"title": "Nie do odrzucenia", "isSpecial": True}}
        )
        odpowiedz = ws.receive_json()

    assert odpowiedz["type"] == "error"
    assert "administrator" in odpowiedz["payload"]["text"]


def test_gosc_nie_usunie_cudzego_pomyslu_przez_ws(client, sesja):
    host, gosc = sesja
    drugi = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Bartek"}
    ).json()
    _do_etapu_1(client, host)

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "idea.create", "payload": {"title": "Moje"}})
        idea_id = _nastepny_stan(ws)["payload"]["ideas"][0]["id"]

    with client.websocket_connect(f"/ws/session/{host['code']}?token={drugi['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "idea.delete", "payload": {"id": idea_id}})
        odpowiedz = ws.receive_json()

    assert odpowiedz["type"] == "error"
    assert "tylko swoje" in odpowiedz["payload"]["text"]


def test_pomysl_dociera_do_innych_telefonow_na_zywo(client, sesja):
    """Sedno etapu 1 — każdy widzi listę rosnącą w czasie rzeczywistym."""
    host, gosc = sesja
    drugi = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Bartek"}
    ).json()
    _do_etapu_1(client, host)

    with client.websocket_connect(f"/ws/session/{host['code']}?token={drugi['token']}") as ws_bartek:
        ws_bartek.receive_json()

        with client.websocket_connect(
            f"/ws/session/{host['code']}?token={gosc['token']}"
        ) as ws_ania:
            ws_ania.receive_json()
            ws_ania.send_json({"type": "idea.create", "payload": {"title": "Kajaki"}})
            ws_ania.receive_json()

            stan = _stan_gdy(ws_bartek, lambda p: p["ideaCounts"]["total"] == 1)

    assert "Kajaki" in [i["title"] for i in stan["payload"]["ideas"]]


def test_brama_etapu_dziala_mimo_dlugo_otwartego_polaczenia(client, sesja):
    """Regresja: połączenie otwarte od LOBBY nie może pracować na starym stanie.

    Gość łączy się w poczekalni i nie rusza połączenia. Host w tym czasie
    przechodzi dwa etapy. Gdyby sesja bazy żyła tyle, co połączenie, gość
    widziałby wciąż COLLECTING i dopisałby pomysł po zamknięciu etapu.
    """
    host, gosc = sesja

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws_gosc:
        ws_gosc.receive_json()

        with client.websocket_connect(
            f"/ws/session/{host['code']}?token={host['token']}"
        ) as ws_host:
            ws_host.receive_json()
            ws_host.send_json({"type": "host.advance"})
            _stan_gdy(ws_host, lambda p: p["session"]["status"] == "COLLECTING")
            ws_host.send_json({"type": "host.advance"})
            _stan_gdy(ws_host, lambda p: p["session"]["status"] == "SWIPING")

        ws_gosc.send_json({"type": "idea.create", "payload": {"title": "Za późno"}})
        tekst = _blad(ws_gosc)

    assert "nie jest aktywny" in tekst

    info = client.get(f"/api/session/{host['code']}").json()
    assert info["status"] == "SWIPING"


def test_awans_admina_dziala_na_otwartym_polaczeniu(client, sesja):
    """Regresja: awans przez REST musi być widoczny dla trwającego WebSocketu.

    Admin loguje się hasłem, mając już otwarte połączenie jako gość. Gdyby rola
    była zapamiętana na czas połączenia, wpis specjalny zostałby odrzucony
    i trzeba by przeładować stronę.
    """
    host, gosc = sesja
    _do_etapu_1(client, host)

    with client.websocket_connect(f"/ws/session/{host['code']}?token={gosc['token']}") as ws:
        ws.receive_json()

        awans = client.post(
            f"/api/session/{host['code']}/promote",
            json={"token": gosc["token"], "login": LOGIN, "password": HASLO},
        )
        assert awans.status_code == 200

        ws.send_json(
            {"type": "idea.create", "payload": {"title": "Urodziny babci", "isSpecial": True}}
        )
        stan = _stan_gdy(ws, lambda p: p["ideaCounts"]["special"] == 1)

    assert stan["payload"]["you"]["role"] == "ADMIN"
    assert stan["payload"]["ideas"][0]["isSpecial"] is True


def _blad(ws, proby: int = 8) -> str:
    """Treść pierwszego komunikatu o błędzie, pomijając snapshoty."""
    for _ in range(proby):
        wiadomosc = ws.receive_json()
        if wiadomosc["type"] == "error":
            return wiadomosc["payload"]["text"]
    raise AssertionError("oczekiwano błędu, nie przyszedł")


def _nastepny_stan(ws, proby: int = 5) -> dict:
    """Pierwszy snapshot z kolejki, pomijając komunikaty poboczne."""
    for _ in range(proby):
        wiadomosc = ws.receive_json()
        if wiadomosc["type"] == "state":
            return wiadomosc
    raise AssertionError("nie doczekano się snapshotu")


def _stan_gdy(ws, warunek, proby: int = 8) -> dict:
    """Snapshot spełniający warunek.

    Potrzebne, gdy w kolejce czeka więcej niż jeden snapshot: dołączenie
    kolejnego telefonu i dodanie pomysłu to dwa osobne broadcasty, a test
    interesuje dopiero ten drugi. Czekanie na warunek zamiast na n-tą
    wiadomość nie psuje się, gdy liczba broadcastów się zmieni.
    """
    for _ in range(proby):
        wiadomosc = ws.receive_json()
        if wiadomosc["type"] == "state" and warunek(wiadomosc["payload"]):
            return wiadomosc
    raise AssertionError("nie doczekano się snapshotu spełniającego warunek")
