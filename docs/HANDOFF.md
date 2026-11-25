# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Phase 01–05 Branches (all pushed, open & unmerged pending user review):**
  1. `feat/daw-workspace-phase-01` — PR #15 → `develop/ai-native-daw`
  2. `fix/daw-phase-01-1-stabilization` — PR #16 → `feat/daw-workspace-phase-01`
  3. `feat/daw-korean-localization` — PR #17 → `fix/daw-phase-01-1-stabilization`
  4. `feat/daw-reference-intelligence` — PR #18 → `feat/daw-korean-localization`
  5. `feat/daw-agent-bridge` — PR #19 → `feat/daw-reference-intelligence`
  6. `feat/daw-ai-composition-phase-03` — PR #20 → `feat/daw-agent-bridge`
  7. `fix/daw-phase-03-engine-integration` — PR #21 → `feat/daw-ai-composition-phase-03`
  8. `feat/daw-phase-04-arrangement` — PR #22 → `fix/daw-phase-03-engine-integration`
  9. `feat/daw-advanced-reference-intelligence` — PR #23 → `feat/daw-phase-04-arrangement`
  10. `feat/daw-reference-fidelity` — PR #24 → `feat/daw-advanced-reference-intelligence` (GATE 1)
  11. `fix/daw-native-audio-runtime` — PR #25 → `feat/daw-reference-fidelity` (GATE 2)
  12. `feat/daw-professional-instruments` — PR #26 → `fix/daw-native-audio-runtime` (GATE 3)
  13. `feat/daw-professional-fx` — PR #27 → `feat/daw-professional-instruments` (GATE 4)
  14. `feat/daw-phase05-integration` (HEAD) — PR #28 → `feat/daw-professional-fx` (GATE 5–7)

## Run Commands

```bash
# Single-command launch (auto-rebuilds frontend if sources changed, starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Full verification suites
.venv/bin/python -m pytest -q
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 72 daw.* = 81 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 03.2.1 + Phase 05 Verification Summary

- **Backend & Real Music Production (`pytest`):** **`93 passed`** (`0 failed`), covering Gate 1 Reference Fidelity (8-bar unique drum lock with 0% 2-bar collapse, 15-quality sub-bar chords), Gate 2 Native Audio Protection & Demucs Vocal Leakage Gate, Gate 3 FluidSynth SF3 / Pro Synth / Drum Rack Choke Groups / Sampler / AU Scanner, Gate 4 Pedalboard 6-Band EQ / External Sidechain (`0.0 dB` silent check) / Convolution IR Reverb / Guitar Amp + Cab IR / Cutoff Automation / Track Freeze, and Gate 7 Real Music Production **Tests A–E** (Reference Reconstruction, 128 BPM House, 90 BPM Jazzy Hip-Hop, 118 BPM Indie Rock, 5-Turn Conversational Korean Sound Design + 81 MCP Tools).
- **Frontend (`vitest` + `vite build`):** **`14 passed`** + clean `tsc -b && vite build`.
- **Live Browser QA (`http://127.0.0.1:8796`):**
  - Verified at `1440×900` and `1280×800` with **`0` console errors**, **`0` page errors**, **`0` HTTP >= 400 errors**, and **`0` occluded controls**.
  - Verified Left Browser **`가상악기`** (`SF3 / SYNTH / RACK / SAMP / PREV` badges) and **`이펙트`** (18 processors), Bottom Dock **`Device Rack`** (Instrument + live curved RBJ Parametric EQ SVG + Compressor transfer SVG + Room Reverb depth SVG + Sends + Freeze), **`믹서`** (FX badges + Return Bus + sticky unclipped `MASTER`), and Korean AI Producer staged Sound Design proposals.
  - Verified screenshots saved in:
    - `docs/screenshots/phase-05-device-rack.png`
    - `docs/screenshots/phase-05-mixer-ai-producer.png`

## Local Environment Truth (Apple M1, 16 GiB RAM)

- **Verified & Live on this Mac:**
  - **Spotify Pedalboard (`0.9.22`, GPL-3.0)** C++ DSP & Convolution IR engine — `verified`
  - **FluidSynth (`2.6.3`, LGPL-2.1) + `MuseScore_General.sf3` (`MIT`, 39.9 MB)** — `verified`
  - **Spotify Basic Pitch `0.4.0` + ONNX Runtime (`Apache-2.0`)** — `verified`
  - **Demucs `4.1.0` (`htdemucs` on Apple Silicon MPS, `MIT`)** — `verified`
  - **Claude Code CLI (`loggedIn: true`, isolated `--tools ""`)** — `verified`
  - **81-tool MCP Server (`app/mcp_server.py`)** + **3-Pass 48 kHz Studio WAV Exporter**
- **Genuinely Uninstalled on this Mac (Honest 6-State Registry):**
  - YuE2 native binary & GGUF weights, ACE-Step checkpoints, `SheetSage2` (`CC BY-NC 4.0`), `YourMT3+`, `All-In-One`, Ollama, Codex CLI, `ffmpeg`, `REAPER.app`.

## Next Priorities (Phase 06 — AI Mixing & Mastering)

1. Multi-track AI Mix Balance diagnosis (frequency masking matrix across Kick/Bass/Guitar/Synth, LUFS loudness target matching, stereo imaging balance).
2. Master Bus Mastering Chain UI (Linear-phase / Master EQ, Bus Glue Compressor, True-Peak Limiter targeting `-14 LUFS / -1.0 dBTP`) with level-matched A/B reference comparison.
3. Optional user-approved installation helper for YuE2 native audio weights (`TEST A` neural audio generation).
