"""Diagnostics on the rendered master and its matching MIDI performance."""

from collections import defaultdict

import numpy as np
import soundfile as sf
from scipy.ndimage import uniform_filter1d

from .project import LANES, assignments


def diagnostics(spec, job):
    midi, _ = assignments(spec)
    bars = len(spec["chart"])
    patterns = {}
    for lane in LANES:
        groups = defaultdict(list)
        for bar in range(1, bars + 1):
            # Ignore sampler channel/take when comparing performance patterns.
            fingerprint = tuple(
                sorted((a, b, n, v) for a, b, _, n, v in midi[lane, bar])
            )
            if fingerprint:
                groups[fingerprint].append(bar)
        stem, sr = sf.read(job / f"dry-{lane}.wav", always_2d=True)
        rms = np.mean(stem**2) ** 0.5
        patterns[lane] = {
            "active_bars": sum(len(g) for g in groups.values()),
            "unique_patterns": len(groups),
            "repeated_bars": [g for g in groups.values() if len(g) > 1],
            "dry_rms_dbfs": float(20 * np.log10(rms)) if rms else None,
        }
    x, sr = sf.read(job / "master.wav", always_2d=True)
    d = np.diff(x, axis=0)
    # An isolated one-sample excursion has a large slope followed by its inverse.
    # Require both an absolute floor and separation from nearby transient energy.
    background = np.sqrt(
        np.maximum(0, uniform_filter1d(d * d, size=round(0.006 * sr), axis=0))
    )
    spike = (d[:-1] * d[1:] < 0) & (
        np.minimum(abs(d[:-1]), abs(d[1:])) > np.maximum(0.04, 9 * background[:-1])
    )
    frames = np.flatnonzero(np.any(spike, axis=1)) + 1
    edges = []
    for n in range(1, bars):
        frame = round(n * 240 / spec["music_plan"]["rhythm"]["bpm"] * sr)
        edges.append(round(float(max(abs(d[frame - 1]))), 7))
    return {
        "patterns": patterns,
        "first_last_sample_abs": [float(np.max(abs(x[i]))) for i in (0, -1)],
        "isolated_impulse_candidates_seconds": (frames[:100] / sr).tolist(),
        "isolated_impulse_count": len(frames),
        "bar_boundary_abs_sample_steps": edges,
        "sections": [
            {
                "name": s["name"],
                "notes": sum(
                    len(midi[lane, b])
                    for lane in LANES
                    for b in range(s["first"], s["last"] + 1)
                ),
            }
            for s in spec["sections"]
        ],
    }
