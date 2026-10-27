"""Ograniczanie prób hasła — ma znaczenie dopiero, gdy adres jest publiczny."""

import pytest
from fastapi.testclient import TestClient

from app import ratelimit
from app.db import engine
from app.main import app
from app.models import Base

LOGIN = "admin"
HASLO = "Test-Haslo1!"


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    # Limiter trzyma stan w pamięci procesu — bez czyszczenia testy
    # wpływałyby na siebie nawzajem.
    ratelimit.failed_auth.clear()
    ratelimit.joins.clear()
    yield TestClient(app)
    Base.metadata.drop_all(engine)
    ratelimit.failed_auth.clear()
    ratelimit.joins.clear()


def test_zgadywanie_hasla_zostaje_zablokowane(client):
    for _ in range(ratelimit.failed_auth.limit):
        res = client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "zle"})
        assert res.status_code == 401

    res = client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "zle"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers


def test_blokada_obejmuje_takze_poprawne_haslo(client):
    """Inaczej atakujący sprawdzałby hasło, licząc na trafienie po limicie."""
    for _ in range(ratelimit.failed_auth.limit):
        client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "zle"})

    res = client.post("/api/session", json={"name": "X", "login": LOGIN, "password": HASLO})
    assert res.status_code == 429


def test_udane_logowanie_zeruje_licznik(client):
    for _ in range(ratelimit.failed_auth.limit - 1):
        client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "zle"})

    assert client.post("/api/session", json={"name": "OK", "login": LOGIN, "password": HASLO}).status_code == 201

    # Po wyzerowaniu znów jest pełna pula prób — literówka nie blokuje na długo.
    for _ in range(ratelimit.failed_auth.limit - 1):
        assert (
            client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "zle"}).status_code == 401
        )


def test_awans_admina_tez_jest_limitowany(client):
    host = client.post("/api/session", json={"name": "S", "login": LOGIN, "password": HASLO}).json()
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Ania"}
    ).json()

    for _ in range(ratelimit.failed_auth.limit):
        res = client.post(
            f"/api/session/{host['code']}/promote",
            json={"token": gosc["token"], "login": LOGIN, "password": "zle"},
        )
        assert res.status_code == 401

    res = client.post(
        f"/api/session/{host['code']}/promote",
        json={"token": gosc["token"], "login": LOGIN, "password": "zle"},
    )
    assert res.status_code == 429


def test_dolaczanie_ma_zapas_na_cala_grupe(client):
    """W trybie lokalnym Docker pokazuje wszystkie telefony jako jeden adres.

    Limit musi przepuścić trzydziestoosobową grupę wchodzącą naraz, bo inaczej
    zablokowałby prawdziwe spotkanie.
    """
    host = client.post("/api/session", json={"name": "S", "login": LOGIN, "password": HASLO}).json()

    for i in range(30):
        res = client.post(
            f"/api/session/{host['code']}/join", json={"display_name": f"Osoba{i}"}
        )
        assert res.status_code == 200, f"osoba {i} odbita"


def test_powrot_z_tokenem_nie_zjada_limitu(client):
    """Telefon w słabym zasięgu wraca wiele razy — to nie są nowe dołączenia."""
    host = client.post("/api/session", json={"name": "S", "login": LOGIN, "password": HASLO}).json()
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Ania"}
    ).json()

    for _ in range(ratelimit.joins.limit + 20):
        res = client.post(
            f"/api/session/{host['code']}/join",
            json={"display_name": "Ania", "token": gosc["token"]},
        )
        assert res.status_code == 200


def test_klucz_klienta_bierze_adres_zza_tunelu():
    """Bez tego wszyscy w trybie zdalnym byliby jednym klientem."""
    assert ratelimit.client_key({"cf-connecting-ip": "203.0.113.7"}, "172.19.0.1") == "203.0.113.7"
    assert ratelimit.client_key({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, None) == "203.0.113.7"
    assert ratelimit.client_key({}, "192.168.1.5") == "192.168.1.5"
