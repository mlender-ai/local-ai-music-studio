# STATUS.md — Current Development Status

**Last Updated:** 2026-11-28  
**Active Phase:** **Phase 05.3 — Native Musical Performance Lab (YuE2 Performance Diversity · Dual-Model Vocal QA · Native Performance Policy)** — **Experiments A–H Complete & Verified (User Listening Pending)**  
**Integration Branch:** `develop/ai-native-daw` (unmerged pending user review)  
**Stacked Task Branches (all pushed, open & unmerged pending user review):**
1. `feat/daw-workspace-phase-01` (PR #15 → `develop/ai-native-daw`)
2. `fix/daw-phase-01-1-stabilization` (PR #16 → `feat/daw-workspace-phase-01`)
3. `feat/daw-korean-localization` (PR #17 → `fix/daw-phase-01-1-stabilization`)
4. `feat/daw-reference-intelligence` (PR #18 → `feat/daw-korean-localization`)
5. `feat/daw-agent-bridge` (PR #19 → `feat/daw-reference-intelligence`)
6. `feat/daw-ai-composition-phase-03` (PR #20 → `feat/daw-agent-bridge`)
7. `fix/daw-phase-03-engine-integration` (PR #21 → `feat/daw-ai-composition-phase-03`)
8. `feat/daw-phase-04-arrangement` (PR #22 → `fix/daw-phase-03-engine-integration`)
9. `feat/daw-advanced-reference-intelligence` (PR #23 → `feat/daw-phase-04-arrangement`)
10. `feat/daw-reference-fidelity` (PR #24 → `feat/daw-advanced-reference-intelligence`) — GATE 1 Reference Fidelity
11. `fix/daw-native-audio-runtime` (PR #25 → `feat/daw-reference-fidelity`) — GATE 2 Native Audio Lineage & Vocal Leakage Gate
12. `feat/daw-professional-instruments` (PR #26 → `fix/daw-native-audio-runtime`) — GATE 3 Professional Instruments
13. `feat/daw-professional-fx` (PR #27 → `feat/daw-professional-instruments`) — GATE 4 Professional FX
14. `feat/daw-phase05-integration` (PR #28 → `feat/daw-professional-fx`) — GATE 5–7 Device Rack UI, AI Sound Design & 81 MCP Tools
15. `feat/daw-yue2-native-production` (PR #29 → `feat/daw-phase05-integration`) — Phase 05.1 YuE2 First Native Engine, Permanent Production Policy, Studio Preview Parity & 88 MCP Tools
16. `feat/daw-ai-session-loop-production` (PR #30 → `feat/daw-yue2-native-production`) — Phase 05.2 AI Session & Loop Infrastructure (`SessionContext`, Layer Protection, Take Lanes, Studio Session Library, 104 MCP Tools; SF3/MIDI audio output rejected on user listening)
17. **`experiment/yue2-native-performance-lab` (→ `feat/daw-ai-session-loop-production`) — Phase 05.3 Native Musical Performance Lab, Native Performance Mode Policy, Demucs+PANNs Dual Vocal QA & 8 YuE2 Performance Experiments (A–H)**

## Completed in Phase 05.3

- [x] **Permanent Native Performance Policy & Taste Feedback Sync (Sections 18–20):**
  - Updated `config/production/default_policy.json` (`schemaVersion: 2`), `config/production/engine_routing.json`, `engine/daw_workspace/proposals.py`, `app/daw_server.py`, and `engine/generation/daw_jobs.py` so general performance requests (`"기타 리프 만들어줘"`, `"피아노 솔로 만들어줘"`, `"독특한 드럼 그루브 만들어줘"`, `"베이스 리프 만들어줘"`, `"브릿지 만들어줘"`) default to **YuE2 Native Performance Mode (`yue2-native`)** with honest isolation notices.
  - Preserved Phase 05.2 `SessionContext`, Layer Protection, Take Lanes, and Session Library infrastructure while restricting MIDI Performer strictly to **explicit MIDI opt-in** prompts.
  - Synced Phase 05.1 positive and Phase 05.2 SF3 rejection feedback into `engine/production/taste_profile.py` / `outputs/daw/taste_profile.json`, marked Phase 05.2 SF3 library assets `poor` (retained for comparison), and stored 8 new unrated (`unused`) Native Performance Recipes in `outputs/daw/session_library.json` with `find_approved_native_recipes()` reuse gating.
- [x] **YuE2 Instrumental Vocal-Leakage Fix & Dual-Model Vocal QA (`yue2_adapter.py`, `advisor.py`):**
  - Integrated cached local **PANNs MobileNetV1 AudioSet (527-class)** classifier dynamically via Runtime Registry alongside Demucs `htdemucs` (`demucs_plus_panns_corroborated`), cleanly separating melodic guitar bleed (Exp G: `PASS`) from real humming/speech leakage (prior `% verse`/`% chorus`/`% bridge` attempts: `REJECT`).
  - Normalized instrumental ABC section markers (`% verse`/`% chorus`/`% bridge` → `% intro`/`% instrumental`/`% interlude`/`% outro`) after proving vocal section headers trigger YuE2 humming leakage (`Humming 0.93` → `-42.4 dBFS PASS`).
  - Fixed `diagnose_track_audio()` to render from each track's first clip position instead of hardcoded beat `0.0`.
- [x] **8 Pure YuE2 Native Audio Performance Experiments (`Native Performance Lab 001` · `proj_bdb68c87bd`):**
  - Generated, diagnosed, minimally treated (non-destructive EQ/Room), and exported 8 separate 48 kHz Stereo 24-bit listening WAVs (`01_Funk_Guitar_Riff.wav` … `08_Musical_Bridge.wav`) plus untouched `originals/` and full `metadata/` JSON logs (`docs/production-tests/PHASE_053_NATIVE_PERFORMANCE_LAB.md`).
  - **7 of 8 `Vocal QA: PASS`** (A, B, C, D, F, G, H) and **1 `UNCERTAIN`** (E: borderline PANNs `Speech 0.234`, flagged honestly for human verification). Zero MIDI/SoundFont substitution.

## Verification Status

- **Backend Regression Suite (`pytest`):** **`26 passed`** (`0 failed`) across Phase 05.2/05.3 routing, Phase 05.1 native production, Phase 04 arrangement, Phase 03 composition, and Agent Bridge.
- **Frontend (`vitest`):** **`14 passed`** (`0 failed`).
- **Live Browser QA (`http://127.0.0.1:8796`):** Verified `Native Performance Lab 001` (`proj_bdb68c87bd`, `102.00 BPM`, `4/4`, 8 sequential non-overlapping tracks `01`–`08`, 8 section markers, waveforms, Device Rack non-destructive EQ, green `STUDIO PREVIEW` up-to-date badge, transport Play/Stop, full reload persistence, and **`0` console / page / HTTP 4xx-5xx errors**).

## Honest Host Limitations & Next Gate

- **Subjective Musicality:** Strictly **`UNVERIFIED`** until direct user listening of `01_Funk_Guitar_Riff.wav` … `08_Musical_Bridge.wav`.
- **Experiment E Vocal QA:** `UNCERTAIN` (`PANNs mix Speech=0.234`) — awaiting manual listening confirmation.
- **YuE2 Single-Instrument Isolation:** Full-band/featured-ensemble Native Audio is live and default; accompaniment-free isolated YuE2 stems remain `UNSUPPORTED` (Demucs stem extraction carries bleed/quality-loss risk).
- **Deferred:** Phase 06 (AI Mixing & Mastering Automation), Phase 07 (Vocal Synthesis & Lyrics).
