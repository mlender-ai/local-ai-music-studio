"""Isolate SRC, room and stereo contributions using the unmodified source session."""

import argparse
import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from engine.paths import DATA
from engine.session.bank import pcm, select_sample
from engine.session.mixer import mix
from engine.session.render import analyze, voices_for, write_json


def diagnose(folder):
    spec = json.loads((folder / "01-reference/session.json").read_text())
    sr = spec["sample_rate"]
    sources = {}
    for i, e in enumerate(spec["events"]):
        for j, p in enumerate(e["notes"]):
            track = e["track"]
            _, root, _, _, path, digest = select_sample(
                track, e["voice"], p, e["velocity"], i + j
            )
            shift = p - root
            if track in sources and abs(shift) <= abs(sources[track]["semitones"]):
                continue
            x, rate = pcm(digest)
            speed = rate / sr * 2 ** (shift / 12)
            ratio = Fraction(1 / speed).limit_denominator(1024)
            # Use identical phase positions for both interpolators.
            n = min(int(sr * 0.35), int(len(x) * ratio))
            idx = np.arange(n) * ratio.denominator / ratio.numerator
            linear = np.interp(idx, np.arange(len(x)), x)
            sinc = resample_poly(x, ratio.numerator, ratio.denominator)[:n]
            error = np.sqrt(np.mean((linear - sinc) ** 2))
            sources[track] = {
                "recording": path,
                "semitones": shift,
                "source_rate": rate,
                "frames": n,
                "linear_minus_polyphase_relative_db": float(
                    20 * np.log10(max(1e-15, error) / np.sqrt(np.mean(sinc**2)))
                ),
            }
    v = voices_for(spec, spec["events"])
    comparisons = {}
    for label, send, width in [
        ("original", 0.18, 0.28),
        ("no_room", 0, 0.28),
        ("no_side_delay", 0.18, 0),
    ]:
        mixer = deepcopy(spec["mixer"])
        mixer["keys"].update(send=send, width=width)
        _, wet, _ = mix(v, sr, mixer)
        r = analyze(wet["keys"], sr)
        comparisons[label] = {
            k: r[k]
            for k in (
                "rms_dbfs",
                "mono_fold_db",
                "lr_correlation",
                "low_mid_fraction",
                "presence_fraction",
                "crest_db",
            )
        }
    return {
        "src_probe": sources,
        "keys_effect_isolation": comparisons,
        "guitar_spread_ms": 5,
        "bass_slide_approximation_ms": 55,
        "original_contains_time_stretch": False,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--folder", type=Path, default=DATA / "daw-session")
    folder = cli.parse_args().folder
    result = diagnose(folder)
    write_json(folder / "diagnosis.json", result)
