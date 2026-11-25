"""Real Multi-Band Drum & Groove Transcriber (Phase 03.2 · Section 4).

Analyzes Demucs Drums stem (or HPSS percussive fallback) to extract real Kick (36), Snare/Clap (38),
Closed Hi-Hat (42), Open Hi-Hat (46), and Tom/Percussion (45/48) hits, preserving BOTH true human/audio
microtiming (`rawMidiNotes`) AND beat-grid-snapped timing (`quantizedMidiNotes`), plus measured swing,
syncopation, 16-step accent grid, turnaround fill bars, and pattern repetition period.
Never substitutes random humanize for real groove analysis!
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

from engine.daw_workspace.schema import make_id


def _load_mono(path: Path, max_sec: float = 240.0) -> tuple[np.ndarray, int]:
    info = sf.info(str(path))
    max_frames = int(min(info.frames, max_sec * info.samplerate))
    data, sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float64)
    return np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0), int(sr)


def _band_flux(mag: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return np.zeros(max(1, mag.shape[1] - 1), dtype=np.float64)
    sub = mag[mask]
    flux = np.maximum(np.diff(sub, axis=1), 0.0).sum(axis=0)
    return flux


def _pick_band_onsets(
    flux: np.ndarray,
    frame_rate: float,
    min_dist_sec: float,
    sigma_mult: float,
    floor_frac: float = 0.14,
) -> list[tuple[float, float]]:
    if len(flux) < 8:
        return []
    mx = float(np.max(flux))
    if mx <= 1e-9:
        return []
    norm = flux / mx
    thresh = max(floor_frac, float(np.mean(norm) + sigma_mult * np.std(norm)))
    dist = max(1, int(round(min_dist_sec * frame_rate)))
    peaks, props = signal.find_peaks(norm, height=thresh, distance=dist, prominence=thresh * 0.35)
    out: list[tuple[float, float]] = []
    for p, h in zip(peaks, props["peak_heights"]):
        out.append((float(p) / frame_rate, float(h)))
    return out


def transcribe_drum_groove(
    audio_path: Path,
    *,
    bpm: float = 120.0,
    beat_offset_sec: float = 0.0,
    bpb: float = 4.0,
    source_kind: str = "demucs_drums_stem",
) -> dict[str, Any]:
    """Extract Kick, Snare, Closed/Open Hi-Hat, Percussion MIDI notes & exact Groove Profile."""
    mono, sr = _load_mono(audio_path)
    duration_sec = len(mono) / max(1, sr)
    rms_all = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
    if rms_all < 1e-4 or duration_sec < 0.4:
        return {
            "sourceKind": source_kind,
            "hasDrums": False,
            "rmsDbfs": round(20.0 * math.log10(max(rms_all, 1e-9)), 2),
            "hitCounts": {"kick": 0, "snare": 0, "closedHat": 0, "openHat": 0, "percussion": 0},
            "swingRatio": 0.5,
            "grooveFeel": "straight",
            "syncopationScore": 0.0,
            "meanMicrotimingMs": 0.0,
            "microtimingStdMs": 0.0,
            "accentGrid16": [0.0] * 16,
            "fillBars": [],
            "patternRepetitionBars": 1,
            "rawMidiNotes": [],
            "quantizedMidiNotes": [],
            "patternTemplate1Bar": [],
            "patternTemplate2Bar": [],
        }

    # Resample to 22050 Hz for consistent multi-band transient resolution up to 11 kHz
    target_sr = 22050
    if sr != target_sr:
        g = math.gcd(sr, target_sr)
        mono = signal.resample_poly(mono, target_sr // g, sr // g)
        sr = target_sr

    # If operating on full mix fallback (no Demucs stem), isolate percussive spectrogram via HPSS median filter!
    nperseg = 1024
    hop = 220  # ~100 Hz frame rate (10ms resolution)
    freqs, _, zxx = signal.stft(mono, fs=sr, nperseg=nperseg, noverlap=nperseg - hop, boundary=None)
    mag = np.abs(zxx)
    if source_kind != "demucs_drums_stem":
        h_mag = ndimage.median_filter(mag, size=(1, 17))
        p_mag = ndimage.median_filter(mag, size=(17, 1))
        mask_p = (p_mag ** 2) / (p_mag ** 2 + h_mag ** 2 + 1e-12)
        mag = mag * mask_p

    frame_rate = sr / float(hop)
    kick_flux = _band_flux(mag, freqs, 35.0, 145.0)
    snare_flux = _band_flux(mag, freqs, 180.0, 2600.0)
    hat_flux = _band_flux(mag, freqs, 4800.0, 10800.0)
    perc_flux = _band_flux(mag, freqs, 150.0, 650.0)

    kicks = _pick_band_onsets(kick_flux, frame_rate, min_dist_sec=0.14, sigma_mult=1.15, floor_frac=0.18)
    snares_raw = _pick_band_onsets(snare_flux, frame_rate, min_dist_sec=0.14, sigma_mult=1.20, floor_frac=0.18)
    hats_raw = _pick_band_onsets(hat_flux, frame_rate, min_dist_sec=0.075, sigma_mult=0.90, floor_frac=0.12)
    percs_raw = _pick_band_onsets(perc_flux, frame_rate, min_dist_sec=0.12, sigma_mult=1.55, floor_frac=0.26)

    # Filter snare hits that are pure low-end kick bleed (keep if snare band dominates or not coincident)
    kick_norm = kick_flux / (np.max(kick_flux) + 1e-9)
    snare_norm = snare_flux / (np.max(snare_flux) + 1e-9)
    snares: list[tuple[float, float]] = []
    for t_s, strength in snares_raw:
        f_idx = min(len(kick_norm) - 1, int(round(t_s * frame_rate)))
        coincides_kick = any(abs(t_s - kt) < 0.035 for kt, _ in kicks)
        if coincides_kick and kick_norm[f_idx] > snare_norm[f_idx] * 1.35:
            continue
        snares.append((t_s, strength))

    # Classify Closed (42) vs Open (46) Hi-Hat by measuring post-onset high-band decay energy (60–180ms tail)
    hi_mask = (freqs >= 4800.0) & (freqs <= 10800.0)
    hi_energy = mag[hi_mask].mean(axis=0) if np.any(hi_mask) else np.zeros(mag.shape[1])
    hats: list[tuple[float, float, int]] = []
    for t_s, strength in hats_raw:
        f0 = min(len(hi_energy) - 1, int(round(t_s * frame_rate)))
        atk_e = float(np.mean(hi_energy[f0 : min(len(hi_energy), f0 + 4)])) + 1e-9
        tail_e = float(np.mean(hi_energy[min(len(hi_energy) - 1, f0 + 7) : min(len(hi_energy), f0 + 18)]))
        is_open = (tail_e / atk_e) >= 0.42
        hats.append((t_s, strength, 46 if is_open else 42))

    # Keep percussion/tom hits distinct from kick/snare onsets
    percs: list[tuple[float, float]] = []
    for t_s, strength in percs_raw:
        if any(abs(t_s - kt) < 0.04 for kt, _ in kicks) or any(abs(t_s - st) < 0.04 for st, _ in snares):
            continue
        percs.append((t_s, strength))

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    raw_notes: list[dict[str, Any]] = []
    quant_notes: list[dict[str, Any]] = []
    micro_offsets_ms: list[float] = []
    offbeat_phases: list[float] = []
    accent_sums = np.zeros(16, dtype=np.float64)
    accent_cnts = np.zeros(16, dtype=np.float64)

    def add_hit(t_sec: float, strength: float, pitch: int, dur_beats: float, role: str) -> None:
        raw_b = max(0.0, (t_sec - beat_offset_sec) / sec_per_beat)
        q_b = round(round(raw_b * 4.0) / 4.0, 4)  # 16th-note grid
        offset_ms = round((raw_b - q_b) * sec_per_beat * 1000.0, 2)
        if abs(offset_ms) <= 65.0:
            micro_offsets_ms.append(offset_ms)
        vel = max(38, min(124, int(round(46 + strength * 76))))
        conf = round(float(np.clip(strength, 0.15, 0.99)), 3)

        step16 = int(round((q_b % bpb) * 4.0)) % 16
        accent_sums[step16] += vel / 127.0
        accent_cnts[step16] += 1.0

        # Measure offbeat swing ratio on 8th-note offbeats (0.35..0.72 of beat)
        frac = raw_b - math.floor(raw_b)
        if 0.35 <= frac <= 0.72:
            offbeat_phases.append(frac)

        base_ev = {
            "pitch": pitch,
            "velocity": vel,
            "durationBeats": dur_beats,
            "role": role,
            "onsetSec": round(t_sec, 4),
            "microtimingOffsetMs": offset_ms,
            "confidence": conf,
        }
        raw_notes.append({"id": make_id("note"), "startBeat": round(raw_b, 4), **base_ev})
        quant_notes.append({"id": make_id("note"), "startBeat": q_b, **base_ev})

    for t_s, st in kicks:
        add_hit(t_s, st, 36, 0.35, "kick")
    for t_s, st in snares:
        add_hit(t_s, st, 38, 0.28, "snare")
    for t_s, st, hp in hats:
        add_hit(t_s, st, hp, 0.32 if hp == 46 else 0.16, "open_hat" if hp == 46 else "closed_hat")
    for t_s, st in percs:
        add_hit(t_s, st, 45, 0.24, "percussion")

    # Deduplicate quantized collisions on identical (pitch, 16th step) keeping higher velocity
    dedup_q: dict[tuple[int, float], dict[str, Any]] = {}
    for n in quant_notes:
        key = (n["pitch"], round(n["startBeat"], 2))
        if key not in dedup_q or n["velocity"] > dedup_q[key]["velocity"]:
            dedup_q[key] = n
    quant_notes = sorted(dedup_q.values(), key=lambda x: (x["startBeat"], x["pitch"]))
    raw_notes.sort(key=lambda x: (x["startBeat"], x["pitch"]))

    # Compute Groove Metrics: Swing, Syncopation, Fill Bars, Pattern Repetition!
    swing_ratio = round(float(np.median(offbeat_phases)), 3) if len(offbeat_phases) >= 6 else 0.50
    groove_feel = "swung" if swing_ratio >= 0.555 else ("pushed" if swing_ratio <= 0.455 else "straight")

    # Syncopation: fraction of kick/snare energy falling off main beats (quarter-note grid)
    ks_hits = [n for n in quant_notes if n["pitch"] in (36, 38)]
    offgrid_ks = [n for n in ks_hits if abs(n["startBeat"] - round(n["startBeat"])) > 0.08]
    syncopation = round(len(offgrid_ks) / max(1, len(ks_hits)), 3)

    # 16-step normalized accent profile
    accent_avg = accent_sums / np.maximum(1.0, accent_cnts)
    accent_max = float(np.max(accent_avg)) if np.max(accent_avg) > 0 else 1.0
    accent_grid_16 = [round(float(v / accent_max), 3) for v in accent_avg]

    # Detect Fill Bars (bars whose beats 2.5..4.0 snare/tom hit density exceeds 1.5x median)
    total_bars = max(1, int(math.ceil(duration_sec / (sec_per_beat * bpb))))
    tail_counts = []
    for bar in range(total_bars):
        b0 = bar * bpb + max(0.0, bpb - 1.5)
        b1 = (bar + 1) * bpb
        cnt = sum(1 for n in quant_notes if b0 <= n["startBeat"] < b1 and n["pitch"] in (38, 45, 48))
        tail_counts.append(cnt)
    med_tail = float(np.median(tail_counts)) if tail_counts else 0.0
    fill_bars = [bar + 1 for bar, c in enumerate(tail_counts) if c >= max(3, med_tail * 1.6)]

    # Measure Pattern Repetition (1-bar vs 2-bar vs 4-bar correlation on 16-step binary grid)
    bar_vecs = np.zeros((total_bars, 16), dtype=np.float64)
    for n in quant_notes:
        b_idx = int(n["startBeat"] // bpb)
        if 0 <= b_idx < total_bars:
            s_idx = int(round((n["startBeat"] % bpb) * 4.0)) % 16
            bar_vecs[b_idx, s_idx] += 1.0 if n["pitch"] in (36, 38) else 0.4

    def _lag_sim(lag: int) -> float:
        if total_bars <= lag:
            return 0.0
        sims = []
        for i in range(total_bars - lag):
            a, b = bar_vecs[i], bar_vecs[i + lag]
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na > 0 and nb > 0:
                sims.append(float((a @ b) / (na * nb)))
        return float(np.mean(sims)) if sims else 0.0

    rep_scores = {1: _lag_sim(1), 2: _lag_sim(2), 4: _lag_sim(4)}
    pattern_rep_bars = max(rep_scores, key=lambda k: rep_scores[k]) if any(rep_scores.values()) else 1

    # Extract representative 2-bar (8-beat) recurring groove template from highest-energy full 2-bar window!
    best_win_start = 0
    best_win_hits = -1
    for bar in range(0, max(1, total_bars - 1)):
        s0, s1 = bar * bpb, (bar + 2) * bpb
        cnt = sum(1 for n in quant_notes if s0 <= n["startBeat"] < s1)
        if cnt > best_win_hits:
            best_win_hits = cnt
            best_win_start = bar
    t2_start = best_win_start * bpb
    t2_end = t2_start + bpb * 2.0
    template_2bar = [
        {
            "pitch": n["pitch"],
            "velocity": n["velocity"],
            "startBeat": round(n["startBeat"] - t2_start, 4),
            "durationBeats": n["durationBeats"],
            "role": n["role"],
            "microtimingOffsetMs": n["microtimingOffsetMs"],
        }
        for n in quant_notes
        if t2_start <= n["startBeat"] < t2_end
    ]
    template_1bar = [n for n in template_2bar if n["startBeat"] < bpb]

    return {
        "sourceKind": source_kind,
        "hasDrums": len(quant_notes) >= 4,
        "rmsDbfs": round(20.0 * math.log10(max(rms_all, 1e-9)), 2),
        "hitCounts": {
            "kick": len(kicks),
            "snare": len(snares),
            "closedHat": sum(1 for _, _, p in hats if p == 42),
            "openHat": sum(1 for _, _, p in hats if p == 46),
            "percussion": len(percs),
        },
        "swingRatio": swing_ratio,
        "grooveFeel": groove_feel,
        "syncopationScore": syncopation,
        "meanMicrotimingMs": round(float(np.mean(micro_offsets_ms)), 2) if micro_offsets_ms else 0.0,
        "microtimingStdMs": round(float(np.std(micro_offsets_ms)), 2) if micro_offsets_ms else 0.0,
        "accentGrid16": accent_grid_16,
        "fillBars": fill_bars[:16],
        "patternRepetitionBars": pattern_rep_bars,
        "patternRepetitionScores": {str(k): round(v, 3) for k, v in rep_scores.items()},
        "rawMidiNotes": raw_notes[:1200],
        "quantizedMidiNotes": quant_notes[:1200],
        "patternTemplate1Bar": template_1bar,
        "patternTemplate2Bar": template_2bar,
    }
