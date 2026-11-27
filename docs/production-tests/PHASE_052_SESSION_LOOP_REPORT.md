# PHASE 05.2 · AI SESSION & LOOP PRODUCTION REPORT

**Date:** 2026-11-28  
**Branch:** `feat/daw-ai-session-loop-production` (stacked on `feat/daw-yue2-native-production`, PR #29)  
**Reference Session Project:** `Late Night Sessions 001` (`proj_1b410631f3`, saved in `outputs/daw/projects/proj_1b410631f3/`)  
**Specification:** 90 BPM · 4/4 · D minor · 8-bar Main Groove (`21.333 s`) + 4-bar Bridge with 2-beat Transition (`32.0 s` total) · Strict Instrumental (zero vocals/humming/chops)

---

## 1. Direct User Listening Audio Groups (`outputs/exports/phase052_late_night_sessions_001/`)

> **Important Honesty Note (Gate E · User Listening):** Automated checks verified engine integrity, cryptographic layer protection, loop boundaries, harmonic compatibility, zero clipping, and zero vocals. **Subjective musical quality (groove feel, guitar realism, mix attractiveness, and emotional impact) remains `UNVERIFIED` until direct human listening.**

### Group A · Groove Foundation (Drums -> Bass -> Rhodes)

| # | File (Repo-Relative) | Duration | Integrated LUFS | True Peak | Notes |
|---|---|---:|---:|---:|---|
| A1 | `outputs/exports/phase052_late_night_sessions_001/GroupA_01_Drums_Solo.wav` | 21.333 s | -17.36 | -1.00 dBTP | `pro-drum-rack` (`boombap-vintage`), laid-back snare (+16 ms), ghost snares, hi-hat choke, Bar 4 & 8 fills |
| A2 | `outputs/exports/phase052_late_night_sessions_001/GroupA_02_Bass_Solo.wav` | 21.333 s | -16.00 | -2.47 dBTP | `sf-bass-electric` (`fingered`, `legato`), kick-locked pocket + slide pickups, `STRONG_MATCH` harmony |
| A3 | `outputs/exports/phase052_late_night_sessions_001/GroupA_03_Drums_Bass_Mix.wav` | 21.333 s | -17.24 | -1.00 dBTP | Drums + Bass together (Drums hash verified unchanged) |
| A4 | `outputs/exports/phase052_late_night_sessions_001/GroupA_04_Rhodes_Solo.wav` | 21.333 s | -16.00 | -2.50 dBTP | `sf-ep-rhodes` (`jazz_warm_ep`, `warm_roll`), rootless 9th/13th voice-led comping, `STRONG_MATCH` |
| A5 | `outputs/exports/phase052_late_night_sessions_001/GroupA_05_Drums_Bass_Rhodes_Mix.wav` | 21.333 s | -17.05 | -1.00 dBTP | Core 3-piece groove foundation (Drums + Bass hashes verified unchanged) |

### Group B · Guitar Performance Comparison (Same Guitar Track · Take Lane A vs Take Lane B)

| # | File (Repo-Relative) | Duration | Integrated LUFS | True Peak | Notes |
|---|---|---:|---:|---:|---|
| B1 | `outputs/exports/phase052_late_night_sessions_001/GroupB_01_GuitarA_Funk_Solo.wav` | 21.333 s | -24.25 | -1.00 dBTP | Take A: `sf-guitar-clean` (`muted_funk`, `palm_mute` + `guitar_amp` clean), 98 notes, upper-neck stabs & muted chucks |
| B2 | `outputs/exports/phase052_late_night_sessions_001/GroupB_02_GuitarB_Clean_Solo.wav` | 21.333 s | -16.00 | -3.78 dBTP | Take B: `sf-guitar-clean` (`jazz_hollow`, `strum_down` + `guitar_amp` + dotted-8th delay), 30 notes, sparse melodic phrases |
| B3 | `outputs/exports/phase052_late_night_sessions_001/GroupB_03_Session_Plus_GuitarA_Funk.wav` | 21.333 s | -17.05 | -1.00 dBTP | Session + Take A Funk Guitar (zero double-playing; Drums/Bass/Rhodes hashes unchanged) |
| B4 | `outputs/exports/phase052_late_night_sessions_001/GroupB_04_Session_Plus_GuitarB_Clean.wav` | 21.333 s | -17.07 | -1.00 dBTP | Session + Take B Clean Melodic Guitar (stored non-destructively in `takeLanes` on same track) |

### Group C · Musical Development (Percussion, Guitar Solo, Transition & Bridge)

| # | File (Repo-Relative) | Duration | Integrated LUFS | True Peak | Notes |
|---|---|---:|---:|---:|---|
| C1 | `outputs/exports/phase052_late_night_sessions_001/GroupC_01_Percussion_Solo.wav` | 21.333 s | -22.04 | -1.00 dBTP | `pro-drum-rack` (`percussion-latin-studio`), 172 notes (Shaker/Cabasa/Congas/Bongos/Claves/Tambourine), zero kick/snare duplication |
| C2 | `outputs/exports/phase052_late_night_sessions_001/GroupC_02_With_Percussion_Mix.wav` | 21.333 s | -16.88 | -1.00 dBTP | Main Groove + Syncopated Percussion layer |
| C3 | `outputs/exports/phase052_late_night_sessions_001/GroupC_03_Guitar_Solo_Isolated.wav` | 21.333 s | -16.00 | -1.94 dBTP | `sf-guitar-clean` (`clean_strat`), 30 notes, 9 real smooth pitch-bend/slide ramps, 4-phrase climax/resolution arc |
| C4 | `outputs/exports/phase052_late_night_sessions_001/GroupC_04_MainGroove_Plus_Solo.wav` | 21.333 s | -16.79 | -1.00 dBTP | Full 6-layer Main Groove + Expressive Guitar Solo |
| C5 | `outputs/exports/phase052_late_night_sessions_001/GroupC_05_MainGroove_Transition_Bridge.wav` | 32.000 s | -18.46 | -1.00 dBTP | Full 12 bars: Main Groove (`Dm9-G13-Cmaj9-A7`) -> 2-beat Drum Fill & Bass Pickup -> Contrasting Bridge (`Bbmaj9-A7sus4-Gm9-A7`) |

- **Official Studio Preview Copy:** `outputs/exports/LateNightSessions001_StudioPreview.wav` (`Studio Preview` status `upToDate: true`).
- **Persistent Studio Session Library:** `outputs/daw/session_library.json` (`8` verified assets + `8` Performance Recipes saved & searchable).

---

## 2. GATE 0 · Empirical YuE2 Solo-Instrument Capability Audit (Honest Limits)

Before choosing generation strategies for individual layers, we ran two real 16-second Metal `yue-synth` probes (`YuE2-3B-Q8_0.gguf`, Apple M5, ~63 s / ~4.5 GiB RSS each) + Demucs `htdemucs` 4-stem isolation analysis (`outputs/daw/phase052_gate0_audit/gate0_audit_results.json`):

| Probe | Engine / Score | Elapsed | Est. BPM | Target Stem Share | Bleed / Leakage Evidence | Vocal QA | Empirical Status |
|---|---|---:|---:|---:|---|---|---|
| `yue2_solo_drums` | `yue-synth` (`cot=off`, solo drums prompt) | 62.8 s | 84.7 | `drums`: **19.1%** | `other` bleed **76.7%** (`-24.34 dBFS`), `bass` 4.0% | `PASS` (`-43.5 dBFS`) | **`UNSUPPORTED`** |
| `yue2_solo_guitar` | `yue-synth` (`official_v6_compile_score`, `cot=melody`) | 63.7 s | 89.9 | `other`: **28.2%** | `drums` bleed `-28.54 dBFS` (7.9%), `bass` `-32.79 dBFS` (3.0%), vocal-band bleed 60.9% | `UNCERTAIN` (`-19.05 dBFS`) | **`UNSUPPORTED`** |
| Full-band Instrumental | `yue-synth` + official `compile_score.py` | ~65 s | Locked | Full mix | Verified in Phase 05.1 (`Native Production Validation 001`) | Screened | **`VERIFIED`** |
| Accompaniment-free Overdub | YuE2 Runtime | — | — | — | Model does not support audio-conditioned single-instrument overdub inpainting | — | **`UNSUPPORTED`** |

**Architectural Decision:**
- **Full-music requests** strictly keep **Phase 05.1 YuE2 First** (`yue2-native`, zero silent MIDI fallback).
- **Independent single-instrument session layers** NEVER disguise mixed YuE2 audio or Demucs `other` stems as isolated guitar/piano. They use **Strategy C (`Pro SF3 / Pro Drum Rack / Pro Synth + Musical Performance Intelligence + Subtle FX + Shared Natural Room Bus`)** with exact harmonic alignment, zero stem bleed, and full Piano Roll / Mixer / Take Lane editability.

---

## 3. Architectural & Performance Highlights Verified

1. **Shared `SessionContext` & Cryptographic Layer Protection (`engine/session_lab/context.py`):**
   - Extracts real kick/snare pocket positions, occupied pitch registers, chord timeline, and motif memory before generating each new layer.
   - `Approved`/`Locked` layers are fingerprinted with SHA-256 hashes before and after every operation. Direct overwrites of `Locked` tracks return HTTP `400`; all 6 Main Groove layers kept 100% identical hashes through Guitar A/B Take Lanes, Percussion, Solo, Transition, and Bridge generation.
2. **Smooth Pitch-Bend & FluidSynth Pooling (`engine/instruments/soundfont_engine.py`, `drum_rack.py`):**
   - Upgraded per-note `pitchBendSemitones` from static detune to real sample-accurate bend ramps (string bend up for positive semitones; fret slide-in for negative semitones).
   - Added process-wide FluidSynth SF3 pooling and batched Drum Rack one-shot pre-warming, cutting multi-layer preview render time by >3x while preserving 48 kHz studio quality.
   - Fixed Phase 05.1 SoundFont ID mismatches (`sf-bass-finger` -> `sf-bass-electric`, `sf-organ-b3` -> `sf-organ-vintage`, `sf-strings-pad` -> `sf-pad-warm`) and added the real GM Percussion `percussion-latin-studio` kit.
3. **Real Defects Found & Fixed During Live Production Run:**
   - *Multi-instrument context prompt routing:* `"현재 드럼과 베이스에 어울리는 Neo Soul 건반 연주를 추가해줘"` initially matched `"베이스"` instead of the target `"건반"`. Fixed in `proposals.py` via rightmost target-instrument extraction and added regression coverage.
   - *Style alias precedence:* Generic noun aliases in first presets (`"퍼커션"`, `"베이스"`, `"건반"`) shadowed style-specific presets (`syncopated_riff`). Removed generic noun short-circuits in `vocabulary.py`.
   - *Guitar & Percussion mix level:* Dry SF3 guitar + clean amp IR sat ~10 dB quieter than Drums/Bass. Tuned `guitar_amp` output makeup gain and role fader defaults so solo riffs, percussion, and guitar solo bends sit clearly in the mix.
4. **Loop Alignment, Vocal Policy & 5-Part Quality Gate (`engine/session_lab/alignment.py`):**
   - Click-free bar-boundary trimming (`align_audio_loop_to_bars`) preserving originals untouched; honest BPM drift blocking (`check_tempo_alignment`, flagging `90.8 vs 90.0 BPM` over 8 bars as `DRIFT_RISK`); jazz-tension-aware harmonic check (`9th/11th/13th` + passing tones).
   - Strict instrumental enforcement across all layers (`vocalStatus: PASS` on deterministic non-vocal SF3/Drum Rack layers; Demucs vocal screening retained on neural audio).

---

## 4. Known Limits & Next Priorities

1. **SF3 Guitar Expressive Realism Ceiling:** While smooth pitch-bend ramps, upper-neck funk stabs, palm-mute presets, and tube amp/cab IR noticeably improve playability over Phase 03 MIDI, authentic human finger vibrato, pinch harmonics, and pick-scrape micro-nuance remain `UNSUPPORTED` / `PARTIALLY_SUPPORTED` on SF3 soundfonts. Integrating sampled/hybrid guitar loop libraries (Strategy D) or future stem-clean instrument neural models is the clear next quality leap.
2. **Funk Guitar & Percussion Solo Crest Factor:** Because percussive muted guitar stabs and shakers have high transient crest factors, peak-limited (`-1.0 dBTP`) solo renders measure `-22` to `-24 LUFS` even when peaks hit `-1.0 dBTP` (while sitting properly at `-16.8` to `-17.0 LUFS` inside the full mix). Adding a gentle transparent solo transient compressor option for audition previews would make solo A/B loudness even closer to `-16 LUFS`.
3. **User Listening & Feedback Loop:** Please audition Groups A, B, and C above and submit ratings/comments via `/api/session-library/{asset_id}/feedback` or chat to refine the persistent Taste Profile and prioritize Phase 05.3 / Phase 06 (AI Mixing & Mastering).
