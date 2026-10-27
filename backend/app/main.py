"""Punkt wejścia aplikacji."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .migrations import upgrade_to_head
from .net import in_container, lan_ip
from .routers import admin as admin_router
from .routers import export as export_router
from .routers import session as session_router
from .routers import ws as ws_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("spotkanioapka")

STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    upgrade_to_head()
    _bootstrap_admin()
    announce()
    yield


def _schema_revision() -> str | None:
    """Wersja schematu bazy — przydaje się, gdy coś nie gra po aktualizacji."""
    from sqlalchemy import text

    from .db import engine

    try:
        with engine.connect() as polaczenie:
            return polaczenie.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None


def _bootstrap_admin() -> None:
    """Zakłada konto startowe z `.env`, gdy baza jest jeszcze pusta.

    Przy starcie, a nie dopiero przy pierwszym logowaniu: dzięki temu zaraz po
    uruchomieniu widać w logach, czy konto powstało, a `start.ps1` może
    sprawdzić stan kont, zanim wystawi aplikację na świat.
    """
    from .accounts import bootstrap
    from .db import SessionLocal

    with SessionLocal() as db:
        konto = bootstrap(db)
        if konto is not None:
            log.info("Założono konto startowe: %s (superadmin)", konto.login)


app = FastAPI(
    title=config.APP_NAME,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(session_router.router)
app.include_router(export_router.router)
app.include_router(admin_router.router)
app.include_router(ws_router.router)


@app.get("/api/health")
async def health(request: Request) -> dict:
    """Diagnostyka.

    Telefon, który to zobaczy, udowodnił trzy rzeczy naraz: dosięgnął laptopa,
    przeszedł przez firewall i dostał odpowiedź z kontenera.
    """
    return {
        "status": "ok",
        "app": config.APP_NAME,
        # Wersja schematu zamiast numeru kamienia: aktualizuje się sama
        # z migracjami, więc nie zdezaktualizuje się po cichu.
        "schema": _schema_revision(),
        "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "client_host": request.client.host if request.client else None,
        "requested_host": request.headers.get("host"),
        "frontend_built": (config.STATIC_DIR / "index.html").is_file(),
        "in_container": in_container(),
    }


def announce() -> None:
    """Wypisuje przy starcie adresy, pod którymi aplikacja jest osiągalna."""
    ip = lan_ip()
    log.info("=" * 62)
    log.info("  %s", config.APP_NAME)
    log.info("  lokalnie:      http://localhost:%s", config.APP_PORT)
    if config.PUBLIC_URL:
        log.info("  PUBLIC_URL:    %s", config.PUBLIC_URL)
    else:
        log.warning("  PUBLIC_URL puste — kod QR może wskazać zły adres")
    if in_container():
        log.info("  adres kontenera: %s (NIE podawaj go telefonom)", ip)
    elif ip:
        log.info("  z telefonu:    http://%s:%s", ip, config.APP_PORT)
    if not config.ADMIN_PASSWORD:
        log.warning("  ADMIN_PASSWORD puste — nie da się założyć sesji")
    if not (config.STATIC_DIR / "index.html").is_file():
        log.warning("  frontend niezbudowany — w trybie dev serwuje go Vite na :5173")
    log.info("=" * 62)


def _looks_like_file(path: str) -> bool:
    """Czy to żądanie o konkretny plik, a nie o ścieżkę routingu frontendu.

    Kryterium: kropka w ostatnim segmencie. `/host` i `/join` to ścieżki
    aplikacji, `/assets/index-a1b2.js` to plik.
    """
    return "." in path.rsplit("/", 1)[-1]


# Uwaga na kolejność: ta trasa łapie wszystko, więc musi być zarejestrowana
# jako ostatnia. Każdy nowy endpoint API dopisuj POWYŻEJ (albo w routerze).
@app.get("/{full_path:path}")
async def spa(full_path: str):
    """Serwuje zbudowany frontend, z fallbackiem na index.html.

    Fallback obsługuje ścieżki routingu (`/host`, `/join`), żeby odświeżenie
    strony nie dawało 404 — te adresy należą do frontendu, nie do serwera.

    Ale **nie obejmuje żądań o pliki**. Gdyby obejmował, przeglądarka
    z zapamiętanym starym `index.html` poprosiłaby o plik JS o nieaktualnym
    hashu, dostała w odpowiedzi HTML z kodem 200 — i po cichu nie wykonała
    żadnego skryptu. Strona ładowałaby się w nieskończoność bez śladu błędu.
    Brakujący plik musi zwrócić 404.
    """
    root = config.STATIC_DIR.resolve()

    if full_path:
        candidate = (root / full_path).resolve()
        # Bez tego sprawdzenia "../" wyprowadziłoby poza katalog statyczny.
        if candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate, headers=_cache_headers(full_path))

        if _looks_like_file(full_path):
            return JSONResponse(
                {"detail": f"Nie ma pliku {full_path}."},
                status_code=404,
            )

    index = root / "index.html"
    if index.is_file():
        # index.html zawsze rewalidowany: to on wskazuje na aktualne hashe
        # plików. Zapamiętany na zapas skazywałby użytkownika na poprzednią
        # wersję aplikacji aż do ręcznego wyczyszczenia pamięci podręcznej.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return JSONResponse(
        {
            "detail": "Frontend nie jest zbudowany.",
            "hint": "Tryb dev: wejdź na port 5173. Tryb docelowy: docker compose build.",
        },
        status_code=503,
    )


def _cache_headers(path: str) -> dict[str, str]:
    # Pliki z /assets/ mają hash w nazwie, więc ich treść nigdy się nie zmienia —
    # można je trzymać dowolnie długo. Zmiana kodu daje nową nazwę.
    if path.startswith("assets/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    return {"Cache-Control": "no-cache"}
