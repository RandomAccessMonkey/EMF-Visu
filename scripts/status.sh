#!/usr/bin/env bash
# Show the state of the EMF-Visu local preview (macOS / Linux).
set -u
cd "$(dirname "$0")/.." || exit 1
port=${FRONTEND_PORT:-}
if [ -z "$port" ] && [ -f .env ]; then
  port=$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d= -f2- | tr -d "\r\"'")
fi
port=${port:-8080}
docker info >/dev/null 2>&1 || { echo "Docker is not running."; exit 1; }
echo "Containers (STATUS shows the health check result):"
docker compose ps -a
echo
if command -v curl >/dev/null 2>&1; then
  echo "Application health (http://localhost:$port/api/v1/health):"
  curl -sS --max-time 5 "http://localhost:$port/api/v1/health" || echo "  not reachable"
  echo
fi
echo
echo "Logs of one service:  docker compose logs --tail 50 api"
echo "                      (or frontend, worker-analytical, postgres, redis)"
