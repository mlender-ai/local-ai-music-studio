"""Compare the V5 rendered media with its source, control render and approved rock."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.signal import correlate, find_peaks, resample_poly

from engine.daw.alt_rock import RATE, aligned, dbfs, read
from engine.daw.qa import levels
from engine.paths import ROOT
from engine.session.render import write_json
from scripts.v4_evaluate import transcriber


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def pitch_screen(guitar, start, stop):
    """Report periodic content in the guitar estimate, not instrument identity."""
    x = resample_poly(
        guitar[round(start * RATE) : round(stop * RATE)].mean(axis=1), 1, 6
    )
    pitches = []
    for i in range(0, len(x) - 1024, 800):
        w = x[i : i + 1024]
        if dbfs(w) < -37:
            continue
        w = w - w.mean()
        corr = correlate(w, w, method="fft")[len(w) - 1 :]
        peaks, _ = find_peaks(corr)
        candidates = [p for p in peaks if 7 <= p <= 50 and corr[p] >= 0.58 * corr[0]]
        if candidates:
            pitches.append(8000 / candidates[0])
    return {
        "strong_periodicity_windows": len(pitches),
        "analysis_hop_seconds": 0.1,
        "fundamental_hz_percentiles": (
            np.percentile(pitches, [10, 50, 90]).round(1).tolist() if pitches else []
        ),
    }


def verify(production, control, stems, reference):
    meta = json.loads((production / "production.json").read_text())
    wave = "METALLIC DREAM - Final Master.wav"
    original = production / "YuE2 Original.wav"
    x, _ = read(production / wave)
    y, _ = read(control / wave)
    g, _ = read(production / "Audio/guitar.wav")
    v, _ = read(production / "Audio/vocals.wav")
    other_vocals = aligned(stems / "htdemucs/vocals.wav", len(v))
    start, end = (meta["settings"][key] for key in ("lead_start", "lead_end"))
    window = slice(round(start * RATE), round(end * RATE))
    bands = []
    for interval in meta["score_regions"]:
        s = slice(round(interval["start"] * RATE), round(interval["end"] * RATE))
        delta = x[s] - y[s]
        bands.append(
            {
                "section": interval["name"],
                "direction_delta_db_relative_to_control": dbfs(delta) - dbfs(y[s]),
                "side_to_mid_change_db": (
                    (dbfs(x[s, 0] - x[s, 1]) - dbfs(x[s, 0] + x[s, 1]))
                    - (dbfs(y[s, 0] - y[s, 1]) - dbfs(y[s, 0] + y[s, 1]))
                ),
            }
        )
    if np.array_equal(x, y):
        raise RuntimeError("Mix direction did not change PCM")
    lead = {
        "excerpt_seconds": [start, end],
        "six_source_guitar_dbfs": dbfs(g[window]),
        "six_source_vocal_dbfs": dbfs(v[window]),
        "four_source_vocal_dbfs": dbfs(other_vocals[window]),
        "estimate_pitch": pitch_screen(g, start, end),
    }
    lyrics = (ROOT / "examples/v5/metallic-dream.txt").read_text()
    hear = transcriber()
    return {
        "sha256": {
            path.name: digest(path) for path in (reference, original, production / wave)
        },
        "approved_rock_reference": levels(reference),
        "solo_audio_evidence": lead,
        "command_delta": bands,
        "original_asr": hear(original, lyrics),
        "master_asr": hear(production / wave, lyrics),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("production", "control", "stems", "reference"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    write_json(
        args.production / "verification.json",
        verify(args.production, args.control, args.stems, args.reference),
    )
