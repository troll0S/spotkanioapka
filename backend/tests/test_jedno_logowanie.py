"""Jedno logowanie na całą aplikację.

Zalogowany administrator nie powinien podawać danych drugi raz tylko dlatego,
że przeszedł z archiwum na ekran prowadzącego.
"""

import pytest
from fastapi.testclient import TestClient

from app import accounts, admin_auth, ratelimit
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
    yield TestClient(app)
    Base.metadata.drop_all(engine)
    admin_auth.clear()
    ratelimit.failed_auth.clear()


def zaloguj(client, login=LOGIN, haslo=HASLO) -> dict:
    res = client.post("/api/admin/login", json={"login": login, "password": haslo})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


# ── zakładanie sesji ────────────────────────────────────────────────────────


def test_zalogowany_zaklada_sesje_bez_podawania_hasla(client):
    naglowki = zaloguj(client)

    res = client.post("/api/session", json={"name": "Wakacje"}, headers=naglowki)

    assert res.status_code == 201
    assert res.json()["role"] == "HOST"


def test_sesja_z_tokenu_pamieta_wlasciwe_konto(client):
    naglowki = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia = zaloguj(client, "kasia", "Dlugie-Haslo1!")

    host = client.post("/api/session", json={"name": "Sesja Kasi"}, headers=kasia).json()
    szczegoly = client.get(f"/api/admin/sessions/{host['code']}", headers=naglowki).json()

    assert szczegoly["createdBy"] == "kasia"


def test_bez_tokenu_i_bez_hasla_nie_da_sie_zalozyc(client):
    zaloguj(client)  # wymuszamy istnienie konta
    res = client.post("/api/session", json={"name": "Wakacje"})

    assert res.status_code == 401
    assert "Zaloguj" in res.json()["detail"]


def test_login_i_haslo_wciaz_dzialaja(client):
    """Stara droga zostaje — ktoś może wejść wprost na ekran prowadzącego."""
    zaloguj(client)
    res = client.post(
        "/api/session", json={"name": "Wakacje", "login": LOGIN, "password": HASLO}
    )
    assert res.status_code == 201


def test_zmyslony_token_nie_wpuszcza(client):
    zaloguj(client)
    res = client.post(
        "/api/session",
        json={"name": "Wakacje"},
        headers={"Authorization": "Bearer bzdura"},
    )
    assert res.status_code == 401


# ── konto odebrane w trakcie ────────────────────────────────────────────────


def test_wylaczone_konto_traci_dostep_mimo_waznego_tokenu(client):
    """Token żyje osiem godzin — wyłączenie konta musi działać natychmiast."""
    naglowki = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia = zaloguj(client, "kasia", "Dlugie-Haslo1!")
    assert client.post("/api/session", json={"name": "A"}, headers=kasia).status_code == 201

    client.patch("/api/admin/users/kasia", json={"is_active": False}, headers=naglowki)

    res = client.post("/api/session", json={"name": "B"}, headers=kasia)
    assert res.status_code == 401


def test_usuniete_konto_traci_dostep(client, db):
    naglowki = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia = zaloguj(client, "kasia", "Dlugie-Haslo1!")

    # Usuwamy wprost w bazie, z pominięciem unieważniania tokenów — chcemy
    # sprawdzić, czy sam endpoint broni się przed tokenem widmo.
    accounts.delete(db, accounts.by_login(db, "kasia"))

    res = client.post("/api/session", json={"name": "B"}, headers=kasia)
    assert res.status_code == 401
    assert "straciło dostęp" in res.json()["detail"]


# ── awans w sesji ───────────────────────────────────────────────────────────


def test_zalogowany_awansuje_sie_bez_podawania_hasla(client):
    naglowki = zaloguj(client)
    host = client.post("/api/session", json={"name": "Wakacje"}, headers=naglowki).json()
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Szef"}
    ).json()

    res = client.post(
        f"/api/session/{host['code']}/promote",
        json={"token": gosc["token"]},
        headers=naglowki,
    )

    assert res.status_code == 200
    assert res.json()["role"] == "ADMIN"


def test_awans_bez_niczego_odrzucony(client):
    naglowki = zaloguj(client)
    host = client.post("/api/session", json={"name": "Wakacje"}, headers=naglowki).json()
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Szef"}
    ).json()

    res = client.post(
        f"/api/session/{host['code']}/promote", json={"token": gosc["token"]}
    )
    assert res.status_code == 401
