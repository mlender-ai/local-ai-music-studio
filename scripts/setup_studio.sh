#!/usr/bin/env bash
# One-command macOS studio bootstrap for AI-Native DAW (Phase 03.2.1 + Phase 05).
# Safe & idempotent: installs Homebrew fluid-synth, Python .venv deps, MIT MuseScore_General.sf3,
# builds the React/TypeScript frontend, and seeds the local demo studio sessions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> 1/5 Checking Homebrew FluidSynth (LGPL-2.1)..."
if command -v brew >/dev/null 2>&1; then
  if ! brew list fluid-synth >/dev/null 2>&1; then
    brew install fluid-synth
  else
    echo "    fluid-synth already installed."
  fi
else
  echo "    WARNING: Homebrew not found. Install FluidSynth manually for SF3 multi-sampled instruments."
fi

echo "==> 2/5 Preparing Python 3.12 virtual environment (.venv)..."
if [ ! -x ".venv/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv --python 3.12
  else
    python3.12 -m venv .venv
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python .venv/bin/python -e ".[studio,dev]"
else
  .venv/bin/pip install -e ".[studio,dev]"
fi

echo "==> 3/5 Checking MIT MuseScore_General.sf3 (39.9 MB)..."
SF3_DIR="outputs/daw/soundfonts"
SF3_PATH="$SF3_DIR/MuseScore_General.sf3"
mkdir -p "$SF3_DIR"
if [ ! -f "$SF3_PATH" ]; then
  echo "    Downloading MuseScore_General.sf3 (MIT license)..."
  curl -fL "https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3" -o "$SF3_PATH.tmp" \
    || curl -fL "https://raw.githubusercontent.com/musescore/MuseScore/master/share/sound/MuseScore_General.sf3" -o "$SF3_PATH.tmp"
  mv "$SF3_PATH.tmp" "$SF3_PATH"
  echo "    Saved $SF3_PATH ($(du -h "$SF3_PATH" | awk '{print $1}'))"
else
  echo "    MuseScore_General.sf3 already present."
fi

echo "==> 4/5 Installing & building frontend (apps/daw)..."
(
  cd apps/daw
  npm install
  npm run build
)

echo "==> 5/5 Seeding local demo projects..."
.venv/bin/python scripts/seed_daw_demos.py

echo ""
echo "Setup complete! Launch AI-Native DAW with:"
echo "  ./scripts/start_daw.sh"
echo "Then open http://127.0.0.1:8796"
