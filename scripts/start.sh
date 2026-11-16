#!/usr/bin/env bash
# Start the EMF-Visu local preview (macOS / Linux).
#
#   ./scripts/start.sh              build the images if needed, start, wait until healthy
#   ./scripts/start.sh --no-build   start the images that are already built
#
# Equivalent plain command: docker compose up -d --build
set -u
cd "$(dirname "$0")/.." || exit 1

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

fail() {
  echo
  red "ERROR: $1" >&2
  shift
  for line in "$@"; do printf '  %s\n' "$line" >&2; done
  exit 1
}

# Port settings as docker compose resolves them: environment first, then .env, then default.
env_value() {
  local value="${!1:-}"
  if [ -z "$value" ] && [ -f .env ]; then
    value=$(grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | tr -d "\r\"'")
  fi
  echo "${value:-$2}"
}
FRONTEND_PORT=$(env_value FRONTEND_PORT 8080)
API_PORT=$(env_value API_PORT 8000)
URL="http://localhost:${FRONTEND_PORT}"

# 1. Docker present, running, with Compose v2.
command -v docker >/dev/null 2>&1 || fail "Docker is not installed." \
  "Install Docker Desktop (macOS) or Docker Engine with the Compose plugin (Linux):" \
  "https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Docker is installed but not running, or you lack permission to use it." \
  "macOS: start Docker Desktop and wait until it reports that the engine is running." \
  "Linux: sudo systemctl start docker" \
  "Linux, 'permission denied': sudo usermod -aG docker \$USER, then log out and in again."
docker compose version >/dev/null 2>&1 || fail "'docker compose' (Compose v2) is not available." \
  "Install the Compose plugin: https://docs.docker.com/compose/install/"

# 2. Ports free (unless our own containers already hold them).
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
ours_running() { [ -n "$(docker compose ps -q --status running "$1" 2>/dev/null)" ]; }
check_port() { # service port variable
  if ! ours_running "$1" && port_busy "$2"; then
    fail "Port $2 is already in use by another program." \
      "Stop that program, or create a file named .env next to docker-compose.yml containing" \
      "  $3=$(($2 + 1))" \
      "(any free port) and run this script again."
  fi
}
check_port frontend "$FRONTEND_PORT" FRONTEND_PORT
check_port api "$API_PORT" API_PORT

health() { # service -> healthy | unhealthy | starting | running | exited | missing
  local id
  id=$(docker compose ps -a -q "$1" 2>/dev/null | head -n 1)
  [ -z "$id" ] && { echo missing; return; }
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null
}

diagnose() {
  echo
  echo "Service status:"
  docker compose ps -a
  for svc in postgres redis api worker-analytical frontend; do
    state=$(health "$svc")
    case "$state" in
      healthy | starting | running) ;;
      *)
        echo
        echo "--- last 30 log lines of '$svc' ($state) ---"
        docker compose logs --tail 30 "$svc" 2>&1
        ;;
    esac
  done
}

# 3. Build (first time) and start.
build_flag="--build"
[ "${1:-}" = "--no-build" ] && build_flag=""
echo "Starting EMF-Visu. The first start builds the images, which can take 5-10 minutes."
# shellcheck disable=SC2086
if ! docker compose up -d $build_flag; then
  diagnose
  fail "docker compose could not start the application (details above)." \
    "Common causes: no internet access during the first build, Docker Hub rate limits," \
    "too little disk space. See docs/local-preview.md, section Troubleshooting."
fi

# 4. Wait until the API and the web frontend report healthy.
echo "Waiting for the services to become healthy..."
deadline=$((SECONDS + 240))
while :; do
  api=$(health api)
  frontend=$(health frontend)
  [ "$api" = healthy ] && [ "$frontend" = healthy ] && break
  if [ "$api" = unhealthy ] || [ "$frontend" = unhealthy ] || [ "$api" = exited ] ||
    [ "$frontend" = exited ] || [ $SECONDS -ge $deadline ]; then
    diagnose
    fail "The application did not become healthy (api: $api, frontend: $frontend)." \
      "See the log lines above and docs/local-preview.md, section Troubleshooting."
  fi
  sleep 3
done

# 5. End-to-end check through the frontend, as the browser will use it.
if command -v curl >/dev/null 2>&1; then
  body=$(curl -fsS --max-time 5 "$URL/api/v1/health" 2>/dev/null) ||
    fail "The frontend is up, but $URL/api/v1/health does not answer." \
      "Run ./scripts/status.sh and see docs/local-preview.md, section Troubleshooting."
  case "$body" in
    *'"status":"ok"'*) ;;
    *) red "Warning: the API reports a degraded state: $body" ;;
  esac
fi

worker=$(health worker-analytical)
echo
green "EMF-Visu is running:  $URL"
echo "API documentation:    http://localhost:${API_PORT}/docs"
case "$worker" in
  healthy) echo "Solver worker:        healthy" ;;
  starting) echo "Solver worker:        starting (only needed for high-resolution solves)" ;;
  *) red "Solver worker:        $worker - high-resolution solves will not run; see ./scripts/status.sh" ;;
esac
echo "Stop with:            ./scripts/stop.sh   (saved projects are kept)"
