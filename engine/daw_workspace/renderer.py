"""Deterministic offline Stereo WAV renderer matching Web Audio playback semantics."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from engine.instruments import synth_note_for_instrument

from .schema import Clip, Project, Track
from .store import project_dir, resolve_asset_file


def db_to_linear(db: float) -> float:
    if db <= -60.0:
        return 0.0
    return float(10.0 ** (db / 20.0))


def equal_power_pan(pan: float) -> tuple[float, float]:
    """Match Web Audio StereoPannerNode equal-power panning law."""
    p = max(-1.0, min(1.0, float(pan)))
    x = (p + 1.0) * 0.5
    angle = x * (math.pi * 0.5)
    return math.cos(angle), math.sin(angle)


def _load_stereo_audio(path: Path, target_sr: int) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != target_sr and len(data) > 0:
        g = math.gcd(int(sr), int(target_sr))
        up = int(target_sr) // g
        down = int(sr) // g
        left = resample_poly(data[:, 0], up, down)
        right = resample_poly(data[:, 1], up, down)
        data = np.stack([left, right], axis=1).astype(np.float32)
    return data


def _apply_edge_fades(buf: np.ndarray, sr: int, fade_ms: float = 4.0) -> np.ndarray:
    fade_samples = min(len(buf) // 2, max(1, int(sr * fade_ms / 1000.0)))
    if fade_samples <= 0 or len(buf) == 0:
        return buf
    out = buf.copy()
    ramp = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
    out[:fade_samples] *= ramp
    out[-fade_samples:] *= ramp[::-1]
    return out


def _synth_midi_note(pitch: int, velocity: int, duration_sec: float, sr: int) -> np.ndarray:
    """Warm band-limited poly-synth voice matching Phase 01 Web Audio basic synth."""
    release_sec = 0.08
    total_sec = max(0.02, duration_sec + release_sec)
    n_samples = int(round(total_sec * sr))
    if n_samples <= 0:
        return np.zeros((0, 2), dtype=np.float32)

    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    # Fundamental + soft 2nd & 3rd harmonics (warm electric synth tone)
    phase = 2.0 * math.pi * freq * t
    sig = (
        0.62 * np.sin(phase)
        + 0.24 * np.sin(2.0 * phase) * np.exp(-3.5 * t)
        + 0.10 * np.sin(3.0 * phase) * np.exp(-6.0 * t)
    )

    # ADSR envelope
    env = np.ones(n_samples, dtype=np.float32)
    atk_n = min(n_samples, max(1, int(0.008 * sr)))
    env[:atk_n] = np.linspace(0.0, 1.0, atk_n, dtype=np.float32)

    note_off_idx = min(n_samples, max(atk_n, int(round(duration_sec * sr))))
    decay_n = note_off_idx - atk_n
    if decay_n > 0:
        env[atk_n:note_off_idx] = 0.55 + 0.45 * np.exp(
            -np.linspace(0.0, 3.0, decay_n, dtype=np.float32)
        )
    rel_n = n_samples - note_off_idx
    if rel_n > 0:
        start_val = float(env[note_off_idx - 1]) if note_off_idx > 0 else 0.55
        env[note_off_idx:] = np.linspace(start_val, 0.0, rel_n, dtype=np.float32)

    amp = (velocity / 127.0) * 0.24
    mono = (sig * env * amp).astype(np.float32)
    return np.stack([mono, mono], axis=1)


def active_tracks(tracks: list[Track]) -> list[Track]:
    any_solo = any(t.solo for t in tracks)
    if any_solo:
        return [t for t in tracks if t.solo and not t.mute]
    return [t for t in tracks if not t.mute]


def render_project_to_array(
    project: Project,
    start_beats: float = 0.0,
    end_beats: float | None = None,
) -> tuple[np.ndarray, int]:
    """Render full or ranged Project timeline into float32 stereo numpy array."""
    sr = project.sampleRate
    sec_per_beat = 60.0 / project.bpm
    render_end_beats = end_beats if end_beats is not None else project.lengthBeats
    render_dur_sec = max(0.1, (render_end_beats - start_beats) * sec_per_beat)
    total_samples = int(round(render_dur_sec * sr))
    mix = np.zeros((total_samples, 2), dtype=np.float64)

    asset_cache: dict[str, np.ndarray] = {}

    for trk in active_tracks(project.tracks):
        trk_gain = db_to_linear(trk.gainDb)
        if trk_gain <= 0.0:
            continue
        pan_l, pan_r = equal_power_pan(trk.pan)
        trk_buf = np.zeros((total_samples, 2), dtype=np.float64)

        for clip in trk.clips:
            clip_gain = db_to_linear(clip.gainDb)
            if clip_gain <= 0.0:
                continue
            clip_start_sec = (clip.timelineStartBeats - start_beats) * sec_per_beat
            clip_dur_sec = clip.durationBeats * sec_per_beat
            if clip_start_sec + clip_dur_sec <= 0.0 or clip_start_sec >= render_dur_sec:
                continue

            if clip.type == "audio" and clip.assetId:
                if clip.assetId not in asset_cache:
                    _, abs_path = resolve_asset_file(project.id, clip.assetId)
                    asset_cache[clip.assetId] = _load_stereo_audio(abs_path, sr)
                src = asset_cache[clip.assetId]
                if len(src) == 0:
                    continue

                src_offset_samp = max(0, int(round(clip.sourceOffsetSec * sr)))
                clip_len_samp = max(1, int(round(clip_dur_sec * sr)))
                loop_len_sec = clip.loopLengthSec or max(0.05, (len(src) / sr) - clip.sourceOffsetSec)
                loop_len_samp = max(1, int(round(loop_len_sec * sr)))

                clip_pcm = np.zeros((clip_len_samp, 2), dtype=np.float32)
                if clip.loop:
                    pos = 0
                    while pos < clip_len_samp:
                        chunk_end_src = min(len(src), src_offset_samp + loop_len_samp)
                        avail = max(0, chunk_end_src - src_offset_samp)
                        if avail == 0:
                            break
                        take = min(avail, clip_len_samp - pos)
                        clip_pcm[pos : pos + take] = src[src_offset_samp : src_offset_samp + take]
                        pos += take
                else:
                    avail = max(0, len(src) - src_offset_samp)
                    take = min(avail, clip_len_samp)
                    if take > 0:
                        clip_pcm[:take] = src[src_offset_samp : src_offset_samp + take]

                clip_pcm = _apply_edge_fades(clip_pcm, sr) * clip_gain
                dst_start = int(round(clip_start_sec * sr))
                src_slice_start = max(0, -dst_start)
                dst_write_start = max(0, dst_start)
                write_len = min(len(clip_pcm) - src_slice_start, total_samples - dst_write_start)
                if write_len > 0:
                    trk_buf[dst_write_start : dst_write_start + write_len] += clip_pcm[
                        src_slice_start : src_slice_start + write_len
                    ]

            elif clip.type == "midi":
                loop_len_beats = clip.loopLengthBeats or max(
                    4.0,
                    max((n.startBeat + n.durationBeats for n in clip.notes), default=4.0),
                )
                reps = int(math.ceil(clip.durationBeats / loop_len_beats)) if clip.loop else 1
                for rep in range(reps):
                    rep_offset_beats = rep * loop_len_beats
                    for note in clip.notes:
                        rel_start_beats = rep_offset_beats + note.startBeat
                        if rel_start_beats >= clip.durationBeats:
                            continue
                        clipped_dur_beats = min(note.durationBeats, clip.durationBeats - rel_start_beats)
                        if clipped_dur_beats <= 0.0:
                            continue
                        note_start_sec = clip_start_sec + rel_start_beats * sec_per_beat
                        note_dur_sec = clipped_dur_beats * sec_per_beat
                        voice = (
                            synth_note_for_instrument(trk.instrumentRef, note.pitch, note.velocity, note_dur_sec, sr)
                            * clip_gain
                        )
                        dst_start = int(round(note_start_sec * sr))
                        src_slice_start = max(0, -dst_start)
                        dst_write_start = max(0, dst_start)
                        write_len = min(len(voice) - src_slice_start, total_samples - dst_write_start)
                        if write_len > 0:
                            trk_buf[dst_write_start : dst_write_start + write_len] += voice[
                                src_slice_start : src_slice_start + write_len
                            ]

        mix[:, 0] += trk_buf[:, 0] * trk_gain * pan_l
        mix[:, 1] += trk_buf[:, 1] * trk_gain * pan_r

    master_gain = db_to_linear(project.masterGainDb)
    mix *= master_gain
    return mix.astype(np.float32), sr


def export_project_wav(
    project: Project,
    filename: str | None = None,
    start_beats: float = 0.0,
    end_beats: float | None = None,
) -> dict[str, Any]:
    """Render and write a Stereo PCM-24 WAV export into project/exports/."""
    audio, sr = render_project_to_array(project, start_beats=start_beats, end_beats=end_beats)
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    rms = float(np.sqrt(np.mean(audio * audio))) if len(audio) > 0 else 0.0
    clipped = int(np.sum(np.abs(audio) >= 1.0))

    pdir = project_dir(project.id).resolve()
    exports_dir = pdir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_base = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.name).strip("_") or "export"
    out_name = filename or f"{safe_base}_export.wav"
    if not out_name.lower().endswith(".wav"):
        out_name += ".wav"
    out_path = (exports_dir / out_name).resolve()
    if not out_path.is_relative_to(exports_dir.resolve()):
        raise ValueError("Invalid export path")

    clipped_audio = np.clip(audio, -1.0, 1.0)
    sf.write(str(out_path), clipped_audio, sr, subtype="PCM_24")
    raw_bytes = out_path.read_bytes()

    return {
        "filename": out_name,
        "relativePath": f"exports/{out_name}",
        "sampleRate": sr,
        "channels": 2,
        "durationSec": round(len(audio) / sr, 6),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "peakLinear": round(peak, 6),
        "peakDbfs": round(20.0 * math.log10(peak), 2) if peak > 1e-9 else -120.0,
        "rmsDbfs": round(20.0 * math.log10(rms), 2) if rms > 1e-9 else -120.0,
        "clippedSamples": clipped,
    }
