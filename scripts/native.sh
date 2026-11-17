#!/usr/bin/env bash
# Run EMF-Visu natively (macOS / Linux), without Docker:  ./scripts/native.sh start|stop|status
# Makes sure the project's Python environment exists (uv sync), then runs scripts/native.py.
set -euo pipefail
cd "$(dirname "$0")/.."
cmd="${1:-start}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv was not found. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi
if [ "$cmd" = "start" ] || [ ! -x .venv/bin/python ]; then
  uv sync --frozen --quiet
fi
exec .venv/bin/python scripts/native.py "$cmd"
