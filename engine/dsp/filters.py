"""RBJ biquads and oversampled soft saturation (no plugin dependency)."""

import numpy as np
from scipy.signal import lfilter, butter, sosfilt, resample_poly


def equalize(x, sr, p):
    if p.frequency >= sr * 0.49:
        raise ValueError("EQ frequency must be below 0.49 × sample rate.")
    a = 10 ** (p.gain_db / 40)
    w = 2 * np.pi * p.frequency / sr
    c, s = np.cos(w), np.sin(w)
    alpha = s / (2 * p.q)
    beta = 2 * np.sqrt(a) * alpha
    if p.mode == "peaking":
        b = [1 + alpha * a, -2 * c, 1 - alpha * a]
        d = [1 + alpha / a, -2 * c, 1 - alpha / a]
    elif p.mode == "low_shelf":
        b = [
            a * ((a + 1) - (a - 1) * c + beta),
            2 * a * ((a - 1) - (a + 1) * c),
            a * ((a + 1) - (a - 1) * c - beta),
        ]
        d = [
            (a + 1) + (a - 1) * c + beta,
            -2 * ((a - 1) + (a + 1) * c),
            (a + 1) + (a - 1) * c - beta,
        ]
    else:
        b = [
            a * ((a + 1) + (a - 1) * c + beta),
            -2 * a * ((a - 1) + (a + 1) * c),
            a * ((a + 1) + (a - 1) * c - beta),
        ]
        d = [
            (a + 1) - (a - 1) * c + beta,
            2 * ((a - 1) - (a + 1) * c),
            (a + 1) - (a - 1) * c - beta,
        ]
    return lfilter(np.array(b) / d[0], np.array(d) / d[0], x, axis=0)


def saturate(x, sr, p):
    if p.tone_hz >= sr * 0.49:
        raise ValueError("Tone cutoff must be below 0.49 × sample rate.")
    up = resample_poly(x, 4, 1, axis=0)
    driven = np.tanh(up * 10 ** (p.drive_db / 20))
    filtered = sosfilt(butter(2, p.tone_hz, fs=sr * 4, output="sos"), driven, axis=0)
    return resample_poly(filtered, 1, 4, axis=0)[: len(x)] * 10 ** (p.output_db / 20)
