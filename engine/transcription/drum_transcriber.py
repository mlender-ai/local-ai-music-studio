"""Full-Length Multi-Band Drum Performance, Ghost-Note & Bar-by-Bar Variation Transcriber (Phase 03.2.1).

Upgrades over Phase 03.2:
- Full-length coverage up to 600s with explicit `analysisCoverage` (`originalDurationSec`, `analyzedDurationSec`,
  `coveragePct`, `isComplete`, `truncated`) — NEVER silently truncates drum hits to 1200 notes or 2 bars!
- Expanded 11-class percussion classification:
    kick (36), snare (38), rimshot (37), clap (39), closed_hat (42), open_hat (46),
    ride (51), crash (49), tom (45/48), shaker (70), percussion (56), plus `isGhostNote` flag!
- Full canonical Drum Event Schema on BOTH `rawMidiNotes` and `quantizedMidiNotes`:
    eventId, timeSeconds, startBeat, barIndex, beatInBar, drumClass, midiPitch, velocityEstimate,
    duration, timingDeviationMs, confidence, sourceStem, isGhostNote
- Bar-by-bar `variationMap`: per-bar hit breakdown, fills, breakdowns (drum dropouts), cymbal re-entries,
  pattern hashes, repeated vs unique exception bars!
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

from engine.daw_workspace.schema import make_id

DRUM_CLASS_TO_PITCH: dict[str, int] = {
    "kick": 36,
    "rimshot": 37,
    "snare": 38,
    "clap": 39,
    "closed_hat": 42,
    "tom": 45,
    "open_hat": 46,
    "crash": 49,
    "ride": 51,
    "percussion": 56,
    "shaker": 70,
}


def _load_mono_with_coverage(path: Path, max_sec: float = 600.0) -> tuple[np.ndarray, int, dict[str, Any]]:
    info = sf.info(str(path))
    orig_sec = float(info.frames) / max(1, int(info.samplerate))
    max_frames = int(min(info.frames, max_sec * info.samplerate))
    data, sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    analyzed_sec = len(data) / max(1, int(sr))
    mono = data.mean(axis=1).astype(np.float64)
    coverage = {
        "originalDurationSec": round(orig_sec, 3),
        "analyzedDurationSec": round(analyzed_sec, 3),
        "coveragePct": round(min(100.0, (analyzed_sec / max(1e-6, orig_sec)) * 100.0), 2),
        "isComplete": analyzed_sec >= orig_sec - 0.15,
        "truncated": analyzed_sec < orig_sec - 0.15,
    }
    return np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0), int(sr), coverage


def _band_flux(mag: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs <= hi)
    if not np.any(mask):
        return np.zeros(max(1, mag.shape[1] - 1), dtype=np.float64)
    sub = mag[mask]
    return np.maximum(np.diff(sub, axis=1), 0.0).sum(axis=0)


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
    peaks, props = signal.find_peaks(norm, height=thresh, distance=dist, prominence=thresh * 0.30)
    return [(float(p) / frame_rate, float(h)) for p, h in zip(peaks, props["peak_heights"])]


def transcribe_drum_groove(
    audio_path: Path,
    *,
    bpm: float = 120.0,
    beat_offset_sec: float = 0.0,
    bpb: float = 4.0,
    source_kind: str = "demucs_drums_stem",
    max_sec: float = 600.0,
) -> dict[str, Any]:
    """Extract full-length bar-by-bar Drum Performance (11 classes + ghost notes), Variation Map & Groove Profile."""
    mono, sr, coverage = _load_mono_with_coverage(audio_path, max_sec=max_sec)
    duration_sec = len(mono) / max(1, sr)
    rms_all = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
    if rms_all < 1e-4 or duration_sec < 0.4:
        return {
            "sourceKind": source_kind,
            "hasDrums": False,
            "analysisCoverage": coverage,
            "rmsDbfs": round(20.0 * math.log10(max(rms_all, 1e-9)), 2),
            "hitCounts": {k: 0 for k in ("kick", "snare", "rimshot", "clap", "closedHat", "openHat", "ride", "crash", "tom", "shaker", "percussion", "ghostNotes")},
            "swingRatio": 0.5,
            "grooveFeel": "straight",
            "syncopationScore": 0.0,
            "meanMicrotimingMs": 0.0,
            "microtimingStdMs": 0.0,
            "accentGrid16": [0.0] * 16,
            "fillBars": [],
            "breakdownBars": [],
            "cymbalReentryBars": [],
            "patternRepetitionBars": 1,
            "variationMap": {"totalBars": 0, "bars": [], "uniquePatternCount": 0, "repetitionRatio": 0.0, "hasBarByBarVariation": False},
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

    nperseg = 1024
    hop = 220  # ~100.2 Hz frame rate (~10 ms resolution)
    freqs, _, zxx = signal.stft(mono, fs=sr, nperseg=nperseg, noverlap=nperseg - hop, boundary=None)
    mag = np.abs(zxx)
    if source_kind != "demucs_drums_stem":
        h_mag = ndimage.median_filter(mag, size=(1, 17))
        p_mag = ndimage.median_filter(mag, size=(17, 1))
        mask_p = (p_mag ** 2) / (p_mag ** 2 + h_mag ** 2 + 1e-12)
        mag = mag * mask_p

    frame_rate = sr / float(hop)
    kick_flux = _band_flux(mag, freqs, 35.0, 145.0)
    snare_flux = _band_flux(mag, freqs, 180.0, 2800.0)
    hat_flux = _band_flux(mag, freqs, 4800.0, 10800.0)
    tom_flux = _band_flux(mag, freqs, 110.0, 520.0)

    kicks = _pick_band_onsets(kick_flux, frame_rate, min_dist_sec=0.12, sigma_mult=1.05, floor_frac=0.16)
    # Slightly lower floor on snare so genuine soft ghost notes are captured too
    snares_raw = _pick_band_onsets(snare_flux, frame_rate, min_dist_sec=0.10, sigma_mult=0.95, floor_frac=0.13)
    hats_raw = _pick_band_onsets(hat_flux, frame_rate, min_dist_sec=0.07, sigma_mult=0.82, floor_frac=0.10)
    toms_raw = _pick_band_onsets(tom_flux, frame_rate, min_dist_sec=0.11, sigma_mult=1.45, floor_frac=0.22)

    # Spectral masks for sub-classification (snare vs rimshot vs clap; hat vs open hat vs ride vs crash vs shaker)
    kick_norm = kick_flux / (np.max(kick_flux) + 1e-9)
    snare_norm = snare_flux / (np.max(snare_flux) + 1e-9)
    low_body_mask = (freqs >= 160.0) & (freqs <= 420.0)
    mid_crack_mask = (freqs >= 750.0) & (freqs <= 3200.0)
    hi_hat_mask = (freqs >= 4800.0) & (freqs <= 10800.0)
    ride_mask = (freqs >= 2800.0) & (freqs <= 6200.0)

    low_body_e = mag[low_body_mask].mean(axis=0) if np.any(low_body_mask) else np.zeros(mag.shape[1])
    mid_crack_e = mag[mid_crack_mask].mean(axis=0) if np.any(mid_crack_mask) else np.zeros(mag.shape[1])
    hi_energy = mag[hi_hat_mask].mean(axis=0) if np.any(hi_hat_mask) else np.zeros(mag.shape[1])
    ride_energy = mag[ride_mask].mean(axis=0) if np.any(ride_mask) else np.zeros(mag.shape[1])

    # Classify snare family: snare (38), rimshot (37), clap (39)
    snare_events: list[tuple[float, float, str, int]] = []
    for t_s, strength in snares_raw:
        f_idx = min(len(kick_norm) - 1, int(round(t_s * frame_rate)))
        coincides_kick = any(abs(t_s - kt) < 0.032 for kt, _ in kicks)
        if coincides_kick and kick_norm[f_idx] > snare_norm[f_idx] * 1.35:
            continue
        f0 = min(len(low_body_e) - 1, int(round(t_s * frame_rate)))
        body = float(np.mean(low_body_e[f0 : min(len(low_body_e), f0 + 4)])) + 1e-9
        crack = float(np.mean(mid_crack_e[f0 : min(len(mid_crack_e), f0 + 4)])) + 1e-9
        hi_sp = float(np.mean(hi_energy[f0 : min(len(hi_energy), f0 + 5)])) + 1e-9
        tail_crack = float(np.mean(mid_crack_e[min(len(mid_crack_e) - 1, f0 + 4) : min(len(mid_crack_e), f0 + 10)]))
        if crack / body > 2.4 and tail_crack / crack < 0.25 and hi_sp / crack < 0.35:
            snare_events.append((t_s, strength, "rimshot", 37))
        elif hi_sp / body > 1.45 and tail_crack / crack >= 0.36:
            snare_events.append((t_s, strength, "clap", 39))
        else:
            snare_events.append((t_s, strength, "snare", 38))

    # Classify high-band cymbals & shakers: closed_hat (42), open_hat (46), ride (51), crash (49), shaker (70)
    cymbal_events: list[tuple[float, float, str, int, float]] = []
    for t_s, strength in hats_raw:
        f0 = min(len(hi_energy) - 1, int(round(t_s * frame_rate)))
        atk_e = float(np.mean(hi_energy[f0 : min(len(hi_energy), f0 + 4)])) + 1e-9
        med_tail = float(np.mean(hi_energy[min(len(hi_energy) - 1, f0 + 7) : min(len(hi_energy), f0 + 18)]))
        long_tail = float(np.mean(hi_energy[min(len(hi_energy) - 1, f0 + 25) : min(len(hi_energy), f0 + 45)]))
        ride_ratio = float(np.mean(ride_energy[f0 : min(len(ride_energy), f0 + 6)])) / atk_e
        if strength >= 0.58 and (long_tail / atk_e) >= 0.34:
            cymbal_events.append((t_s, strength, "crash", 49, 1.25))
        elif (med_tail / atk_e) >= 0.40:
            if ride_ratio >= 1.35 and (long_tail / atk_e) >= 0.20:
                cymbal_events.append((t_s, strength, "ride", 51, 0.45))
            else:
                cymbal_events.append((t_s, strength, "open_hat", 46, 0.35))
        elif strength < 0.28 and (med_tail / atk_e) >= 0.24:
            cymbal_events.append((t_s, strength, "shaker", 70, 0.14))
        else:
            cymbal_events.append((t_s, strength, "closed_hat", 42, 0.16))

    # Keep tom/percussion hits distinct from kick/snare onsets
    tom_perc_events: list[tuple[float, float, str, int]] = []
    for t_s, strength in toms_raw:
        if any(abs(t_s - kt) < 0.04 for kt, _ in kicks) or any(abs(t_s - st) < 0.04 for st, _, _, _ in snare_events):
            continue
        f0 = min(len(low_body_e) - 1, int(round(t_s * frame_rate)))
        body = float(np.mean(low_body_e[f0 : min(len(low_body_e), f0 + 5)])) + 1e-9
        crack = float(np.mean(mid_crack_e[f0 : min(len(mid_crack_e), f0 + 5)])) + 1e-9
        if body >= crack * 0.9:
            tom_perc_events.append((t_s, strength, "tom", 45))
        else:
            tom_perc_events.append((t_s, strength, "percussion", 56))

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    raw_notes: list[dict[str, Any]] = []
    quant_notes: list[dict[str, Any]] = []
    micro_offsets_ms: list[float] = []
    offbeat_phases: list[float] = []
    accent_sums = np.zeros(16, dtype=np.float64)
    accent_cnts = np.zeros(16, dtype=np.float64)

    def add_hit(t_sec: float, strength: float, pitch: int, dur_beats: float, drum_class: str) -> None:
        raw_b = max(0.0, (t_sec - beat_offset_sec) / sec_per_beat)
        q_b = round(round(raw_b * 4.0) / 4.0, 4)  # 16th-note grid
        offset_ms = round((raw_b - q_b) * sec_per_beat * 1000.0, 2)
        if abs(offset_ms) <= 65.0:
            micro_offsets_ms.append(offset_ms)
        vel = max(28, min(125, int(round(36 + strength * 88))))
        conf = round(float(np.clip(strength, 0.15, 0.99)), 3)

        step16 = int(round((q_b % bpb) * 4.0)) % 16
        accent_sums[step16] += vel / 127.0
        accent_cnts[step16] += 1.0

        frac = raw_b - math.floor(raw_b)
        if 0.35 <= frac <= 0.72:
            offbeat_phases.append(frac)

        bar_idx_raw = int(raw_b // bpb) + 1
        bar_idx_q = int(q_b // bpb) + 1
        beat_in_bar_raw = round((raw_b % bpb) + 1.0, 4)
        beat_in_bar_q = round((q_b % bpb) + 1.0, 4)
        is_main_backbeat = abs((q_b % bpb) - 1.0) < 0.08 or abs((q_b % bpb) - 3.0) < 0.08
        is_ghost = bool(drum_class in ("snare", "rimshot", "closed_hat") and vel < 68 and not is_main_backbeat)

        ev_id = make_id("drhit")
        common = {
            "eventId": ev_id,
            "timeSeconds": round(t_sec, 4),
            "onsetSec": round(t_sec, 4),
            "drumClass": drum_class,
            "role": drum_class,
            "pitch": pitch,
            "midiPitch": pitch,
            "velocity": vel,
            "velocityEstimate": vel,
            "duration": round(dur_beats * sec_per_beat, 4),
            "durationBeats": dur_beats,
            "timingDeviationMs": offset_ms,
            "microtimingOffsetMs": offset_ms,
            "confidence": conf,
            "sourceStem": source_kind,
            "isGhostNote": is_ghost,
        }
        raw_notes.append(
            {
                "id": make_id("note"),
                "startBeat": round(raw_b, 4),
                "barIndex": bar_idx_raw,
                "beatInBar": beat_in_bar_raw,
                **common,
            }
        )
        quant_notes.append(
            {
                "id": make_id("note"),
                "startBeat": q_b,
                "barIndex": bar_idx_q,
                "beatInBar": beat_in_bar_q,
                **common,
            }
        )

    for t_s, st in kicks:
        add_hit(t_s, st, 36, 0.35, "kick")
    for t_s, st, dcls, pitch in snare_events:
        add_hit(t_s, st, pitch, 0.28, dcls)
    for t_s, st, dcls, pitch, dur_b in cymbal_events:
        add_hit(t_s, st, pitch, dur_b, dcls)
    for t_s, st, dcls, pitch in tom_perc_events:
        add_hit(t_s, st, pitch, 0.24, dcls)

    # Deduplicate quantized collisions on identical (pitch, 16th step) keeping higher velocity
    dedup_q: dict[tuple[int, float], dict[str, Any]] = {}
    for n in quant_notes:
        key = (n["pitch"], round(n["startBeat"], 2))
        if key not in dedup_q or n["velocity"] > dedup_q[key]["velocity"]:
            dedup_q[key] = n
    quant_notes = sorted(dedup_q.values(), key=lambda x: (x["startBeat"], x["pitch"]))
    raw_notes.sort(key=lambda x: (x["startBeat"], x["pitch"]))

    swing_ratio = round(float(np.median(offbeat_phases)), 3) if len(offbeat_phases) >= 6 else 0.50
    groove_feel = "swung" if swing_ratio >= 0.555 else ("pushed" if swing_ratio <= 0.455 else "straight")

    ks_hits = [n for n in quant_notes if n["pitch"] in (36, 37, 38, 39)]
    offgrid_ks = [n for n in ks_hits if abs(n["startBeat"] - round(n["startBeat"])) > 0.08]
    syncopation = round(len(offgrid_ks) / max(1, len(ks_hits)), 3)

    accent_avg = accent_sums / np.maximum(1.0, accent_cnts)
    accent_max = float(np.max(accent_avg)) if np.max(accent_avg) > 0 else 1.0
    accent_grid_16 = [round(float(v / accent_max), 3) for v in accent_avg]

    # Build FULL bar-by-bar Variation Map (fills, breakdowns, cymbal re-entries, pattern hashes & similarity!)
    total_bars = max(1, int(math.ceil(duration_sec / max(0.25, sec_per_beat * bpb))))
    bar_vecs = np.zeros((total_bars, 16), dtype=np.float64)
    bar_notes_map: dict[int, list[dict[str, Any]]] = {b: [] for b in range(total_bars)}
    for n in quant_notes:
        b_idx = int(n["startBeat"] // bpb)
        if 0 <= b_idx < total_bars:
            bar_notes_map[b_idx].append(n)
            s_idx = int(round((n["startBeat"] % bpb) * 4.0)) % 16
            bar_vecs[b_idx, s_idx] += 1.0 if n["pitch"] in (36, 38, 39) else 0.4

    tail_counts = []
    bar_hit_totals = []
    for bar in range(total_bars):
        b_hits = bar_notes_map[bar]
        bar_hit_totals.append(len(b_hits))
        b0 = bar * bpb + max(0.0, bpb - 1.5)
        b1 = (bar + 1) * bpb
        tail_cnt = sum(1 for n in b_hits if b0 <= n["startBeat"] < b1 and n["pitch"] in (37, 38, 39, 45, 48, 56))
        tail_counts.append(tail_cnt)

    nonzero_totals = [c for c in bar_hit_totals if c > 0]
    med_hits = float(np.median(nonzero_totals)) if nonzero_totals else 0.0
    med_tail = float(np.median(tail_counts)) if tail_counts else 0.0

    variation_bars: list[dict[str, Any]] = []
    seen_hashes: dict[str, int] = {}
    fill_bars: list[int] = []
    breakdown_bars: list[int] = []
    cymbal_reentry_bars: list[int] = []
    prev_was_breakdown = False

    for bar in range(total_bars):
        b_hits = bar_notes_map[bar]
        bar_num = bar + 1
        k_cnt = sum(1 for n in b_hits if n["pitch"] == 36)
        s_cnt = sum(1 for n in b_hits if n["pitch"] in (37, 38, 39))
        h_cnt = sum(1 for n in b_hits if n["pitch"] in (42, 46, 70))
        cym_cnt = sum(1 for n in b_hits if n["pitch"] in (49, 51))
        tp_cnt = sum(1 for n in b_hits if n["pitch"] in (45, 48, 56))
        ghost_cnt = sum(1 for n in b_hits if n.get("isGhostNote"))

        # Exact normalized bar pattern signature (pitch + 16th position)
        pat_tokens = sorted((int(n["pitch"]), int(round((n["startBeat"] % bpb) * 4.0)) % 16) for n in b_hits)
        sig_hash = hashlib.sha1(str(pat_tokens).encode("utf-8")).hexdigest()[:8] if pat_tokens else "empty"
        matched_bar = seen_hashes.get(sig_hash)
        if sig_hash != "empty" and sig_hash not in seen_hashes:
            seen_hashes[sig_hash] = bar_num

        is_fill = bool(tail_counts[bar] >= max(3, med_tail * 1.6))
        is_breakdown = bool(med_hits >= 4.0 and (len(b_hits) <= max(1, int(med_hits * 0.25)) or (k_cnt == 0 and s_cnt == 0 and len(b_hits) < med_hits * 0.5)))
        has_downbeat_crash = any(n["pitch"] == 49 and (n["startBeat"] % bpb) < 0.35 for n in b_hits)
        is_reentry = bool(has_downbeat_crash or (prev_was_breakdown and not is_breakdown and k_cnt > 0))
        prev_was_breakdown = is_breakdown

        if is_fill:
            fill_bars.append(bar_num)
        if is_breakdown:
            breakdown_bars.append(bar_num)
        if is_reentry:
            cymbal_reentry_bars.append(bar_num)

        sim_prev = 0.0
        if bar > 0:
            a, b = bar_vecs[bar - 1], bar_vecs[bar]
            na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
            if na > 0 and nb > 0:
                sim_prev = round(float((a @ b) / (na * nb)), 3)

        variation_bars.append(
            {
                "barIndex": bar_num,
                "totalHits": len(b_hits),
                "kickCount": k_cnt,
                "snareCount": s_cnt,
                "hatCount": h_cnt,
                "cymbalCount": cym_cnt,
                "tomPercCount": tp_cnt,
                "ghostNoteCount": ghost_cnt,
                "signatureHash": sig_hash,
                "isFill": is_fill,
                "isBreakdown": is_breakdown,
                "isCymbalReentry": is_reentry,
                "matchesBarIndex": matched_bar,
                "similarityToPrevBar": sim_prev,
            }
        )

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

    rep_scores = {1: _lag_sim(1), 2: _lag_sim(2), 4: _lag_sim(4), 8: _lag_sim(8)}
    pattern_rep_bars = max(rep_scores, key=lambda k: rep_scores[k]) if any(rep_scores.values()) else 1

    non_empty_bars = [vb for vb in variation_bars if vb["totalHits"] > 0]
    unique_pat_count = len({vb["signatureHash"] for vb in non_empty_bars})
    rep_ratio = round(1.0 - (unique_pat_count / max(1, len(non_empty_bars))), 3) if non_empty_bars else 0.0

    variation_map = {
        "totalBars": total_bars,
        "bars": variation_bars,
        "fillBars": fill_bars,
        "breakdownBars": breakdown_bars,
        "cymbalReentryBars": cymbal_reentry_bars,
        "uniquePatternCount": unique_pat_count,
        "repetitionRatio": rep_ratio,
        "hasBarByBarVariation": unique_pat_count > 1 or bool(fill_bars) or bool(breakdown_bars),
    }

    # Representative 2-bar summary template (for quick preview & reference mode ONLY — NEVER used to truncate locked mode!)
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
            "beatIn2Bar": round(n["startBeat"] - t2_start, 4),
            "durationBeats": n["durationBeats"],
            "role": n["role"],
            "drumClass": n["drumClass"],
            "microtimingOffsetMs": n["microtimingOffsetMs"],
            "isGhostNote": n["isGhostNote"],
        }
        for n in quant_notes
        if t2_start <= n["startBeat"] < t2_end
    ]
    template_1bar = [n for n in template_2bar if n["startBeat"] < bpb]

    hit_counts = {
        "kick": len(kicks),
        "snare": sum(1 for _, _, c, _ in snare_events if c == "snare"),
        "rimshot": sum(1 for _, _, c, _ in snare_events if c == "rimshot"),
        "clap": sum(1 for _, _, c, _ in snare_events if c == "clap"),
        "closedHat": sum(1 for _, _, c, _, _ in cymbal_events if c == "closed_hat"),
        "openHat": sum(1 for _, _, c, _, _ in cymbal_events if c == "open_hat"),
        "ride": sum(1 for _, _, c, _, _ in cymbal_events if c == "ride"),
        "crash": sum(1 for _, _, c, _, _ in cymbal_events if c == "crash"),
        "tom": sum(1 for _, _, c, _ in tom_perc_events if c == "tom"),
        "shaker": sum(1 for _, _, c, _, _ in cymbal_events if c == "shaker"),
        "percussion": sum(1 for _, _, c, _ in tom_perc_events if c == "percussion"),
        "ghostNotes": sum(1 for n in quant_notes if n.get("isGhostNote")),
    }

    return {
        "sourceKind": source_kind,
        "hasDrums": len(quant_notes) >= 4,
        "analysisCoverage": coverage,
        "totalBars": total_bars,
        "rmsDbfs": round(20.0 * math.log10(max(rms_all, 1e-9)), 2),
        "hitCounts": hit_counts,
        "swingRatio": swing_ratio,
        "grooveFeel": groove_feel,
        "syncopationScore": syncopation,
        "meanMicrotimingMs": round(float(np.mean(micro_offsets_ms)), 2) if micro_offsets_ms else 0.0,
        "microtimingStdMs": round(float(np.std(micro_offsets_ms)), 2) if micro_offsets_ms else 0.0,
        "accentGrid16": accent_grid_16,
        "fillBars": fill_bars,
        "breakdownBars": breakdown_bars,
        "cymbalReentryBars": cymbal_reentry_bars,
        "patternRepetitionBars": pattern_rep_bars,
        "patternRepetitionScores": {str(k): round(v, 3) for k, v in rep_scores.items()},
        "variationMap": variation_map,
        "rawMidiNotes": raw_notes,
        "quantizedMidiNotes": quant_notes,
        "patternTemplate1Bar": template_1bar,
        "patternTemplate2Bar": template_2bar,
    }
