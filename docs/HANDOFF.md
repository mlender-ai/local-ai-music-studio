# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, open & unmerged pending user review):**
  1. `feat/daw-workspace-phase-01` — PR #15 → `develop/ai-native-daw`
  2. `fix/daw-phase-01-1-stabilization` — PR #16 → `feat/daw-workspace-phase-01`
  3. `feat/daw-korean-localization` — PR #17 → `fix/daw-phase-01-1-stabilization`
  4. `feat/daw-reference-intelligence` — PR #18 → `feat/daw-korean-localization`
  5. `feat/daw-agent-bridge` — PR #19 → `feat/daw-reference-intelligence`
  6. `feat/daw-ai-composition-phase-03` — PR #20 → `feat/daw-agent-bridge`
  7. `fix/daw-phase-03-engine-integration` — PR #21 → `feat/daw-ai-composition-phase-03`
  8. `feat/daw-phase-04-arrangement` — PR #22 → `fix/daw-phase-03-engine-integration`
  9. `feat/daw-advanced-reference-intelligence` (HEAD) — PR #23 → `feat/daw-phase-04-arrangement`

## Run Commands

```bash
# Single-command launch (auto-rebuilds frontend if sources changed, starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Full verification suites
.venv/bin/python -m pytest -q
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 59 daw.* = 68 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 03.2 Verification Summary

- **Backend & Regression (`pytest -q`):** `69 passed` (including real-audio `tests/test_phase032_advanced_reference.py` covering **TEST A–E**, real V7.2 studio recording transcription, sub-bar chord lock note-for-note verification, drum groove transfer, Mode B honest 5-state feature verification, Mode A reconstruct + 1-click Undo, Korean NL routing, and all 68 MCP tools).
- **Frontend (`vitest` + `vite build`):** `13 passed` + clean `tsc -b && vite build`.
- **Live Browser QA (`http://127.0.0.1:8796`):**
  - Verified at `1440×900` and `1280×800` with **`0` console errors**, **`0` failed HTTP requests**, **`0` horizontal overflow**, and **`0` clipped controls**.
  - Verified real precision transcription on `v72_groove_8s.wav` (`Demucs htdemucs` MPS 4 stems with playable stem preview buttons, `Basic Pitch ONNX` Bass/Melody MIDI, Multi-band Drums + Swing, Sub-bar Chords, inline chord editing, `YuE2 Gate PASS` ABC preview, Timeline Chord Track import & lock, Mode B Reference Compose with 5-state Feature Verification badges, and Mode A Session Reconstruct).
  - Verified screenshots saved in:
    - `docs/screenshots/phase-032-desktop-1440.png`
    - `docs/screenshots/phase-032-responsive-1280.png`

## Local Environment Truth (Apple M1, 16 GiB RAM)

- **Verified & Live on this Mac:**
  - **Spotify Basic Pitch `0.4.0` + ONNX Runtime** (`Apache-2.0`, zero TensorFlow/FFmpeg) — `verified`
  - **Demucs `4.1.0` (`htdemucs` on Apple Silicon MPS)** (`MIT`, `soundfile` runner, zero FFmpeg) — `verified`
  - **Claude Code CLI `2.1.330`** (`loggedIn: true`, isolated `--tools ""`) — `verified`
  - **Built-in Music Director + Reference-Conditioned MIDI Composer + Selective Variation Engine + 6-Voice Studio Synth + 68-tool MCP Server**.
- **Genuinely Uninstalled on this Mac (Adapters & Shared Runtime Registry honest & ready):**
  - YuE2 native binary & GGUF weights, ACE-Step checkpoints, `SheetSage2` (`CC BY-NC 4.0`), `YourMT3+`, `All-In-One`, Ollama, Codex CLI, `ffmpeg`, `REAPER.app`.

## Next Priorities (Phase 05 — Sound Design & FX Rack)

1. Per-track non-destructive FX Rack (`EQ`, `Compressor`, `Reverb`, `Delay`, `Saturation`) mirrored cleanly between realtime Web Audio DSP and Python offline WAV export.
2. Automation lanes (Volume, Pan, Filter Cutoff) and Sound Design / Sampler presets.
3. Optional user-approved installation helper for YuE2 (`TEST A` neural audio) and REAPER / AU / VST3 bridge.
