"""Stereo-linked compressor and sample-peak limiter with smooth release."""

import numpy as np
from numba import njit


@njit(cache=True)
def _smooth_gain(target, attack, release):
    result = np.empty_like(target)
    gain = 1.0
    for i in range(len(target)):
        coeff = attack if target[i] < gain else release
        gain = coeff * gain + (1 - coeff) * target[i]
        result[i] = gain
    return result


def compress(x, sr, p):
    level = 20 * np.log10(np.maximum(np.max(np.abs(x), axis=1), 1e-12))
    reduction = np.maximum(level - p.threshold_db, 0) * (1 - 1 / p.ratio)
    target = 10 ** (-reduction / 20)
    gain = _smooth_gain(
        target,
        np.exp(-1 / (sr * p.attack_ms / 1000)),
        np.exp(-1 / (sr * p.release_ms / 1000)),
    )
    return x * gain[:, None] * 10 ** (p.makeup_db / 20)


def limit(x, sr, p):
    ceiling = 10 ** (p.ceiling_db / 20)
    target = np.minimum(1, ceiling / np.maximum(np.max(np.abs(x), axis=1), 1e-12))
    gain = _smooth_gain(target, 0.0, np.exp(-1 / (sr * p.release_ms / 1000)))
    return x * gain[:, None]
