# AGENTS.md — AI-Native DAW Shared Engineering Directive

All development agents (Antigravity, Claude Code, Codex, and others) MUST read this file and `docs/STATUS.md` before starting any task.

## 1. Product Goal

Transform `local-ai-music-studio` into **AI-Native DAW** — a local-first macOS desktop music studio combining Ableton Live / Logic Pro timeline & editing workflows with a natural-language AI Producer.

- Music and the Arrangement Timeline are the center of the product.
- AI acts as an assistive producer through a shared Command System, never as a replacement for direct editing.
- Never fabricate waveforms, meters, MIDI notes, stems, or AI outputs.

## 2. Current Phase

- **Active Phase:** Phase 03.1 + Phase 04 — Engine Recovery · AI Arrangement · Musical Variation · Take Comping (`docs/phases/PHASE_04.md`)
- **Integration Branch:** `develop/ai-native-daw`
- **Latest Stacked Task Branch:** `feat/daw-phase-04-arrangement` (stacked on `fix/daw-phase-03-engine-integration` PR #21)
- Read `docs/STATUS.md` for live progress and `docs/HANDOFF.md` for the latest handoff context.

## 3. Repository Map

| Path | Role |
|---|---|
| `apps/daw/` | React + TypeScript + Vite DAW frontend (Timeline + Take Lanes, Audio Engine, Clip Editor Fades/Reverse, Piano Roll, Mixer, AI Producer, Commands) |
| `engine/daw_workspace/` | Python DAW backend (Project persistence v1.3.0, asset store, waveform cache, MIDI SMF parser, BS.1770-4 loudness, offline WAV renderer with fades, shared command executor, staged proposals, MCP tools) |
| `engine/runtime/` | Shared Runtime Registry (`~/.config/ai-native-daw/runtime.json`) with honest 6-state engine lifecycle (`uninstalled` → `verified`) |
| `engine/providers/` | AI Producer Provider Registry (verified isolated local Claude Code CLI `--tools ""`, Built-in Music Director, MCP Bridge, Ollama/Codex/Env API probes) |
| `engine/composition/` | Composition Director, Reference Context Binding, Motif MIDI Composer, Musical Validation, Sample Catalog |
| `engine/generation/` | Single-worker Generation Job Manager, Process-Group Guard (`SIGTERM → SIGKILL`, 10 GiB RSS cap), Safe Take Apply, YuE2/ACE-Step/Demucs/Local adapters |
| `engine/arrangement/` | Phase 04 Selective Arrangement, `EditScope`/`ArrangementEditPlan`, MIDI Musical Variations, Non-Destructive Audio Reverse & Seam Validation, Contextual A/B Previews, Timeline Take Lanes & Selective Comping, Project Music Memory |
| `engine/instruments/` | 6-voice multi-timbre studio synth voices mirrored in Web Audio |
| `app/daw_server.py` | FastAPI DAW HTTP + SSE server (`127.0.0.1:8796`, serves API + built frontend) |
| `engine/` | Existing Local AI Music Studio engine (ACE-Step generation, DSP chain, SQLite version store, jobs, rendering). Do not break. |
| `app/player/` | Existing A/B player (`127.0.0.1:8795`). Preserve compatibility. |
| `app/mcp_server.py` | FastMCP STDIO server exposing 61 tools (`9 music.*` + `52 daw.*`) |
| `scripts/start_daw.sh` | Single-command launcher for DAW backend + frontend |
| `scripts/seed_daw_demos.py` | Seeds Demo Project A (V7.2 Magnetic Afterhours) and Demo Project B (Multitrack Session) locally |
| `docs/` | Shared product, design, architecture, project format, roadmap, status, handoff, phase specs, and screenshots |

## 4. Development Commands

```bash
# Python environment (Python 3.11–3.12 via uv)
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e . pytest httpx python-multipart

# Frontend dependencies & build
cd apps/daw && npm install && npm run build

# Seed demo projects locally (into gitignored outputs/daw/projects/)
.venv/bin/python scripts/seed_daw_demos.py

# Run complete DAW app (serves built UI + API on http://127.0.0.1:8796)
./scripts/start_daw.sh

# Development mode (hot reload)
.venv/bin/python -m app.daw_server        # Terminal 1 (API on 127.0.0.1:8796)
cd apps/daw && npm run dev                # Terminal 2 (Vite on 127.0.0.1:5173)

# Verification tests
.venv/bin/python -m pytest -q             # Backend + regression tests
cd apps/daw && npm test && npm run build  # Frontend unit tests + TypeScript build
```

## 5. Git Collaboration Rules

- **NEVER** force push, delete existing branches, run `git reset --hard`, or overwrite uncommitted work.
- **NEVER** auto-merge into `main` before user review.
- **NEVER** commit model weights, `.venv/`, `outputs/`, `node_modules/`, large audio caches, personal paths, or credentials.
- Work in small, verifiable commits on dedicated task branches or git worktrees branched from `develop/ai-native-daw`.
- Do not modify the same files concurrently across parallel agents.

## 6. Code & Architecture Conventions

- Every project state mutation MUST pass through the Shared Command System (`apps/daw/src/commands/` and `engine/daw_workspace/commands.py`).
- Keep unit types strictly separated: `beats`, `seconds`, `samples`, `bars`, `ticks` (`PPQ = 480`). See `docs/PROJECT_FORMAT.md`.
- Keep Realtime Preview (`Web Audio API`) and Offline Stereo WAV Export (`OfflineAudioContext` / Python renderer) using the exact same project schema and edit semantics.
- Keep original audio/MIDI assets immutable; all timeline edits are non-destructive.
- Save `project.json` atomically (`tmp` + `os.replace`) with autosave recovery.

## 7. Verification Standards

A task is NEVER complete on static code or text tests alone:
1. Run backend `pytest` (including existing regression tests) and frontend `npm test` + `npm run build`.
2. Verify real audio scheduling, mute/solo, gain/pan, clip edits, MIDI playback, persistence round-trip, and exported Stereo WAV signal integrity.
3. Inspect the live app in a real browser at `1440×900` and `1280×800` across key states and attach screenshots to PRs.
4. Update `docs/STATUS.md` and `docs/HANDOFF.md` before ending a session.

## 8. Context Efficiency

Keep `AGENTS.md` and `docs/STATUS.md` concise. Read only the detailed specs relevant to your task:
- Product scope: `docs/PRODUCT.md`
- UI & tokens: `docs/DESIGN.md`
- System boundaries: `docs/ARCHITECTURE.md`
- Project schema & units: `docs/PROJECT_FORMAT.md`
- Dev setup & QA: `docs/DEVELOPMENT.md`
- Current phase checklist: `docs/phases/PHASE_04.md`
