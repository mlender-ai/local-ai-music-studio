# HANDOFF.md — Multi-Agent Handoff

## Snapshot

- **Base Commit:** `a5085de` (`main`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Branches (all pushed, open & unmerged pending user review):**
  1–15. Phases 01–05.1 (`PR #15`–`PR #29`, latest base `feat/daw-yue2-native-production` @ `a124b21`)
  16. **`feat/daw-ai-session-loop-production` (HEAD → `feat/daw-yue2-native-production`) — Phase 05.2 AI Session & Loop Production, Musical Performance Intelligence, Layer Protection, Studio Session Library & 104 MCP Tools**

## Run Commands

```bash
# Single-command launch (starts http://127.0.0.1:8796)
./scripts/start_daw.sh

# Verification suites
.venv/bin/python -m pytest -v tests/test_phase052_session_loop.py tests/test_phase051_native_production.py
.venv/bin/python -m pytest -v tests/test_phase04_arrangement.py tests/test_phase03_composition.py tests/test_agent_bridge.py
cd apps/daw && npm test && npm run build

# MCP STDIO server (exposes 9 music.* + 95 daw.* = 104 tools)
.venv/bin/python -m app.mcp_server
```

## Phase 05.2 Architecture & Deliverables Summary

- **AI Session & Loop Engine (`engine/session_lab/`):**
  - `vocabulary.py`: Empirical GATE 0 YuE2 capability matrix (`full_band_instrumental: VERIFIED`; `solo_drums`/`solo_guitar`/`accompaniment_free_overdub: UNSUPPORTED`), Strategies A–E, and 6-family Performance Vocabulary.
  - `context.py`: Shared `SessionContext` builder (locked Chord Timeline, extracted kick/snare groove anchors, occupied pitch registers, motif memory) + SHA-256 **Layer Protection** (`Draft | Generated | Auditioned | Approved | Rejected | Locked`).
  - `performers.py`: Context-aware idiomatic performers for Drums (D1–D3), Bass (B1–B3), Keys/Rhodes (P1–P3), Guitar (G1–G3 with real smooth `pitchBendSemitones` ramps), Percussion (PC1–PC3 on `percussion-latin-studio` SF3 GM kit), Synth, 8-mode Variation, and Contrasting Bridge + 2-beat Transition.
  - `alignment.py`: Loop boundary & seam integrity, click-free bar-boundary trimming (`align_audio_loop_to_bars`), honest Tempo Drift blocking (`check_tempo_alignment`), jazz-tension-aware Harmonic Compatibility, and 5-Part Musical Quality Gate (Gate E `User Listening` always `UNVERIFIED`).
  - `library.py`: Persistent Studio Session Library (`outputs/daw/session_library.json`, 18 categories, Performance Recipes, user ratings/feedback linked into persistent Taste Profile).
  - `engine.py`: Single-layer, solo, bridge, transition orchestration with non-destructive Take Lane A/B switching (zero double-playing) and 3-mode level-matched previews (`solo`, `in_context`, `before_mix`).
- **Phase 05.1 Protections Strictly Maintained:**
  - Full-music prompts (`"인디 록 만들어줘"`, `"세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘"`) STILL route strictly to **`yue2-native`** with zero silent MIDI fallback and zero `PREVIEW` instruments in production.
  - FluidSynth SF3 pooling (`soundfont_engine.py`) + batched Drum Rack pre-warming (`drum_rack.py`) dramatically speed up multi-layer renders.
- **Validation Deliverables (Report: `docs/production-tests/PHASE_052_SESSION_LOOP_REPORT.md`):**
  - Saved DAW project: **`Late Night Sessions 001`** (`proj_1b410631f3`, 90 BPM, 4/4, D minor, 8-bar Main Groove + 4-bar Bridge + Transition, `Studio Preview` up-to-date).
  - Direct listening audio exports under `outputs/exports/phase052_late_night_sessions_001/` (Group A: 5 WAVs, Group B: 4 WAVs comparing Guitar Take A Funk vs Take B Clean, Group C: 5 WAVs covering Percussion, Guitar Solo, and Main Groove -> Transition -> Bridge).
  - Populated Studio Session Library (`outputs/daw/session_library.json`, 8 verified assets + recipes).
  - Live Browser QA (`http://127.0.0.1:8796`): **`0` console / page / HTTP 4xx-5xx errors**, verified 13 tracks, 12 Chord Track events, 2 Guitar Take Lanes, `STUDIO PREVIEW` badge & playhead advance, and full reload persistence.

## Local Environment Truth (Current Host: Apple M5, 24 GiB RAM)

- **Verified & Live:** YuE2 Metal (`yue2.cpp e646d52`, `GENERATION_VERIFIED` for full-band instrumental; `UNSUPPORTED` for solo isolated stems per GATE 0), Pedalboard `0.9.26`, FluidSynth `2.6.3` + `MuseScore_General.sf3` (pooled), Demucs `htdemucs` MPS, Basic Pitch `0.4.0` ONNX, **104-tool MCP Server**, Studio Preview & 3-Pass 48 kHz WAV Renderer.
- **Genuinely Uninstalled / Optional:** `SheetSage2`, `YourMT3+`, `All-In-One`, `REAPER.app`.

## Next Priorities

1. **User Listening Evaluation (Phase 05.2 Gate E):** User auditions Groups A, B, and C from `outputs/exports/phase052_late_night_sessions_001/` and opens `Late Night Sessions 001` in the live DAW to record ratings/feedback into the Studio Session Library & Taste Profile.
2. **Sample/Hybrid Guitar Loop Option (Strategy D):** Complement SF3 guitar solos/riffs with curated studio guitar samples/loops for higher acoustic nuance (vibrato/pick attack) when desired.
3. **Phase 06 (AI Mixing & Mastering):** Multi-track masking diagnosis, bus mastering chain, and level-matched reference A/B.
