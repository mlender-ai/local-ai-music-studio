# DEVELOPMENT.md — Setup, Running & Verification

## Prerequisites (macOS Apple Silicon)

- Python 3.11 or 3.12 (`uv` recommended)
- Node.js 20+ & npm
- Git & GitHub CLI (`gh`)

## First-Time Setup

```bash
# 1. Python virtual environment (isolated inside repo)
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e . pytest httpx python-multipart

# 2. Frontend dependencies & production build
cd apps/daw
npm install
npm run build
cd ../..

# 3. Seed local demo projects (into gitignored outputs/daw/projects/)
.venv/bin/python scripts/seed_daw_demos.py
```

## Running the DAW

### Single-Command Mode (Recommended)
```bash
./scripts/start_daw.sh
```
Opens the DAW API and built UI on **http://127.0.0.1:8796** (keeps legacy A/B player free on `127.0.0.1:8795`).

### Development Mode (Hot Reload)
```bash
# Terminal 1 — FastAPI DAW backend
.venv/bin/python -m app.daw_server

# Terminal 2 — Vite dev server (proxies /api -> 127.0.0.1:8796)
cd apps/daw && npm run dev
```
Open **http://127.0.0.1:5173**.

## Running Tests

```bash
# All Python tests (legacy engine + Phase 01 DAW backend + Audio/Export QA)
.venv/bin/python -m pytest -q

# Frontend unit tests (command system, time math, MIDI parser, WAV encoder)
cd apps/daw && npm test

# Frontend TypeScript check & production build
cd apps/daw && npm run build
```

## Port Map

| Service | Address | Notes |
|---|---|---|
| AI-Native DAW (API + Built UI) | `http://127.0.0.1:8796` | Primary Phase 01 entry point |
| Vite Dev Server (optional) | `http://127.0.0.1:5173` | Proxies `/api` to `:8796` |
| Legacy Music Studio A/B Player | `http://127.0.0.1:8795` | Existing `music player` command |

## Memory & Resource Safety

- Waveform peaks are downsampled and cached in `cache/waveforms/<sha256>.json`.
- Decoded Web Audio `AudioBuffer`s are cached per `assetId` and released on project switch/dispose.
- Existing ACE-Step MLX/MPS memory guards (`engine/generation/supervisor.py`) remain unmodified.
