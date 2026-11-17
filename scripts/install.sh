#!/bin/sh
# All runtime changes stay inside this project. No global pip / shell-profile edits.
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .bootstrap/bin/uv ]; then
  python3 -m venv .bootstrap
  .bootstrap/bin/python -m pip install 'uv==0.13.8'
fi
export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export UV_CACHE_DIR="$PWD/.runtime/uv-cache"
if [ ! -x .venv/bin/python ]; then
  .bootstrap/bin/uv venv --python 3.12 .venv
fi
if [ ! -d vendor/ACE-Step-1.5 ]; then
  git clone https://github.com/ace-step/ACE-Step-1.5.git vendor/ACE-Step-1.5
fi
git -C vendor/ACE-Step-1.5 checkout ca1e85fe9430179831e6bc6be790c332190a3866
.bootstrap/bin/uv pip install --python .venv/bin/python -r requirements.lock
.bootstrap/bin/uv pip install --python .venv/bin/python --no-deps -e .
HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1 .venv/bin/python scripts/download_models.py
