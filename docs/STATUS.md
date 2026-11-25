# STATUS.md — Current Development Status

**Last Updated:** 2026-11-25  
**Active Phase:** **Phase 03.2 · Advanced Reference Intelligence (Music Transcription · Reference Reconstruction · Reference-Conditioned Composition)** — **Complete & Verified on Real Audio & Live Browser QA**  
**Integration Branch:** `develop/ai-native-daw` (unmerged pending user verification)  
**Stacked Task Branches (all open & unmerged pending user review):**
1. `feat/daw-workspace-phase-01` (PR #15 → `develop/ai-native-daw`)
2. `fix/daw-phase-01-1-stabilization` (PR #16 → `feat/daw-workspace-phase-01`)
3. `feat/daw-korean-localization` (PR #17 → `fix/daw-phase-01-1-stabilization`)
4. `feat/daw-reference-intelligence` (PR #18 → `feat/daw-korean-localization`)
5. `feat/daw-agent-bridge` (PR #19 → `feat/daw-reference-intelligence`)
6. `feat/daw-ai-composition-phase-03` (PR #20 → `feat/daw-agent-bridge`)
7. `fix/daw-phase-03-engine-integration` (PR #21 → `feat/daw-ai-composition-phase-03`) — **Phase 03.1 Engine Recovery + GATE 2 Safe Take Apply**
8. `feat/daw-phase-04-arrangement` (PR #22 → `fix/daw-phase-03-engine-integration`) — **Phase 04 Selective Arrangement, Musical Variation, Take Lanes & Contextual Preview**
9. `feat/daw-advanced-reference-intelligence` (PR #23 → `feat/daw-phase-04-arrangement`) — **Phase 03.2 Advanced Reference Intelligence**

## Completed in Phase 03.2

- [x] **Real Local Transcription & Stem Separation Engines Installed & Live-Verified on Apple M1 (16 GiB RAM):**
  - **Spotify Basic Pitch `0.4.0` + ONNX Runtime (`nmp.onnx`, Apache-2.0):** Runs without TensorFlow or FFmpeg; verified live on studio Bass, Guitar/Keys, and 96s V7.2 master (`2.20s`, `312 MB RSS`).
  - **Demucs `4.1.0` + PyTorch MPS (`htdemucs`, MIT):** Runs via clean `soundfile` + MPS subprocess runner (`engine/generation/adapters/_demucs_runner.py`, zero FFmpeg required) under `run_cancellable_guarded()` with content-addressed stem caching.
  - **Honest Audit of Additional Models:** `SheetSage2` (`CC BY-NC 4.0` non-commercial license + ~3 GiB `MERT-v2`), `YourMT3+`, and `All-In-One` remain honestly labeled `uninstalled` in Shared Runtime Registry while `sheetsage_adapter.py` builds validated YuE2 Instrumental ABC scores passing `check_resting_voice()`.
- [x] **Unified Sequential Transcription Package (`engine/transcription/`):**
  - `basic_pitch_transcriber.py`: Polyphonic MIDI transcription with pitch bends, quantization + microtiming offset preservation, monophonic Bass cleaner, and Lead Melody topline extraction.
  - `drum_transcriber.py`: Multi-band Kick (`36`), Snare (`38`), Closed Hat (`42`), Open Hat (`46`), Percussion (`45`) groove extractor preserving BOTH raw & quantized MIDI, swing ratio, syncopation score, 16-step accents, fill bars, and 2-bar groove templates.
  - `chord_tracker.py`: Sub-bar (2-beat slice) Viterbi-smoothed chord & bass-inversion analyzer across 84 chord templates + symbol parser.
  - `pipeline.py`: Sequential Apple Silicon transcription pipeline (`transcribe_reference_audio`), stem-enriched Arrangement Map (`activeStems`/`enteredStems`/`exitedStems`), **Reference Blueprint v2** (`blueprintVersion: "2.0.0"`), **10-feature Reference Feature Lock Matrix** (`free | reference | locked | unsupported`), and **Mode A Reconstruct** (`reconstruct_reference_to_project`) with 1-click Undo.
- [x] **Editable Timeline Chord Track (Schema `1.4.0`):**
  - Added `ChordEvent`, `project.chordTrack`, `project.chordTrackLocked`, and shared commands `chord.setTrack`, `chord.upsert`, `chord.delete`, `chord.setLocked` mirrored in Python & TypeScript.
  - Rendered pixel-aligned 22px **Timeline Chord Track** right beneath Section Markers supporting sub-bar chord changes, click-to-edit inline symbols, and lock toggle (`🔒`).
- [x] **Real Reference-Conditioned Composition & Post-Generation 5-State Feature Verification:**
  - Upgraded `reference_context.py`, `director.py`, and `midi_composer.py` to consume sub-bar `chordTimeline`, `drumGroovePattern`, `bassGroovePattern`, and locked `project.chordTrack` while generating fresh melodies in Mode B (`reference_compose`) & Mode C (`reinterpret`).
  - Upgraded `yue2_adapter.py` to auto-wire validated Blueprint v2 instrumental ABC scores.
  - Implemented real post-generation verification (`_verify_consumed_reference_features` in `local_composer_adapter.py`) measuring exact note-level `chordMatchRatio` and `grooveHitMatchRatio` while strictly keeping unconsumed MIDI features (`stereoWidthTarget`, `spectralCentroidTargetHz`) `consumed: false, verified: false`.
- [x] **REST API, Korean Natural-Language Routing & 68 MCP Tools:**
  - Added 7 REST endpoints (`/transcribe`, `/stems/{role}/audio`, `/locks`, `/reconstruct`, `/abc`, `GET/PUT /chords`) and Korean NL routing for transcription, chord import, reconstruction, and feature-locked composition.
  - Expanded `app/mcp_server.py` from 61 to **68 MCP tools** (`9 music.*` + `59 daw.*`).
- [x] **Live QA Bug Fixes Caught & Verified:**
  - Fixed macOS transient VM pressure false-kill in `process_guard.py` (now requires 3 consecutive sustained readings + `rss > 2 GiB`, and never swallows `RuntimeError`).
  - Fixed `halfDoubleRelation` object formatting in `ReferenceAnalysisPanel.tsx` (`half-time (63.9↔128) · pulse 128`, zero `[object Object]`).

## Verification Status

- **Python tests (`pytest -q`):** `69 passed` (all legacy + Phase 01/02/03/03.1/04 suites + real-audio Phase 03.2 **TEST A–E** + V7.2 real studio excerpt transcription + 68 MCP tools).
- **Frontend tests & build:** `13 passed` (Vitest, including `chord.*` commands & `ko.json`/`en.json` 1:1 key parity) + clean `tsc -b && vite build`.
- **Live Browser QA (`http://127.0.0.1:8796`):** Verified at **`1440×900`** and **`1280×800`** with **`0` console errors**, **`0` failed HTTP requests**, **`0` horizontal overflow**, and **`0` `[object Object]`** across real `v72_groove_8s.wav` precision transcription (`Demucs 4 stems` + `Basic Pitch` + `Chords`), inline chord editing, Timeline Chord Track import & lock, Mode B Reference Compose with 5-state Feature Verification badges, Mode A Session Reconstruct, and Runtime Registry honesty check. Screenshots saved in `docs/screenshots/phase-032-*.png`.

## Honest Host Limitations & Deferred Phases

- **Neural Full-Audio Generation (`YuE2` / `ACE-Step`):** Still genuinely uninstalled on this Mac (adapters, exact V7.2 CLI flags, YuE2 Blueprint v2 ABC auto-wiring, and `check_resting_voice()` gates are ready).
- **Deferred:** Phase 05 (FX Rack / EQ / Comp / Reverb / AU / VST3 / REAPER host), Phase 06 (AI Mixing & Mastering), Phase 07 (Vocal synthesis & lyrics).
