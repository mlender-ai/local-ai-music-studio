#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtualenv .venv not found. Run: uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e . pytest httpx python-multipart"
  exit 1
fi

if [ ! -f "apps/daw/dist/index.html" ]; then
  echo "Building AI-Native DAW frontend..."
  (cd apps/daw && npm install && npm run build)
fi

.venv/bin/python scripts/seed_daw_demos.py

echo "Starting AI-Native DAW Workspace at http://127.0.0.1:8796"
exec .venv/bin/python -m app.daw_server --host 127.0.0.1 --port 8796
