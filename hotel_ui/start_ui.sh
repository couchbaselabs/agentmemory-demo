#!/bin/bash
# Starts the Next.js UI. Portable — resolves paths relative to this script.
#
# Override the port with UI_PORT, e.g. `UI_PORT=3000 ./start_ui.sh`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec npm start -- -p "${UI_PORT:-8501}"
