# PROJECT_FORMAT.md — AI-Native DAW Project Data Model (v1.5.0)

## Directory Layout

Each project is a self-contained, portable folder under `outputs/daw/projects/<project_id>/`:

```text
<project_id>/
├── project.json              # Canonical versioned project state (atomic write, schema v1.5.0)
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
│   ├── analysis/             # Cached v3.1.0 full-length acoustic analysis results
│   ├── transcription/        # Cached v4.0.0 transcription results (<sha256>_4.0.0_*.json)
│   ├── stems/                # Cached Demucs separated reference stems (<sha256[:16]>/htdemucs/)
│   ├── freeze/               # Deterministic state-hashed 48kHz Frozen Track WAVs
│   └── extracted/            # Audio extracted from video references
├── versions/                 # Manual/checkpoint snapshots
└── exports/                  # Rendered 48 kHz 24-bit Stereo WAV outputs
```

Shared studio assets (gitignored under `outputs/daw/`):
- `outputs/daw/soundfonts/MuseScore_General.sf3` — MIT-licensed multi-sampled GM SoundFont rendered via FluidSynth (`2.6.3`)
- `outputs/daw/cache/ir/` — Cached L2-normalized Convolution Reverb IRs and Guitar Speaker Cabinet IRs (`1x12_open`, `2x12_british`, `4x12_modern`, `direct_di`)

**Invariants:**
- Never embed Base64 audio inside `project.json`.
- Original assets under `assets/` are immutable; deleting a track/clip, reversing audio, or freezing/unfreezing never alters or deletes original assets.
- Native Audio Protection: `native_audio_original` tracks imported from studio/YuE2 renders remain untouched when Hybrid MIDI layers are added.
- Every project save checks `revision` (optimistic locking, HTTP `409 REVISION_CONFLICT` on mismatch) and uses temp file + `fsync` + `os.replace()`.
- Automatic migration upgrades `1.0.0`–`1.4.0` projects into `1.5.0` cleanly on load (`instrumentConfig`, `sends`, `automationLanes`, `freezeState`, `outputBusId`, `buses`, `masterEffects`).

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

## Schema `1.5.0` Additions (Phase 03.2.1 + Phase 05)

- **Track Sound Design & Studio DSP Fields:**
  - `track.instrumentConfig: dict` — Preset ID, live synthesis/instrument parameters, articulation (`sustain`, `staccato`, `legato`, `palm_mute`, `ghost`), `samplerConfig` (transient slices/zones), `drumRackConfig` (kit/pads/choke groups).
  - `track.effects: list[EffectSlot]` — Ordered non-destructive insert FX chain (`id`, `type`, `name`, `nameKo`, `enabled`, `bypass`, `wetDry`, `preset`, `parameters`, `sidechainTrackId`).
  - `track.sends: list[SendSlot]` — Per-track Return Bus sends (`id`, `busId`, `levelDb`, `preFader`, `enabled`).
  - `track.automationLanes: list[AutomationLane]` — Beat-timed parameter curves (`targetType: track|fx|instrument|send`, `targetId`, `parameterId`, `enabled`, `points: [{id, beat, value, interpolation: linear|step}]`).
  - `track.freezeState: TrackFreezeState | null` — Deterministic `stateHash` freeze metadata (`frozen`, `assetId`, `stateHash`, `frozenAt`, `durationSec`, `sampleRate`, `fxMeters`). Automatically invalidates on MIDI/instrument/FX edits and plays back bit-exact 48 kHz WAV in Web Audio!
  - `track.outputBusId: str` — Output routing (`"master"` or Group Bus ID).
- **Project Mix Graph Fields:**
  - `project.buses: list[BusTrack]` — Return & Group Buses (`id`, `name`, `kind: "return" | "group"`, `gainDb`, `pan`, `mute`, `solo`, `effects`).
  - `project.masterEffects: list[EffectSlot]` — Master Bus insert FX chain.
- **Reference Blueprint v3 (`blueprintVersion: "3.0.0"`):**
  - Full-length `analysisCoverage` (`originalDurationSec`, `analyzedDurationSec`, `coveragePct`, `isComplete`, `truncated`), `actualBeatGrid` vs `fixedBpmGrid`, `tempoStability`, 15-quality Chord Tracker with 1-beat adaptive passing chords + top-3 candidates, full-length 11-class Drum Event Schema + `variationMap`, Acoustic `SoundProfile` + `SpatialProfile` (with honesty disclaimer), full-length `bassPerformance`, and Multi-Reference `featureSourceMap` + conflict detection.

## Schema `1.4.0` & `1.3.0` Fields (Preserved)

- `project.chordTrack: list[ChordEvent]`, `project.chordTrackLocked: bool`
- `project.musicMemory: dict`
- `track.takeLanes: list[TakeLane]`, `track.stemMeta: dict | null`
- `clip.fadeInBeats`, `clip.fadeOutBeats`, `clip.reversed`
- `take.baseRevision`, `take.baseTrackFingerprints`, `take.targetRangeBeats`

### Track Types & Phase 05 Pro `instrumentRef` Families
- `"audio"`: Imported WAV/MP3/FLAC/OGG, full mixes, loops, textures, protected `native_audio_original`.
- `"stem"`: Demucs separated stems (honestly distinguished from studio recordings, with `stemMeta` provenance).
- `"midi"`: Routed to Phase 05 Pro Instruments (3-pass studio render & track freeze) or built-in Web Audio fallback:
  - **FluidSynth SF3 Multi-Sampled (`MuseScore_General.sf3`, MIT):** `sf-drums-acoustic`, `sf-bass-electric`, `sf-piano-grand`, `sf-ep-rhodes`, `sf-organ-hammond`, `sf-guitar-clean`, `sf-guitar-overdrive`, `sf-strings-ensemble`, `sf-vibraphone`, `sf-pad-warm`, `sf-brass-section`
  - **Pro Hybrid Synth (`Pedalboard LadderFilter` + Supersaw/FM):** `pro-synth-analog`, `pro-synth-fm`
  - **Studio Drum Rack (Round-Robin + Hi-Hat Choke Groups):** `pro-drum-rack` (`house-909`, `boombap-vintage`, `indie-rock-acoustic`, `jazz-brush`, `trap-808`)
  - **Transient-Slicing Studio Sampler:** `pro-sampler`
  - **Legacy Phase 03 Web Audio Voices (preserved):** `drum-kit-electronic`, `bass-fm-sub`, `synth-fm-hook`, `keys-electric-ep`, `guitar-clean-pluck`, `pad-warm-analog`, `basic-poly-synth`
