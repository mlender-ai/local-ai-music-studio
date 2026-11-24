# STATUS.md — Current Development Status

**Last Updated:** 2026-11-24  
**Active Phases:** Phase 01.1 (Stabilization) + Phase 01.2 (Korean Localization) + Phase 02 (Reference Intelligence · Agent Bridge · Reference Comparison) — **Ready for Review**  
**Integration Branch:** `develop/ai-native-daw` (unmerged pending user verification)  
**Stacked Task Branches:**
1. `feat/daw-workspace-phase-01` (PR #15 → `develop/ai-native-daw`)
2. `fix/daw-phase-01-1-stabilization` (depends on PR #15)
3. `feat/daw-korean-localization` (depends on Phase 01.1)
4. `feat/daw-reference-intelligence` (depends on Phase 01.2)
5. `feat/daw-agent-bridge` (depends on Phase 02-A/C)

## Completed

- [x] **Phase 01.1 — Workspace Stabilization:**
  - Monotonic `revision` (`schemaVersion: 1.1.0`) with automatic `1.0.0 → 1.1.0` migration, file-locked atomic saves, and HTTP `409 REVISION_CONFLICT` optimistic locking.
  - Non-clobbering save-in-flight logic, structural fingerprint matching so Undo back to last-saved state restores `저장됨`, unsaved-changes confirmation guard, and `localStorage` restoration of last project / track / playhead / zoom / panels.
  - Shared `apps/daw/src/audio/scheduler.ts` uniting Realtime Preview and Offline Stereo WAV Export, full **MIDI Chase** for mid-note starts/seeks/loops, rapid Play/Stop click token protection, per-asset decode status + Retry/Relink recovery + Export block on broken audible assets, and smart source-hash build check in `scripts/start_daw.sh`.
- [x] **Phase 01.2 — Korean Localization:**
  - Korean default UI (`apps/daw/src/i18n/locales/ko.json` & `en.json`) with instant persistent `KO / EN` switcher in Transport Bar, preserving standard studio terms (`BPM`, `MIDI`, `EQ`, `FX`, `Gain`, `Pan`, `Loop`, `Snap`, `Mute / Solo`, `WAV`, `LUFS`, `VST3`, `AU`, `AI Producer`).
  - Full Korean IME composition safety (`isComposing` / `keyCode 229`) across global shortcuts and all inline inputs.
  - Verified clean single-line layout at both `1440×900` and `1280×800` (`내보내기` right edge `1272px <= 1280px`).
- [x] **Phase 02-A & 02-C — Reference Intelligence & Comparison:**
  - Audio & video reference import (`WAV/MP3/FLAC/OGG/AIFF/M4A/MP4/MOV` via `soundfile` / `ffmpeg` / macOS `afconvert`, preserving immutable originals) + safe public URL metadata probe (`audioAvailable: false` with honest audio-required notice).
  - Reference tracks stored in `project.references[]` and automatically excluded from final Stereo WAV Export.
  - Real acoustic analysis (`engine/daw_workspace/analysis.py`): unconstrained spectral-flux BPM candidates + half/double-time ambiguity, onset/beat grid, swing/groove, 12-bin Chroma Key/Mode + threshold-gated chords (`uncertain` when weak), multi-feature novelty sections + time-aligned Energy Curve, 6-band Welch PSD + dynamic range + stereo width/correlation, and HPSS spectral instrument presence estimates (explicitly separated from independent recordings/stems), with SHA-256 disk caching and single-worker cancellable background jobs.
  - Structured `ReferenceBlueprint` with user-toggleable musical influences + normalized 4-phase **Reference vs Project/Track Comparison** (no fake single similarity score).
- [x] **Phase 02-B — AI Agent Bridge:**
  - Shared session registry (`outputs/daw/session.json`) syncing active browser tab Selection Context, Project ID, Revision, and active Reference Blueprint to external MCP processes.
  - Added all 28 `daw.*` MCP tools to `app/mcp_server.py` (preserving all 9 legacy `music.*` tools intact): Read, Edit, Staged Change Proposals (`daw.preview_changes` / `apply_changes` / `reject_changes`), Undo/Redo, and Reference Analysis/Comparison.
  - Real-time SSE event stream (`GET /api/events`) pushing external agent updates and proposals to the live DAW UI without refresh, plus Korean/English supported-command router with honest refusal for Phase 03–07 features.

## Verification Status

- **Python tests (`pytest -q`):** `40 passed` (31 legacy + 4 Phase 01/01.1 + 2 Reference Intelligence/Comparison + 2 Agent Bridge/MCP + 1 revision/relink).
- **Frontend tests & build:** `10 passed` (Vitest) + clean `tsc -b && vite build`.
- **Test A (V7.2 Magnetic Afterhours Real Analysis):** Measured `127.9 BPM`, `F mixolydian`, `8 sections`, `-18.48 LUFS`, `Peak -1.64 dBFS` (exact match to `delivery.json`).
- **Test B (External Reference):** Audio/video import and URL metadata honesty verified in tests & UI; user-supplied external audio/video file analysis awaits user's own local file.
- **Test C (Agent Editing):** Verified end-to-end both in pytest (`test_agent_bridge.py` including bar-range split+clip-gain safety & MCP undo) and live browser QA (`드럼 트랙을 잠깐 뮤트해줘` → Staged Proposal → Live Apply → Revision bump → Undo + honest Phase 05 EQ/Reverb refusal).

## Known Unverified / Deferred Items

- User hands-on listening & subjective editing QA has not yet been performed (PRs remain open and unmerged).
- Phase 03 (AI Composition), Phase 04 (AI Arrangement regeneration), Phase 05 (FX Rack / AU / VST3 / REAPER host), and Audio Time-Stretch / Warp remain deferred.
