"""Standard ITU-R BS.1770-4 Loudness (Integrated & Short-Term LUFS) and 4x True Peak (dBTP).

Pure numpy/scipy implementation requiring zero external binaries:
- Stage 1 K-weighting: pre-filter high-shelf (+4 dB above ~1681 Hz)
- Stage 2 K-weighting: RLB high-pass filter (~38 Hz)
- 400 ms gating blocks (75% overlap / 100 ms hop) with -70 LKFS absolute gate
  and -10 LU relative gate per ITU-R BS.1770-4
- 3.0 s sliding window Short-Term Loudness & Loudness Range (LRA, EBU R128)
- 4x polyphase oversampled True Peak (dBTP)
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal


def _k_weighting_sos(sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute exact bilinear-transformed BS.1770-4 Stage 1 & Stage 2 biquads for arbitrary sr."""
    # Stage 1: acoustic head-model high-shelf (BS.1770-4 exact analog design parameters)
    f0 = 1681.974450955533
    G = 3.999843853973347
    Q = 0.7071752369554196
    K = math.tan(math.pi * f0 / sr)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b1 = np.array(
        [
            (Vh + Vb * K / Q + K * K) / a0,
            2.0 * (K * K - Vh) / a0,
            (Vh - Vb * K / Q + K * K) / a0,
        ],
        dtype=np.float64,
    )
    a1 = np.array(
        [1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0],
        dtype=np.float64,
    )

    # Stage 2: RLB high-pass filter (f0 = 38.13547 Hz, Q = 0.500327)
    f0_hp = 38.13547087602444
    Q_hp = 0.5003270373238773
    K_hp = math.tan(math.pi * f0_hp / sr)
    a0_hp = 1.0 + K_hp / Q_hp + K_hp * K_hp
    b2 = np.array([1.0 / a0_hp, -2.0 / a0_hp, 1.0 / a0_hp], dtype=np.float64)
    a2 = np.array(
        [
            1.0,
            2.0 * (K_hp * K_hp - 1.0) / a0_hp,
            (1.0 - K_hp / Q_hp + K_hp * K_hp) / a0_hp,
        ],
        dtype=np.float64,
    )
    return np.array([np.concatenate([b1, a1]), np.concatenate([b2, a2])], dtype=np.float64), a2


def measure_loudness(stereo: np.ndarray, sr: int) -> dict[str, Any]:
    """Measure ITU-R BS.1770-4 Integrated LUFS, Short-Term LUFS, RMS, Sample Peak, True Peak & Crest."""
    x = np.asarray(stereo, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    elif x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    elif x.shape[1] > 2:
        x = x[:, :2]

    n_frames = len(x)
    if n_frames == 0 or sr <= 0:
        return {
            "standard": "ITU-R BS.1770-4",
            "integratedLufs": -120.0,
            "shortTermMaxLufs": -120.0,
            "shortTermMedianLufs": -120.0,
            "loudnessRangeLu": 0.0,
            "rmsDbfs": -120.0,
            "samplePeakDbfs": -120.0,
            "truePeakDbtp": -120.0,
            "crestFactorDb": 0.0,
            "truePeakSupported": True,
        }

    # Sample Peak & RMS
    sample_peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x * x)))
    sample_peak_dbfs = round(20.0 * math.log10(max(sample_peak, 1e-12)), 2)
    rms_dbfs = round(20.0 * math.log10(max(rms, 1e-12)), 2)
    crest_db = round(sample_peak_dbfs - rms_dbfs, 2)

    # 4x Oversampled True Peak (dBTP) — bounded chunking for low RAM overhead
    tp_max = sample_peak
    chunk_n = 262144
    for start in range(0, n_frames, chunk_n):
        seg = x[start : min(n_frames, start + chunk_n)]
        if len(seg) < 16:
            continue
        up_l = signal.resample_poly(seg[:, 0], 4, 1)
        up_r = signal.resample_poly(seg[:, 1], 4, 1)
        tp_max = max(tp_max, float(np.max(np.abs(up_l))), float(np.max(np.abs(up_r))))
    true_peak_dbtp = round(20.0 * math.log10(max(tp_max, 1e-12)), 2)

    # K-weighting filter
    sos, _ = _k_weighting_sos(sr)
    kw = signal.sosfilt(sos, x, axis=0)
    # Channel-weighted squared energy (L=1.0, R=1.0 for stereo)
    energy = kw[:, 0] ** 2 + kw[:, 1] ** 2

    # 400ms blocks with 100ms hop (75% overlap)
    block_n = max(1, int(round(0.4 * sr)))
    hop_n = max(1, int(round(0.1 * sr)))
    if n_frames < block_n:
        mean_z = float(np.mean(energy))
        lufs = round(-0.691 + 10.0 * math.log10(max(mean_z, 1e-12)), 2)
        return {
            "standard": "ITU-R BS.1770-4",
            "integratedLufs": lufs,
            "shortTermMaxLufs": lufs,
            "shortTermMedianLufs": lufs,
            "loudnessRangeLu": 0.0,
            "rmsDbfs": rms_dbfs,
            "samplePeakDbfs": sample_peak_dbfs,
            "truePeakDbtp": true_peak_dbtp,
            "crestFactorDb": crest_db,
            "truePeakSupported": True,
        }

    csum = np.concatenate([[0.0], np.cumsum(energy)])
    starts = np.arange(0, n_frames - block_n + 1, hop_n)
    block_z = (csum[starts + block_n] - csum[starts]) / float(block_n)
    block_lufs = -0.691 + 10.0 * np.log10(np.maximum(block_z, 1e-12))

    # Absolute gate (-70 LKFS)
    abs_mask = block_lufs > -70.0
    if not np.any(abs_mask):
        integrated_lufs = -120.0
    else:
        ungated_mean_z = float(np.mean(block_z[abs_mask]))
        rel_threshold = -0.691 + 10.0 * math.log10(max(ungated_mean_z, 1e-12)) - 10.0
        rel_mask = abs_mask & (block_lufs > rel_threshold)
        final_z = float(np.mean(block_z[rel_mask])) if np.any(rel_mask) else ungated_mean_z
        integrated_lufs = round(-0.691 + 10.0 * math.log10(max(final_z, 1e-12)), 2)

    # 3.0s Short-Term Loudness (EBU R128 LRA)
    st_n = min(n_frames, max(block_n, int(round(3.0 * sr))))
    st_hop = max(1, int(round(0.25 * sr)))
    st_starts = np.arange(0, max(1, n_frames - st_n + 1), st_hop)
    st_z = (csum[st_starts + st_n] - csum[st_starts]) / float(st_n)
    st_lufs = -0.691 + 10.0 * np.log10(np.maximum(st_z, 1e-12))
    active_st = st_lufs[st_lufs > -70.0]
    if len(active_st) >= 2:
        st_max = round(float(np.max(active_st)), 2)
        st_med = round(float(np.median(active_st)), 2)
        lra = round(float(np.percentile(active_st, 95) - np.percentile(active_st, 10)), 2)
    else:
        st_max = integrated_lufs
        st_med = integrated_lufs
        lra = 0.0

    return {
        "standard": "ITU-R BS.1770-4",
        "integratedLufs": integrated_lufs,
        "shortTermMaxLufs": st_max,
        "shortTermMedianLufs": st_med,
        "loudnessRangeLu": lra,
        "rmsDbfs": rms_dbfs,
        "samplePeakDbfs": sample_peak_dbfs,
        "truePeakDbtp": true_peak_dbtp,
        "crestFactorDb": crest_db,
        "truePeakSupported": True,
    }
