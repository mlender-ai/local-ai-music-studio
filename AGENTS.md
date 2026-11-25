# AGENTS.md — AI-Native DAW Shared Engineering Directive

All development agents (Antigravity, Claude Code, Codex, and others) MUST read this file and `docs/STATUS.md` before starting any task.

## 1. Product Goal

Transform `local-ai-music-studio` into **AI-Native DAW** — a local-first macOS desktop music studio combining Ableton Live / Logic Pro timeline, Device Rack, and mixing workflows with a natural-language AI Producer.

- Music and the Arrangement Timeline are the center of the product.
- AI acts as an assistive producer through a shared Command System, never as a replacement for direct editing.
- Never fabricate waveforms, EQ curves, GR meters, sidechain pumping, MIDI notes, stems, or AI audio outputs.

## 2. Current Phase

- **Active Phase:** **Phase 03.2.1 + Phase 05 — Reference Fidelity · Professional Instruments · Professional FX · Native Audio Recovery · AI Sound Design** (`docs/phases/PHASE_05.md`)
- **Integration Branch:** `develop/ai-native-daw`
- **Stacked Phase 03.2.1 + Phase 05 PR Chain (open & unmerged pending user review):**
  1. `feat/daw-reference-fidelity` (PR #24 → `feat/daw-advanced-reference-intelligence`)
  2. `fix/daw-native-audio-runtime` (PR #25 → `feat/daw-reference-fidelity`)
  3. `feat/daw-professional-instruments` (PR #26 → `fix/daw-native-audio-runtime`)
  4. `feat/daw-professional-fx` (PR #27 → `feat/daw-professional-instruments`)
  5. `feat/daw-phase05-integration` (PR #28 → `feat/daw-professional-fx`)
- Read `docs/STATUS.md` for live progress and `docs/HANDOFF.md` for the latest handoff context.

## 3. Repository Map

| Path | Role |
|---|---|
| `apps/daw/` | React + TypeScript + Vite DAW frontend (Timeline + Chord Track + Take Lanes + FX pills, Instrument/FX Browsers with WAV preview, Device Rack with live RBJ EQ/Comp/Reverb/Amp/Sends/Freeze/Diagnosis, Mixer with Return Buses, Audio Engine with Frozen Studio WAV playback & Studio Server Export, AI Producer) |
| `engine/daw_workspace/` | Python DAW backend (Project persistence v1.5.0, Shared Command System with `instrument.*`/`fx.*`/`bus.*`/`send.*`/`automation.*`, 3-Pass Studio Renderer, BS.1770-4 loudness, staged proposals, 81 MCP tools) |
| `engine/instruments/` | Phase 05 Professional Instruments: FluidSynth 2.6.3 SF3 (`MuseScore_General.sf3`, MIT) multi-sampled engine, Pro Hybrid Analog/FM/Supersaw Synth (`Pedalboard LadderFilter`), Drum Rack with true Hi-Hat Choke Groups & Round-Robin, Transient-Slicing Sampler, Crash-Isolated AU/VST3 Host Plugin Scanner |
| `engine/fx/` | Phase 05 Professional FX: 6-Band Spotify Pedalboard Parametric EQ + exact RBJ analytical curve, Studio Compressor + real GR metering, **True External-Track Sidechain Compressor**, Limiter/Gate/Transient Shaper, 6-Mode Convolution IR Reverb, Tempo-Synced Delay/Mod/Saturation/PitchShift, Tube Guitar Amp + Speaker Cab IRs, Automated Filter/Parameter Curves, Deterministic `stateHash` Track Freeze |
| `engine/sound_design/` | Phase 05 AI Producer Sound Design Advisor (`diagnose_track_audio`, natural-language FX/Instrument/Sidechain/Automation planner, real Before/After acoustic delta comparison) |
| `engine/transcription/` | Phase 03.2 + 03.2.1 Reference Fidelity (`Basic Pitch ONNX`, `Demucs htdemucs` MPS, full-length 11-class Drum Event Schema & `variationMap`, 15-quality Viterbi Chord Tracker with 1-beat passing chords, Acoustic `SoundProfile`/`SpatialProfile`, full-length Bass Performance, Blueprint v3, Multi-Reference `featureSourceMap`, honest 5-category instrumentation) |
| `engine/runtime/` | Shared Runtime Registry (`~/.config/ai-native-daw/runtime.json`) with honest 6-state lifecycle across Pedalboard, FluidSynth SF3, Demucs, Basic Pitch, YuE2, ACE-Step, SheetSage2, and Editable MIDI |
| `engine/generation/` | Job Manager, Process-Group Guard, Safe Take Apply, V7.2 Golden Native Reference & Hybrid Layering (`native_audio_original` protection), Demucs-isolated Multi-Window Vocal Leakage Gate (`PASS`/`REJECT`/`UNCERTAIN`), Post-Generation Per-Bar Feature Verification |
| `engine/arrangement/` | Phase 04 Selective Arrangement, Musical Variations, Non-Destructive Audio Reverse, Contextual A/B Previews, Timeline Take Lanes & Comping, Project Music Memory |
| `app/daw_server.py` | FastAPI DAW HTTP + SSE server (`127.0.0.1:8796`, serves API + built frontend + 48 kHz Studio WAV export) |
| `app/mcp_server.py` | FastMCP STDIO server exposing **81 tools** (`9 music.*` + `72 daw.*`) |
| `THIRD_PARTY_NOTICES.md` | Open-source license, SHA-256 checksum, and commercial-use audit table |
| `scripts/start_daw.sh` | Single-command launcher for DAW backend + frontend |
| `docs/` | Shared product, design, architecture, project format (`v1.5.0`), status, handoff, phase specs (`PHASE_01`–`PHASE_05`), and screenshots |

## 4. Development Commands

```bash
# Python environment (Python 3.11–3.12 via uv)
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e . pytest httpx python-multipart pedalboard pyfluidsynth

# Frontend dependencies & build
cd apps/daw && npm install && npm run build

# Run complete DAW app (serves built UI + API on http://127.0.0.1:8796)
./scripts/start_daw.sh

# Verification tests
.venv/bin/python -m pytest -q             # Full backend + Gate 1–7 real music production tests
cd apps/daw && npm test && npm run build  # Frontend unit tests + TypeScript build
```

## 5. Git Collaboration Rules

- **NEVER** force push, delete existing branches, run `git reset --hard`, or overwrite uncommitted work.
- **NEVER** auto-merge into `main` or `develop/ai-native-daw` before user review.
- **NEVER** commit model weights, `.venv/`, `outputs/` (including `outputs/daw/soundfonts/` and `outputs/daw/cache/ir/`), `node_modules/`, `dist/`, personal paths, or credentials.
- Work in small, verifiable commits on dedicated task branches.

## 6. Code & Architecture Conventions

- Every project state mutation MUST pass through the Shared Command System (`apps/daw/src/commands/` and `engine/daw_workspace/commands.py`).
- Keep unit types strictly separated: `beats`, `seconds`, `samples`, `bars`, `ticks` (`PPQ = 480`). See `docs/PROJECT_FORMAT.md`.
- Keep Realtime Preview (`Web Audio API` + bit-exact Frozen Studio WAV playback) and Offline Stereo WAV Export (`POST /api/projects/{id}/export/studio-wav` 3-pass Pedalboard/FluidSynth studio render) aligned to the exact same project schema (`v1.5.0`).
- Keep original audio/MIDI/native studio assets immutable; all timeline & sound design edits are non-destructive and undoable.

## 7. Verification Standards

A task is NEVER complete on static code or text tests alone:
1. Run full backend `pytest` (including real-audio DSP/instrument/FX & production Tests A–E) and frontend `npm test` + `npm run build`.
2. Verify real rendered 48 kHz Stereo WAV loudness (BS.1770-4), spectral response, sidechain/choke-group behavior, zero clipping, and persistence round-trip.
3. Inspect the live app in a real browser at `1440×900` and `1280×800` across key states and attach verified screenshots to PRs.
4. Update `docs/STATUS.md`, `docs/HANDOFF.md`, and `docs/phases/PHASE_XX.md` before ending a session.
