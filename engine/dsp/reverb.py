"""Deterministic diffuse stereo convolution reverb with explicit RT60.

Noise is used only as a reverb impulse response, never as generated music.
The tail is intentionally truncated to preserve exact input duration.
"""

import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt


def reverb(x, sr, p):
    if p.wet == 0:
        return x.copy()
    delay = round(p.pre_delay_ms * sr / 1000)
    count = round(p.decay * sr)
    t = np.arange(count) / sr
    wet = np.zeros_like(x)
    for channel in range(x.shape[1]):
        rng = np.random.default_rng(1907 + channel)
        impulse = rng.normal(0, 1, count) * np.exp(-np.log(1000) * t / p.decay)
        impulse = sosfilt(butter(2, min(6500, sr * 0.4), fs=sr, output="sos"), impulse)
        impulse *= np.minimum(t / 0.015, 1)
        impulse /= max(np.linalg.norm(impulse), 1e-12)
        for seconds, strength in [(0.017, 0.35), (0.031, 0.24), (0.043, 0.17)]:
            index = round(seconds * sr)
            if index < count:
                impulse[index] += strength
        impulse = np.pad(impulse, (delay, 0))
        wet[:, channel] = fftconvolve(x[:, channel], impulse, mode="full")[: len(x)]
    return (1 - p.wet) * x + p.wet * wet
