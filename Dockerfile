# ─── etap 1: build frontendu ────────────────────────────────────────────────
FROM node:22-alpine AS frontend

WORKDIR /build

# Zależności kopiujemy osobno — dopóki package.json się nie zmieni,
# Docker użyje cache'u zamiast instalować wszystko od nowa.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ─── etap 2: obraz docelowy ─────────────────────────────────────────────────
# Świadomie 3.13, nie 3.14: przy 3.14 część bibliotek z zależnościami C
# (m.in. te do PDF-ów w K7) nie ma jeszcze gotowych wheeli.
FROM python:3.13-slim

WORKDIR /app

# WeasyPrint składa PDF przez Pango i HarfBuzz — to biblioteki systemowe,
# nie pakiety Pythona. DejaVu dokładamy dla polskich znaków: bez żadnego
# fontu w obrazie PDF wyszedłby z pustymi prostokątami zamiast ą, ć, ę.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /build/dist ./static

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STATIC_DIR=/app/static \
    DB_PATH=/data/spotkania.db

EXPOSE 8000

# 0.0.0.0, nie 127.0.0.1 — inaczej kontener odetnie się od świata,
# a port zmapowany w compose i tak nic nie da.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
