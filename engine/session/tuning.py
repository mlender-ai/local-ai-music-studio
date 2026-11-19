"""Estimate single-note F0 from periodicity, independently of the mapped MIDI key."""

import numpy as np
from scipy.signal import correlate, find_peaks, resample_poly


def pitch(x, sr):
    x = np.asarray(x)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if sr > 16000:
        x = resample_poly(x, 1, 4)
        sr /= 4
    results = []
    for begin in (0.18, 0.27, 0.36):
        frame = x[round(begin * sr) : round((begin + 0.16) * sr)]
        if len(frame) < 0.12 * sr or np.max(abs(frame)) < 1e-6:
            continue
        frame = frame - frame.mean()
        corr = correlate(frame, frame, mode="full", method="fft")[len(frame) - 1 :]
        power = np.r_[0, np.cumsum(frame * frame)]
        lags = np.arange(min(len(frame) // 2, round(sr / 29)))
        nsdf = (
            2
            * corr[lags]
            / np.maximum(1e-18, power[len(frame) - lags] + power[-1] - power[lags])
        )
        peaks = find_peaks(nsdf)[0]
        peaks = peaks[peaks >= sr / 1400]
        if not len(peaks):
            continue
        candidates = peaks[nsdf[peaks] >= max(0.65, 0.94 * max(nsdf[peaks]))]
        if not len(candidates):
            continue
        k = candidates[0]
        l, c, r = nsdf[k - 1 : k + 2]
        delta = 0.5 * (l - r) / (l - 2 * c + r) if l - 2 * c + r else 0
        rough = sr / (k + delta)
        # String upper partials stretch sharp. Refine using the two lowest
        # observable partials after independently identifying the period.
        mag = abs(np.fft.rfft(frame * np.hanning(len(frame)), 32768))
        frequencies = np.fft.rfftfreq(32768, 1 / sr)
        partials = []
        for h in (1, 2):
            ids = np.where(
                (frequencies > rough * h * 0.964) & (frequencies < rough * h * 1.037)
            )[0]
            if len(ids) < 3:
                continue
            idx = ids[np.argmax(mag[ids])]
            if idx in (ids[0], ids[-1]) or mag[idx] < mag.max() * 0.04:
                continue
            l, c, r = np.log(np.maximum(1e-16, mag[idx - 1 : idx + 2]))
            partials.append((idx + 0.5 * (l - r) / (l - 2 * c + r)) * sr / 32768 / h)
        hz = np.median(partials) if partials else rough
        results.append(69 + 12 * np.log2(hz / 440))
    return float(np.median(results)) if results else None
