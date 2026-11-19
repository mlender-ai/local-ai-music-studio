"""Offline mix. Wet stems include their individual contribution to a linear room bus."""

import numpy as np
from scipy.signal import butter, sosfilt
from engine.dsp.chain import process


def eq(hz, db, mode="peaking"):
    return dict(type="eq", mode=mode, frequency=hz, gain_db=db, q=0.8)


def comp(threshold, ratio, attack, release):
    return dict(
        type="compressor",
        threshold_db=threshold,
        ratio=ratio,
        attack_ms=attack,
        release_ms=release,
    )


MIX = {
    "levels": {
        "kick": 0.49,
        "snare": 0.43,
        "hat": 0.19,
        "openhat": 0.16,
        "bass": 0.46,
        "keys": 0.28,
        "guitar": 0.47,
        "chuck": 0.21,
    },
    "drums": {
        "chain": [comp(-16, 2.1, 16, 92)],
        "transient_gain": 0.14,
        "send": 0.085,
        "pan": 0,
    },
    "bass": {
        "chain": [
            eq(90, -1, "low_shelf"),
            dict(type="distortion", drive_db=2, tone_hz=4500, output_db=-2),
            comp(-19, 2.4, 15, 95),
        ],
        "duck": 0.17,
        "duck_ms": 85,
        "pan": 0,
        "send": 0,
    },
    "keys": {
        "chain": [eq(360, -2.3)],
        "pan": 0.24,
        "modulation_ms": 3,
        "rate_hz": 0.71,
        "width": 0.28,
        "send": 0.18,
    },
    "guitar": {
        "chain": [eq(2400, 1.3)],
        "highpass_hz": 155,
        "pan": -0.42,
        "echo_ms": 33,
        "echo_level": 0.09,
        "send": 0.055,
    },
    "room": {"type": "reverb", "wet": 1, "pre_delay_ms": 9, "decay": 0.51},
    "master": [
        eq(285, -1.2),
        comp(-14, 1.45, 28, 140),
        dict(type="limiter", ceiling_db=-1.2, release_ms=95),
    ],
}


def stereo(x):
    return np.column_stack((x, x))


def mix(voices, sr, cfg):
    leveled = {k: v * cfg["levels"][k] for k, v in voices.items()}
    drums = sum(leveled[v] for v in ("kick", "snare", "hat", "openhat"))
    dry = {
        k: stereo(v)
        for k, v in dict(
            drums=drums,
            bass=leveled["bass"],
            keys=leveled["keys"],
            guitar=leveled["guitar"] + leveled["chuck"],
        ).items()
    }
    wet = {}
    for track, x in dry.items():
        p = cfg[track]
        if track == "drums":
            # Exponentially tracked level emphasizes attacks over the body.
            from scipy.signal import lfilter

            env = abs(x[:, 0])
            coef = np.exp(-1 / (0.018 * sr))
            smooth = lfilter([1 - coef], [1, -coef], env)
            x = (
                x
                * (
                    1
                    + p["transient_gain"]
                    * np.clip((env - smooth) / np.maximum(0.025, env), 0, 1)
                )[:, None]
            )
        if track == "guitar":
            x = sosfilt(
                butter(2, p["highpass_hz"], fs=sr, btype="highpass", output="sos"),
                x,
                axis=0,
            )
        y = process(x, sr, p["chain"])
        if track == "bass":
            from scipy.ndimage import maximum_filter1d

            n = max(2, round(sr * p["duck_ms"] / 1000))
            kick = abs(voices["kick"])
            detect = maximum_filter1d(kick, n, origin=(n - 1) // 2, mode="constant")
            y *= 1 - p["duck"] * np.minimum(1, detect / 0.6)[:, None]
        if track == "keys":
            index = np.arange(len(y))
            side = np.interp(
                index
                - (
                    0.005
                    + 0.001
                    * p["modulation_ms"]
                    * np.sin(index * 2 * np.pi * p["rate_hz"] / sr)
                )
                * sr,
                index,
                y[:, 0],
                left=0,
            )
            y[:, 0] += side * p["width"]
            y[:, 1] -= side * p["width"]
        pan = p["pan"]
        y *= np.sqrt([1 - pan, 1 + pan])
        if track == "guitar":
            n = round(sr * p["echo_ms"] / 1000)
            y[n:, 1] += p["echo_level"] * y[:-n, 0]
        if p["send"]:
            y += p["send"] * process(y, sr, [cfg["room"]])
        wet[track] = y
    return dry, wet, process(sum(wet.values()), sr, cfg["master"])
