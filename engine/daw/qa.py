"""Measurement of decoded PCM and the recorded samples actually used by a score."""

import hashlib
import json
import subprocess
from collections import Counter, defaultdict

import numpy as np
import soundfile as sf
from scipy.signal import welch

from engine.session.bank import CACHE, select_sample
from engine.session.render import analyze

from .instruments import key_region


def levels(path, sections=()):
    x, sr = sf.read(path, always_2d=True)
    if not np.isfinite(x).all() or len(x) < 1:
        raise ValueError(f"Invalid audio: {path}")
    stats = analyze(x, sr)
    run = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    loud = json.loads(run.stderr[run.stderr.rindex("{") : run.stderr.rindex("}") + 1])
    stats.update(
        integrated_lufs=float(loud["input_i"]),
        true_peak_dbtp=float(loud["input_tp"]),
        pcm_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
    )
    stats["section_rms_dbfs"] = {
        s["name"]: float(
            10
            * np.log10(
                max(
                    1e-24,
                    np.mean(x[round(s["start"] * sr) : round(s["end"] * sr)] ** 2),
                )
            )
        )
        for s in sections
    }
    return stats


def sources(spec):
    selected = defaultdict(set)
    layers = defaultdict(Counter)
    shifts = defaultdict(list)
    for i, e in enumerate(spec["events"]):
        if e.get("muted"):
            continue
        pitches = e["notes"][::-1] if e["art"] == "up" else e["notes"]
        for j, pitch in enumerate(pitches):
            track = e["track"]
            if track == "keys" and spec.get("keyboard_mapping"):
                root, cents, _, path, digest = key_region(
                    pitch, e["velocity"], spec["keyboard_mapping"]
                )
                layer = (
                    path.rsplit("_", 1)[-1].split(".")[0]
                    if spec["keyboard_mapping"] == "rhodes-sfz"
                    else next(
                        s
                        for s in ("ff", "pp", "mp", "f")
                        if path.lower().endswith(s + ".flac")
                    )
                )
            else:
                _, root, layer, _, path, digest = select_sample(
                    track, e["voice"], pitch, e["velocity"], i + j
                )
                cents = 0
            selected[track].add((path, digest))
            layers[track][layer] += 1
            shifts[track].append(abs(pitch - root + cents / 100))
    report = {}
    for track, files in selected.items():
        samples = []
        for path, digest in sorted(files):
            x, rate = sf.read(CACHE / digest, always_2d=True)
            f, p = welch(x, rate, nperseg=min(4096, len(x)), axis=0)
            samples.append(
                {
                    "source": path,
                    "channels": x.shape[1],
                    "rate": rate,
                    "peak": float(np.max(abs(x))),
                    "clipped": int(np.sum(abs(x) >= 1)),
                    "endpoint_abs": float(np.max(abs(x[[0, -1]]))),
                    "low_mid_fraction": float(
                        p[(f >= 180) & (f < 500)].sum() / p.sum()
                    ),
                    "presence_fraction": float(
                        p[(f >= 2000) & (f < 6000)].sum() / p.sum()
                    ),
                }
            )
        report[track] = {
            "layer_note_counts": layers[track],
            "max_shift_semitones": max(shifts[track]),
            "shortest_event_ms": min(
                e["length"]
                for e in spec["events"]
                if e["track"] == track and not e.get("muted")
            )
            * 15000
            / spec["music_plan"]["rhythm"]["bpm"],
            "recordings": samples,
        }
    return report
