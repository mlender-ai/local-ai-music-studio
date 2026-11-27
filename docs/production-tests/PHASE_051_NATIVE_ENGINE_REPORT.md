# Phase 05.1 · Native Music Engine Integration Verification Report

**Date:** 2026-11-27  
**Branch:** `feat/daw-yue2-native-production` (branched from `feat/daw-phase05-integration` @ `a59fc22`)  
**Workspace:** `http://127.0.0.1:8796`  
**Saved DAW Validation Project:** `Native Production Validation 001` (`proj_5e536a5f75`)  
**Saved Hybrid Validation Project:** `Native Production Validation 001 (Hybrid)` (`proj_deb5741452`)  

---

## 1. Executive Summary

Phase 05.1 recovered the real local **YuE2 Native Audio** runtime (`yue-synth` + `yue-plan` `yue2.cpp e646d52`, Metal `MTL0`, `YuE2-3B-Q8_0.gguf`, `YuE2-Vae-F32.gguf`, official `v6/instrumental/compile_score.py`) via the user-local Shared Runtime Registry (`~/.config/ai-native-daw/runtime.json`, zero duplicated weights, zero personal paths in Git), switched the DAW's default full-music generation engine to **YuE2 First**, permanently blocked silent MIDI fallback and automatic selection of `PREVIEW` instruments across UI / REST / MCP, added **Studio Preview** parity (`Original Audio` / `Realtime Preview` / `Studio Preview` / `Rendering` / `Outdated Preview` / `Failed`), implemented a persistent **User Music Taste & Feedback Profile**, and executed all 8 required verification tests (`TEST 01`–`TEST 08`).

> **Honesty & Anti-Fabrication Statement:** Automated gates verify engine provenance, policy compliance, audio integrity, objective acoustic risks, and browser playback. **Subjective musical quality (groove feel, vibe, arrangement taste) remains `UNVERIFIED` until the user directly listens to Audio A, Audio B, and Audio C.**

---

## 2. YuE2 Runtime Recovery (GATE 1 / TEST 01)

- **Discovery:** Located existing local YuE2 Metal binaries, GGUF backbone/VAE weights, official `v6/instrumental/` ABC compiler/validator, PANNs/Whisper assets, and Demucs runtime on the host machine and linked via user-local `~/.config/ai-native-daw/runtime.json` (`sharedRuntimeRoot`) without duplicating any gigabyte weights or hardcoding personal paths into Git.
- **Canonical Runtime Status:** Added `runtimeStatus` (`NOT_INSTALLED`, `RUNTIME_FOUND`, `MODEL_FOUND`, `READY`, `GENERATION_VERIFIED`, `FAILED`) alongside backward-compatible `state` in `engine/runtime/registry.py`.
- **TEST 01 Smoke Test Result:**
  - Output: `outputs/daw/smoke_test_01/yue2_smoke_22s.wav` (`48000 Hz`, stereo, `21.999 s`, `8,447,532 bytes`)
  - Hardware & Performance: Apple M5 (`MTL0`), elapsed `73.7 s` (`0.3x realtime`), Peak RSS `4.557 GiB` (well within `10 GiB` guard), exit code `0`, clean Metal deallocation (`ggml_metal_free`).
  - Registry Transition: `ready` → `verified` (`GENERATION_VERIFIED`).

---

## 3. Permanent Production Policy & Architecture Changes

- **Permanent Policy Configs (`config/production/`):**
  - `config/production/default_policy.json`: `defaultFullMusicEngine: "yue2-native"`, `allowSilentMidiFallback: false`, `allowPreviewInstrumentsInProduction: false`, `preserveNativeAudio: true`, `instrumentalByDefault: true`, `autoSoundDesign: true`, `requireActualAudioRender: true`, `requireEngineProvenance: true`, `preserveOriginalTake: true`, `requireUserApprovalForPaidServices: true`.
  - `config/production/engine_routing.json`: Single routing table across Full Music (`yue2-native`), Hybrid (`hybrid`), Editable MIDI (`local-multitrack-composer` / `midi-composer-v3` with Pro-tier instruments), and Exact Event Lock (`compatible_controlled`).
  - `config/production/instrument_quality.json`: Explicit `PREVIEW` / `PRODUCTION_CANDIDATE` / `USER_APPROVED` / `UNAVAILABLE` classification with honest acoustic realism advisories (e.g., SF3 Clean Guitar vs live R&B guitar).
- **Production Enforcement Package (`engine/production/`):**
  - `policy.py`, `instrument_resolver.py`, `taste_profile.py`, `quality_gate.py`, `provenance.py`.
  - Documented permanently in `docs/MUSIC_PRODUCTION_POLICY.md`.
