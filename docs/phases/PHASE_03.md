# PHASE 03 · AI COMPOSITION ENGINE

**Branch:** `feat/daw-ai-composition-phase-03` (stacked on `feat/daw-agent-bridge` / PR #19)  
**Schema Version:** `1.2.0`  
**Status:** Implemented & Verified (`51` pytest + `11` vitest + live Korean browser QA)

## Architecture Summary

### 1. Phase 03-A — Reference Intelligence & Bridge Hardening
- **`engine/daw_workspace/loudness.py`**: Pure NumPy/SciPy ITU-R BS.1770-4 loudness metering (K-weighting Stage-1 high shelf + Stage-2 RLB highpass, 400ms 75%-overlap absolute `-70 LKFS` & relative `-10 LU` gated Integrated LUFS, 3.0s Short-Term Max/Median & LRA, plus 4× polyphase oversampled True Peak `dBTP`).
- **`engine/daw_workspace/analysis.py` (v3.0.0) & `comparison.py`**: Explicit half-time / double-time BPM octave resolution (`resolve_octave_tempo_relation`), bass-weighted harmony chroma, honest separation of `harmonicRepetitionScore` vs `melodicMotifStatus: "not_transcribed_in_dsp_mode"`, and explicit `unconfirmed` status for HPSS instrument confidence `< 0.35`.
- **Bridge Safety:** All 9 MCP edit tools default to `stage_only=True`; SSE auto-resyncs project & proposals on reconnect; verified cross-process STDIO MCP client in `tests/test_mcp_subprocess.py`.

### 2. Phase 03-B — AI Producer Provider Adapter
- **`engine/providers/{base,registry}.py`**: Compact `build_producer_context()` and live honest detection for `local-music-director`, `mcp-external`, `ollama`, `claude-cli`, `codex-cli`, and env-only `custom-api` (`DAW_LLM_BASE_URL` / `DAW_LLM_API_KEY`). Zero credentials stored in browser or Git; zero unapproved paid API calls.

### 3. Phase 03-C — Composition Director & MIDI Composer
- **`engine/composition/{schemas,reference_context,director,midi_composer,validation,library}.py`**:
  - Genre-adaptive `CompositionPlan` supporting House, Lo-fi, Synthwave, Hip-Hop, Ambient, and Pop with dynamic section layouts (never hardcoded 48 bars).
  - Traceable `ReferenceBinding` recording exact `appliedFeatures` vs `unmappedFeatures` from selected `ReferenceBlueprint` toggles.
  - Motif-based MIDI Composer generating Drums, Bass, Synth Hook (Motif A → A' → B → Cadence), Keys, Guitar, and Pad + standard SMF `.mid` export + musical validation.
  - Cached Sample & Loop Library catalog with BPM compatibility flags against active project BPM.

### 4. Phase 03-D/E — Multi-Timbre Voices & Generation Adapters
- **6 Studio Multi-Timbre Voices** mirrored in `engine/instruments/synth_engine.py` and `apps/daw/src/audio/instruments.ts`, selectable in Track Headers and Piano Roll via `track.setInstrument`.
- **Adapters (`engine/generation/adapters/`)**:
  - `local_composer_adapter.py`: Mode A (`local-multitrack-composer`), Mode B (`instrument-session`), Mode C (`loop-midi`) — honestly labeled, never pretending to be YuE2.
  - `yue2_adapter.py`: Real probe for `.runtime/v4/yue2cpp/build/yue-synth` / `YUE2_BIN`, `check_resting_voice()` ABC gate, YuE2 request builder, and vocal-leakage screen.
  - `acestep_adapter.py` & `stem_separator.py`: Real probes for ACE-Step checkpoints & Demucs (`htdemucs`, muting Original Mix to prevent double-summing). Report `available: false` honestly when uninstalled.

### 5. Phase 03-F/G — Job Manager, Takes, UI & 54 MCP Tools
- **`engine/generation/daw_jobs.py`**: Single-worker `GenerationJobManager`, persisted `Take` store, `-16 LUFS` level-matched preview audition, Planned vs Detected section distinction, and single-transaction Revision-checked Undoable Take Apply (`new_tracks`, `selected_range`, `new_project`, `keep_take`, `reject`).
- **`app/mcp_server.py`**: 17 new Phase 03 `daw.*` tools added alongside 9 legacy `music.*` + 28 Phase 02 `daw.*` tools (= 54 total).
- **`apps/daw/src/producer/AIProducerPanel.tsx`**: Conversational Korean/English Producer UI with `작곡 · 대화`, `Take`, and `엔진 · 상세` tabs and collapsible Developer Details.

## Evidence Screenshots
- `docs/screenshots/phase-03-take-card-1440x900.png`
- `docs/screenshots/phase-03-hook-piano-roll-engines-1440x900.png`
- `docs/screenshots/phase-03-compact-1280x800.png`
