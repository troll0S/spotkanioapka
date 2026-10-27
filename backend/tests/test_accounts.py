"""Konta administratorów i zarządzanie nimi przez superadmina."""

import pytest
from fastapi.testclient import TestClient

from app import accounts, admin_auth, ratelimit
from app.accounts import AccountError
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


def zaloguj(client, login=LOGIN, haslo=HASLO):
    res = client.post("/api/admin/login", json={"login": login, "password": haslo})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}, res.json()


# ── konto startowe ──────────────────────────────────────────────────────────


def test_pierwsze_konto_powstaje_z_env(client):
    """Bez tego nie dałoby się zalogować, żeby założyć pierwsze konto."""
    _, dane = zaloguj(client)

    assert dane["login"] == "admin"
    assert dane["isSuperadmin"] is True


def test_konto_startowe_powstaje_tylko_raz(db):
    """Po założeniu kont zmienne z .env przestają mieć znaczenie."""
    assert accounts.bootstrap(db) is not None
    assert accounts.bootstrap(db) is None
    assert accounts.count(db) == 1


# ── logowanie ───────────────────────────────────────────────────────────────


def test_zly_login_i_zle_haslo_daja_ten_sam_komunikat(client):
    """Inaczej dałoby się sprawdzać, które konta istnieją."""
    zaloguj(client)  # wymuszamy bootstrap

    a = client.post("/api/admin/login", json={"login": "nieistnieje", "password": HASLO})
    b = client.post("/api/admin/login", json={"login": LOGIN, "password": "zle"})

    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_login_jest_niewrazliwy_na_wielkosc_liter(client):
    zaloguj(client)
    res = client.post("/api/admin/login", json={"login": "ADMIN", "password": HASLO})
    assert res.status_code == 200


# ── zakładanie kont ─────────────────────────────────────────────────────────


def test_superadmin_zaklada_konto(client):
    naglowki, _ = zaloguj(client)

    res = client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )

    assert res.status_code == 201
    assert res.json() == {
        "login": "kasia",
        "isSuperadmin": False,
        "isActive": True,
        "createdAt": res.json()["createdAt"],
        "lastLoginAt": None,
    }


def test_nowe_konto_moze_zalozyc_sesje(client):
    """Zwykły admin prowadzi spotkania tak samo jak superadmin."""
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )

    res = client.post(
        "/api/session", json={"name": "Sesja Kasi", "login": "kasia", "password": "Dlugie-Haslo1!"}
    )
    assert res.status_code == 201


