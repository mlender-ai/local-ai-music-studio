"""Measure acoustic and electric guitar evidence across a rendered arrangement."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from engine.paths import RUNTIME
from evaluation.house_hook import db, pitch_classes
from evaluation.vocal_models import panns
from scripts.v71_strict import digest

ACOUSTIC = "Acoustic guitar"
ELECTRIC = "Electric guitar"
TAGS = (
    ACOUSTIC,
    ELECTRIC,
    "Guitar",
    "Bass guitar",
    "Drum kit",
    "Singing",
    "Distortion",
)


def windows(audio, rate, classifier, seconds=4):
    divisor = math.gcd(rate, 32000)
    mono = resample_poly(audio.mean(axis=1), 32000 // divisor, rate // divisor)
    span = 32000 * seconds
    if len(mono) < span:
        return []
    starts = np.arange(0, len(mono) - span + 1, span // 2)
    rows = []
    for part in np.array_split(starts, max(1, math.ceil(len(starts) / 8))):
        samples = np.stack([mono[at : at + span] for at in part])
        predictions = classifier(samples, TAGS)
        rows.extend(
            {
                "start_seconds": float(at / 32000),
                "end_seconds": float((at + span) / 32000),
                "rms_dbfs": db(np.sqrt(np.mean(sample**2))),
                **tags,
            }
            for at, sample, tags in zip(part, samples, predictions, strict=True)
        )
    return rows


def tonal_profile(audio, rate):
    chroma = pitch_classes(audio.mean(axis=1), rate)
    weight = chroma.mean(axis=1)
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return {
        name: round(float(value), 3) for name, value in zip(names, weight, strict=True)
    }


def split_evidence(rows, duration):
    opening = [row for row in rows if row["end_seconds"] <= 16]
    late = [
        row
        for row in rows
        if 0.58 * duration <= row["start_seconds"] <= 0.93 * duration
    ]
    strong_acoustic = [
        row
        for row in opening
        if row[ACOUSTIC] >= 0.25 and row[ACOUSTIC] - row[ELECTRIC] >= 0.10
    ]
    strong_electric = [
        row
        for row in late
        if row[ELECTRIC] >= 0.23 and row[ELECTRIC] - row[ACOUSTIC] >= 0.10
    ]
    early_electric = [
        row
        for row in opening
        if row[ELECTRIC] >= 0.23 and row[ELECTRIC] - row[ACOUSTIC] >= 0.10
    ]
    return {
        "acoustic_opening_seconds": [row["start_seconds"] for row in strong_acoustic],
        "electric_opening_seconds": [row["start_seconds"] for row in early_electric],
        "late_electric_seconds": [row["start_seconds"] for row in strong_electric],
        "acoustic_opening_supported": len(strong_acoustic) >= 2 and not early_electric,
        "late_electric_supported": bool(strong_electric)
        and not early_electric
        and duration >= 60,
    }


def inspect(take):
    source = take / "original.wav"
    voice = json.loads((take / "vocal-leakage.json").read_text())
    diagnostics = take / "diagnostics"
    source_sha = digest(source)
    if (
        voice["status"] != "PASS"
        or voice["wav_sha256"] != source_sha
        or (diagnostics / "source.sha256").read_text().strip() != source_sha
    ):
        raise ValueError("Inspect the same original and estimates admitted by vocal QA")
    classifier = panns(RUNTIME / "v7/panns")
    data, rate = sf.read(source, dtype="float32", always_2d=True)
    guitar, guitar_rate = sf.read(
        diagnostics / "htdemucs_6s/guitar.wav", dtype="float32", always_2d=True
    )
    sources = {
        "mix": windows(data, rate, classifier),
        "guitar_estimate": windows(guitar, guitar_rate, classifier),
    }
    duration = len(data) / rate
    measurements = {
        "source_sha256": source_sha,
        "length_seconds": duration,
        "sections": {
            name: split_evidence(rows, duration) for name, rows in sources.items()
        },
        "windows": sources,
        "opening_pitch_class_profile": tonal_profile(
            guitar[: 16 * guitar_rate], guitar_rate
        ),
        "scope": "AudioSet instrument-tag evidence on four-second windows, not confirmed instrument identity or listening quality",
    }
    (take / "guitar-timbre.json").write_text(json.dumps(measurements, indent=2) + "\n")
    return measurements


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("take", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.take)["sections"], indent=2))
