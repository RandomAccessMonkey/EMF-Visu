#!/usr/bin/env bash
# Stop the EMF-Visu local preview (macOS / Linux). Saved projects are kept.
# Equivalent plain command: docker compose down
set -u
cd "$(dirname "$0")/.." || exit 1
command -v docker >/dev/null 2>&1 || { echo "Docker is not installed; nothing to stop."; exit 0; }
docker info >/dev/null 2>&1 || { echo "Docker is not running; the application is already stopped."; exit 0; }
docker compose down || exit 1
echo
echo "EMF-Visu stopped. Saved projects are kept in the Docker volume 'emf-visu_pgdata'."
echo "Start again with ./scripts/start.sh"
