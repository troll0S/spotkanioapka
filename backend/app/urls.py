"""Adres, który trafia do kodu QR.

To jedyne miejsce w systemie, które decyduje „pod jakim adresem nas widać".
Trzy źródła, w kolejności pierwszeństwa:

1. `origin` podany wprost przez ekran hosta — ręczne nadpisanie, gdy host wie
   lepiej (np. wkleja adres tunelu).
2. `PUBLIC_URL` z konfiguracji — ustawiane przez `start.ps1` na aktualny adres
   laptopa w sieci, albo ręcznie na adres tunelu.
3. Nagłówek `Host` z żądania przeglądarki hosta — czyli adres, przez który host
   sam wszedł do aplikacji.

Źródło 3 jest zwykle trafne i samo dostosowuje się do zmiany sieci: jeśli host
wchodzi przez `http://192.168.2.172:8000`, to właśnie ten adres trafi do QR.
Zawodzi tylko wtedy, gdy host wejdzie przez `localhost` — wtedy sygnalizujemy
to wprost, bo telefony takiego adresu nie otworzą.

Czego tu świadomie NIE ma: wykrywania adresu laptopa po stronie serwera.
W kontenerze widać wyłącznie adres kontenera (172.x), a Docker na Windowsie
podmienia też adres klienta na adres bramy — ani jedno, ani drugie nie nadaje
się do podania telefonom. Dlatego adres wchodzi z zewnątrz.
"""

import re

from . import config

_LOOPBACK = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1")

#: Dozwolony kształt nadpisania: schemat, host, opcjonalny port. Bez ścieżki,
#: bez parametrów — ta wartość trafia do kodu QR, więc nie może być dowolna.
_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9._\-]+(:\d{1,5})?$")


def clean_origin(origin: str | None) -> str | None:
    """Sprawdza nadpisanie podane przez ekran hosta. Zwraca None, gdy niepoprawne."""
    if not origin:
        return None
    candidate = origin.strip().rstrip("/")
    return candidate if _ORIGIN_RE.match(candidate) else None


def scheme_from(headers, fallback: str = "http") -> str:
    """Schemat widziany przez przeglądarkę, nie przez kontener.

    Tunel Cloudflare kończy TLS u siebie i przekazuje ruch do nas zwykłym HTTP.
    Bez tego nagłówka kod QR dostałby adres `http://…trycloudflare.com`, mimo
    że przeglądarka rozmawia po HTTPS — a strona na HTTPS nie otworzy
    niezaszyfrowanego WebSocketu.
    """
    forwarded = headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return fallback


def base_url(host_header: str | None, scheme: str = "http", origin: str | None = None) -> str:
    override = clean_origin(origin)
    if override:
        return override
    if config.PUBLIC_URL:
        return config.PUBLIC_URL.rstrip("/")
    if host_header:
        return f"{scheme}://{host_header}"
    return f"http://localhost:{config.APP_PORT}"


def join_url(
    code: str, host_header: str | None, scheme: str = "http", origin: str | None = None
) -> str:
    return f"{base_url(host_header, scheme, origin)}/join?code={code}"


def looks_unreachable(url: str) -> bool:
    """Czy ten adres na pewno nie zadziała z telefonu.

    Sprawdzamy sam host, nie całą treść: `localhost` w nazwie sesji albo
    w kodzie nie ma z tym nic wspólnego.
    """
    without_scheme = url.split("://", 1)[-1]
    host = without_scheme.split("/", 1)[0].split(":")[0]
    return host in _LOOPBACK or not host
