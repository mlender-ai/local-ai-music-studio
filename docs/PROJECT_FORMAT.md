# PROJECT_FORMAT.md — AI-Native DAW Project Data Model (v1.4.0)

## Directory Layout

Each project is a self-contained, portable folder under `outputs/daw/projects/<project_id>/`:

```text
<project_id>/
├── project.json              # Canonical versioned project state (atomic write, schema v1.4.0)
├── project.autosave.json     # Latest periodic autosave snapshot
├── assets/
│   ├── audio/                # Immutable audio files (<asset_id>_<sanitized_name>.<ext>)
│   ├── midi/                 # Immutable Standard MIDI Files (.mid)
│   └── references/           # Reference audio/video tracks (excluded from WAV export)
├── takes/
│   └── <take_id>/
│       ├── preview.wav                 # Solo level-matched preview WAV
│       ├── preview_in_context.wav      # Phase 04 In-Context mix preview WAV (-16 LUFS)
│       ├── preview_original_context.wav# Phase 04 Original Context A/B preview WAV (-16 LUFS)
│       └── *.mid                       # Editable MIDI part artifacts
├── cache/
│   ├── waveforms/            # Cached real PCM peak envelopes (<sha256>.json)
│   ├── analysis/             # Cached v3.0.0 acoustic analysis results
│   ├── transcription/        # Cached v4.0.0 transcription results (<sha256>_4.0.0_*.json)
│   ├── stems/                # Cached Demucs separated reference stems (<sha256[:16]>/htdemucs/)
│   └── extracted/            # Audio extracted from video references
├── versions/                 # Manual/checkpoint snapshots
└── exports/                  # Rendered 48 kHz 24-bit Stereo WAV outputs
```

**Invariants:**
- Never embed Base64 audio inside `project.json`.
- Original assets under `assets/` are immutable; deleting a track/clip or reversing an audio clip never alters or deletes the original asset file.
- Every project save checks `revision` (optimistic locking, HTTP `409 REVISION_CONFLICT` on mismatch) and uses temp file + `fsync` + `os.replace()`.
- Automatic migration upgrades `1.0.0`–`1.3.0` projects into `1.4.0` cleanly on load (`chordTrack`, `chordTrackLocked`, `revision`, `references`, `compositionPlans`, `takes`, `musicMemory`, `track.takeLanes`, `track.stemMeta`, `clip.fadeInBeats`, `clip.fadeOutBeats`, `clip.reversed`).

## Explicit Time & Unit Conventions

| Unit | Type | Convention |
|---|---|---|
| `beats` | `number` (float) | Quarter-note musical beats from timeline start (`0.0` = Bar 1, Beat 1) |
| `seconds` | `number` (float) | Wall-clock audio seconds (`seconds = beats * 60 / bpm`) |
| `samples` | `integer` | Sample frames at `sampleRate` (`samples = round(seconds * sampleRate)`) |
| `bars` | `integer` | 1-based for display (`beatsPerBar = numerator * (4 / denominator)`) |
| `ticks` | `integer` | MIDI ticks at `PPQ = 480` ticks per quarter note |
| `gainDb` | `number` (float) | Decibels relative to unity (`0.0 dB` = linear `1.0`, `<= -60.0 dB` = silence) |
| `pan` | `number` (float) | Stereo balance in `[-1.0, 1.0]` |
| `integratedLufs` | `number` (float) | Standard ITU-R BS.1770-4 gated loudness |
| `truePeakDbtp` | `number` (float) | 4× polyphase oversampled True Peak in dBTP |

## Schema `1.4.0` Additions (Phase 03.2 Advanced Reference Intelligence)

- `project.chordTrack: list[ChordEvent]` — Editable global Timeline Chord Track supporting fractional sub-bar boundaries (`id`, `symbol`, `root`, `quality`, `extension`, `bassNote`, `startBeat`, `endBeat`, `sourceReferenceId`, `confidence`, `isEstimate`, `userCorrected`, `locked`).
- `project.chordTrackLocked: bool` — Locks the Timeline Chord Track so AI composition strictly obeys every beat-aligned chord symbol and bass inversion.
- `reference.transcription` & `reference.blueprint` (Blueprint v2, `blueprintVersion: "2.0.0"`) — Stores Demucs `htdemucs` stem references (`assetKind: "separated_stem"`), Basic Pitch ONNX Bass & Melody MIDI notes, Multi-band Drum & Microtiming groove templates, Sub-bar Chord Timeline, stem-enriched Arrangement Map, validated YuE2 Instrumental ABC score, 10-feature `featureLocks` (`free | reference | locked | unsupported`), and `userCorrections`.

## Schema `1.3.0` Additions (Phase 03.1 + Phase 04)

- `project.musicMemory: dict` — Compact Project Music Memory (`genre`, `bpm`, `key`, `chords`, `mainHookSummary`, `referenceIds`, `instrumentRoles`, `likedTakes`, `rejectedTakes`, `conversationTurns`, `lastTargetTrackId`, `lastBarRange`, `lastTakeId`).
- `track.takeLanes: list[TakeLane]` — Per-track non-destructive alternative Take Lanes (`id`, `name`, `takeId`, `startBeats`, `endBeats`, `clip` / `clips`, `isOriginalBackup`, `active`, `createdAt`). Inactive lanes are strictly excluded from playback and WAV export (zero double-summing).
- `track.stemMeta: dict | null` — Provenance metadata for Demucs stem tracks (`sourceTrackId`, `parentSourceAssetId`, `separationModel`, `separationJobId`).
- `clip.fadeInBeats: float`, `clip.fadeOutBeats: float` — Non-destructive beat-synced linear fade-in / fade-out envelopes mirrored identically across Web Audio realtime, OfflineAudioContext export, and Python offline WAV export.
- `clip.reversed: bool` — Tracks whether the clip currently points to a non-destructively reversed immutable WAV asset.
- `take.baseRevision`, `take.baseTrackFingerprints`, `take.targetRangeBeats` — Concurrent-edit protection metadata enabling safe merges when unrelated tracks change during AI generation.

### Track Types & Multi-Timbre `instrumentRef`
- `"audio"`: Imported WAV/MP3/FLAC/OGG, full mixes, loops, textures.
- `"stem"`: Separated stems (visibly distinguished from independent recordings, with `stemMeta` provenance).
- `"midi"`: Note events routed to `instrumentRef` across both Web Audio playback and Python offline WAV export:
  - `"drum-kit-electronic"` — GM-mapped electronic drum kit
  - `"bass-fm-sub"` / `"analog-sub-bass"` — Sub-bass voices
  - `"synth-fm-hook"` / `"fm-pluck-lead"` — Melodic hook/lead synth voices
  - `"keys-electric-ep"` — Warm electric piano (EP)
  - `"guitar-clean-pluck"` — Clean plucked guitar
  - `"pad-warm-analog"` — Slow-attack stereo analog pad
  - `"basic-poly-synth"` — Phase 01 default polyphonic synth
