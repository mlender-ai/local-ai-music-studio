"""FluidSynth Multi-Sampled SF3/SF2 Virtual Instrument Engine (Phase 05 · GATE 3).

Uses Homebrew FluidSynth (`libfluidsynth.dylib`, LGPL-2.1) + MIT-licensed `MuseScore_General.sf3`
(downloaded to gitignored `outputs/daw/soundfonts/MuseScore_General.sf3`) to render real multi-sampled
Acoustic/Electric Pianos, Organs, Guitars, Basses, Strings, Pads, and Acoustic/Electronic Drum Kits.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal

from engine import paths as engine_paths

_LIB_LOADED = False
_FLUIDSYNTH_MOD: Any = None


def _ensure_fluidsynth() -> Any:
    """Safely load Homebrew libfluidsynth.dylib on macOS Apple Silicon before importing pyfluidsynth."""
    global _LIB_LOADED, _FLUIDSYNTH_MOD
    if _FLUIDSYNTH_MOD is not None:
        return _FLUIDSYNTH_MOD
    if not _LIB_LOADED:
        for candidate in (
            "/opt/homebrew/lib/libfluidsynth.dylib",
            "/usr/local/lib/libfluidsynth.dylib",
        ):
            if Path(candidate).is_file():
                try:
                    ctypes.CDLL(candidate)
                except OSError:
                    pass
                cur_fb = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
                lib_dir = str(Path(candidate).parent)
                if lib_dir not in cur_fb.split(":"):
                    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = f"{lib_dir}:{cur_fb}" if cur_fb else lib_dir
                # Patch ctypes.util.find_library if pyfluidsynth calls it on macOS
                _orig_find = ctypes.util.find_library

                def _patched_find(name: str) -> str | None:
                    if "fluidsynth" in name.lower():
                        return candidate
                    return _orig_find(name)

                ctypes.util.find_library = _patched_find  # type: ignore[assignment]
                break
        _LIB_LOADED = True
    try:
        import fluidsynth as fs_mod  # type: ignore

        _FLUIDSYNTH_MOD = fs_mod
        return fs_mod
    except Exception:
        return None


def resolve_default_soundfont() -> Path | None:
    candidates = [
        engine_paths.ROOT / "outputs" / "daw" / "soundfonts" / "MuseScore_General.sf3",
        engine_paths.ROOT / "outputs" / "daw" / "soundfonts" / "MuseScore_General.sf2",
        Path("/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2"),
    ]
    # Also check versioned Homebrew Cellar path
    cellar = Path("/opt/homebrew/Cellar/fluid-synth")
    if cellar.is_dir():
        for sf2 in cellar.glob("*/share/fluid-synth/sf2/*.sf2"):
            candidates.append(sf2)
    for p in candidates:
        if p.is_file():
            return p
    return None


def probe_fluidsynth_engine() -> dict[str, Any]:
    fs_mod = _ensure_fluidsynth()
    sf_path = resolve_default_soundfont()
    avail = bool(fs_mod is not None and sf_path is not None)
    return {
        "available": avail,
        "pyfluidsynthLoaded": fs_mod is not None,
        "soundfontPath": str(sf_path) if sf_path else None,
        "soundfontName": sf_path.name if sf_path else None,
        "license": "LGPL-2.1 (FluidSynth) + MIT (MuseScore_General.sf3)",
    }


# Canonical studio SF3/SF2 multi-sampled instruments mapped to GM/GS banks in MuseScore_General.sf3
SOUNDFONT_INSTRUMENTS: dict[str, dict[str, Any]] = {
    # --- P0 Drums ---
    "sf-drums-acoustic": {
        "name": "Studio Acoustic Drum Kit",
        "nameKo": "스튜디오 어쿠스틱 드럼 킷",
        "category": "drums",
        "bank": 128,
        "program": 0,
        "isDrum": True,
        "presets": [
            {"id": "standard", "name": "Studio Standard", "bank": 128, "program": 0, "brightness": 0.65, "punch": 0.6},
            {"id": "rock", "name": "Indie Rock Power", "bank": 128, "program": 16, "brightness": 0.72, "punch": 0.8},
            {"id": "jazz", "name": "Jazz Warm Kit", "bank": 128, "program": 32, "brightness": 0.55, "punch": 0.45},
            {"id": "brush", "name": "Jazz Brush Kit", "bank": 128, "program": 40, "brightness": 0.50, "punch": 0.35},
            {"id": "room", "name": "Live Room Kit", "bank": 128, "program": 8, "brightness": 0.62, "punch": 0.68},
        ],
    },
    "sf-drums-electronic": {
        "name": "Electronic & 808/909 Drum Kit",
        "nameKo": "일렉트로닉 808/909 드럼 킷",
        "category": "drums",
        "bank": 128,
        "program": 24,
        "isDrum": True,
        "presets": [
            {"id": "electronic", "name": "House Electronic", "bank": 128, "program": 24, "brightness": 0.78, "punch": 0.85},
            {"id": "tr808", "name": "TR-808 Analog", "bank": 128, "program": 25, "brightness": 0.68, "punch": 0.90},
        ],
    },
    # --- P0 Bass ---
    "sf-bass-electric": {
        "name": "Studio Electric Bass",
        "nameKo": "스튜디오 일렉트릭 베이스",
        "category": "bass",
        "bank": 0,
        "program": 33,
        "isDrum": False,
        "presets": [
            {"id": "fingered", "name": "Fingered Precision", "bank": 0, "program": 33, "cutoffHz": 4200.0},
            {"id": "picked", "name": "Picked Rock Bass", "bank": 0, "program": 34, "cutoffHz": 5800.0},
            {"id": "fretless", "name": "Fretless Warm", "bank": 0, "program": 35, "cutoffHz": 3200.0},
            {"id": "slap", "name": "Funk Slap Bass", "bank": 0, "program": 36, "cutoffHz": 7200.0},
            {"id": "upright", "name": "Jazz Upright Bass", "bank": 0, "program": 32, "cutoffHz": 2600.0},
        ],
    },
    "sf-bass-synth": {
        "name": "Sampled Synth Bass",
        "nameKo": "샘플드 신스 베이스",
        "category": "bass",
        "bank": 0,
        "program": 38,
        "isDrum": False,
        "presets": [
            {"id": "analog_bass_1", "name": "Analog Punch Bass", "bank": 0, "program": 38, "cutoffHz": 2800.0},
            {"id": "analog_bass_2", "name": "Sub Round Bass", "bank": 0, "program": 39, "cutoffHz": 1600.0},
        ],
    },
    # --- P0 Keys & Pianos ---
    "sf-piano-grand": {
        "name": "Concert Grand Piano",
        "nameKo": "콘서트 그랜드 피아노",
        "category": "keys",
        "bank": 0,
        "program": 0,
        "isDrum": False,
        "presets": [
            {"id": "concert_grand", "name": "Concert Grand", "bank": 0, "program": 0, "cutoffHz": 12000.0},
            {"id": "bright_piano", "name": "Bright Pop Piano", "bank": 0, "program": 1, "cutoffHz": 14000.0},
            {"id": "warm_felt", "name": "Warm Felt Lo-Fi", "bank": 0, "program": 0, "cutoffHz": 2400.0},
        ],
    },
    "sf-ep-rhodes": {
        "name": "Vintage Rhodes & Electric Piano",
        "nameKo": "빈티지 로즈 일렉트릭 피아노",
        "category": "keys",
        "bank": 0,
        "program": 4,
        "isDrum": False,
        "presets": [
            {"id": "rhodes_tine", "name": "Rhodes Tine Classic", "bank": 0, "program": 4, "cutoffHz": 7500.0},
            {"id": "dx_chorus", "name": "DX Chorus EP", "bank": 0, "program": 5, "cutoffHz": 9500.0},
            {"id": "jazz_warm_ep", "name": "Jazz Dusty Rhodes", "bank": 0, "program": 4, "cutoffHz": 3400.0},
            {"id": "clavinet", "name": "Funk Clavinet", "bank": 0, "program": 7, "cutoffHz": 8500.0},
        ],
    },
    "sf-organ-vintage": {
        "name": "Vintage Tonewheel Organ",
        "nameKo": "빈티지 오르간",
        "category": "keys",
        "bank": 0,
        "program": 16,
        "isDrum": False,
        "presets": [
            {"id": "drawbar", "name": "Soul Drawbar Organ", "bank": 0, "program": 16, "cutoffHz": 6800.0},
            {"id": "percussive", "name": "Jazz Percussive Organ", "bank": 0, "program": 17, "cutoffHz": 7500.0},
            {"id": "rock_organ", "name": "Overdrive Rock Organ", "bank": 0, "program": 18, "cutoffHz": 6200.0},
        ],
    },
    # --- P0 Guitars ---
    "sf-guitar-clean": {
        "name": "Studio Clean & Jazz Electric Guitar",
        "nameKo": "스튜디오 클린/재즈 기타",
        "category": "guitar",
        "bank": 0,
        "program": 27,
        "isDrum": False,
        "presets": [
            {"id": "clean_strat", "name": "Clean Electric", "bank": 0, "program": 27, "cutoffHz": 8500.0},
            {"id": "jazz_hollow", "name": "Jazz Hollowbody", "bank": 0, "program": 26, "cutoffHz": 4200.0},
            {"id": "muted_funk", "name": "Palm Muted Electric", "bank": 0, "program": 28, "cutoffHz": 6000.0},
            {"id": "acoustic_steel", "name": "Acoustic Steel", "bank": 0, "program": 25, "cutoffHz": 11000.0},
            {"id": "acoustic_nylon", "name": "Acoustic Nylon", "bank": 0, "program": 24, "cutoffHz": 8000.0},
        ],
    },
    "sf-guitar-overdrive": {
        "name": "Rock Overdrive & Distortion Guitar",
        "nameKo": "록 오버드라이브/디스토션 기타",
        "category": "guitar",
        "bank": 0,
        "program": 29,
        "isDrum": False,
        "presets": [
            {"id": "indie_overdrive", "name": "Indie Overdrive", "bank": 0, "program": 29, "cutoffHz": 6500.0},
            {"id": "alt_distortion", "name": "Alternative Distortion", "bank": 0, "program": 30, "cutoffHz": 5800.0},
        ],
    },
    # --- P1 Strings, Mallets, Pads, Brass ---
    "sf-strings-ensemble": {
        "name": "Studio Strings Ensemble",
        "nameKo": "스튜디오 스트링 앙상블",
        "category": "strings",
        "bank": 0,
        "program": 48,
        "isDrum": False,
        "presets": [
            {"id": "strings_rich", "name": "Rich Strings Ensemble", "bank": 0, "program": 48, "cutoffHz": 9000.0},
            {"id": "strings_slow", "name": "Slow Cinematic Strings", "bank": 0, "program": 49, "cutoffHz": 7200.0},
            {"id": "pizzicato", "name": "Pizzicato Strings", "bank": 0, "program": 45, "cutoffHz": 8500.0},
        ],
    },
    "sf-vibraphone": {
        "name": "Jazz Vibraphone & Mallets",
        "nameKo": "재즈 비브라폰 · 말렛",
        "category": "keys",
        "bank": 0,
        "program": 11,
        "isDrum": False,
        "presets": [
            {"id": "vibraphone", "name": "Warm Vibraphone", "bank": 0, "program": 11, "cutoffHz": 8500.0},
            {"id": "marimba", "name": "Wood Marimba", "bank": 0, "program": 12, "cutoffHz": 6500.0},
        ],
    },
    "sf-pad-warm": {
        "name": "Sampled Warm Atmosphere Pad",
        "nameKo": "샘플드 웜 애트모스피어 패드",
        "category": "pad",
        "bank": 0,
        "program": 89,
        "isDrum": False,
        "presets": [
            {"id": "warm_pad", "name": "Warm Analog Bed", "bank": 0, "program": 89, "cutoffHz": 4500.0},
            {"id": "halo_pad", "name": "Airy Halo Pad", "bank": 0, "program": 94, "cutoffHz": 7500.0},
            {"id": "choir_pad", "name": "Soft Synth Strings", "bank": 0, "program": 50, "cutoffHz": 6200.0},
        ],
    },
    "sf-brass-section": {
        "name": "Studio Brass & Horns",
        "nameKo": "스튜디오 브라스 섹션",
        "category": "brass",
        "bank": 0,
        "program": 61,
        "isDrum": False,
        "presets": [
            {"id": "brass_section", "name": "Brass Section", "bank": 0, "program": 61, "cutoffHz": 9000.0},
            {"id": "muted_trumpet", "name": "Jazz Muted Trumpet", "bank": 0, "program": 59, "cutoffHz": 7200.0},
            {"id": "tenor_sax", "name": "Soul Tenor Sax", "bank": 0, "program": 66, "cutoffHz": 6800.0},
        ],
    },
}


def render_soundfont_sequence(
    notes: list[dict[str, Any]],
    *,
    instrument_id: str,
    bpm: float = 120.0,
    total_beats: float = 16.0,
    sr: int = 48000,
    preset_id: str | None = None,
    params: dict[str, Any] | None = None,
    soundfont_path: Path | None = None,
) -> np.ndarray:
    """Render a full MIDI note timeline through FluidSynth (48 kHz Stereo float32) with sample-accurate events."""
    fs_mod = _ensure_fluidsynth()
    sf_p = soundfont_path or resolve_default_soundfont()
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    tail_sec = float((params or {}).get("releaseTailSec", 1.25))
    total_samples = max(int(sr * 0.5), int(round((total_beats * sec_per_beat + tail_sec) * sr)))
    if fs_mod is None or sf_p is None or not sf_p.is_file() or not notes:
        return np.zeros((total_samples, 2), dtype=np.float32)

    spec = SOUNDFONT_INSTRUMENTS.get(instrument_id, SOUNDFONT_INSTRUMENTS["sf-piano-grand"])
    presets = spec.get("presets") or []
    preset_meta = next((p for p in presets if p["id"] == preset_id), presets[0] if presets else {})
    bank = int((params or {}).get("bank", preset_meta.get("bank", spec["bank"])))
    program = int((params or {}).get("program", preset_meta.get("program", spec["program"])))
    is_drum = bool(spec.get("isDrum", False)) or bank == 128
    channel = 9 if is_drum else 0
    gain = float((params or {}).get("gain", 0.72))
    cutoff_hz = float((params or {}).get("cutoffHz", preset_meta.get("cutoffHz", 18000.0)))
    sustain_pedal = bool((params or {}).get("sustainPedal", False))
    pitch_bend_semi = float((params or {}).get("pitchBendSemitones", 0.0))
    transpose = int((params or {}).get("transpose", 0))

    synth = fs_mod.Synth(gain=gain, samplerate=float(sr))
    try:
        sfid = synth.sfload(str(sf_p))
        synth.program_select(channel, sfid, bank, program)
        # Keep FluidSynth built-in reverb/chorus subtle/clean so our dedicated DAW FX chain controls space!
        try:
            synth.set_reverb(0.25, 0.2, 0.5, 0.05)
            synth.set_chorus(0, 0.0, 0.3, 0.0, 0)
        except Exception:
            pass
        if sustain_pedal and not is_drum:
            synth.cc(channel, 64, 127)
        if abs(pitch_bend_semi) > 1e-4 and not is_drum:
            pb_val = int(max(-8192, min(8191, round((pitch_bend_semi / 2.0) * 8192.0))))
            synth.pitch_bend(channel, pb_val)

        # Build sample-sorted MIDI event queue: (sample_index, order_priority, kind, pitch, vel_or_val)
        events: list[tuple[int, int, str, int, int]] = []
        for n in notes:
            st_sec = max(0.0, float(n.get("startBeat", 0.0)) * sec_per_beat)
            dur_sec = max(0.02, float(n.get("durationBeats", 0.25)) * sec_per_beat)
            pitch = int(n.get("pitch", 60)) + (0 if is_drum else transpose)
            pitch = max(0, min(127, pitch))
            vel = max(1, min(127, int(n.get("velocity", 96))))
            s_on = int(round(st_sec * sr))
            s_off = int(round((st_sec + dur_sec) * sr))
            if s_on >= total_samples:
                continue
            events.append((s_on, 1, "on", pitch, vel))
            # Optional per-note pitch bend
            if "pitchBendSemitones" in n and not is_drum:
                pb_n = int(max(-8192, min(8191, round((float(n["pitchBendSemitones"]) / 2.0) * 8192.0))))
                events.append((s_on, 0, "pb", pb_n, 0))
                events.append((min(total_samples - 1, s_off), 0, "pb", 0, 0))
            events.append((min(total_samples - 1, max(s_on + 64, s_off)), 0, "off", pitch, 0))

        events.sort(key=lambda e: (e[0], e[1]))
        out = np.zeros((total_samples, 2), dtype=np.float32)
        cursor = 0
        ev_idx = 0
        n_events = len(events)

        def _render_chunk(start_i: int, end_i: int) -> None:
            n_frames = end_i - start_i
            if n_frames <= 0:
                return
            raw = synth.get_samples(n_frames)
            # pyfluidsynth returns interleaved int16 (2 * n_frames,)
            pcm = np.asarray(raw, dtype=np.float32) / 32768.0
            if pcm.size >= n_frames * 2:
                out[start_i:end_i, 0] = pcm[0 : n_frames * 2 : 2]
                out[start_i:end_i, 1] = pcm[1 : n_frames * 2 : 2]

        while cursor < total_samples:
            if ev_idx < n_events:
                next_pos = min(total_samples, events[ev_idx][0])
            else:
                next_pos = total_samples
            if next_pos > cursor:
                _render_chunk(cursor, next_pos)
                cursor = next_pos
            while ev_idx < n_events and events[ev_idx][0] <= cursor:
                _, _, kind, a, b = events[ev_idx]
                if kind == "on":
                    synth.noteon(channel, a, b)
                elif kind == "off":
                    synth.noteoff(channel, a)
                elif kind == "pb":
                    synth.pitch_bend(channel, a)
                ev_idx += 1
    finally:
        synth.delete()

    # Apply real brightness / low-pass tone shaping if cutoffHz < 16 kHz
    if cutoff_hz < 16000.0 and cutoff_hz >= 120.0:
        nyq = sr * 0.5
        norm_c = min(0.95, max(0.01, cutoff_hz / nyq))
        sos = signal.butter(2, norm_c, btype="lowpass", output="sos")
        out[:, 0] = signal.sosfilt(sos, out[:, 0]).astype(np.float32)
        out[:, 1] = signal.sosfilt(sos, out[:, 1]).astype(np.float32)

    return out
