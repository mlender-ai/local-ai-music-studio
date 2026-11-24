# PRODUCT.md — AI-Native DAW

## Vision

**AI-Native DAW** is a local-first macOS desktop music studio that pairs the precision and speed of professional DAWs (Ableton Live, Logic Pro, Bitwig Studio) with an assistive natural-language AI Producer.

It is **not** a prompt-to-song generator dashboard. Users open directly into a high-density studio workspace where tracks, waveforms, MIDI notes, transport, and mixer controls are primary, and AI operates on explicit musical selection context (track, clips, bar range, section).

## Core User Experience

Across the product lifecycle, users will:
1. Import and analyze reference tracks.
2. Compose with natural language and local generation models (YuE2 / ACE-Step).
3. Build multi-instrument sessions with audio, stem, and MIDI tracks.
4. Edit clips non-destructively (move, trim, split, duplicate, loop, gain) and edit MIDI in a Piano Roll.
5. Regenerate or vary selected bars/instruments with take comparison and restore.
6. Apply virtual instruments, FX chains, automation, mixing, and mastering.
7. Export full mixes and stems locally.

## Phase 01 Scope (Workspace Foundation)

Phase 01 proves the real studio workbench without building new AI generation models:
- Create, open, rename, save, Save As, and autosave local projects.
- Import real WAV/MP3/FLAC/OGG audio and `.mid` Standard MIDI Files (plus existing studio music assets like V7.2 Magnetic Afterhours).
- Display real PCM-extracted waveforms and real MIDI note previews on a musical Bar/Beat timeline.
- Synchronize multi-track Web Audio playback with play, pause, stop, seek, BPM, time signature, loop region, and master volume.
- Control per-track Mute, Solo, Volume, Pan, and view real signal-driven Peak/RMS meters and clipping indicator.
- Perform non-destructive clip editing (select, multi-select, move with grid snap, trim, split, duplicate, loop, clip gain, delete) and Undo/Redo.
- Edit Audio Clips in a zoomed Clip Editor and MIDI Clips in an interactive Piano Roll with velocity lane and basic synth auditioning.
- Manage Section Markers and shared Selection Context surfaced in the AI Producer Panel (explicitly marked as offline/unconnected in Phase 01).
- Export true edited **Stereo WAV** reflecting timeline positions, trims, loops, track gain/pan, mute/solo, MIDI synth playback, and master volume.

## Out of Scope in Phase 01

- New generative model training or inference pipelines
- In-app LLM chat execution or paid external APIs
- Audio Time-Stretch / Elastic Warp (explicitly noted in UI and docs)
- Live microphone/MIDI hardware recording (control visibly disabled)
- AU/VST3 plugin hosting and FX DSP rack editing (scheduled for Phase 05)
