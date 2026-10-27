"""Konfiguracja czytana ze zmiennych środowiskowych.

Wszystko, co różni tryb lokalny od zdalnego i development od produkcji,
przechodzi przez ten plik — w kodzie aplikacji nie ma rozgałęzień na tryb.
"""

import os
from pathlib import Path

APP_NAME = "Spotkaniooapka"
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Adres, pod którym aplikacja jest widoczna dla telefonów.
# Lokalnie: http://<IP-laptopa>:8000   Zdalnie: adres tunelu Cloudflare.
# Używane od K1 do generowania kodu QR.
PUBLIC_URL = os.getenv("PUBLIC_URL") or None

# Hasło pierwszego superadmina. Używane **tylko** przy pustej bazie, do
# założenia konta startowego — potem hasła żyją w bazie i zmienia się je
# w panelu. W trybie zdalnym musi być mocne, patrz README.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Login konta startowego.
SUPERADMIN_LOGIN = os.getenv("SUPERADMIN_LOGIN", "admin")

# Baza (używana od K1). Katalog jest wolumenem Dockera, więc przeżywa restart.
DB_PATH = Path(os.getenv("DB_PATH", "./data/spotkania.db"))

# Zbudowany frontend. W trybie dev katalog nie istnieje — serwuje go Vite.
STATIC_DIR = Path(os.getenv("STATIC_DIR", "static"))

DEV_MODE = os.getenv("DEV_MODE", "").lower() in {"1", "true", "yes"}
