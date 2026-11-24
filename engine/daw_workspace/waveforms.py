"""Real PCM waveform peak extraction and disk cache."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

DEFAULT_PEAK_BINS = 1024


def inspect_audio_file(path: Path) -> dict[str, Any]:
    """Read real audio metadata via libsndfile (WAV, FLAC, OGG, AIFF, MP3 if supported)."""
    info = sf.info(str(path))
    duration_sec = float(info.frames / info.samplerate) if info.samplerate > 0 else 0.0
    return {
        "sampleRate": int(info.samplerate),
        "channels": int(info.channels),
        "durationSamples": int(info.frames),
        "durationSec": round(duration_sec, 6),
    }


def compute_waveform_peaks(path: Path, bins: int = DEFAULT_PEAK_BINS) -> dict[str, Any]:
    """Compute real downsampled min/max/rms PCM envelopes for timeline & clip editor."""
    info = sf.info(str(path))
    total_frames = int(info.frames)
    sr = int(info.samplerate)
    channels = int(info.channels)
    if total_frames <= 0 or sr <= 0:
        return {
            "sampleRate": sr,
            "channels": channels,
            "durationSamples": 0,
            "durationSec": 0.0,
            "bins": 0,
            "peaks": [],
            "rms": [],
        }

    actual_bins = min(bins, max(1, total_frames))
    peaks = np.zeros(actual_bins, dtype=np.float32)
    rms_vals = np.zeros(actual_bins, dtype=np.float32)

    # Stream in chunks so large WAV files don't duplicate huge arrays in RAM
    frames_per_bin = total_frames / actual_bins
    chunk_size = max(65536, int(frames_per_bin * 16))

    with sf.SoundFile(str(path), "r") as handle:
        frame_cursor = 0
        while frame_cursor < total_frames:
            data = handle.read(chunk_size, dtype="float32", always_2d=True)
            if len(data) == 0:
                break
            mono = np.mean(data, axis=1)
            abs_mono = np.abs(mono)
            sq_mono = mono * mono
            chunk_len = len(mono)

            start_bin = int(frame_cursor / frames_per_bin)
            end_bin = min(actual_bins, int((frame_cursor + chunk_len - 1) / frames_per_bin) + 1)

            for b in range(start_bin, end_bin):
                b_start = max(0, int(b * frames_per_bin) - frame_cursor)
                b_end = min(chunk_len, max(b_start + 1, int((b + 1) * frames_per_bin) - frame_cursor))
                if b_end <= b_start:
                    continue
                seg_abs = abs_mono[b_start:b_end]
                seg_sq = sq_mono[b_start:b_end]
                p = float(np.max(seg_abs))
                if p > peaks[b]:
                    peaks[b] = p
                r = float(np.sqrt(np.mean(seg_sq)))
                if r > rms_vals[b]:
                    rms_vals[b] = r

            frame_cursor += chunk_len

    return {
        "sampleRate": sr,
        "channels": channels,
        "durationSamples": total_frames,
        "durationSec": round(total_frames / sr, 6),
        "bins": actual_bins,
        "peaks": [round(float(v), 5) for v in peaks],
        "rms": [round(float(v), 5) for v in rms_vals],
    }


def load_or_compute_waveform(
    audio_file: Path, cache_dir: Path, sha256: str, bins: int = DEFAULT_PEAK_BINS
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{sha256}_{bins}.json"
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    payload = compute_waveform_peaks(audio_file, bins=bins)
    tmp = cache_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, cache_path)
    return payload
