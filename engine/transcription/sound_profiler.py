"""Acoustic Sound Profile, Spatial Profile, Full-Length Bass Performance & Honest Instrument Classification (Phase 03.2.1).

Strictly adheres to acoustic honesty:
- Separates measured acoustic features (band balance, centroid, rolloff, stereo correlation, M/S dB, transient crest,
  reverb tail decay slope, bass-kick onset interaction) from starting-point sound design suggestions.
- NEVER claims to reverse-engineer exact original EQ/Compressor/Reverb plugin parameters.
- NEVER masquerades a Demucs `other` stem as an isolated guitar or synth studio recording.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import ndimage, signal


def _load_stereo_bounded(path: Path, max_sec: float = 600.0) -> tuple[np.ndarray, int, dict[str, Any]]:
    info = sf.info(str(path))
    sr = int(info.samplerate)
    orig_sec = float(info.frames) / max(1, sr)
    max_frames = int(min(info.frames, max_sec * sr))
    data, read_sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    analyzed_sec = len(data) / max(1, int(read_sr))
    cov_pct = round(min(100.0, (analyzed_sec / max(1e-6, orig_sec)) * 100.0), 2)
    coverage = {
        "originalDurationSec": round(orig_sec, 3),
        "analyzedDurationSec": round(analyzed_sec, 3),
        "coveragePct": cov_pct,
        "isComplete": analyzed_sec >= orig_sec - 0.15,
        "truncated": analyzed_sec < orig_sec - 0.15,
    }
    return data.astype(np.float64), int(read_sr), coverage


def _band_stereo_width(left: np.ndarray, right: np.ndarray, sr: int, lo_hz: float, hi_hz: float) -> float:
    nyq = sr * 0.5
    lo = max(10.0, lo_hz) / nyq
    hi = min(nyq * 0.96, hi_hz) / nyq
    if lo >= hi or len(left) < 256:
        return 0.0
    try:
        sos = signal.butter(3, [lo, hi], btype="bandpass", output="sos")
        fl = signal.sosfilt(sos, left)
        fr = signal.sosfilt(sos, right)
    except Exception:
        return 0.0
    mid = 0.5 * (fl + fr)
    side = 0.5 * (fl - fr)
    mid_e = float(np.mean(mid * mid))
    side_e = float(np.mean(side * side))
    if mid_e + side_e < 1e-12:
        return 0.0
    return round(float(np.clip(math.sqrt(side_e / (mid_e + 1e-12)), 0.0, 1.5)), 3)


def extract_sound_and_spatial_profile(
    audio_path: Path,
    *,
    role: str = "master",
    bpm: float = 120.0,
    max_sec: float = 600.0,
) -> dict[str, Any]:
    """Compute detailed measured Sound Profile & Spatial Profile for master or a separated stem."""
    stereo, sr, coverage = _load_stereo_bounded(audio_path, max_sec=max_sec)
    mono = stereo.mean(axis=1)
    rms = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
    rms_db = round(20.0 * math.log10(max(rms, 1e-9)), 2)
    peak = float(np.max(np.abs(stereo))) if len(stereo) else 0.0
    peak_db = round(20.0 * math.log10(max(peak, 1e-9)), 2)
    crest_db = round(peak_db - rms_db, 2) if rms > 1e-7 else 0.0

    if rms < 1e-5 or len(mono) < 512:
        return {
            "role": role,
            "active": False,
            "coverage": coverage,
            "soundProfile": {
                "rmsDbfs": rms_db,
                "peakDbfs": peak_db,
                "frequencyBalancePct": {},
                "spectralCentroidHz": 0.0,
                "spectralRolloff85Hz": 0.0,
                "harmonicRatio": 0.0,
                "percussiveRatio": 0.0,
                "transientStrength": 0.0,
                "attackCharacter": "silent",
                "sustainEstimateSec": 0.0,
                "dynamicRangeDb": 0.0,
                "distortionRoughnessEstimate": 0.0,
                "lowEndProfile": "silent",
                "stereoWidth": 0.0,
            },
            "spatialProfile": {
                "directAmbientRatio": 1.0,
                "reverbTailSecEstimate": 0.0,
                "stereoCorrelation": 1.0,
                "midDbfs": rms_db,
                "sideDbfs": -120.0,
                "sideToMidDb": -60.0,
                "freqDependentWidth": {"low_20_250": 0.0, "mid_250_2500": 0.0, "high_2500_20k": 0.0},
                "delayRepetitionCandidate": None,
                "relativeDistance": "silent",
            },
            "suggestedSoundDesignHints": [],
            "honestyDisclaimer": "음향 실측 기반 추정치이며 원본 믹스의 정확한 플러그인 파라미터를 역산하지 않습니다.",
        }

    # Welch PSD spectral balance, centroid, and 85% rolloff
    nperseg = min(8192, max(512, len(mono)))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg)
    total_pow = float(psd.sum()) + 1e-18

    def _band_pct(lo: float, hi: float) -> float:
        m = (freqs >= lo) & (freqs < hi)
        return round(float(psd[m].sum() / total_pow) * 100.0, 2)

    freq_balance = {
        "sub_20_60": _band_pct(20.0, 60.0),
        "bass_60_200": _band_pct(60.0, 200.0),
        "low_mid_200_500": _band_pct(200.0, 500.0),
        "mid_500_2000": _band_pct(500.0, 2000.0),
        "presence_2k_6k": _band_pct(2000.0, 6000.0),
        "air_6k_20k": _band_pct(6000.0, 20000.0),
    }
    centroid_hz = round(float((freqs * psd).sum() / total_pow), 1)
    cumsum_p = np.cumsum(psd) / total_pow
    rolloff_idx = int(np.searchsorted(cumsum_p, 0.85))
    rolloff_85_hz = round(float(freqs[min(len(freqs) - 1, rolloff_idx)]), 1)

    # Downsampled STFT for HPSS, sustain, transient, roughness, and reverb tail estimation
    target_sr = 16000
    if sr != target_sr:
        g = math.gcd(sr, target_sr)
        mono_16k = signal.resample_poly(mono, target_sr // g, sr // g)
    else:
        mono_16k = mono

    f16, _, z16 = signal.stft(mono_16k, fs=target_sr, nperseg=1024, noverlap=768, boundary=None)
    mag16 = np.abs(z16)
    frame_rate = target_sr / 256.0  # 62.5 Hz (16 ms hop)

    h_mag = ndimage.median_filter(mag16, size=(1, 15))
    p_mag = ndimage.median_filter(mag16, size=(15, 1))
    h_pow = float(np.sum(h_mag ** 2))
    p_pow = float(np.sum(p_mag ** 2))
    hp_tot = h_pow + p_pow + 1e-12
    harmonic_ratio = round(h_pow / hp_tot, 3)
    percussive_ratio = round(p_pow / hp_tot, 3)

    # Frame RMS envelope (16 ms) for dynamic range, transient strength, and reverb tail decay
    frame_rms = np.sqrt(np.mean(mag16 ** 2, axis=0) + 1e-18)
    frame_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-9))
    active_db = frame_db[frame_db > np.max(frame_db) - 55.0]
    dyn_range_db = round(float(np.percentile(active_db, 95) - np.percentile(active_db, 15)), 2) if len(active_db) >= 8 else 0.0

    # Onset flux & transient sharpness
    flux = np.maximum(np.diff(mag16, axis=1), 0.0).sum(axis=0)
    flux_max = float(np.max(flux)) + 1e-9
    flux_norm = flux / flux_max
    transient_strength = round(float(np.clip((crest_db / 22.0) * 0.55 + percussive_ratio * 0.45, 0.0, 1.0)), 3)
    attack_char = "sharp / punchy" if transient_strength >= 0.58 else ("medium" if transient_strength >= 0.34 else "soft / sustained")

    # Estimate post-peak decay / sustain time & reverb tail from strong onset peaks
    peaks, _ = signal.find_peaks(flux_norm, height=max(0.22, float(np.mean(flux_norm) + np.std(flux_norm))), distance=int(0.18 * frame_rate))
    decay_secs: list[float] = []
    direct_energies: list[float] = []
    ambient_energies: list[float] = []
    for p in peaks[:40]:
        if p + int(0.8 * frame_rate) >= len(frame_rms):
            continue
        peak_val = float(np.max(frame_rms[p : min(len(frame_rms), p + 4)])) + 1e-9
        # Direct window: 0..64ms; Ambient/tail window: 120..500ms
        d_e = float(np.mean(frame_rms[p : p + 4]))
        a_e = float(np.mean(frame_rms[p + 7 : min(len(frame_rms), p + 30)]))
        direct_energies.append(d_e)
        ambient_energies.append(a_e)
        # Measure time until envelope drops -18 dB (or fraction 0.126)
        thresh = peak_val * 0.18
        tail_slice = frame_rms[p + 2 : min(len(frame_rms), p + int(2.5 * frame_rate))]
        below = np.where(tail_slice <= thresh)[0]
        if len(below) > 0:
            decay_secs.append(float(below[0] + 2) / frame_rate)
        else:
            decay_secs.append(min(2.5, len(tail_slice) / frame_rate))

    sustain_est_sec = round(float(np.median(decay_secs)), 3) if decay_secs else 0.45
    direct_ambient_ratio = round(
        float(np.clip(np.mean(direct_energies) / (np.mean(ambient_energies) + 1e-9), 0.1, 12.0)), 2
    ) if direct_energies else 1.5

    # Distortion / saturation roughness proxy: upper-mid spectral flatness + upper harmonic energy ratio
    hi_mask = (f16 >= 1800.0) & (f16 <= 7500.0)
    hi_pow = mag16[hi_mask] ** 2 + 1e-18
    geo_mean = np.exp(np.mean(np.log(hi_pow), axis=0))
    arith_mean = np.mean(hi_pow, axis=0)
    flatness = float(np.median(geo_mean / (arith_mean + 1e-18)))
    hi_share = (freq_balance["presence_2k_6k"] + freq_balance["air_6k_20k"]) / 100.0
    distortion_est = round(float(np.clip(flatness * 1.45 + hi_share * 0.55 - 0.12, 0.0, 1.0)), 3)

    # Low-end character classification
    low_tot = freq_balance["sub_20_60"] + freq_balance["bass_60_200"]
    if freq_balance["sub_20_60"] >= 14.0:
        low_end_profile = "sub_heavy"
    elif low_tot >= 32.0 and transient_strength >= 0.48:
        low_end_profile = "tight_punch"
    elif low_tot >= 24.0:
        low_end_profile = "warm_full_low"
    else:
        low_end_profile = "light_low_end"

    # Stereo & Mid-Side spatial measurements
    left, right = stereo[:, 0], stereo[:, 1]
    lr_denom = float(np.sqrt((left @ left) * (right @ right))) + 1e-12
    lr_corr = round(float(np.clip((left @ right) / lr_denom, -1.0, 1.0)), 3)
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = float(np.sqrt(np.mean(mid * mid)))
    side_rms = float(np.sqrt(np.mean(side * side)))
    mid_db = round(20.0 * math.log10(max(mid_rms, 1e-9)), 2)
    side_db = round(20.0 * math.log10(max(side_rms, 1e-9)), 2)
    side_to_mid_db = round(side_db - mid_db, 2)
    stereo_width = round(float(np.clip(side_rms / (mid_rms + 1e-12), 0.0, 1.5)), 3)

    freq_width = {
        "low_20_250": _band_stereo_width(left, right, sr, 20.0, 250.0),
        "mid_250_2500": _band_stereo_width(left, right, sr, 250.0, 2500.0),
        "high_2500_20k": _band_stereo_width(left, right, sr, 2500.0, 18000.0),
    }

    # Estimate Reverb Tail RT60-like decay proxy from side-channel ambient energy + envelope decay
    reverb_tail_est = round(
        float(np.clip(sustain_est_sec * (0.55 + 0.65 * min(1.0, stereo_width)) * (1.25 / max(0.5, min(3.0, direct_ambient_ratio))), 0.08, 4.5)),
        2,
    )

    # Detect rhythmic delay repetition candidate (between 90ms and 750ms) via onset-flux autocorrelation
    delay_candidate: dict[str, Any] | None = None
    if len(flux_norm) > 64:
        fc = flux_norm - np.mean(flux_norm)
        f_en = float(fc @ fc)
        if f_en > 1e-9:
            ac = signal.correlate(fc, fc, mode="full", method="fft")[len(fc) - 1 :] / f_en
            lo_lag = max(3, int(round(0.09 * frame_rate)))
            hi_lag = min(len(ac) - 2, int(round(0.75 * frame_rate)))
            if hi_lag > lo_lag + 2:
                sec_per_beat = 60.0 / max(30.0, float(bpm))
                best_lag = int(lo_lag + np.argmax(ac[lo_lag:hi_lag]))
                best_val = float(ac[best_lag])
                if best_val >= 0.24:
                    lag_sec = best_lag / frame_rate
                    ratio_beats = lag_sec / sec_per_beat
                    # Map to nearest musical subdivision
                    subdivs = [("1/16", 0.25), ("1/8", 0.5), ("1/8 dotted", 0.75), ("1/4", 1.0), ("1/4 triplet", 0.667)]
                    best_sub, _ = min(subdivs, key=lambda kv: abs(kv[1] - ratio_beats))
                    delay_candidate = {
                        "delayMs": round(lag_sec * 1000.0, 1),
                        "nearestSubdivision": best_sub,
                        "correlation": round(best_val, 3),
                        "isEstimate": True,
                    }

    if direct_ambient_ratio >= 2.2 and stereo_width < 0.28:
        rel_dist = "close_dry"
    elif reverb_tail_est >= 1.25 or stereo_width >= 0.45:
        rel_dist = "distant_ambient"
    else:
        rel_dist = "medium_room"

    # Honest Sound Design Starting-Point Hints (never claiming original plugin settings!)
    hints: list[dict[str, Any]] = []
    if freq_balance["low_mid_200_500"] > 28.0:
        hints.append({"fx": "parametric_eq", "reason": "Warm/dense 200–500 Hz low-mid energy detected; gentle low-mid shaping starting point."})
    if centroid_hz < 1100.0 and role in ("other", "master"):
        hints.append({"fx": "parametric_eq", "reason": "Dark spectral centroid (< 1.1 kHz); warm low-pass / smooth top-end character."})
    elif centroid_hz > 2600.0:
        hints.append({"fx": "parametric_eq", "reason": "Bright spectral balance (> 2.6 kHz); airy high-shelf presence."})
    if rel_dist == "distant_ambient":
        hints.append({"fx": "reverb", "reason": f"Spacious tail (~{reverb_tail_est}s est.) & wide stereo ({stereo_width}); start with Hall/Plate reverb."})
    elif rel_dist == "medium_room":
        hints.append({"fx": "reverb", "reason": f"Balanced room ambience (~{reverb_tail_est}s est.); start with Studio Room reverb."})
    if delay_candidate:
        hints.append({"fx": "delay", "reason": f"Rhythmic echo candidate near {delay_candidate['nearestSubdivision']} ({delay_candidate['delayMs']} ms)."})
    if distortion_est >= 0.48 and role in ("other", "bass"):
        hints.append({"fx": "saturation_or_amp", "reason": "Elevated upper-harmonic roughness estimate; consider gentle saturation or crunch amp."})

    return {
        "role": role,
        "active": rms_db > -48.0,
        "coverage": coverage,
        "soundProfile": {
            "rmsDbfs": rms_db,
            "peakDbfs": peak_db,
            "crestFactorDb": crest_db,
            "frequencyBalancePct": freq_balance,
            "spectralCentroidHz": centroid_hz,
            "spectralRolloff85Hz": rolloff_85_hz,
            "harmonicRatio": harmonic_ratio,
            "percussiveRatio": percussive_ratio,
            "transientStrength": transient_strength,
            "attackCharacter": attack_char,
            "sustainEstimateSec": sustain_est_sec,
            "dynamicRangeDb": dyn_range_db,
            "distortionRoughnessEstimate": distortion_est,
            "lowEndProfile": low_end_profile,
            "stereoWidth": stereo_width,
        },
        "spatialProfile": {
            "directAmbientRatio": direct_ambient_ratio,
            "reverbTailSecEstimate": reverb_tail_est,
            "stereoCorrelation": lr_corr,
            "midDbfs": mid_db,
            "sideDbfs": side_db,
            "sideToMidDb": side_to_mid_db,
            "freqDependentWidth": freq_width,
            "delayRepetitionCandidate": delay_candidate,
            "relativeDistance": rel_dist,
        },
        "suggestedSoundDesignHints": hints,
        "honestyDisclaimer": "음향 실측 기반 사운드·공간감 프로필이며, 원본 곡의 정확한 EQ/컴프레서/리버브 플러그인 파라미터를 역산한 값이 아닙니다.",
    }


def analyze_bass_performance(
    bass_notes: list[dict[str, Any]],
    *,
    drum_notes: list[dict[str, Any]] | None = None,
    bpb: float = 4.0,
    duration_sec: float = 0.0,
    bpm: float = 120.0,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build full-length Bar-by-Bar Bass Performance analysis: timing, durations, rests, octave jumps, slides & kick interaction."""
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    total_bars = max(1, int(math.ceil(duration_sec / max(0.5, sec_per_beat * bpb)))) if duration_sec > 0 else 1
    if bass_notes:
        max_b = max(float(n.get("quantizedStartBeat", n.get("startBeat", 0.0))) + float(n.get("quantizedDurationBeats", n.get("durationBeats", 0.25))) for n in bass_notes)
        total_bars = max(total_bars, int(math.ceil(max_b / max(1.0, bpb))))

    sorted_notes = sorted(bass_notes, key=lambda x: float(x.get("startBeat", 0.0)))
    kick_beats = [
        float(d.get("startBeat", 0.0))
        for d in (drum_notes or [])
        if int(d.get("pitch", d.get("midiPitch", 0))) == 36
    ]

    enriched: list[dict[str, Any]] = []
    octave_jumps = 0
    slide_candidates = 0
    syncopated_count = 0
    kick_aligned_count = 0

    for idx, n in enumerate(sorted_notes):
        sb = float(n.get("startBeat", 0.0))
        qsb = float(n.get("quantizedStartBeat", round(sb * 4.0) / 4.0))
        dur = max(0.0625, float(n.get("durationBeats", 0.25)))
        qdur = max(0.0625, float(n.get("quantizedDurationBeats", round(dur * 4.0) / 4.0 or 0.25)))
        pitch = int(n.get("pitch", 40))
        vel = int(n.get("velocity", 96))
        bar_idx = int(qsb // bpb) + 1
        beat_in_bar = round((qsb % bpb) + 1.0, 4)

        rest_after = 0.0
        is_oct_jump = False
        is_slide = False
        if idx + 1 < len(sorted_notes):
            nxt = sorted_notes[idx + 1]
            nxt_sb = float(nxt.get("startBeat", sb + dur))
            rest_after = round(max(0.0, nxt_sb - (sb + dur)), 4)
            pitch_diff = abs(int(nxt.get("pitch", pitch)) - pitch)
            if pitch_diff == 12:
                is_oct_jump = True
                octave_jumps += 1
            elif 1 <= pitch_diff <= 2 and rest_after <= 0.04:
                is_slide = True
                slide_candidates += 1

        is_sync = abs(qsb - round(qsb)) > 0.08
        if is_sync:
            syncopated_count += 1

        kick_locked = any(abs(sb - kb) <= 0.14 for kb in kick_beats)
        if kick_locked:
            kick_aligned_count += 1

        enriched.append(
            {
                **n,
                "barIndex": bar_idx,
                "beatInBar": beat_in_bar,
                "quantizedStartBeat": round(qsb, 4),
                "quantizedDurationBeats": round(qdur, 4),
                "restAfterBeats": rest_after,
                "isOctaveJump": is_oct_jump,
                "slideCandidate": is_slide,
                "isSyncopated": is_sync,
                "kickAligned": kick_locked,
            }
        )

    # Bar-by-bar variation map & repeated riff detection
    bar_summaries: list[dict[str, Any]] = []
    bar_sigs: dict[int, tuple[float, ...]] = {}
    for b in range(1, total_bars + 1):
        b_notes = [x for x in enriched if x["barIndex"] == b]
        sig = tuple(round((x["quantizedStartBeat"] % bpb) * 4.0) / 4.0 for x in b_notes)
        bar_sigs[b] = sig
        matched_prev = next((pb for pb in range(1, b) if bar_sigs[pb] == sig and len(sig) > 0), None)
        bar_summaries.append(
            {
                "barIndex": b,
                "noteCount": len(b_notes),
                "syncopatedCount": sum(1 for x in b_notes if x["isSyncopated"]),
                "isSilent": len(b_notes) == 0,
                "matchesBarIndex": matched_prev,
            }
        )

    non_empty_sigs = [s for s in bar_sigs.values() if s]
    unique_riffs = len(set(non_empty_sigs))
    repeated_bars = [bs["barIndex"] for bs in bar_summaries if bs["matchesBarIndex"] is not None]

    return {
        "totalBars": total_bars,
        "noteCount": len(enriched),
        "pitchMin": min((x["pitch"] for x in enriched), default=None),
        "pitchMax": max((x["pitch"] for x in enriched), default=None),
        "syncopationScore": round(syncopated_count / max(1, len(enriched)), 3),
        "octaveJumpCount": octave_jumps,
        "slideCandidateCount": slide_candidates,
        "kickInteractionScore": round(kick_aligned_count / max(1, len(enriched)), 3) if kick_beats else None,
        "uniqueBarRhythmCount": unique_riffs,
        "repeatedRiffBars": repeated_bars,
        "variationMap": bar_summaries,
        "coverage": coverage,
        "notes": enriched,
    }


def classify_instruments_honestly(
    *,
    stem_analyses: dict[str, dict[str, Any]],
    drum_result: dict[str, Any],
    bass_result: dict[str, Any],
    melody_result: dict[str, Any],
    other_result: dict[str, Any],
    dsp_elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify reference audio sources strictly into the 5 honest Phase 03.2.1 categories.

    Categories:
      - `Separated Stem`
      - `Transcribed Instrument`
      - `Estimated Instrument`
      - `Mixed Harmonic Content`
      - `Unknown`
    """
    out: list[dict[str, Any]] = []
    if stem_analyses:
        for role in ("drums", "bass", "other", "vocals"):
            st = stem_analyses.get(role)
            if not st:
                continue
            active = bool(st.get("active"))
            if role == "drums":
                out.append(
                    {
                        "role": "drums",
                        "label": "Drums Stem (Separated)",
                        "classification": "Separated Stem" if active else "Unknown",
                        "active": active,
                        "transcribedNoteCount": len(drum_result.get("quantizedMidiNotes", [])),
                        "confidence": 0.88 if active else 0.15,
                        "note": "Demucs 분리 드럼 스템 및 멀티밴드 타격 채보 결과입니다 (원본 스튜디오 멀티트랙 아님).",
                    }
                )
            elif role == "bass":
                out.append(
                    {
                        "role": "bass",
                        "label": "Bass Stem (Separated & Transcribed)",
                        "classification": "Transcribed Instrument" if (active and bass_result.get("noteCount", 0) > 0) else ("Separated Stem" if active else "Unknown"),
                        "active": active,
                        "transcribedNoteCount": int(bass_result.get("noteCount", 0)),
                        "confidence": round(float(bass_result.get("meanConfidence", 0.72)), 3) if active else 0.12,
                        "note": "분리된 베이스 스템에서 Basic Pitch로 채보된 저역 연주입니다.",
                    }
                )
            elif role == "other":
                # NEVER claim Other stem is isolated guitar/synth!
                out.append(
                    {
                        "role": "other",
                        "label": "Harmonic Mix (Guitar / Keys / Synth / Pad — Mixed)",
                        "classification": "Mixed Harmonic Content" if active else "Unknown",
                        "active": active,
                        "transcribedNoteCount": int(other_result.get("noteCount", 0)),
                        "melodyNoteCount": int(melody_result.get("noteCount", 0)),
                        "confidence": round(float(other_result.get("meanConfidence", 0.55)), 3) if active else 0.1,
                        "note": "Other 스템은 기타·건반·신스·패드가 혼합된 하모닉 콘텐츠이며 개별 스튜디오 악기로 단정하지 않습니다.",
                    }
                )
            elif role == "vocals":
                out.append(
                    {
                        "role": "vocals",
                        "label": "Vocals Stem (Separated)",
                        "classification": "Separated Stem" if active else "Unknown",
                        "active": active,
                        "transcribedNoteCount": 0,
                        "confidence": 0.75 if active else 0.05,
                        "note": "Demucs 분리 보컬 스템입니다." if active else "유의미한 보컬 에너지가 감지되지 않았습니다 (인스트루멘털 가능성).",
                    }
                )
    else:
        for el in dsp_elements:
            is_conf = el.get("status") == "estimated"
            out.append(
                {
                    "role": str(el.get("name", "unknown")).lower().replace(" ", "_")[:24],
                    "label": str(el.get("name", "Unknown")),
                    "classification": "Estimated Instrument" if is_conf else "Unknown",
                    "active": is_conf,
                    "transcribedNoteCount": 0,
                    "confidence": float(el.get("confidence", 0.0)),
                    "note": "스템 분리 없이 DSP 스펙트럼/HPSS로 보수 추정된 항목입니다.",
                }
            )
    return out
