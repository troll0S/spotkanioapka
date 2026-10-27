"""Ustalanie adresu dla kodu QR.

Regresja z prawdziwego użycia: adres laptopa wpisany na stałe w PUBLIC_URL
przestał istnieć po przeniesieniu laptopa do innej sieci. Telefony dostawały
w QR martwy adres i ładowały stronę w nieskończoność.
"""

import pytest

from app import config, urls


@pytest.fixture()
def bez_public_url(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", None)


@pytest.fixture()
def z_public_url(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "http://10.0.0.5:8000")


def test_bez_konfiguracji_adres_idzie_z_zadania(bez_public_url):
    """Domyślnie adres bierze się z tego, jak host sam wszedł do aplikacji.

    To właśnie ta droga sprawia, że zmiana sieci nie wymaga żadnej edycji:
    host wchodzi przez nowy adres i ten adres trafia do QR.
    """
    assert urls.base_url("192.168.2.172:8000") == "http://192.168.2.172:8000"
    assert (
        urls.join_url("ABCDEF", "192.168.2.172:8000")
        == "http://192.168.2.172:8000/join?code=ABCDEF"
    )


def test_public_url_ma_pierwszenstwo_nad_zadaniem(z_public_url):
    assert urls.base_url("192.168.2.172:8000") == "http://10.0.0.5:8000"


def test_reczne_nadpisanie_bije_wszystko(z_public_url):
    """Ekran hosta musi móc naprawić adres bez restartu aplikacji."""
    assert (
        urls.base_url("192.168.2.172:8000", origin="http://192.168.8.11:8000")
        == "http://192.168.8.11:8000"
    )


def test_https_przechodzi_dla_tunelu(bez_public_url):
    assert (
        urls.base_url("x.trycloudflare.com", scheme="https")
        == "https://x.trycloudflare.com"
    )


def test_schemat_bierze_sie_z_naglowka_proxy():
    """Regresja: tunel kończy TLS u siebie i przekazuje ruch zwykłym HTTP.

    Bez czytania X-Forwarded-Proto kod QR wskazywałby `http://…` mimo że
    przeglądarka rozmawia po HTTPS — a strona na HTTPS nie otworzy
    niezaszyfrowanego WebSocketu.
    """
    assert urls.scheme_from({"x-forwarded-proto": "https"}) == "https"
    assert urls.scheme_from({"x-forwarded-proto": "https,http"}) == "https"
    assert urls.scheme_from({}) == "http"
    assert urls.scheme_from({}, fallback="https") == "https"


def test_pelny_adres_za_tunelem(bez_public_url):
    naglowki = {"x-forwarded-proto": "https"}
    assert urls.join_url(
        "ABCDEF", "x.trycloudflare.com", urls.scheme_from(naglowki)
    ) == "https://x.trycloudflare.com/join?code=ABCDEF"


@pytest.mark.parametrize(
    "adres",
    [
        "http://localhost:8000/join?code=X",
        "http://127.0.0.1:8000/join?code=X",
        "http://0.0.0.0:8000/join?code=X",
    ],
)
def test_adresy_petli_zwrotnej_sa_oznaczane(adres):
    """Telefon nie otworzy adresu wskazującego na sam laptop."""
    assert urls.looks_unreachable(adres) is True


@pytest.mark.parametrize(
    "adres",
    [
        "http://192.168.2.172:8000/join?code=X",
        "https://cos.trycloudflare.com/join?code=X",
    ],
)
def test_adresy_sieciowe_nie_sa_oznaczane(adres):
    assert urls.looks_unreachable(adres) is False


def test_slowo_localhost_w_kodzie_sesji_nie_myli_wykrywania():
    """Sprawdzamy host, nie całą treść adresu."""
    assert urls.looks_unreachable("http://192.168.2.172:8000/join?code=LOCALHOST") is False


@pytest.mark.parametrize(
    "smiec",
    [
        "nie-adres",
        "ftp://192.168.1.1",
        "http://1.2.3.4/sciezka",
        "http://1.2.3.4:8000?x=1",
        "javascript:alert(1)",
        "",
        None,
    ],
)
def test_niepoprawne_nadpisanie_jest_odrzucane(smiec):
    """Ta wartość trafia do kodu QR, więc nie może być dowolna."""
    assert urls.clean_origin(smiec) is None


def test_nadpisanie_bez_koncowego_ukosnika():
    assert urls.clean_origin("http://192.168.2.172:8000/") == "http://192.168.2.172:8000"
