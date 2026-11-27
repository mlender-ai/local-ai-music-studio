# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, open & unmerged pending user review):**
  1–15. Phases 01–05.1 (`PR #15`–`PR #29`, latest native baseline `feat/daw-yue2-native-production` @ `a124b21`)
  16. `feat/daw-ai-session-loop-production` (`PR #30` @ `2999bdf`) — Phase 05.2 Session/Layer/Library infrastructure (SF3 audio output rejected on user listening; technical infrastructure retained)
  17. **`experiment/yue2-native-performance-lab` (HEAD → `feat/daw-ai-session-loop-production`) — Phase 05.3 Native Musical Performance Lab, Permanent Native Performance Mode Routing, Demucs+PANNs Vocal QA & 8 YuE2 Listening Experiments (A–H)**

## Run Commands

```bash
# Single-command launch (starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Verification suites
.venv/bin/python -m pytest -v tests/test_phase052_session_loop.py tests/test_phase051_native_production.py tests/test_phase04_arrangement.py tests/test_phase03_composition.py tests/test_agent_bridge.py
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 95 daw.* = 104 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 05.3 Architecture & Experiment Summary

- **Permanent Policy Shift (Sections 18–20):**
  - `config/production/default_policy.json` (`schemaVersion: 2`) & `engine_routing.json`: Sets `defaultPerformanceEngine: "yue2-native"`, `nativePerformanceFirst: true`, and `midiPerformerExplicitOptInOnly: true`.
  - `engine/daw_workspace/proposals.py`, `app/daw_server.py`, `engine/generation/daw_jobs.py`: General performance prompts (`"기타 리프 만들어줘"`, `"피아노 솔로 만들어줘"`, `"독특한 드럼 그루브 만들어줘"`, `"베이스 리프 만들어줘"`, `"브릿지 만들어줘"`) route by default to **YuE2 Native Performance Mode (`composition_plan`)** with honest isolation notices and approved-recipe matching (`find_approved_native_recipes`). Phase 05.2 MIDI Performer (`session_layer_action`) is invoked **only on explicit MIDI opt-in**.
  - `engine/production/taste_profile.py` & `engine/session_lab/library.py`: Recorded Phase 05.1 positive and Phase 05.2 SF3 rejection feedback; preserved Phase 05.2 SF3 assets marked `poor` for comparison; stored 8 new YuE2 Native Performance Recipes (`A`–`H`) as `unused` until user listening approval.
- **YuE2 Native Audio Reliability & Dual Vocal QA:**
  - `engine/generation/adapters/yue2_adapter.py`: Added Runtime-Registry-loaded local **PANNs MobileNetV1 AudioSet (527-class)** classifier corroborating Demucs `htdemucs` vocal stems (`PASS` / `UNCERTAIN` / `REJECT`), custom `nativePerformance` ABC compilation, and instrumental ABC section normalization (`% verse`/`% chorus`/`% bridge` → `% intro`/`% instrumental`/`% interlude`/`% outro`) to eliminate YuE2 humming/speech leakage.
  - `engine/sound_design/advisor.py`: Fixed `diagnose_track_audio()` to render from each track's first clip position instead of beat `0.0`.
- **Deliverables (`docs/production-tests/PHASE_053_NATIVE_PERFORMANCE_LAB.md`):**
  - Saved DAW Project: **`Native Performance Lab 001`** (`outputs/daw/projects/proj_bdb68c87bd/`, 8 sequential non-overlapping tracks `01`–`08`, 8 section markers, non-destructive EQ/Room, up-to-date `Studio Preview`).
  - 8 standalone 48 kHz Stereo 24-bit listening WAVs under `outputs/exports/Native_Performance_Lab_001/listening/` (`01_Funk_Guitar_Riff.wav` … `08_Musical_Bridge.wav`), untouched YuE2 originals under `originals/`, and complete JSON provenance under `metadata/`.
  - Vocal QA results: **7 `PASS`** (A, B, C, D, F, G, H) and **1 `UNCERTAIN`** (E: borderline PANNs `Speech 0.234`, flagged for human listening).
  - Live Browser QA (`http://127.0.0.1:8796`): **`0` console / page / HTTP 4xx-5xx errors**, verified all 8 tracks, waveforms, Device Rack EQ, `STUDIO PREVIEW` badge, Play/Stop, and reload persistence.

## Local Environment Truth (Current Host: Apple M5, 24 GiB RAM)

- **Verified & Live:** YuE2 Metal (`yue2.cpp e646d52`, `YuE2-3B-Q8_0.gguf` + `YuE2-Vae-F32.gguf`, `GENERATION_VERIFIED`), Demucs `htdemucs` MPS + local PANNs MobileNetV1 527-class AudioSet corroborator, Pedalboard `0.9.26`, FluidSynth `2.6.3` + `MuseScore_General.sf3` (explicit MIDI opt-in only), Basic Pitch `0.4.0` ONNX, **104-tool MCP Server**, Studio Preview & 48 kHz 24-bit WAV Renderer.
- **Genuinely Uninstalled / Optional:** `SheetSage2`, `YourMT3+`, `All-In-One`, `REAPER.app`.

## Next Priorities

1. **Direct User Listening Evaluation (Phase 05.3 Gate):** User auditions `01_Funk_Guitar_Riff.wav` … `08_Musical_Bridge.wav` (including manual vocal check on `05_Drum_Percussion_Groove.wav`) and promotes only approved recipes in `outputs/daw/session_library.json` to `userRating="good"`.
2. **Post-Approval Evolution:** Only after musical quality is confirmed on approved recipes, explore Demucs stem extraction / hybrid layering / full-song arrangement built from approved Native Audio takes.
3. **Phase 06 (AI Mixing & Mastering):** Multi-track masking diagnosis, bus mastering chain, and level-matched reference A/B.
