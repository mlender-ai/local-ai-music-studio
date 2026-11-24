# ARCHITECTURE.md — AI-Native DAW & Local AI Music Studio

## System Overview

```text
+----------------------------------------------------------------------+
| Browser DAW Workspace (React + TypeScript + Vite, apps/daw/)         |
|  - Workspace Shell (Browser, Transport, Timeline, Bottom Dock, AI)   |
|  - Shared Command Dispatcher + Undo/Redo History                     |
|  - Web Audio Realtime Engine (AudioClock scheduler + Analyser meters)|
|  - Shared OfflineAudioContext Stereo WAV Renderer                    |
+-------------------------------+--------------------------------------+
                                | REST JSON + Range Audio Streams
                                v
+----------------------------------------------------------------------+
| Python DAW Backend (app/daw_server.py + engine/daw_workspace/)       |
|  - Port: 127.0.0.1:8796 (does not conflict with legacy player :8795) |
|  - Atomic Project Store (outputs/daw/projects/<id>/project.json)     |
|  - Immutable Asset Store (audio/, midi/, references/) + SHA-256      |
|  - Real PCM Waveform Peak Cache (cache/waveforms/<sha256>.json)      |
|  - Standard MIDI File (.mid) Parser & Writer                         |
|  - Server-side Shared Command Executor (for MCP / external agents)   |
|  - Deterministic Python Offline WAV Renderer (QA & headless render)  |
+-------------------------------+--------------------------------------+
                                | Adapters (Future Phases)
                                v
+----------------------------------------------------------------------+
| Existing Local AI Music Studio Assets (Preserved)                    |
|  - engine/generation/ (ACE-Step MLX/MPS worker + memory supervisor)  |
|  - engine/dsp/ (RBJ EQ, compressor, convolution reverb, limiter)     |
|  - engine/store.py & engine/jobs.py (SQLite version graph & jobs)    |
|  - app/player/server.py (:8795) & app/mcp_server.py (FastMCP STDIO)  |
|  - REAPER Bridge Adapter Interface (engine/daw_workspace/reaper.py)  |
+----------------------------------------------------------------------+
```

## Key Architectural Decisions (Phase 01)

### 1. Realtime Preview vs. Offline Render Parity
Both Realtime Playback and Offline Stereo WAV Export consume the exact same `Project` state and `scheduleProjectGraph()` scheduling math:
- **Realtime Preview (`apps/daw/src/audio/audioEngine.ts`):** Uses a Web Audio `AudioContext` with lookahead scheduling, per-track `GainNode` + `StereoPannerNode` + `AnalyserNode`, master `GainNode` + `AnalyserNode`, and polyphonic Web Audio synthesizer for MIDI tracks. Playhead position is computed strictly from `audioContext.currentTime - anchorTime` to prevent UI/audio drift.
- **Offline Render (`apps/daw/src/audio/offlineRenderer.ts` & `engine/daw_workspace/renderer.py`):** Renders the full edited timeline (clip positions, non-destructive source offsets, trims, loops, clip gain, track gain/pan, mute/solo resolution, MIDI note synthesis, master gain) into 48 kHz Stereo PCM WAV. The browser renderer saves exported WAVs back to `outputs/daw/projects/<id>/exports/` and triggers local download; the Python renderer enables headless verification and CLI/agent export.
- **No Double Playback:** REAPER is never started concurrently with Web Audio preview; REAPER integration is isolated behind a future offline host render adapter (`reaper.py`).

### 2. Local-First Persistence & Path Safety
- All DAW projects live under `DATA/daw/projects/<project_id>/` (`DATA` defaults to `<repo>/outputs`, configurable via `MUSIC_DATA_DIR`).
- Every write to `project.json` writes to a sibling temporary file, flushes + `fsync`s, and atomically replaces `project.json` via `os.replace()`.
- Original imported audio and MIDI files are immutable and referenced by relative paths (`assets/audio/...`, `assets/midi/...`) so project folders are portable.
- Symlink escapes and path traversal outside allowed directories are rejected with HTTP 400.

### 3. Shared Command System (UI + Backend + Future AI Agents)
- All project mutations flow through typed commands (`track.add`, `clip.move`, `clip.split`, `midi.addNote`, etc.) with identical schemas in TypeScript (`apps/daw/src/commands/`) and Python (`engine/daw_workspace/commands.py`).
- Transport commands (`transport.play`, `transport.seek`, etc.) do not enter Undo/Redo history.
- The AI Producer Panel publishes live `SelectionContext` (`selectedTrackId`, `selectedClipIds`, `timeRangeBeats`, `sectionId`) so future Phases 02–04 and MCP agents can target exact musical regions without altering core state primitives.

### 4. Preserved Legacy Engine Boundaries
The initial Local AI Music Studio prototype remains intact and tested:
- `engine/generation/backend.py`, `worker.py`, `supervisor.py`, `mlx_quantized.py` (ACE-Step 2B Turbo, MLX 4-bit DiT + MPS bf16, 10 GiB memory guard)
- `engine/dsp/` (RBJ EQ, compressor, reverb, saturation, limiter)
- `engine/store.py`, `engine/jobs.py`, `engine/service.py`
- `app/cli.py`, `app/mcp_server.py`, `app/player/server.py` (port `8795`)
- Note: Experimental branches (`codex/ai-daw-production-engine`, `codex/v7-2-house-hook-first`, `codex/v7-3-indie-experimental-rock`, `codex/v7-3-acoustic-lift`) remain untouched as open PRs; verified music outputs (e.g. V7.2 Magnetic Afterhours) are imported as immutable assets via `scripts/seed_daw_demos.py`. See `docs/decisions/0001-phase-01-architecture.md`.
