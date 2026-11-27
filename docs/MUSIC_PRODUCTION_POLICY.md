# AI-Native DAW · Permanent Music Production Policy

**Status:** Active (Permanent — Phase 05.1+)  
**Source of Truth:**
- `config/production/default_policy.json`
- `config/production/engine_routing.json`
- `config/production/instrument_quality.json`
- `engine/production/policy.py`

---

## 1. Core Production Rules (Enforced across UI, REST, MCP, Claude Code, Codex, Antigravity)

1. **YuE2 First (`defaultFullMusicEngine: "yue2-native"`):**
   - Full-music natural-language requests (`"세련된 R&B 힙합 인스트루멘탈 만들어줘"`, `"인디 록 만들어줘"`, `"이 레퍼런스 느낌으로 만들어줘"`) MUST default to **YuE2 Native Audio** (`yue2-native`).
2. **No Silent MIDI Fallback (`allowSilentMidiFallback: false`):**
   - If `yue2-native` is not installed, missing weights/binaries, or fails, the DAW MUST stop honestly, explain the exact missing requirement or error, present explicit alternatives (`Editable MIDI + Pro Instruments`, `Hybrid Mode`), and wait for explicit user selection.
   - It MUST NEVER silently generate low-quality MIDI and present it as a normal full-music generation.
3. **No Preview Instruments in Production (`allowPreviewInstrumentsInProduction: false`):**
   - Legacy Phase 03 lightweight synths (`drum-kit-electronic`, `bass-fm-sub`, `keys-electric-ep`, `guitar-clean-pluck`, `synth-fm-hook`, `pad-warm-analog`, `basic-poly-synth`) are permanently classified as `PREVIEW`.
   - Production planning, generation, and hybrid layering MUST resolve instruments via `engine/production/instrument_resolver.py` (`PRODUCTION_CANDIDATE` or `USER_APPROVED` only), unless the user explicitly overrides with `allowPreviewInstruments=true`.
   - `PREVIEW` voices must never be misrepresented as production-ready or studio-realistic instruments.
4. **Preserve Native Audio (`preserveNativeAudio: true`):**
   - Generated or imported Native Audio is stored untouched (`assetKind: "native_audio_original"`, `protectedFromMidiOverwrite: true`).
   - Editing Native Audio uses non-destructive Audio FX, Demucs stem separation (muting only the source track), or Hybrid Pro Instrument layering — never silently replacing rich Native Audio with flat MIDI transcription.
5. **Instrumental by Default (`instrumentalByDefault: true`):**
   - Unless the user explicitly requests singing/vocals/lyrics (and negative phrasing like `"보컬 없이"`, `"보컬과 허밍은 전혀 사용하지 말고"`, `"무보컬"` is strictly respected as instrumental), generation runs the official YuE2 resting-voice instrumental ABC workflow (`V:Vocal` rests only, `V:Ins` melody) plus post-generation vocal-leakage screening.
6. **Honest Preview & Export Parity (`Studio Preview`):**
   - Playback distinguishes explicitly between `Original Audio`, `Realtime Preview`, `Studio Preview`, `Rendering`, `Outdated Preview`, and `Failed`.
   - Whenever track/master FX, instruments, sends, or automation are present, users can audition the exact revision-tracked Studio Render before exporting WAV.
7. **Honest Sound Design (`autoSoundDesign: true`, Non-Destructive):**
   - Sound Design runs real acoustic diagnosis first. On already-mixed Native Audio, it applies only gentle, acoustically warranted processing (e.g., low-mid mud cleanup, gentle bus/room sheen, headroom protection) and explicitly states when no FX is needed rather than blindly piling reverb/distortion.
8. **Persistent User Music Taste Profile:**
   - Stored in `outputs/daw/taste_profile.json` (gitignored, inspectable, editable, resettable via REST/MCP), separated into global preferences and per-project overrides.
9. **5-Gate Quality Gate & Anti-Fabrication:**
   - Every production take/render can be evaluated across `Gate A` (Engine Integrity), `Gate B` (Production Policy), `Gate C` (Audio Integrity), `Gate D` (Musical Risk Detection), and `Gate E` (Playback Verification).
   - Subjective musicality always stays `UNVERIFIED` until the user listens and decides.
10. **No Paid Services Without Explicit Approval (`requireUserApprovalForPaidServices: true`):**
    - Paid APIs, commercial sample packs, or multi-GB model downloads require explicit user approval.

---

## 2. Engine Routing Table

| Request Type | Default Route | When Engine Unavailable / Constrained |
|---|---|---|
| Full Music Generation | `yue2-native` (`neural_audio`) | Block & explain honestly + offer `Editable MIDI` or `Hybrid` (zero silent fallback) |
| Existing Native Audio + New Layer / Stem Edit | `hybrid` | Preserve native audio untouched; layer `PRODUCTION_CANDIDATE`/`USER_APPROVED` instruments or Demucs stems |
| Explicit MIDI / Loop / Note Editing | `local-multitrack-composer` / `midi-composer-v3` (`editable_midi`) | Strictly enforce `PRODUCTION_CANDIDATE`/`USER_APPROVED` instruments |
| Exact Drum/Bass Event Lock (`LOCK`) | `hybrid` or `editable_midi` | Explicitly warn that YuE2 cannot hard-guarantee event-level note locks |

---

## 3. Instrument Quality Tiers

- **`PREVIEW`**: Lightweight browser sketch voices (`autoSelectInProduction: false`). Never auto-selected in production.
- **`PRODUCTION_CANDIDATE`**: FluidSynth SF3 multi-sampled instruments (`sf-*`), `pro-drum-rack`, `pro-synth-analog`, `pro-synth-fm`, `pro-sampler` (`autoSelectInProduction: true` when runtime ready; honest realism limitations reported, e.g. SF3 clean guitar vs real R&B guitar).
- **`USER_APPROVED`**: Instruments or external AU/VST3 plugins explicitly approved by the user after listening.
- **`UNAVAILABLE`**: Missing local runtime/SoundFont or unverified host plugins.
