"""Professional Audio Sampler, Multi-Zone Key/Velocity Mapping & Transient Slicer (Phase 05 · GATE 3).

Supports:
- Single-sample & Multi-sample (key zones + velocity layers) playback
- Start/End trim, Root Note, Semitone & Fine-Tune Cent pitch transposition, Reverse, Loop
- Playback modes: `one_shot`, `sustain`, `loop`
- Full ADSR envelope, Low-pass Filter cutoff/resonance, Gain dB, Velocity sensitivity
- Transient detection & Slice-to-MIDI (slices any drum break / melodic loop into playable MIDI pads!)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw_workspace.schema import make_id


def _load_stereo_at_sr(path: Path, target_sr: int) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    if int(sr) != target_sr and len(data) > 0:
        g = math.gcd(int(sr), target_sr)
        ch0 = signal.resample_poly(data[:, 0], target_sr // g, int(sr) // g)
        ch1 = signal.resample_poly(data[:, 1], target_sr // g, int(sr) // g)
        data = np.stack([ch0, ch1], axis=1).astype(np.float32)
    return data


def _pitch_shift_resample(stereo: np.ndarray, semitones: float) -> np.ndarray:
    """High-quality linear/cubic pitch transposition preserving stereo imaging."""
    if abs(semitones) < 1e-4 or len(stereo) < 4:
        return stereo
    ratio = 2.0 ** (semitones / 12.0)
    new_len = max(4, int(round(len(stereo) / ratio)))
    x_old = np.linspace(0.0, 1.0, len(stereo), dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, new_len, dtype=np.float64)
    ch0 = np.interp(x_new, x_old, stereo[:, 0])
    ch1 = np.interp(x_new, x_old, stereo[:, 1])
    return np.stack([ch0, ch1], axis=1).astype(np.float32)


def slice_audio_by_transients(
    audio_path: Path,
    *,
    bpm: float = 120.0,
    sensitivity: float = 0.55,
    min_slice_sec: float = 0.08,
    max_slices: int = 32,
    base_midi_note: int = 36,
) -> dict[str, Any]:
    """Detect real spectral-flux transients in an audio file and produce playable Sampler Slices + Slice MIDI."""
    data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float64)
    dur_sec = len(mono) / max(1, int(sr))
    if len(mono) < 512:
        return {"audioPath": str(audio_path), "durationSec": dur_sec, "slices": [], "midiNotes": []}

    target_sr = 22050
    if int(sr) != target_sr:
        g = math.gcd(int(sr), target_sr)
        mono = signal.resample_poly(mono, target_sr // g, int(sr) // g)
    nperseg = 1024
    hop = 220
    _, _, zxx = signal.stft(mono, fs=target_sr, nperseg=nperseg, noverlap=nperseg - hop, boundary=None)
    mag = np.abs(zxx)
    flux = np.maximum(np.diff(mag, axis=1), 0.0).sum(axis=0)
    frame_rate = target_sr / float(hop)
    mx = float(np.max(flux)) + 1e-9
    norm = flux / mx

    sigma_mult = max(0.25, 1.8 - sensitivity * 1.45)
    thresh = max(0.08, float(np.mean(norm) + sigma_mult * np.std(norm)))
    dist = max(1, int(round(min_slice_sec * frame_rate)))
    peaks, _ = signal.find_peaks(norm, height=thresh, distance=dist, prominence=thresh * 0.25)

    boundaries = [0.0]
    for p in peaks:
        t_s = round(float(p) / frame_rate, 4)
        if t_s > boundaries[-1] + min_slice_sec and t_s < dur_sec - 0.03:
            boundaries.append(t_s)
    if len(boundaries) > max_slices:
        boundaries = boundaries[:max_slices]
    boundaries.append(round(dur_sec, 4))

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    slices: list[dict[str, Any]] = []
    midi_notes: list[dict[str, Any]] = []
    for idx in range(len(boundaries) - 1):
        s0, s1 = boundaries[idx], boundaries[idx + 1]
        note_pitch = min(127, base_midi_note + idx)
        slices.append(
            {
                "index": idx,
                "midiNote": note_pitch,
                "startSec": s0,
                "endSec": s1,
                "durationSec": round(s1 - s0, 4),
            }
        )
        midi_notes.append(
            {
                "id": make_id("note"),
                "pitch": note_pitch,
                "velocity": 100,
                "startBeat": round(s0 / sec_per_beat, 4),
                "durationBeats": round(max(0.0625, (s1 - s0) / sec_per_beat), 4),
            }
        )

    return {
        "audioPath": str(audio_path),
        "durationSec": round(dur_sec, 4),
        "sliceCount": len(slices),
        "slices": slices,
        "midiNotes": midi_notes,
    }


def render_sampler_sequence(
    notes: list[dict[str, Any]],
    *,
    sampler_config: dict[str, Any],
    bpm: float = 120.0,
    total_beats: float = 16.0,
    sr: int = 48000,
) -> np.ndarray:
    """Render MIDI notes through a Single-Sample, Sliced, or Multi-Zone Sampler."""
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    rel_sec = max(0.01, float(sampler_config.get("releaseSec", 0.08)))
    total_samples = max(int(sr * 0.5), int(round((total_beats * sec_per_beat + rel_sec + 0.5) * sr)))
    if not notes:
        return np.zeros((total_samples, 2), dtype=np.float32)

    zones: list[dict[str, Any]] = list(sampler_config.get("zones") or [])
    slices: list[dict[str, Any]] = list(sampler_config.get("slices") or [])
    default_path_str = sampler_config.get("samplePath")
    audio_cache: dict[str, np.ndarray] = {}

    def _get_audio(path_str: str | None) -> np.ndarray | None:
        if not path_str:
            return None
        if path_str not in audio_cache:
            p = Path(path_str)
            if not p.is_file():
                return None
            audio_cache[path_str] = _load_stereo_at_sr(p, sr)
        return audio_cache[path_str]

    playback_mode = str(sampler_config.get("playbackMode", "sustain"))  # one_shot | sustain | loop
    root_note_default = int(sampler_config.get("rootNote", 60))
    pitch_semi_global = float(sampler_config.get("pitchSemitones", 0.0))
    fine_cents = float(sampler_config.get("fineTuneCents", 0.0))
    reverse = bool(sampler_config.get("reverse", False))
    atk_sec = max(0.001, float(sampler_config.get("attackSec", 0.003)))
    dec_sec = max(0.01, float(sampler_config.get("decaySec", 0.25)))
    sus_lvl = max(0.0, min(1.0, float(sampler_config.get("sustain", 0.9))))
    cutoff_hz = float(sampler_config.get("filterCutoffHz", 18000.0))
    gain_lin = 10.0 ** (float(sampler_config.get("gainDb", 0.0)) / 20.0)
    vel_sens = max(0.0, min(1.0, float(sampler_config.get("velocitySensitivity", 0.85))))

    buf = np.zeros((total_samples, 2), dtype=np.float64)

    for n in notes:
        pitch = int(n.get("pitch", 60))
        vel = max(1, min(127, int(n.get("velocity", 100))))
        st_sec = max(0.0, float(n.get("startBeat", 0.0)) * sec_per_beat)
        dur_sec = max(0.02, float(n.get("durationBeats", 0.5)) * sec_per_beat)

        # Resolve sample source: 1) slice map -> 2) multi-zone key/vel -> 3) single default sample
        src_path = default_path_str
        start_s = float(sampler_config.get("startSec", 0.0))
        end_s = sampler_config.get("endSec")
        root_note = root_note_default
        is_slice = False

        if slices:
            sl = next((s for s in slices if int(s.get("midiNote", -1)) == pitch), None)
            if sl is not None:
                start_s = float(sl["startSec"])
                end_s = float(sl["endSec"])
                root_note = pitch  # play slice at native pitch!
                is_slice = True
        elif zones:
            matched_z = next(
                (
                    z for z in zones
                    if int(z.get("lowNote", 0)) <= pitch <= int(z.get("highNote", 127))
                    and int(z.get("lowVel", 1)) <= vel <= int(z.get("highVel", 127))
                ),
                zones[0],
            )
            src_path = matched_z.get("samplePath") or default_path_str
            root_note = int(matched_z.get("rootNote", root_note_default))
            start_s = float(matched_z.get("startSec", 0.0))
            end_s = matched_z.get("endSec")

        src = _get_audio(src_path)
        if src is None or len(src) == 0:
            continue

        i0 = max(0, min(len(src) - 1, int(round(start_s * sr))))
        i1 = len(src) if end_s is None else max(i0 + 4, min(len(src), int(round(float(end_s) * sr))))
        seg = src[i0:i1].copy()
        if reverse:
            seg = seg[::-1].copy()

        # Transpose to played MIDI pitch (slices play native pitch + global pitchSemitones)
        semi_shift = (0.0 if is_slice else (pitch - root_note)) + pitch_semi_global + (fine_cents / 100.0)
        seg = _pitch_shift_resample(seg, semi_shift)

        target_len = len(seg) if playback_mode == "one_shot" else int(round((dur_sec + rel_sec) * sr))
        if playback_mode == "loop" and len(seg) < target_len and len(seg) > 8:
            reps = int(math.ceil(target_len / len(seg)))
            seg = np.tile(seg, (reps, 1))[:target_len]
        elif len(seg) > target_len:
            seg = seg[:target_len]

        n_s = len(seg)
        if n_s <= 0:
            continue

        # Apply ADSR envelope
        env = np.ones(n_s, dtype=np.float64)
        atk_n = min(n_s, max(1, int(round(atk_sec * sr))))
        env[:atk_n] = np.linspace(0.0, 1.0, atk_n)
        if playback_mode != "one_shot":
            off_n = min(n_s, max(atk_n, int(round(dur_sec * sr))))
            if off_n > atk_n:
                tb = np.arange(off_n - atk_n) / sr
                env[atk_n:off_n] = sus_lvl + (1.0 - sus_lvl) * np.exp(-tb / dec_sec)
            if n_s > off_n:
                sv = float(env[off_n - 1])
                env[off_n:] = sv * np.linspace(1.0, 0.0, n_s - off_n) ** 1.4
        else:
            fade_n = min(n_s, int(0.008 * sr))
            if fade_n > 1:
                env[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)

        vel_gain = ((1.0 - vel_sens) + vel_sens * (vel / 127.0)) * gain_lin
        dst = int(round(st_sec * sr))
        w = min(n_s, total_samples - dst)
        if w > 0 and dst >= 0:
            buf[dst : dst + w, 0] += seg[:w, 0] * env[:w] * vel_gain
            buf[dst : dst + w, 1] += seg[:w, 1] * env[:w] * vel_gain

    out = buf.astype(np.float32)
    if cutoff_hz < 16000.0 and cutoff_hz >= 120.0:
        sos = signal.butter(2, min(0.95, cutoff_hz / (sr * 0.5)), btype="lowpass", output="sos")
        out[:, 0] = signal.sosfilt(sos, out[:, 0]).astype(np.float32)
        out[:, 1] = signal.sosfilt(sos, out[:, 1]).astype(np.float32)
    return out
