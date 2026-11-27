# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, open & unmerged pending user review):**
  1–14. Phases 01–05 (`PR #15`–`PR #28`, latest base `feat/daw-phase05-integration` @ `a59fc22`)
  15. **`feat/daw-yue2-native-production` (HEAD → `feat/daw-phase05-integration`) — Phase 05.1 YuE2 Native Engine First, Permanent Production Policy, Studio Preview Parity & 88 MCP Tools**

## Run Commands

```bash
# Single-command launch (auto-rebuilds frontend if sources changed, starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Verification suites
.venv/bin/python -m pytest -v tests/test_phase051_native_production.py
.venv/bin/python -m pytest -q
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 79 daw.* = 88 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 05.1 Permanent Policy & Verification Summary

- **Permanent Policy (`config/production/*.json`, `engine/production/`, `docs/MUSIC_PRODUCTION_POLICY.md`):**
  - Default full-music engine is **`yue2-native`** (`allowSilentMidiFallback: false`).
  - Legacy Phase 03 voices are permanently tagged **`PREVIEW`** (`allowPreviewInstrumentsInProduction: false`) and blocked across UI, REST, and MCP unless explicitly overridden.
  - Persistent User Music Taste & Feedback Profile stored in `outputs/daw/taste_profile.json` (gitignored; inspect/update/reset via `/api/production/taste` or `daw.*_taste_profile` MCP tools).
  - **Studio Preview** (`/api/projects/{id}/studio-preview/{status,render,audio}` & `daw.*_studio_preview`) renders exact 3-pass Studio WAV parity and auto-invalidates to `Outdated Preview` on any project edit.
- **Validation Deliverables (Report: `docs/production-tests/PHASE_051_NATIVE_ENGINE_REPORT.md`):**
  - Saved DAW project: **`Native Production Validation 001`** (`proj_5e536a5f75`) — real 22 s Metal YuE2 R&B/Neo Soul audio (`official_v6_compile_score`, `90.8 BPM`, `Native Production Test.wav` + non-destructive `Studio Preview.wav`).
  - Companion Hybrid project: **`Native Production Validation 001 (Hybrid)`** (`proj_deb5741452`) — Demucs 4-stem separation (source track muted, untouched asset preserved) + targeted `Drums (Stem)` saturation + `sf-ep-rhodes` MIDI layer.
  - Live Browser QA (`http://127.0.0.1:8796`): **`0` console / page / HTTP 4xx-5xx errors**, verified waveform, `prod-mode-neural_audio` default, `Studio Preview` badge & audition, transport advance, and reload persistence.

## Local Environment Truth (Current Host: Apple M5, 24 GiB RAM)

- **Verified & Live on this Mac:**
  - **YuE2 Native Audio (`yue2.cpp e646d52` Metal `MTL0`, `YuE2-3B-Q8_0.gguf`, `YuE2-Vae-F32.gguf`, `v6/instrumental/compile_score.py`)** — `GENERATION_VERIFIED` via user-local `~/.config/ai-native-daw/runtime.json` (`sharedRuntimeRoot`)
  - **Spotify Pedalboard (`0.9.26`, GPL-3.0)** — `verified`
  - **FluidSynth (`2.6.3`, LGPL-2.1) + `MuseScore_General.sf3` (`MIT`)** — `verified`
  - **Demucs (`htdemucs` on Apple Silicon MPS, `MIT`)** — `verified`
  - **Spotify Basic Pitch `0.4.0` + ONNX Runtime (`Apache-2.0`)** — `verified`
  - **88-tool MCP Server (`app/mcp_server.py`)** + **Studio Preview & 3-Pass 48 kHz WAV Exporter**
- **Genuinely Uninstalled / Optional:** `SheetSage2` (`CC BY-NC 4.0`), `YourMT3+`, `All-In-One`, `REAPER.app`.

## Next Priorities

1. **User Listening Review (Phase 05.1 Gate):** User compares Audio A (`After Midnight — Take 02.wav`), Audio B (`Native Production Test.wav`), and Audio C (`Studio Preview.wav`) and records taste feedback via `/api/production/taste/feedback` or chat.
2. **Optional PANNs/Whisper Vocal QA Runner Integration:** Wire the already-present local `.runtime/v7/panns/mobilenet.pth` and `.runtime/v4/whisper-small` directly into `screen_vocal_leakage()` to reduce `UNCERTAIN` verdicts on expressive melodic stems.
3. **Phase 06 (AI Mixing & Mastering):** Multi-track masking diagnosis, bus mastering chain, and level-matched reference A/B.
