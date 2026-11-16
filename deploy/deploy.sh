#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker info >/dev/null
docker compose version
test -s .env || { echo 'Run python3 deploy/init_env.py http://YOUR_SERVER_IP first.' >&2; exit 1; }
test -s frontend/dist/index.html || { echo 'Build frontend/dist on your development computer first.' >&2; exit 1; }
docker compose config --quiet
# Serial builds reduce peak memory use on a 2GB instance.
docker compose build backend
docker compose build frontend
docker compose up -d --wait --wait-timeout 300
docker compose ps
echo 'Run python3 deploy/smoke.py http://YOUR_SERVER_IP from outside the server.'
