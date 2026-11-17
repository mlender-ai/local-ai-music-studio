"""Unconstrained onset-periodicity estimate, not a genre or listening-quality verdict.

The requested BPM is never used to steer the estimate. Syncopation and half/double
time can confuse it; expose candidates and strength rather than claim compliance.
"""

import math
import numpy as np
from scipy import signal
from engine.rendering.audio import read_audio


def _candidates(envelope, rate=100):
    centered = envelope - envelope.mean()
    energy = float(centered @ centered)
    if energy < 1e-14:
        return []
    ac = signal.correlate(centered, centered, mode="full", method="fft")[
        len(centered) - 1 :
    ]
    ac /= energy
    # Broad fixed range independent of the request. Adjacent lag interpolation
    # avoids reporting a fixed 125 BPM bin for an actual 124 BPM rhythm.
    lo, hi = int(rate * 60 / 180), int(rate * 60 / 60)
    peaks, _ = signal.find_peaks(ac[lo - 1 : hi + 2])
    lags = peaks + lo - 1
    lags = [int(k) for k in lags if lo <= k <= hi]
    found = []
    for k in sorted(lags, key=lambda k: ac[k], reverse=True)[:4]:
        a, b, c = ac[k - 1 : k + 2]
        denom = a - 2 * b + c
        delta = (
            float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5))
            if abs(denom) > 1e-12
            else 0
        )
        found.append(
            dict(bpm=round(60 * rate / (k + delta), 1), strength=round(float(b), 3))
        )
    return found


def estimate_rhythm(path, requested_bpm=None):
    x, sr = read_audio(path)
    mono = x.mean(axis=1)
    factor = math.gcd(sr, 12000)
    mono = signal.resample_poly(mono, 12000 // factor, sr // factor)
    frequencies, _, spectrum = signal.stft(
        mono, fs=12000, nperseg=512, noverlap=392, boundary=None
    )
    magnitude = abs(spectrum[(frequencies >= 40) & (frequencies <= 5500)])
    flux = np.maximum(np.diff(magnitude, axis=1), 0).sum(axis=0)
    candidates = _candidates(flux)
    windows = []
    for start in range(0, max(0, len(flux) - 750) + 1, 375):
        chunk = flux[start : start + 750]
        if len(chunk) < 600:
            continue
        ranked = _candidates(chunk)
        if ranked and ranked[0]["strength"] >= 0.15:
            windows.append(dict(start_seconds=round(start / 100, 2), **ranked[0]))
    strong = bool(candidates and candidates[0]["strength"] >= 0.15)
    dominant = candidates[0]["bpm"] if strong else None
    ambiguous = strong and any(
        abs(max(c["bpm"], dominant) / min(c["bpm"], dominant) - 2) < 0.04
        and c["strength"] >= candidates[0]["strength"] * 0.65
        for c in candidates[1:]
    )
    bpm = dominant if strong and not ambiguous else None
    return dict(
        method="spectral-flux autocorrelation; unconditioned 60–180 BPM search",
        estimated_bpm=bpm,
        dominant_period_bpm=dominant,
        requested_bpm=requested_bpm,
        absolute_error_bpm=round(abs(bpm - requested_bpm), 1)
        if bpm and requested_bpm
        else None,
        candidates=candidates,
        windows=windows,
        assessment="half_double_time_ambiguous"
        if ambiguous
        else "estimate_only"
        if strong
        else "uncertain",
        note="템포 추정치입니다. 반박·배박 또는 싱코페이션으로 오차가 생길 수 있으며, 장르·박자 정확도는 청취 평가가 필요합니다.",
    )