- **Official YuE2 ABC Compiler & V7.2 Conditioning (`engine/generation/adapters/yue2_adapter.py`):**
  - Fixed `compile_instrumental_abc_for_plan()` to pass the exact official `compile_score.compile_events()` schema (`bpm`, `key`, `bars`, `notes` with fraction strings, optional normalized `chords`) and unpack `(text, check)`.
  - Aligned style prompt and `cfg_scale=2.4` with V7.2 Magnetic Afterhours, added `--tokens` capture (`semantic_tokens.csv`) for continuation/resynthesis, and aligned Demucs vocal-stem QA with V7.2's conservative principle ("stem energy alone cannot establish vocals → `UNCERTAIN`").
- **Director, Jobs, Proposals & Advisor Upgrades:**
  - `director.py`: Added `rnb_neosoul` (90 BPM D minor) and `indie_rock` (116 BPM E minor), fixed Korean vocal negation parsing (`"보컬과 허밍은 전혀 사용하지 말고"` → `instrumentalOnly=True`), fixed `"코드 진행"` misrouting into `loop_midi`, replaced hardcoded preview IDs with `resolve_production_instrument()`, and defaulted full-music plans to `yue2-native`.
  - `daw_jobs.py`: Enforced `resolve_production_route()` with zero silent MIDI fallback, attached real acoustic analysis + 5-Gate Quality Gate + Generation Provenance + `native_audio_original` protection on applied takes.
  - `proposals.py` & `advisor.py`: Protected full-music & reference prompts from being hijacked by single-track FX routing; added Native Audio full-mix diagnosis & mix-safe non-destructive EQ / subtle Return Room send; fixed empty-track targeting.
  - `engine/fx/studio_preview.py`: Revision/hash-tracked Studio Preview (`Original Audio`, `Realtime Preview`, `Studio Preview`, `Rendering`, `Outdated Preview`, `Failed`) using the exact 3-pass Studio Render path + headroom safety protection (`-0.5 dBFS` when float peaks exceed `-0.3 dBFS`).
- **REST, MCP & Minimal UI Wiring:**
  - Added `/api/production/*` (policy, taste CRUD/feedback/reset, instrument resolve/validate) and `/api/projects/{id}/studio-preview/{status,render,audio}`.
  - Expanded MCP server from 81 to **88 tools** (`9 music.*` + `79 daw.*`) with `PREVIEW` blocking on `daw.assign_instrument_preset` unless `allow_preview=True`.
  - Updated `AIProducerPanel.tsx` default `prodMode` to `"neural_audio"` and added compact `Studio Preview` status badge + 1-click audition button (zero UI redesign).

---

## 4. Minimal Validation Suite Results (`TEST 01` – `TEST 08`)

| Test | Description | Result | Key Evidence |
|---|---|---|---|
| **TEST 01** | YuE2 Runtime Smoke Test | **PASS** | `outputs/daw/smoke_test_01/yue2_smoke_22s.wav` (`48kHz stereo`, `21.999s`, `4.56 GiB RSS`, `exit 0`, `GENERATION_VERIFIED`) |
| **TEST 02** | DAW Native Generation (`Native Production Validation 001`) | **PASS (Technical / Policy)** · **UNVERIFIED (Musicality)** | Prompt: `"세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘."` → `yue2-native`, `official_v6_compile_score`, `21.999s`, measured `90.8 BPM` (target `90.0`), `stereoWidth=0.529`, `native_audio_original` protected, `Original Audio` status, saved & reloaded cleanly |
| **TEST 03** | No Silent MIDI Fallback | **PASS** | Simulated unavailable YuE2 via temp `DAW_RUNTIME_CONFIG` (zero models deleted): both REST and MCP returned `engineUnavailable=True`, `silentFallbackBlocked=True`, explicit alternatives, and `0` MIDI takes |
| **TEST 04** | Instrument Quality Policy (UI / REST / MCP) | **PASS** | All 7 legacy voices tagged `PREVIEW` (`autoSelectInProduction=False`); blocked in `/api/production/instruments/validate`, `resolve_production_instrument`, `create_composition_plan`, and `mcp_tools.assign_instrument_preset`; allowed only with explicit `allow_preview=True` |
| **TEST 05** | Acoustic Diagnosis & Sound Design on TEST 02 WAV | **PASS** | Prompt: `"전체적으로 먹먹하지 않게 정리하고 공간감을 자연스럽게 만들어줘."` → diagnosed `290.2 Hz` centroid & `27.75%` low-mid → staged non-destructive Mix-Safe EQ (`HPF 32Hz`, `290Hz -2.0dB`, `9kHz +1.6dB`) + `Natural Room` Return Send (`-17.5 dB`) → centroid `+57.9 Hz`, high clarity `+68%`, width `+0.015`, audible RMS delta `0.06034`, rendered `Studio Preview.wav` (`0` clipped samples) |
| **TEST 06** | Hybrid Editing on TEST 02 WAV | **PASS** | Companion project `Native Production Validation 001 (Hybrid)` (`proj_deb5741452`): Demucs 4-stem separation muted original track (zero double playback, original asset intact), applied `warm_tape` saturation to `Drums (Stem)` only, layered `sf-ep-rhodes` (`PRODUCTION_CANDIDATE`, zero `PREVIEW`), rendered `Studio Preview` |
| **TEST 07** | Persistent Policy & Taste Profile after Restart | **PASS** | After server restart, fresh project + `"인디 록 만들어줘."` routed to `yue2-native` (`indie_rock`, `neural_audio`, `0` preview voices); MCP policy & `outputs/daw/taste_profile.json` persisted |
| **TEST 08** | Reference Binding Smoke Test (`V7.2`) | **PASS** | Analyzed real `V7.2_Magnetic_Afterhours_12s.wav` (`F minor`, `129.4 BPM`) → bound to `yue2-native` plan with traceability note; strict `drum_rhythm=locked` on `yue2-native` honestly marked `unsupported` with Korean warnings |

