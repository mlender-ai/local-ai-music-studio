# ADR 0001: Gate 0 Audit & Phase 01 Architecture

**Date:** 2026-11-24  
**Status:** Accepted

## Context

The repository `mlender-ai/local-ai-music-studio` contains:
- `main` (`a5085de`): Clean, reviewed initial prototype (ACE-Step MLX/MPS worker, memory supervisor, DSP chain, SQLite version store, FastMCP STDIO server, FastAPI A/B player on `:8795`, 31 passing tests).
- 14 open PR branches (`codex/music-style-fidelity` through `codex/v7-3-acoustic-lift`, plus `codex/v5–v6.1`), containing valuable research modules (`engine/daw/` REAPER Lua bridge, `engine/session/` sample score engine, `evaluation/`) alongside ~600 MB of unmerged experiment audio and QA logs.

## Decisions

1. **Base Branch Selection:** Branch `develop/ai-native-daw` from `main` (`a5085de`) rather than blindly merging open experimental PRs. Preserve all existing `codex/*` branches untouched. Import verified music recordings (e.g. `examples/v72/magnetic-afterhours/final.wav` and `examples/v4/yue2-rock-original.wav`) into local DAW demo projects via `scripts/seed_daw_demos.py` using git refs without duplicating large binaries into Git.
2. **Backend & Port Separation:** Implement the Phase 01 DAW API in `engine/daw_workspace/` and `app/daw_server.py` on `127.0.0.1:8796`, reusing `engine/paths.py` and `engine/rendering/audio.py` while keeping `app/player/server.py` (`127.0.0.1:8795`) and all 31 legacy tests unaffected.
3. **Frontend Stack:** Build `apps/daw/` with React 19, TypeScript, Vite, CSS Design Tokens (zero heavy UI frameworks), HTML5 Canvas for high-density waveforms/timeline/piano-roll rendering, and a clean store driven by a Shared Command Dispatcher.
4. **Audio Engine & Export Parity:** Use Web Audio API (`AudioContext`) for sample-accurate realtime multitrack playback and `OfflineAudioContext` (plus a deterministic Python mirror in `engine/daw_workspace/renderer.py`) for Stereo WAV export, sharing identical scheduling math, clip trims/loops, mute/solo resolution, gain/pan laws, and polyphonic MIDI synthesis.
5. **REAPER Bridge Future Hook:** `REAPER.app` is optional and not installed on all hosts. Expose a non-invasive detection/adapter module (`engine/daw_workspace/reaper.py`) ready to connect `engine/daw/` in Phase 05 without causing double playback in Phase 01.
