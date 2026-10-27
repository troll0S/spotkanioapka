"""Przepływ dołączania: zakładanie sesji, goście, reconnect, awans admina."""

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app
from app.models import Base

LOGIN = "admin"
HASLO = "Test-Haslo1!"


@pytest.fixture()
def client():
    # TestClient użyty bez menedżera kontekstu nie uruchamia lifespanu,
    # więc migracje się nie odpalają — tabele zakłada tu fixture.
    Base.metadata.create_all(engine)
    yield TestClient(app)
    Base.metadata.drop_all(engine)


def _zaloz_sesje(client, nazwa="Wakacje"):
    res = client.post("/api/session", json={"name": nazwa, "login": LOGIN, "password": HASLO})
    assert res.status_code == 201, res.text
    return res.json()


def test_zakladanie_sesji_tworzy_hosta_bez_prawa_glosu(client):
    host = _zaloz_sesje(client)

    assert host["role"] == "HOST"
    assert host["is_voting"] is False
    assert len(host["code"]) == 6


def test_zle_haslo_nie_zaklada_sesji(client):
    res = client.post("/api/session", json={"name": "X", "login": LOGIN, "password": "nie-to"})
    assert res.status_code == 401


def test_gosc_dolacza_i_dostaje_token(client):
    host = _zaloz_sesje(client)
    res = client.post(f"/api/session/{host['code']}/join", json={"display_name": "Ania"})

    assert res.status_code == 200
    gosc = res.json()
    assert gosc["role"] == "GUEST"
    assert gosc["is_voting"] is True
    assert gosc["token"] != host["token"]


def test_powrot_z_tokenem_to_ta_sama_osoba(client):
    """Odświeżenie strony nie może tworzyć drugiego uczestnika."""
    host = _zaloz_sesje(client)
    pierwszy = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Ania"}
    ).json()

    drugi = client.post(
        f"/api/session/{host['code']}/join",
        json={"display_name": "cokolwiek-innego", "token": pierwszy["token"]},
    ).json()

    assert drugi["participant_id"] == pierwszy["participant_id"]
    assert drugi["display_name"] == "Ania"

    info = client.get(f"/api/session/{host['code']}").json()
    assert info["participants"] == 2, "host + Ania, bez duplikatu"


def test_zajety_nick_jest_odrzucany(client):
    host = _zaloz_sesje(client)
    client.post(f"/api/session/{host['code']}/join", json={"display_name": "Ania"})
    res = client.post(f"/api/session/{host['code']}/join", json={"display_name": "Ania"})

    assert res.status_code == 409


def test_awans_na_admina_nie_dodaje_glosu(client):
    """Admin dołącza jak każdy, loguje się hasłem i przestaje głosować."""
    host = _zaloz_sesje(client)
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Szef"}
    ).json()

    res = client.post(
        f"/api/session/{host['code']}/promote",
        json={"token": gosc["token"], "login": LOGIN, "password": HASLO},
    )

    assert res.status_code == 200
    admin = res.json()
    assert admin["role"] == "ADMIN"
    assert admin["is_voting"] is False
    assert admin["participant_id"] == gosc["participant_id"], "ta sama tożsamość"


def test_awans_z_wlaczonym_glosowaniem(client):
    host = _zaloz_sesje(client)
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Szef"}
    ).json()

    admin = client.post(
        f"/api/session/{host['code']}/promote",
        json={
            "token": gosc["token"],
            "login": LOGIN,
            "password": HASLO,
            "is_voting": True,
        },
    ).json()

    assert admin["is_voting"] is True


def test_awans_ze_zlym_haslem_odrzucony(client):
    host = _zaloz_sesje(client)
    gosc = client.post(
        f"/api/session/{host['code']}/join", json={"display_name": "Ktos"}
    ).json()

    res = client.post(
        f"/api/session/{host['code']}/promote",
        json={"token": gosc["token"], "login": LOGIN, "password": "zle"},
    )
    assert res.status_code == 401


def test_nieistniejaca_sesja_to_404(client):
    assert client.get("/api/session/ZZZZZZ").status_code == 404


def test_brakujacy_plik_daje_404_a_nie_strony(client):
    """Regresja: fallback SPA nie może udawać, że plik istnieje.

    Przeglądarka z zapamiętanym starym index.html prosi o plik JS o nieaktualnym
    hashu. Gdyby dostała HTML z kodem 200, nie wykonałaby żadnego skryptu
    i strona ładowałaby się w nieskończoność bez śladu błędu.
    """
    res = client.get("/assets/index-STARY-HASH.js")

    assert res.status_code == 404
    assert "text/html" not in res.headers.get("content-type", "")


def test_sciezki_routingu_wciaz_daja_strone(client):
    """Ale /host i /join to ścieżki frontendu — te muszą zwracać index.html."""
    for path in ("/host", "/join", "/cokolwiek/glebiej"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert "text/html" in res.headers["content-type"], path


def test_index_nie_jest_zapamietywany(client):
    """index.html wskazuje na aktualne hashe — musi być rewalidowany."""
    res = client.get("/")
    assert res.headers.get("cache-control") == "no-cache"


def test_pliki_z_hashem_moga_lezec_w_cache_dowolnie_dlugo(client):
    """Nazwa z hashem zmienia się przy każdej zmianie treści, więc cache jest bezpieczny."""
    res = client.get("/assets/index-TEST.js")

    assert res.status_code == 200
    assert "immutable" in res.headers.get("cache-control", "")


def test_kod_qr_jest_svg(client):
    host = _zaloz_sesje(client)
    res = client.get(f"/api/session/{host['code']}/qr.svg")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in res.content