---

## 5. 5-Gate Quality Gate Summary (`Native Production Validation 001`)

| Gate | Status | Details |
|---|---|---|
| **Gate A · Engine Integrity** | **PASS** | Requested `auto`, routed & executed `yue2-native`, `silentFallbackOccurred: false` |
| **Gate B · Production Policy** | **PASS** | `previewInstrumentsDetected: []`, `nativeAudioPreserved: true` |
| **Gate C · Audio Integrity** | **WARNING** | `48 kHz` stereo, `21.999 s`, finite PCM, `0%` silence; raw float take peaked at `+0.67 dBTP` (cleanly headroom-trimmed to `-2.34 dBTP` / `0` clipped samples in Audio B and `-1.58 dBTP` / `0` clipped samples in Audio C); Demucs vocal screening `UNCERTAIN` (low syllabic modulation `0.143`, melodic bleed in vocal stem `-21.7 dBFS` — manual listening required) |
| **Gate D · Musical Risk Detection** | **WARNING** | Tempo locked (`90.8` vs `90.0 BPM`), natural stereo width (`0.529`); low spectral centroid (`302.2 Hz`) flagged and addressed non-destructively in TEST 05; **subjective musicality: `UNVERIFIED`** |
| **Gate E · Playback Verification** | **PASS** | Verified live in browser (`http://127.0.0.1:8796`): waveform & section markers rendered, `prod-mode-neural_audio` active by default, `Studio Preview` badge visible, transport playhead advanced `00:00.00 -> 00:01.61`, Studio Preview button toggled cleanly, persisted across reload, `0` console / page / HTTP 4xx-5xx errors |

---

## 6. Audio Comparison Table (For User Direct Listening)

| Label | File | Engine / Processing | Duration | Integrated LUFS | True Peak | Clipped Samples |
|---|---|---|---:|---:|---:|---:|
| **Audio A (Previous Baseline)** | `outputs/daw/projects/proj_1bc8e66cfe/exports/After Midnight — Take 02.wav` (untouched existing export) | FluidSynth / MIDI Composer | `87.333 s` | `-16.66 LUFS` | `-1.94 dBTP` | `0` |
| **Audio B (New Native Audio)** | `outputs/daw/projects/proj_5e536a5f75/exports/Native Production Test.wav` | **YuE2 Native Audio** (`yue-synth` Metal + official `compile_score.py`, `seed=2026`, headroom-safe PCM-24) | `24.000 s` | `-16.44 LUFS` | `-2.34 dBTP` | `0` |
| **Audio C (Sound Design Studio Preview)** | `outputs/daw/projects/proj_5e536a5f75/exports/Studio Preview.wav` | Audio B + non-destructive Mix-Safe EQ (`HPF 32Hz`, `290Hz -2dB`, `9kHz +1.6dB`) + `Natural Room` Return Send (`-17.5 dB`) | `24.000 s` | `-16.99 LUFS` | `-1.58 dBTP` | `0` |

> Notice all three files are naturally within **±0.35 LU** of `-16.7 LUFS` (`-16.66` / `-16.44` / `-16.99 LUFS`), enabling fair level-matched A/B/C listening by the user without loudness bias.

---

## 7. Automated Test Summary

- **Phase 05.1 Suite (`tests/test_phase051_native_production.py`):** `7 passed` (`0 failed`)
- **Regression Suite (`pytest`):** `98 passed`, `1 skipped` across Phase 01–05.1 (1 pre-existing host-environment sensitivity in `test_real_studio_v72_excerpt_transcription` on Basic Pitch `0.4.0` bass stem note threshold, unrelated to Phase 05.1)
- **Frontend (`vitest` + `tsc -b && vite build`):** `14 passed` (`0 failed`), clean production bundle build.
