# PHASE 01.1 + PHASE 02 · Stabilization, Korean Localization, Reference Intelligence & Agent Bridge

## Acceptance Checklist

### Phase 01.1 — Workspace Stabilization (`fix/daw-phase-01-1-stabilization`)
- [x] Project `revision` (`schemaVersion: 1.1.0`), v1.0.0 migration, file-locked atomic saves, HTTP `409 REVISION_CONFLICT` guard.
- [x] Non-clobbering save-in-flight state, Undo-to-saved-state fingerprint matching, unsaved switch/unload guard.
- [x] Shared Realtime + Offline scheduling rules (`apps/daw/src/audio/scheduler.ts`) and full **MIDI Chase**.
- [x] Per-asset decode status tracking, failed-cache eviction, Retry & Relink UI, Export guard for broken audible assets.
- [x] Last-project & workspace state restoration (`localStorage`) and smart build freshness detection in `scripts/start_daw.sh`.

### Phase 01.2 — Korean Localization (`feat/daw-korean-localization`)
- [x] Korean default UI (`apps/daw/src/i18n/locales/ko.json` & `en.json`) with persistent `KO / EN` switcher.
- [x] Preserved industry terms (`BPM`, `MIDI`, `EQ`, `FX`, `Gain`, `Pan`, `Loop`, `Snap`, `Mute / Solo`, `WAV`, `LUFS`, `VST3`, `AU`, `AI Producer`).
- [x] Korean IME composition safety across global shortcuts and all inline text inputs.
- [x] Verified clean `1440×900` and `1280×800` Korean desktop layouts (`내보내기` right edge `1272px <= 1280px`).

### Phase 02-A & 02-C — Reference Intelligence & Comparison (`feat/daw-reference-intelligence`)
- [x] Reference audio & video ingestion (`WAV/MP3/FLAC/OGG/AIFF/M4A/MP4/MOV`) + safe external URL metadata probe with honest audio-required notice.
- [x] Automatic exclusion of Reference audio from Stereo WAV Export.
- [x] Real acoustic analysis pipeline (Rhythm/BPM/Swing, Chroma Key/Mode/threshold-gated Chords, Novelty Sections + Energy Curve, 6-band Welch PSD + Dynamics + Stereo, HPSS Instrument presence estimates) with disk cache & cancellable background job.
- [x] Structured `ReferenceBlueprint` with user-selectable influence toggles saved per reference.
- [x] Normalized 4-phase Reference vs Project/Asset Comparison with measured deltas and actionable observations (no fake single similarity score).

### Phase 02-B — AI Agent Bridge (`feat/daw-agent-bridge`)
- [x] Shared session registry (`outputs/daw/session.json`) sharing live Selection Context, Project ID, Revision, and Reference Blueprint across browser & MCP processes.
- [x] Complete agent-agnostic `daw.*` MCP tool suite (28 tools) added alongside preserved 9 `music.*` tools in `app/mcp_server.py`.
- [x] Staged Change Proposals (`preview_changes`, `apply_changes`, `reject_changes`) with Revision conflict check, Undo/Redo, and real-time SSE UI sync (`GET /api/events`).
- [x] Korean/English supported-command router (including bar-range split+clip-gain safety) with honest refusal for Phase 03–07 features.
