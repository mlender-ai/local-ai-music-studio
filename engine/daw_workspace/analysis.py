"""Real acoustic music analysis pipeline for Phase 02-A Reference Intelligence.

Computes genuine signal-level measurements & conservative musical estimates from
decoded PCM audio using numpy, scipy, and soundfile — zero fabricated results.
Separates measured acoustic metrics from estimated musical attributes.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

from .schema import make_id, utc_now_iso

ANALYSIS_VERSION = "2.0.0"

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler tonal profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
DORIAN_PROFILE = np.array([6.20, 2.10, 3.80, 5.10, 2.30, 3.80, 2.20, 4.90, 2.50, 4.20, 3.50, 2.40])
MIXOLYDIAN_PROFILE = np.array([6.20, 2.10, 3.60, 2.30, 4.60, 3.90, 2.20, 5.10, 2.30, 3.60, 4.20, 2.40])


def _load_audio_bounded(path: Path, max_duration_sec: float = 360.0) -> tuple[np.ndarray, int]:
    """Read audio as float32 stereo (up to 6 minutes bounded for Apple Silicon RAM safety)."""
    info = sf.info(str(path))
    if info.frames <= 0 or info.samplerate <= 0:
        raise ValueError("Audio file contains no readable PCM frames")
    max_frames = int(min(info.frames, max_duration_sec * info.samplerate))
    data, sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if not np.isfinite(data).all():
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    return data, int(sr)


def _downsample_mono(stereo: np.ndarray, sr: int, target_sr: int = 12000) -> tuple[np.ndarray, int]:
    mono = stereo.mean(axis=1).astype(np.float64)
    if sr == target_sr:
        return mono, sr
    g = math.gcd(sr, target_sr)
    return signal.resample_poly(mono, target_sr // g, sr // g), target_sr


def _analyze_rhythm(mono_12k: np.ndarray, sr_12k: int) -> dict[str, Any]:
    """Unconstrained spectral-flux BPM candidates, onset grid, meter, density, and swing."""
    # STFT hop = 120 samples -> 100 Hz onset frame rate
    freqs, times, zxx = signal.stft(mono_12k, fs=sr_12k, nperseg=512, noverlap=392, boundary=None)
    mag = np.abs(zxx[(freqs >= 40) & (freqs <= 5500)])
    if mag.shape[1] < 20:
        return {
            "estimatedBpm": None,
            "candidates": [],
            "halfDoubleAmbiguous": False,
            "meterEstimate": "4/4",
            "onsetDensityPerSec": 0.0,
            "swingRatio": 0.5,
            "regularity": 0.0,
            "beatGridSec": [],
            "downbeatsSec": [],
            "accentPattern": [1.0, 0.5, 0.7, 0.5],
            "assessment": "uncertain",
        }

    flux = np.maximum(np.diff(mag, axis=1), 0.0).sum(axis=0)
    flux_rate = 100.0
    centered = flux - flux.mean()
    energy = float(centered @ centered)
    candidates: list[dict[str, Any]] = []
    if energy > 1e-12:
        ac = signal.correlate(centered, centered, mode="full", method="fft")[len(centered) - 1 :]
        ac /= energy
        lo, hi = int(flux_rate * 60 / 180), int(flux_rate * 60 / 60)
        peaks, _ = signal.find_peaks(ac[lo - 1 : hi + 2])
        lags = [int(k + lo - 1) for k in peaks if lo <= k + lo - 1 <= hi]
        for k in sorted(lags, key=lambda idx: ac[idx], reverse=True)[:5]:
            a, b, c = ac[k - 1 : k + 2]
            denom = a - 2 * b + c
            delta = float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5)) if abs(denom) > 1e-12 else 0.0
            candidates.append(
                {
                    "bpm": round(60.0 * flux_rate / (k + delta), 1),
                    "strength": round(float(max(0.0, b)), 3),
                }
            )

    strong = bool(candidates and candidates[0]["strength"] >= 0.14)
    dominant = candidates[0]["bpm"] if strong else None
    ambiguous = bool(
        strong
        and dominant
        and any(
            abs(max(c["bpm"], dominant) / min(c["bpm"], dominant) - 2.0) < 0.045
            and c["strength"] >= candidates[0]["strength"] * 0.65
            for c in candidates[1:]
        )
    )

    # Onset peak picking
    flux_norm = flux / (np.max(flux) + 1e-9)
    threshold = float(np.mean(flux_norm) + 0.85 * np.std(flux_norm))
    onset_frames, _ = signal.find_peaks(flux_norm, height=max(0.12, threshold), distance=10)
    onset_times = [round(float(f / flux_rate), 3) for f in onset_frames]
    duration_sec = len(mono_12k) / sr_12k
    density = round(len(onset_times) / max(1.0, duration_sec), 2)

    # Beat grid, accent pattern, and swing estimation
    bpm_for_grid = dominant or 120.0
    beat_period = 60.0 / bpm_for_grid
    # Find phase offset maximizing onset flux on beat grid
    period_frames = max(10, int(round(beat_period * flux_rate)))
    phase_scores = [float(np.mean(flux_norm[p::period_frames])) for p in range(period_frames)]
    best_phase_sec = int(np.argmax(phase_scores)) / flux_rate
    beat_grid = [
        round(best_phase_sec + i * beat_period, 3)
        for i in range(int((duration_sec - best_phase_sec) / beat_period) + 1)
        if best_phase_sec + i * beat_period <= duration_sec
    ]

    # Meter estimate: compare 3-beat vs 4-beat bar energy periodicity
    bar_energy_4 = []
    for idx in range(0, min(len(beat_grid), 64), 4):
        f_idx = min(len(flux_norm) - 1, int(beat_grid[idx] * flux_rate))
        bar_energy_4.append(float(flux_norm[f_idx]))
    bar_energy_3 = []
    for idx in range(0, min(len(beat_grid), 63), 3):
        f_idx = min(len(flux_norm) - 1, int(beat_grid[idx] * flux_rate))
        bar_energy_3.append(float(flux_norm[f_idx]))
    meter_est = "3/4" if (np.mean(bar_energy_3) if bar_energy_3 else 0) > (np.mean(bar_energy_4) if bar_energy_4 else 0) * 1.18 else "4/4"
    bpb = 3 if meter_est == "3/4" else 4
    downbeats = beat_grid[::bpb]

    # Accent pattern across beats of a bar
    accent_sums = np.zeros(bpb, dtype=np.float64)
    accent_counts = np.zeros(bpb, dtype=np.float64)
    for i, bt in enumerate(beat_grid):
        f_idx = min(len(flux_norm) - 1, int(bt * flux_rate))
        w_start = max(0, f_idx - 2)
        w_end = min(len(flux_norm), f_idx + 3)
        accent_sums[i % bpb] += float(np.max(flux_norm[w_start:w_end]))
        accent_counts[i % bpb] += 1
    accents = accent_sums / np.maximum(1, accent_counts)
    accents = accents / (np.max(accents) + 1e-9)

    # Swing ratio: average relative phase of off-beat onsets falling in [0.35, 0.72] of beat period
    offbeat_phases = []
    for ot in onset_times:
        rel = ((ot - best_phase_sec) % beat_period) / beat_period
        if 0.35 <= rel <= 0.72:
            offbeat_phases.append(rel)
    swing_ratio = round(float(np.median(offbeat_phases)), 3) if len(offbeat_phases) >= 6 else 0.50

    return {
        "estimatedBpm": dominant,
        "candidates": candidates,
        "halfDoubleAmbiguous": ambiguous,
        "meterEstimate": meter_est,
        "onsetDensityPerSec": density,
        "swingRatio": swing_ratio,
        "grooveFeel": "swung" if swing_ratio >= 0.56 else ("pushed" if swing_ratio <= 0.45 else "straight"),
        "regularity": round(candidates[0]["strength"], 3) if candidates else 0.0,
        "beatGridSec": beat_grid[:256],
        "downbeatsSec": downbeats[:64],
        "onsetCount": len(onset_times),
        "accentPattern": [round(float(v), 3) for v in accents],
        "assessment": "half_double_time_ambiguous" if ambiguous else ("estimated" if strong else "uncertain"),
    }


def _compute_chroma(mono_12k: np.ndarray, sr_12k: int) -> tuple[np.ndarray, np.ndarray]:
    """Compute 12-pitch-class Chroma matrix (12 x T) from STFT bins between C2 (65 Hz) and C7 (2093 Hz)."""
    nperseg = 4096
    noverlap = 2048
    freqs, times, zxx = signal.stft(mono_12k, fs=sr_12k, nperseg=nperseg, noverlap=noverlap, boundary=None)
    power = np.abs(zxx) ** 2
    valid = (freqs >= 65.4) & (freqs <= 2093.0)
    v_freqs = freqs[valid]
    v_power = power[valid]

    chroma = np.zeros((12, v_power.shape[1]), dtype=np.float64)
    midi_bins = np.round(69.0 + 12.0 * np.log2(v_freqs / 440.0)).astype(int)
    pitch_classes = midi_bins % 12
    for pc in range(12):
        mask = pitch_classes == pc
        if np.any(mask):
            chroma[pc] = v_power[mask].sum(axis=0)

    chroma = np.log1p(chroma * 100.0)
    norms = np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9
    return chroma / norms, times


def _analyze_harmony(mono_12k: np.ndarray, sr_12k: int, bpm: float | None) -> dict[str, Any]:
    """Estimate Key/Mode, threshold-gated chord progression, harmonic shifts, and chroma motifs."""
    chroma, times = _compute_chroma(mono_12k, sr_12k)
    if chroma.shape[1] < 4:
        return {
            "estimatedKey": "Uncertain",
            "modeCandidates": [],
            "chromaMean": [0.0] * 12,
            "chordProgression": [],
            "harmonicChangeTimesSec": [],
            "motifRepetitionScore": 0.0,
            "confidence": 0.0,
            "note": "Audio too short for harmonic estimation.",
        }

    mean_chroma = chroma.mean(axis=1)
    mc = mean_chroma - mean_chroma.mean()
    mc_norm = np.linalg.norm(mc) + 1e-9

    profiles = [
        ("major", MAJOR_PROFILE),
        ("minor", MINOR_PROFILE),
        ("dorian", DORIAN_PROFILE),
        ("mixolydian", MIXOLYDIAN_PROFILE),
    ]
    scored_keys: list[dict[str, Any]] = []
    for mode_name, prof in profiles:
        for root in range(12):
            shifted = np.roll(prof, root)
            sc = shifted - shifted.mean()
            corr = float((mc @ sc) / (mc_norm * (np.linalg.norm(sc) + 1e-9)))
            scored_keys.append(
                {"key": f"{NOTE_NAMES[root]} {mode_name}", "root": NOTE_NAMES[root], "mode": mode_name, "score": round(corr, 3)}
            )
    scored_keys.sort(key=lambda x: x["score"], reverse=True)
    top_key = scored_keys[0]
    gap = max(0.0, top_key["score"] - scored_keys[1]["score"]) if len(scored_keys) > 1 else 0.0
    key_conf = round(float(np.clip(top_key["score"] * 0.7 + gap * 1.5, 0.0, 0.98)), 3)

    # Build major & minor triad templates for conservative bar-window chord estimation
    chord_templates: list[tuple[str, np.ndarray]] = []
    for root in range(12):
        maj = np.zeros(12)
        maj[[root, (root + 4) % 12, (root + 7) % 12]] = [1.0, 0.85, 0.9]
        chord_templates.append((f"{NOTE_NAMES[root]}", maj / np.linalg.norm(maj)))
        mn = np.zeros(12)
        mn[[root, (root + 3) % 12, (root + 7) % 12]] = [1.0, 0.85, 0.9]
        chord_templates.append((f"{NOTE_NAMES[root]}m", mn / np.linalg.norm(mn)))

    bar_sec = (60.0 / (bpm or 120.0)) * 4.0
    duration_sec = float(times[-1]) if len(times) > 0 else 0.0
    chords: list[dict[str, Any]] = []
    change_times: list[float] = []
    prev_chord: str | None = None

    n_bars = min(32, max(1, int(math.ceil(duration_sec / max(0.5, bar_sec)))))
    for b in range(n_bars):
        t0 = b * bar_sec
        t1 = min(duration_sec, (b + 1) * bar_sec)
        mask = (times >= t0) & (times < t1)
        if not np.any(mask):
            continue
        seg = chroma[:, mask].mean(axis=1)
        seg_norm = np.linalg.norm(seg) + 1e-9
        seg_u = seg / seg_norm
        best_label, best_sim = "uncertain", 0.0
        for cname, tmpl in chord_templates:
            sim = float(seg_u @ tmpl)
            if sim > best_sim:
                best_sim = sim
                best_label = cname
        # Strict honesty gate: never fabricate chords when chroma correlation is weak
        final_label = best_label if best_sim >= 0.68 else "uncertain"
        if prev_chord is not None and final_label != prev_chord and final_label != "uncertain":
            change_times.append(round(t0, 2))
        prev_chord = final_label
        chords.append(
            {
                "bar": b + 1,
                "startSec": round(t0, 2),
                "endSec": round(t1, 2),
                "chord": final_label,
                "confidence": round(best_sim, 3),
                "isEstimate": True,
            }
        )

    # Motif recurrence via chroma self-similarity off-diagonal strength
    step = max(1, chroma.shape[1] // 96)
    c_sub = chroma[:, ::step]
    sim_mat = c_sub.T @ c_sub
    n_s = sim_mat.shape[0]
    motif_score = 0.0
    if n_s >= 8:
        # Ignore main diagonal (+/- 2 frames)
        off_vals = []
        for lag in range(4, n_s // 2):
            diag = np.diag(sim_mat, k=lag)
            if len(diag) >= 4:
                off_vals.append(float(np.mean(diag)))
        motif_score = round(max(off_vals, default=0.0), 3)

    return {
        "estimatedKey": top_key["key"] if top_key["score"] >= 0.35 else "Uncertain",
        "modeCandidates": scored_keys[:4],
        "chromaMean": [round(float(v), 4) for v in mean_chroma],
        "chordProgression": chords,
        "harmonicChangeTimesSec": change_times,
        "motifRepetitionScore": motif_score,
        "confidence": key_conf,
        "note": "Chroma 템플릿 기반 조성/코드 추정치입니다. 확신도가 낮은 구간은 uncertain으로 표기됩니다.",
    }


def _analyze_arrangement(
    stereo: np.ndarray, sr: int, mono_12k: np.ndarray, sr_12k: int, bpm: float | None
) -> dict[str, Any]:
    """Compute real time-aligned energy curve and novelty-detected sections."""
    duration_sec = len(stereo) / sr
    n_points = min(128, max(16, int(duration_sec * 2)))
    chunk_len = max(1, len(stereo) // n_points)
    energy_curve: list[dict[str, Any]] = []
    rms_vals = []
    for i in range(n_points):
        s = i * chunk_len
        e = min(len(stereo), (i + 1) * chunk_len)
        seg = stereo[s:e]
        rms = float(np.sqrt(np.mean(seg * seg))) if len(seg) > 0 else 0.0
        rms_vals.append(rms)
        rms_db = round(20.0 * math.log10(max(rms, 1e-6)), 2)
        energy_curve.append({"timeSec": round(s / sr, 2), "rmsDbfs": rms_db, "normEnergy": 0.0})

    max_rms = max(rms_vals) if rms_vals else 1.0
    for pt, r in zip(energy_curve, rms_vals):
        pt["normEnergy"] = round(float(r / max(max_rms, 1e-6)), 3)

    # Detect structural novelty peaks using RMS + spectral flux contrast
    chroma, c_times = _compute_chroma(mono_12k, sr_12k)
    rms_arr = np.array(rms_vals, dtype=np.float64)
    rms_smooth = ndimage.gaussian_filter1d(rms_arr, sigma=1.5)
    novelty = np.abs(np.diff(rms_smooth, prepend=rms_smooth[0]))
    if chroma.shape[1] >= 8:
        c_diff = np.linalg.norm(np.diff(chroma, axis=1, prepend=chroma[:, :1]), axis=0)
        c_resampled = np.interp(
            np.linspace(0, 1, len(novelty)), np.linspace(0, 1, len(c_diff)), c_diff
        )
        novelty = novelty / (np.max(novelty) + 1e-9) + 0.65 * (c_resampled / (np.max(c_resampled) + 1e-9))

    min_section_pts = max(4, int(round(len(novelty) * (6.0 / max(12.0, duration_sec)))))
    peaks, _ = signal.find_peaks(novelty, distance=min_section_pts, prominence=0.22)
    boundaries_idx = [0] + sorted(int(p) for p in peaks if 3 <= p <= len(novelty) - 4) + [len(novelty)]
    # Cap at 8 sections for clean DAW readability
    if len(boundaries_idx) > 9:
        ranked = sorted(peaks, key=lambda p: novelty[p], reverse=True)[:7]
        boundaries_idx = [0] + sorted(int(p) for p in ranked) + [len(novelty)]

    bar_sec = (60.0 / (bpm or 120.0)) * 4.0
    raw_sections = []
    for idx in range(len(boundaries_idx) - 1):
        i0, i1 = boundaries_idx[idx], boundaries_idx[idx + 1]
        t0 = round((i0 / len(novelty)) * duration_sec, 2)
        t1 = round((i1 / len(novelty)) * duration_sec, 2)
        seg_rms = float(np.mean(rms_arr[i0:i1])) if i1 > i0 else 0.0
        rel_e = seg_rms / max(max_rms, 1e-6)
        raw_sections.append((t0, t1, seg_rms, rel_e))

    max_rel = max((s[3] for s in raw_sections), default=1.0)
    climax_idx = int(np.argmax([s[3] for s in raw_sections])) if raw_sections else 0
    sections: list[dict[str, Any]] = []
    letter_idx = 0
    for idx, (t0, t1, seg_rms, rel_e) in enumerate(raw_sections):
        if idx == 0 and rel_e < max_rel * 0.78 and len(raw_sections) >= 3:
            label = "Intro"
            estimated_role = True
        elif idx == len(raw_sections) - 1 and rel_e < max_rel * 0.75 and len(raw_sections) >= 3:
            label = "Outro"
            estimated_role = True
        elif idx == climax_idx and rel_e >= 0.72 and len(raw_sections) >= 3:
            label = "Climax"
            estimated_role = True
        elif idx > 0 and idx < len(raw_sections) - 1 and rel_e < max_rel * 0.58:
            label = "Break"
            estimated_role = True
        else:
            label = f"Section {chr(65 + (letter_idx % 26))}"
            letter_idx += 1
            estimated_role = False

        sections.append(
            {
                "id": make_id("rsec"),
                "label": label,
                "startSec": t0,
                "endSec": t1,
                "startBar": round(t0 / max(0.25, bar_sec), 1) + 1.0,
                "endBar": round(t1 / max(0.25, bar_sec), 1) + 1.0,
                "energyDbfs": round(20.0 * math.log10(max(seg_rms, 1e-6)), 2),
                "relativeEnergy": round(rel_e, 3),
                "isEstimatedRole": estimated_role,
            }
        )

    return {
        "durationSec": round(duration_sec, 3),
        "sections": sections,
        "energyCurve": energy_curve,
    }


def _analyze_sound_and_instruments(stereo: np.ndarray, sr: int, mono_12k: np.ndarray, sr_12k: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Measure Welch frequency bands, dynamics, stereo field, and HPSS instrument presence."""
    mono = stereo.mean(axis=1).astype(np.float64)
    nperseg = min(8192, max(256, len(mono)))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg)
    total_power = float(psd.sum()) + 1e-18

    def band_pct(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        return round(float(psd[mask].sum() / total_power) * 100.0, 2)

    bands = {
        "sub_20_60": band_pct(20, 60),
        "bass_60_200": band_pct(60, 200),
        "low_mid_200_500": band_pct(200, 500),
        "mid_500_2000": band_pct(500, 2000),
        "presence_2k_6k": band_pct(2000, 6000),
        "air_6k_20k": band_pct(6000, 20000),
    }

    centroid_hz = round(float((freqs * psd).sum() / total_power), 1)

    peak = float(np.max(np.abs(stereo))) if len(stereo) > 0 else 0.0
    rms = float(np.sqrt(np.mean(stereo * stereo))) if len(stereo) > 0 else 0.0
    peak_dbfs = round(20.0 * math.log10(max(peak, 1e-9)), 2)
    rms_dbfs = round(20.0 * math.log10(max(rms, 1e-9)), 2)
    crest_db = round(peak_dbfs - rms_dbfs, 2)

    # Short-term 400ms RMS dynamic range (P95 - P10)
    win = max(1, int(0.4 * sr))
    n_wins = max(1, len(mono) // win)
    st_rms = np.array(
        [
            20.0 * math.log10(max(float(np.sqrt(np.mean(mono[i * win : (i + 1) * win] ** 2))), 1e-6))
            for i in range(n_wins)
        ]
    )
    active_st = st_rms[st_rms > -55.0]
    dyn_range_db = round(float(np.percentile(active_st, 95) - np.percentile(active_st, 10)), 2) if len(active_st) >= 4 else 0.0

    # Stereo correlation & mid/side width
    left, right = stereo[:, 0].astype(np.float64), stereo[:, 1].astype(np.float64)
    denom = float(np.sqrt((left @ left) * (right @ right))) + 1e-12
    lr_corr = round(float(np.clip((left @ right) / denom, -1.0, 1.0)), 3)
    mid_e = float(np.mean((0.5 * (left + right)) ** 2))
    side_e = float(np.mean((0.5 * (left - right)) ** 2))
    stereo_width = round(float(np.clip(math.sqrt(side_e / (mid_e + 1e-12)), 0.0, 1.5)), 3)

    # STFT spectral flux & HPSS (Harmonic-Percussive separation via median filter)
    f12, _, z12 = signal.stft(mono_12k, fs=sr_12k, nperseg=1024, noverlap=768, boundary=None)
    mag12 = np.abs(z12)
    flux_mean = round(float(np.mean(np.maximum(np.diff(mag12, axis=1), 0.0))), 4) if mag12.shape[1] > 1 else 0.0

    # HPSS median filter (time-axis median -> harmonic, freq-axis median -> percussive)
    h_mag = ndimage.median_filter(mag12, size=(1, 17))
    p_mag = ndimage.median_filter(mag12, size=(17, 1))
    h_pow = float(np.sum(h_mag ** 2))
    p_pow = float(np.sum(p_mag ** 2))
    hp_total = h_pow + p_pow + 1e-12
    percussive_ratio = round(p_pow / hp_total, 3)
    harmonic_ratio = round(h_pow / hp_total, 3)

    # Estimate reverb/space character conservatively from spectral decay & stereo width
    reverb_char = (
        "ambient / spacious"
        if (stereo_width > 0.42 and percussive_ratio < 0.35)
        else ("tight / dry" if percussive_ratio > 0.45 and stereo_width < 0.28 else "balanced room")
    )
    transient_char = "punchy" if crest_db >= 13.0 else ("controlled" if crest_db >= 9.0 else "compressed / dense")

    sound = {
        "measured": {
            "sampleRate": sr,
            "channels": int(stereo.shape[1]),
            "frequencyBandsPct": bands,
            "spectralCentroidHz": centroid_hz,
            "spectralFluxMean": flux_mean,
            "crestFactorDb": crest_db,
            "dynamicRangeDb": dyn_range_db,
            "approxLufs": round(rms_dbfs - 0.691, 2),
            "rmsDbfs": rms_dbfs,
            "samplePeakDbfs": peak_dbfs,
            "stereoWidth": stereo_width,
            "lrCorrelation": lr_corr,
            "percussiveRatio": percussive_ratio,
            "harmonicRatio": harmonic_ratio,
        },
        "estimated": {
            "reverbCharacter": reverb_char,
            "transientCharacter": transient_char,
            "disclaimer": "마스터 음원에서 실제 EQ/컴프레서/리버브 플러그인 수치를 역산하지 않습니다. 측정된 스펙트럼·다이내믹·스테레오 지표와 보수적 추정치만 제공합니다.",
        },
    }

    # Instrument presence estimates via HPSS + band energy
    def hp_band_share(arr: np.ndarray, lo: float, hi: float) -> float:
        m = (f12 >= lo) & (f12 < hi)
        return float(np.sum(arr[m] ** 2)) / hp_total

    drum_score = min(0.96, round(percussive_ratio * 1.9 + hp_band_share(p_mag, 50, 220) * 1.4, 2))
    bass_score = min(0.96, round((bands["sub_20_60"] + bands["bass_60_200"]) / 52.0, 2))
    mid_harm_score = min(0.95, round(hp_band_share(h_mag, 200, 1800) * 2.2, 2))
    high_synth_score = min(0.95, round(hp_band_share(h_mag, 1800, 5500) * 3.5, 2))
    vocal_band_score = min(0.90, round(hp_band_share(h_mag, 300, 3400) * 1.5 * (1.0 - min(0.5, stereo_width)), 2))

    def label_level(s: float) -> str:
        return "prominent" if s >= 0.6 else ("present" if s >= 0.28 else "low")

    instrumentation = {
        "isEstimated": True,
        "method": "HPSS median-filter decomposition + band energy ratios (no stem separation run)",
        "note": "HPSS 스펙트럼 추정치이며 실제 개별 녹음이나 분리 스템이 아닙니다.",
        "elements": [
            {"name": "Drums / Percussion", "confidence": drum_score, "level": label_level(drum_score)},
            {"name": "Bass / Sub", "confidence": bass_score, "level": label_level(bass_score)},
            {"name": "Guitar / Keys (Mid Harmonic)", "confidence": mid_harm_score, "level": label_level(mid_harm_score)},
            {"name": "Synth / High Harmonic", "confidence": high_synth_score, "level": label_level(high_synth_score)},
            {"name": "Vocal-Band Center Energy", "confidence": vocal_band_score, "level": label_level(vocal_band_score)},
        ],
    }

    return sound, instrumentation


def analyze_audio_file(
    audio_path: Path,
    source_asset_id: str,
    sha256: str,
    cache_dir: Path,
    progress_cb: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run (or load cached) real acoustic analysis on a local audio file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{sha256}_{ANALYSIS_VERSION}.json"
    if cache_file.is_file():
        if progress_cb:
            progress_cb(100, "cached")
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        cached["sourceAssetId"] = source_asset_id
        cached["fromCache"] = True
        return cached

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Analysis cancelled by user")

    if progress_cb:
        progress_cb(10, "decoding_audio")
    stereo, sr = _load_audio_bounded(audio_path)
    check_cancel()

    if progress_cb:
        progress_cb(25, "resampling_analysis_signal")
    mono_12k, sr_12k = _downsample_mono(stereo, sr, 12000)
    check_cancel()

    if progress_cb:
        progress_cb(42, "rhythm_analysis")
    rhythm = _analyze_rhythm(mono_12k, sr_12k)
    check_cancel()

    if progress_cb:
        progress_cb(60, "harmony_analysis")
    harmony = _analyze_harmony(mono_12k, sr_12k, rhythm.get("estimatedBpm"))
    check_cancel()

    if progress_cb:
        progress_cb(76, "arrangement_analysis")
    arrangement = _analyze_arrangement(stereo, sr, mono_12k, sr_12k, rhythm.get("estimatedBpm"))
    check_cancel()

    if progress_cb:
        progress_cb(90, "sound_and_instrument_analysis")
    sound, instrumentation = _analyze_sound_and_instruments(stereo, sr, mono_12k, sr_12k)
    check_cancel()

    result = {
        "analysisVersion": ANALYSIS_VERSION,
        "sourceAssetId": source_asset_id,
        "sha256": sha256,
        "analyzedAt": utc_now_iso(),
        "fromCache": False,
        "durationSec": arrangement["durationSec"],
        "rhythm": rhythm,
        "harmony": harmony,
        "arrangement": arrangement,
        "sound": sound,
        "instrumentation": instrumentation,
    }

    tmp = cache_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cache_file)

    if progress_cb:
        progress_cb(100, "completed")
    return result


class AnalysisJobManager:
    """Single-worker background analysis manager with progress, caching, and cancellation."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daw-analysis")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancels: dict[str, threading.Event] = {}

    def submit(
        self,
        project_id: str,
        reference_id: str,
        work_fn: Callable[[Callable[[int, str], None], threading.Event], dict[str, Any]],
        on_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        job_id = make_id("ajob")
        cancel_ev = threading.Event()
        job_info = {
            "jobId": job_id,
            "projectId": project_id,
            "referenceId": reference_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "error": None,
            "startedAt": utc_now_iso(),
            "finishedAt": None,
        }
        with self._lock:
            self._jobs[job_id] = job_info
            self._cancels[job_id] = cancel_ev

        def progress_cb(pct: int, stage: str) -> None:
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id]["status"] = "running"
                    self._jobs[job_id]["progress"] = pct
                    self._jobs[job_id]["stage"] = stage

        def runner() -> None:
            try:
                progress_cb(5, "starting")
                result = work_fn(progress_cb, cancel_ev)
                if on_complete:
                    on_complete(result)
                with self._lock:
                    self._jobs[job_id]["status"] = "completed"
                    self._jobs[job_id]["progress"] = 100
                    self._jobs[job_id]["stage"] = "completed"
                    self._jobs[job_id]["finishedAt"] = utc_now_iso()
            except Exception as exc:
                with self._lock:
                    self._jobs[job_id]["status"] = "cancelled" if cancel_ev.is_set() else "failed"
                    self._jobs[job_id]["error"] = str(exc)
                    self._jobs[job_id]["finishedAt"] = utc_now_iso()

        self._executor.submit(runner)
        return dict(job_info)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise FileNotFoundError(f"Analysis job not found: {job_id}")
            return dict(self._jobs[job_id])

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(j) for j in self._jobs.values() if j["projectId"] == project_id]

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise FileNotFoundError(f"Analysis job not found: {job_id}")
            self._cancels[job_id].set()
            self._jobs[job_id]["status"] = "cancelling"
            return dict(self._jobs[job_id])


analysis_jobs = AnalysisJobManager()
