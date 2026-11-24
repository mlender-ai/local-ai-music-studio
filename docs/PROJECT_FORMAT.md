# PROJECT_FORMAT.md — AI-Native DAW Project Data Model (v1)

## Directory Layout

Each project is a self-contained, portable folder under `outputs/daw/projects/<project_id>/`:

```text
<project_id>/
├── project.json              # Canonical versioned project state (atomic write)
├── project.autosave.json     # Latest periodic autosave snapshot
├── assets/
│   ├── audio/                # Immutable audio files (<asset_id>_<sanitized_name>.<ext>)
│   ├── midi/                 # Immutable Standard MIDI Files (.mid)
│   └── references/           # Reference audio tracks
├── cache/
│   └── waveforms/            # Cached real PCM peak envelopes (<sha256>.json)
├── versions/                 # Manual/checkpoint snapshots
└── exports/                  # Rendered Stereo WAV outputs
```

**Invariants:**
- Never embed Base64 audio inside `project.json`.
- Original assets under `assets/` are immutable; deleting a track or clip never deletes the underlying asset file.
- Asset paths in `project.json` are always relative to the project folder.
- Writes use temp file + `fsync` + `os.replace()` for crash safety.

## Explicit Time & Unit Conventions

Never mix units implicitly. Every numeric field carries its unit in its field name:

| Unit | Type | Convention |
|---|---|---|
| `beats` | `number` (float) | Quarter-note musical beats from timeline start (`0.0` = Bar 1, Beat 1) |
| `seconds` | `number` (float) | Wall-clock audio seconds (`seconds = beats * 60 / bpm`) |
| `samples` | `integer` | Sample frames at `sampleRate` (`samples = round(seconds * sampleRate)`) |
| `bars` | `integer` (1-based for display, 0-based internally via `beats / beatsPerBar`) | `beatsPerBar = timeSignature.numerator * (4 / timeSignature.denominator)` |
| `ticks` | `integer` | MIDI ticks at `PPQ = 480` ticks per quarter note (`ticks = round(beats * 480)`) |
| `gainDb` | `number` (float) | Decibels relative to unity (`0.0 dB` = linear `1.0`, `<= -60.0 dB` = silence) |
| `pan` | `number` (float) | Stereo balance in `[-1.0, 1.0]` (`-1.0` hard left, `0.0` center, `+1.0` hard right) |

### BPM Change Semantics (Phase 01)
- **MIDI Clips & Notes** are positioned and sized in `beats`, so changing BPM speeds up/slows down MIDI playback musically.
- **Audio / Stem Clips** store `timelineStartBeats` (musical anchor) and `sourceOffsetSec` / `sourceDurationSec` (real seconds). Audio playback preserves natural duration without time-stretching; Phase 01 does not fake Elastic Audio / Warp.

## JSON Schema (`schemaVersion: "1.0.0"`)

```json
{
  "id": "proj_demo_multitrack",
  "schemaVersion": "1.0.0",
  "name": "Midnight Studio · Multitrack",
  "bpm": 128.0,
  "timeSignature": { "numerator": 4, "denominator": 4 },
  "ppq": 480,
  "sampleRate": 48000,
  "lengthBeats": 64.0,
  "masterGainDb": 0.0,
  "loopRegion": {
    "enabled": true,
    "startBeats": 16.0,
    "endBeats": 32.0
  },
  "sections": [
    { "id": "sec_intro", "name": "INTRO", "startBeats": 0.0, "endBeats": 16.0, "color": "#4b5563" }
  ],
  "assets": [
    {
      "id": "ast_drums_01",
      "name": "Drum loop.wav",
      "kind": "audio",
      "relativePath": "assets/audio/ast_drums_01_drum_loop.wav",
      "source": "demo-synthesized",
      "provenance": "Independent studio audio loop (48 kHz Stereo)",
      "sha256": "...",
      "sampleRate": 48000,
      "channels": 2,
      "durationSec": 7.5,
      "durationSamples": 360000
    }
  ],
  "tracks": [
    {
      "id": "trk_drums",
      "name": "Drums",
      "type": "audio",
      "color": "#6a997c",
      "gainDb": 0.0,
      "pan": 0.0,
      "mute": false,
      "solo": false,
      "instrumentRef": null,
      "effects": [],
      "clips": [
        {
          "id": "clp_drums_1",
          "name": "Drums 1",
          "type": "audio",
          "assetId": "ast_drums_01",
          "timelineStartBeats": 0.0,
          "durationBeats": 16.0,
          "sourceOffsetSec": 0.0,
          "sourceDurationSec": 7.5,
          "loop": true,
          "loopLengthSec": 7.5,
          "gainDb": 0.0,
          "notes": []
        }
      ]
    }
  ],
  "createdAt": "2026-11-24T00:00:00Z",
  "updatedAt": "2026-11-24T00:00:00Z"
}
```

### Track Types
- `"audio"`: Imported WAV/MP3/FLAC/OGG, full mixes, recordings, loops, textures.
- `"stem"`: Separated stems from a composite mix (UI visibly distinguishes estimated stems from independent recordings).
- `"midi"`: Note events (`pitch`, `velocity`, `startBeat`, `durationBeats`) routed to `instrumentRef` (Phase 01 default: `"basic-poly-synth"`).
