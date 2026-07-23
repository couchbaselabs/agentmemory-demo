#!/bin/bash
# Starts the FastAPI backend (hotel_server.py). Portable — resolves paths
# relative to this script, so it works from any checkout location.
#
# Override the port with PORT, e.g. `PORT=8001 ./start_server.sh`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load env vars from .env if present.
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# Activate the local virtualenv if present.
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

exec uvicorn hotel_server:app --host 0.0.0.0 --port "${PORT:-8502}"
