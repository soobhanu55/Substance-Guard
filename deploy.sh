#!/usr/bin/env bash
# Run this ON the server (see DEPLOY.md) after `git pull`, or as the whole deploy step
# on a fresh checkout once .env is configured (cp .env.production.example .env && edit it).
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.production.example to .env and fill in secrets first." >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prod.yml)

if grep -q "^DOMAIN_APP=" .env && ! grep -q "^DOMAIN_APP=app.example.com" .env; then
  echo "DOMAIN_APP set in .env -- deploying with the Caddy HTTPS profile enabled."
  docker compose "${COMPOSE_FILES[@]}" --profile with-https up -d --build
else
  echo "No custom DOMAIN_APP set -- deploying without the HTTPS proxy (plain IP:port)."
  docker compose "${COMPOSE_FILES[@]}" up -d --build
fi

echo
echo "Waiting for services to report healthy..."
sleep 5
docker compose "${COMPOSE_FILES[@]}" ps