def test_sesja_pamieta_kto_ja_zalozyl(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    host = client.post(
        "/api/session", json={"name": "Sesja Kasi", "login": "kasia", "password": "Dlugie-Haslo1!"}
    ).json()

    szczegoly = client.get(f"/api/admin/sessions/{host['code']}", headers=naglowki).json()
    assert szczegoly["createdBy"] == "kasia"


def test_zwykly_admin_nie_zarzadza_kontami(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia, _ = zaloguj(client, "kasia", "Dlugie-Haslo1!")

    assert client.get("/api/admin/users", headers=kasia).status_code == 403
    assert (
        client.post(
            "/api/admin/users",
            json={"login": "ktos", "password": "Dlugie-Haslo1!"},
            headers=kasia,
        ).status_code
        == 403
    )


def test_zwykly_admin_widzi_archiwum(client):
    """Konta różnią się tylko zarządzaniem użytkownikami."""
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia, _ = zaloguj(client, "kasia", "Dlugie-Haslo1!")

    assert client.get("/api/admin/sessions", headers=kasia).status_code == 200


@pytest.mark.parametrize("zly", ["a", "ma spacje", "kasia@dom", "-start", "", "zażółć"])
def test_niepoprawny_login_odrzucony(client, zly):
    naglowki, _ = zaloguj(client)
    res = client.post(
        "/api/admin/users", json={"login": zly, "password": "Dlugie-Haslo1!"}, headers=naglowki
    )
    assert res.status_code in (400, 422)


def test_wielkie_litery_w_loginie_sa_sprowadzane_do_malych(client):
    """Login to identyfikator — „Kasia" i „kasia" muszą być tym samym kontem,
    żeby nie dało się założyć dwóch wyglądających identycznie."""
    naglowki, _ = zaloguj(client)

    res = client.post(
        "/api/admin/users", json={"login": "Kasia", "password": "Dlugie-Haslo1!"}, headers=naglowki
    )

    assert res.status_code == 201
    assert res.json()["login"] == "kasia"


@pytest.mark.parametrize(
    "haslo,brak",
    [
        ("Ab1!", "co najmniej"),
        ("dlugie-haslo1!", "wielką literę"),
        ("DLUGIE-HASLO1!", "małą literę"),
        ("Dlugie-Haslo!", "cyfrę"),
        ("DlugieHaslo1", "znak specjalny"),
        # Spacja nie jest znakiem specjalnym — inaczej wymóg nic by nie dawał.
        ("Dlugie Haslo1", "znak specjalny"),
    ],
)
def test_slabe_haslo_odrzucone_z_wyjasnieniem(client, haslo, brak):
    naglowki, _ = zaloguj(client)
    res = client.post(
        "/api/admin/users", json={"login": "kasia", "password": haslo}, headers=naglowki
    )

    assert res.status_code == 400
    assert brak in res.json()["detail"], res.json()["detail"]


def test_polityka_hasla_obowiazuje_takze_przy_zmianie(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )

    res = client.patch(
        "/api/admin/users/kasia", json={"password": "slabe"}, headers=naglowki
    )
    assert res.status_code == 409
    assert "Hasło musi zawierać" in res.json()["detail"]


def test_konto_startowe_tez_podlega_polityce(db, monkeypatch):
    """Gdyby superadmin z .env omijał wymagania, cała polityka byłaby dekoracją."""
    from app import config

    monkeypatch.setattr(config, "ADMIN_PASSWORD", "slabe")
    assert accounts.bootstrap(db) is None
    assert accounts.count(db) == 0

    monkeypatch.setattr(config, "ADMIN_PASSWORD", "Mocne-Haslo1!")
    assert accounts.bootstrap(db) is not None


def test_duplikat_loginu_odrzucony(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    res = client.post(
        "/api/admin/users",
        json={"login": "KASIA", "password": "Inne-Dlugie1!"},
        headers=naglowki,
    )
    assert res.status_code == 400


# ── zmiany na kontach ───────────────────────────────────────────────────────


def test_zmiana_hasla_uniewaznia_sesje_tego_konta(client):
    """Odebranie dostępu musi działać od razu, nie po ośmiu godzinach."""
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    kasia, _ = zaloguj(client, "kasia", "Dlugie-Haslo1!")
    assert client.get("/api/admin/sessions", headers=kasia).status_code == 200

    client.patch(
        "/api/admin/users/kasia", json={"password": "Nowe-Dlugie1!"}, headers=naglowki
    )

    assert client.get("/api/admin/sessions", headers=kasia).status_code == 401
    zaloguj(client, "kasia", "Nowe-Dlugie1!")


def test_wylaczone_konto_nie_loguje_sie(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    client.patch("/api/admin/users/kasia", json={"is_active": False}, headers=naglowki)

    res = client.post(
        "/api/admin/login", json={"login": "kasia", "password": "Dlugie-Haslo1!"}
    )
    assert res.status_code == 401


def test_wylaczone_konto_nie_zaklada_sesji(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )
    client.patch("/api/admin/users/kasia", json={"is_active": False}, headers=naglowki)

    res = client.post(
        "/api/session", json={"name": "X", "login": "kasia", "password": "Dlugie-Haslo1!"}
    )
    assert res.status_code == 401


def test_usuniecie_konta(client):
    naglowki, _ = zaloguj(client)
    client.post(
        "/api/admin/users",
        json={"login": "kasia", "password": "Dlugie-Haslo1!"},
        headers=naglowki,
    )

    assert client.delete("/api/admin/users/kasia", headers=naglowki).status_code == 204
    loginy = [u["login"] for u in client.get("/api/admin/users", headers=naglowki).json()]
    assert "kasia" not in loginy


def test_nie_da_sie_usunac_wlasnego_konta(client):
    naglowki, _ = zaloguj(client)
    res = client.delete(f"/api/admin/users/{LOGIN}", headers=naglowki)

    assert res.status_code == 409
    assert "własnego" in res.json()["detail"]


# ── ostatni superadmin ──────────────────────────────────────────────────────


def test_ostatniego_superadmina_nie_da_sie_wylaczyc(db):
    """Bez niego nikt nie doda ani nie odbierze kont."""
    konto = accounts.bootstrap(db)

    with pytest.raises(AccountError, match="ostatni aktywny superadmin"):
        accounts.set_active(db, konto, False)


def test_ostatniemu_superadminowi_nie_da_sie_odebrac_uprawnien(db):
    konto = accounts.bootstrap(db)

    with pytest.raises(AccountError, match="ostatni superadmin"):
        accounts.set_superadmin(db, konto, False)


def test_ostatniego_superadmina_nie_da_sie_usunac(db):
    konto = accounts.bootstrap(db)

    with pytest.raises(AccountError, match="ostatni superadmin"):
        accounts.delete(db, konto)


def test_przy_dwoch_superadminach_jednego_mozna_usunac(db):
    pierwszy = accounts.bootstrap(db)
    drugi = accounts.create(db, "kasia", "Dlugie-Haslo1!", is_superadmin=True)

    accounts.delete(db, drugi)

    assert [u.login for u in accounts.all_users(db)] == [pierwszy.login]
