#!/usr/bin/env bash
set -euo pipefail

has() { command -v "$1" &>/dev/null; }

if ! has docker; then echo "[!] Docker n'est pas installé"; exit 1; fi
if ! docker compose version &>/dev/null; then echo "[!] docker compose plugin requis"; exit 1; fi
if ! has openssl; then echo "[!] openssl requis"; exit 1; fi
if ! has sed; then echo "[!] sed requis"; exit 1; fi

cp -n .env.example .env || true

# Génère des secrets si les valeurs sont par défaut
if grep -q "^SECRET_KEY=please-change-this" .env; then
  sed -i "s/SECRET_KEY=please-change-this/SECRET_KEY=$(openssl rand -hex 32)/" .env
fi

PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
if [ "$PGPASS" = "change-me" ]; then
  NEWPASS=$(openssl rand -hex 16)
  sed -i "s/POSTGRES_PASSWORD=change-me/POSTGRES_PASSWORD=${NEWPASS}/" .env
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://valtrack:${NEWPASS}@db:5432/valtrack|" .env
fi

ACTION=${1:---up}
case "$ACTION" in
  --up)
    docker compose pull
    docker compose build --pull
    docker compose up -d
    echo ""
    echo "[✓] ValTrack lancé : http://localhost:8080"
    echo "    API: http://localhost:8080/api  | Health: /api/healthz"
    echo "    Admin par défaut: $(grep '^ADMIN_EMAIL=' .env | cut -d= -f2) / $(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2)"
    ;;
  --down)
    docker compose down
    ;;
  --rebuild)
    docker compose build --no-cache
    docker compose up -d
    ;;
  *)
    echo "Usage: bash install.sh [--up|--down|--rebuild]"
    exit 1
    ;;
esac
