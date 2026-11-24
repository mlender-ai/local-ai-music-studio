# PROJECT_FORMAT.md — AI-Native DAW Project Data Model (v1.2.0)

## Directory Layout

Each project is a self-contained, portable folder under `outputs/daw/projects/<project_id>/`:

```text
<project_id>/
├── project.json              # Canonical versioned project state (atomic write, schema v1.2.0)
├── project.autosave.json     # Latest periodic autosave snapshot
├── assets/
│   ├── audio/                # Immutable audio files (<asset_id>_<sanitized_name>.<ext>)
│   ├── midi/                 # Immutable Standard MIDI Files (.mid)
│   └── references/           # Reference audio/video tracks (excluded from WAV export)
├── takes/
│   └── <take_id>/            # Generated Take preview WAV (-16 LUFS metadata), .mid parts & analysis cache
├── cache/
│   ├── waveforms/            # Cached real PCM peak envelopes (<sha256>.json)
│   ├── analysis/             # Cached v3.0.0 acoustic analysis results
│   └── extracted/            # Audio extracted from video references
├── versions/                 # Manual/checkpoint snapshots
└── exports/                  # Rendered 48 kHz 24-bit Stereo WAV outputs
```

**Invariants:**
- Never embed Base64 audio inside `project.json`.
- Original assets under `assets/` are immutable; deleting a track or clip never deletes the underlying asset file.
- Every project save checks `revision` (optimistic locking, HTTP `409 REVISION_CONFLICT` on mismatch) and uses temp file + `fsync` + `os.replace()`.
- Automatic migration upgrades `1.0.0` and `1.1.0` projects into `1.2.0` cleanly on load (`revision`, `references`, `compositionPlans`, `takes`).

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

## Schema `1.2.0` Top-Level Additions

- `revision: int` — Monotonic optimistic-locking revision number (added in `1.1.0`).
- `references: list[ReferenceItem]` — Reference tracks, v3.0.0 acoustic analysis, and `ReferenceBlueprint` (added in `1.1.0`, excluded from final WAV export).
- `compositionPlans: list[CompositionPlan]` — Structured pre-generation musical plans (`musicalIdentity`, `signatureMotif`, `harmonyAndGroove`, `instrumentRoles`, `arrangement`, `variations`, `climax`, `generationStrategy`, `referenceBinding`, `providerProvenance`) (added in `1.2.0`).
- `takes: list[Take]` — Generated audio/MIDI take history with `provenance`, `qualityReport` (BS.1770-4 + MIDI validation + Reference comparison + Vocal screening), `levelMatchedGainDb`, `plannedSections` vs `detectedSections`, and `status` (`ready | applied | kept | rejected`) (added in `1.2.0`).

### Track Types & Multi-Timbre `instrumentRef`
- `"audio"`: Imported WAV/MP3/FLAC/OGG, full mixes, loops, textures.
- `"stem"`: Separated stems (visibly distinguished from independent recordings).
- `"midi"`: Note events routed to `instrumentRef` across both Web Audio playback and Python offline WAV export:
  - `"drum-kit-electronic"` — GM-mapped electronic drum kit
  - `"bass-fm-sub"` — FM sub-bass
  - `"synth-fm-hook"` — Stereo detuned melodic hook/lead synth
  - `"keys-electric-ep"` — Warm electric piano (EP)
  - `"guitar-clean-pluck"` — Clean plucked guitar
  - `"pad-warm-analog"` — Slow-attack stereo analog pad
  - `"basic-poly-synth"` — Phase 01 default polyphonic synth
