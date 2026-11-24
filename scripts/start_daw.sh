#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python virtualenv .venv not found. Run: uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e . pytest httpx python-multipart"
  exit 1
fi

# Detect frontend source freshness without unnecessary full rebuilds
STAMP_FILE="apps/daw/dist/.build-stamp"
CURRENT_HASH="$(.venv/bin/python - <<'PY'
import hashlib
from pathlib import Path

root = Path("apps/daw")
h = hashlib.sha256()
targets = [root / "package.json", root / "index.html", root / "vite.config.ts", root / "tsconfig.json"]
targets.extend(sorted((root / "src").rglob("*")))
for p in targets:
    if p.is_file():
        h.update(str(p).encode())
        h.update(p.read_bytes())
print(h.hexdigest())
PY
)"

NEEDS_BUILD=0
if [ ! -f "apps/daw/dist/index.html" ] || [ ! -f "$STAMP_FILE" ]; then
  NEEDS_BUILD=1
elif [ "$(cat "$STAMP_FILE" 2>/dev/null || true)" != "$CURRENT_HASH" ]; then
  NEEDS_BUILD=1
fi

if [ "$NEEDS_BUILD" -eq 1 ]; then
  echo "Frontend changes detected — building AI-Native DAW..."
  (
    cd apps/daw
    if [ ! -d "node_modules" ]; then
      npm install
    fi
    npm run build
  )
  printf "%s" "$CURRENT_HASH" > "$STAMP_FILE"
fi

.venv/bin/python scripts/seed_daw_demos.py

echo "Starting AI-Native DAW Workspace at http://127.0.0.1:8796"
exec .venv/bin/python -m app.daw_server --host 127.0.0.1 --port 8796
