# Third-Party Open-Source Engines, Models & Sound Libraries

AI-Native DAW builds on verified open-source audio engines, DSP libraries, and multi-sampled soundfonts instead of reinventing every synthesizer or effect from scratch. Every external component's license, provenance, and installation status is tracked honestly below.

| Component | Role in AI-Native DAW | License | Commercial Use Note | Status in Current Local Environment |
|---|---|---|---|---|
| **Spotify `pedalboard` (`0.9.26`)** | C++ JUCE DSP effects (EQ, Compressor, Reverb, Convolution IR, Delay, Chorus, Phaser, Distortion, Limiter, NoiseGate, LadderFilter, PitchShift, Bitcrush) + macOS AU / VST3 plugin hosting | **GPL-3.0** | Copyleft (GPL-3.0) if distributed | Installed & live-verified in `.venv` |
| **FluidSynth (`2.6.3`) + `pyfluidsynth` (`1.4.0`)** | Real-time & offline SF2 / SF3 multi-sampled virtual instrument playback (Acoustic/Electric Pianos, Organs, Guitars, Electric/Upright Basses, Acoustic/Electronic Drum Kits, Strings, Pads) | **LGPL-2.1** | Dynamic linking permitted under LGPL-2.1 | Installed via Homebrew (`/opt/homebrew/lib/libfluidsynth.dylib`) & live-verified |
| **MuseScore General SoundFont (`MuseScore_General.sf3`, 39.9 MB)** | Multi-sampled General MIDI studio instrument library (downloaded to gitignored `outputs/daw/soundfonts/MuseScore_General.sf3`, SHA-256 `5b85b6c2c61d10b2b91cddd41efcce7b25cd31c8271d511c73afafbef20b6fa3`) | **MIT** | Permissive (MIT — Frank Wen / Michael Cowgill / S. Christian Collins) | Downloaded locally (gitignored) & live-verified |
| **VintageDreamsWaves-v2 (`VintageDreamsWaves-v2.sf2`)** | Bundled FluidSynth vintage analog waveform SoundFont | **Public Domain / FluidSynth bundled** | Bundled with Homebrew FluidSynth | Installed via Homebrew FluidSynth |
| **Demucs (`htdemucs`, Meta Research)** | 4-stem audio separation (`drums`, `bass`, `other`, `vocals`) on Apple Silicon MPS + isolated vocal-stem screening | **MIT** | Permissive | Installed & live-verified in `.venv` |
| **Spotify Basic Pitch (`ONNX`)** | Polyphonic & monophonic Audio-to-MIDI transcription (`bass` & `other` melody extraction) | **Apache-2.0** | Permissive | Installed & live-verified in `.venv` |
| **Web Audio API (Browser Native)** | Realtime browser playback, transport scheduling, low-latency preview, mirrored live EQ/Comp/Reverb/Delay/Automation | **W3C Standard** | Built into macOS browsers | Built-in & live-verified |
| **Apple CoreAudio Built-in AU (`AUNBandEQ`, `AUDynamicsProcessor`, `AUReverb2`, `AUDelay`, `AUPeakLimiter`, etc.)** | Host-detected system Audio Unit plugins (read-only scanner via `auval -a`) | **macOS System** | Host OS component (not redistributed) | Detected on macOS host (note: Logic-only AUs are NOT assumed installed) |
| **Surge XT (`v1.3.4`, optional host AU/VST3)** | Open-source hybrid synthesizer (auto-detected if user installs AU/VST3 into `/Library/Audio/Plug-Ins/`) | **GPL-3.0** | Copyleft (user-installed plugin) | Optional — not pre-installed globally |
| **YuE2 Native (`yue2.cpp` + `YuE2-3B-Q8_0.gguf` + `YuE2-Vae-F32.gguf`)** | Local neural full-song audio generation (Apple Metal) | **Apache-2.0** (weights) / MIT (`yue2.cpp`) | Separate optional local install (~4.5 GiB weights + `cmake`) | Optional — not present on local disk (V7.2 golden WAVs preserved locally) |
| **SheetSage2 (optional)** | Lead sheet & chord/melody transcription | **CC BY-NC 4.0** | **Non-Commercial ONLY** | Uninstalled by default due to non-commercial license & FFmpeg/3 GiB MERT dependency |

## Copyright & Sample Safety Policy
- No copyrighted commercial sample packs, ripped audio stems, or proprietary Logic Pro / Ableton stock packs are downloaded or bundled.
- Large binary soundfonts (`.sf2`, `.sf3`) and neural weights (`.gguf`, `.pth`, `.safetensors`) remain strictly gitignored under `outputs/` or `.runtime/`.
