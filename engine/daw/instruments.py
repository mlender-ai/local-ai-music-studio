"""Pinned Wurlitzer regions. Retain the recorded dynamics and SFZ tuning/gain."""

import json
from fractions import Fraction
from functools import lru_cache, partial
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from engine.session.bank import BANKS, CACHE, fetch, note

# Greg Sullivan, Wurlitzer EP200. Mapping by kinwie. See docs/DAW.md.
REGIONS = {
    name + "-sfz": json.loads(Path(__file__).with_name(name + ".json").read_text())
    for name in ("ep200", "cp80", "rhodes")
}


RHODES = dict(
    repo="sfzinstruments/jlearman.jRhodes3d",
    revision="aea5b8d3e11e2f7102593789a4e0a0e41b30271a",
    author="Jeff Learman",
    license="See upstream LICENSE for recordings and musical works",
)


def key_region(pitch, velocity, mapping):
    for low_v, high_v, low_k, high_k, *source in REGIONS[mapping]:
        if low_v <= velocity <= high_v and low_k <= pitch <= high_k:
            return source
    raise ValueError(f"No {mapping} region for note {pitch} at velocity {velocity}")


def prepare_keys(events, mapping):
    sources = {
        tuple(key_region(p, e["velocity"], mapping))
        for e in events
        if e["track"] == "keys"
        for p in e["notes"]
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    for _, _, _, path, digest in sorted(sources):
        fetch((RHODES if mapping == "rhodes-sfz" else BANKS["keys"], path, digest))


@lru_cache(maxsize=48)
def pitched_key(pitch, velocity, sr, mapping):
    root, cents, gain_db, _, digest = key_region(pitch, velocity, mapping)
    x, source_rate = sf.read(CACHE / digest)
    if x.ndim == 2:
        x = x.mean(axis=1)
    ratio = Fraction(sr / source_rate * 2 ** ((root - pitch - cents / 100) / 12))
    ratio = ratio.limit_denominator(256)
    return resample_poly(x, ratio.numerator, ratio.denominator) * 10 ** (gain_db / 20)


def render_note(
    track, voice, pitch, velocity, take, duration, release, sr, slide, *, mapping
):
    if track != "keys":
        return note(track, voice, pitch, velocity, take, duration, release, sr, slide)
    pcm = pitched_key(pitch, velocity, sr, mapping)
    frames = min(len(pcm), round((duration + release) * sr))
    t = np.arange(frames) / sr
    envelope = (
        np.minimum(t / 0.001, 1) * np.clip(1 - (t - duration) / release, 0, 1) ** 2
    )
    return pcm[:frames] * envelope * (velocity / 127) ** 1.35


def renderer_for(mapping):
    if mapping not in REGIONS:
        raise ValueError(f"Unsupported keyboard mapping: {mapping}")
    return partial(render_note, mapping=mapping)


def audition(spec):
    from engine.session.render import analyze, voices_for

    keys = [e for e in spec["events"] if e["track"] == "keys"]
    candidates = {}
    for mapping in ("session-v1", "ep200-sfz", "cp80-sfz"):
        renderer = note
        if mapping != "session-v1":
            prepare_keys(keys, mapping)
            renderer = renderer_for(mapping)
        y = voices_for(spec, keys, renderer)["keys"]
        stats = analyze(np.column_stack((y, y)), spec["sample_rate"])
        candidates[mapping] = {
            k: stats[k] for k in ("presence_fraction", "low_mid_fraction", "rms_dbfs")
        }

    def separation(mapping):
        stats = candidates[mapping]
        return stats["presence_fraction"] / stats["low_mid_fraction"]

    selected = "ep200-sfz"
    if separation("cp80-sfz") > max(separation("ep200-sfz"), separation("session-v1")):
        selected = "cp80-sfz"
    return selected, candidates
