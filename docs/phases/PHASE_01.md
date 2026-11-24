# PHASE 01 · Workspace Foundation

## Objective

Build a real, local-first DAW workspace where users can create/open projects, import audio & MIDI files (including existing studio recordings like V7.2 Magnetic Afterhours), inspect real waveforms and MIDI notes on a musical timeline, play back synchronized multitrack audio with loop/seek/mixer controls, edit clips non-destructively, edit MIDI notes in a Piano Roll, save/reopen projects, and export edited Stereo WAV audio.

## Acceptance Checklist

- [x] **Project Management:** New, Open, Recent, Save, Save As, Rename, Autosave, Audio/MIDI Import.
- [x] **Transport:** Play, Pause, Stop, Audio-Clock Position (Bar.Beat.Tick + mm:ss.ms), BPM, Time Signature, Loop Toggle & Range, Project Length, Master Volume.
- [x] **Tracks:** Audio, Stem (clearly labeled as estimated vs independent), MIDI, and Master tracks; Add, Delete (without deleting source assets), Rename, Color, Reorder, Mute, Solo, Volume, Pan.
- [x] **Arrangement Timeline:** Bar/Beat/Time grid, Horizontal Zoom & Scroll, Vertical Scroll, Snap to Grid, Playhead, Loop Region, Section Markers, Selection Context (Track / Clip / Multi-Clip / Bar Range).
- [x] **Audio & MIDI Clips:** Real PCM waveform rendering, real MIDI note previews, Select, Move, Trim, Split (`Cmd+E`), Duplicate (`Cmd+D`), Delete, Loop, Clip Gain, Undo/Redo (`Cmd+Z` / `Cmd+Shift+Z`).
- [x] **Realtime Audio & Mixer:** Synchronized AudioContext clock playback, mid-song seek, loop without drift, live gain/pan/mute/solo, real AnalyserNode Peak/RMS meters, Master clipping indicator.
- [x] **Clip Editor & Piano Roll:** Zoomed audio waveform editor with trim/gain/range sync; Piano Roll with keyboard audition, note create/move/resize/delete, velocity lane, basic synth playback.
- [x] **AI Producer Foundation:** Live Selection Context display, structured Command Payload preview, explicit `Not connected` / Phase 01 offline indicator.
- [x] **Shared Command System:** Unified command dispatcher used by UI and backend API, with Undo/Redo excluding transport actions.
- [x] **Demo Projects:** Demo A (V7.2 Magnetic Afterhours House) and Demo B (5-track Multitrack Session: Drums, Bass, Guitar/Keys, Synth MIDI, Texture).
- [x] **Persistence & Export:** Save/reopen round-trip integrity; real Stereo WAV export reflecting all edits, mixer levels, mute/solo, and MIDI playback.
- [x] **QA:** Unit/integration tests, Audio signal QA, live browser Visual QA (`1440×900`, `1280×800`), legacy regression check, PR against `develop/ai-native-daw`.
