"""Advanced 15-Quality Sub-Bar Chord Track, Passing Chord & Bass Inversion Analyzer (Phase 03.2.1).

Supports all 15 canonical chord qualities:
  Major, Minor, Dominant 7, Major 7, Minor 7, Sus2, Sus4, Add9, Diminished, Half-Diminished (m7b5),
  Augmented, 6th, 9th (9 / maj9 / m9), Power Chord (5), and Slash Chords (/BassNote).

Features:
- Operates on Demucs separated harmonic stems (`bass.wav` + `other.wav`) or full mix fallback
- Full-length coverage up to 600s (never truncates slices to 256!)
- 1-beat adaptive resolution inside Viterbi decoding to preserve genuine passing chords (`isPassing`)
  while smoothing jitter across sustained chords
- Top-3 ranked `candidates` per event for transparent user verification & 1-click correction
- Strict `N/C` / `uncertain` honesty on non-harmonic / percussive-only sections
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw_workspace.schema import make_id

NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
NOTE_TO_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# (suffix, quality, extension, interval_weights, parsimony_prior)
CHORD_TEMPLATES_SPEC: list[tuple[str, str, str | None, list[tuple[int, float]], float]] = [
    ("", "major", None, [(0, 1.0), (4, 0.85), (7, 0.90)], 0.032),
    ("m", "minor", None, [(0, 1.0), (3, 0.85), (7, 0.90)], 0.032),
    ("7", "dom7", "7", [(0, 1.0), (4, 0.82), (7, 0.84), (10, 0.72)], 0.022),
    ("maj7", "maj7", "maj7", [(0, 1.0), (4, 0.82), (7, 0.84), (11, 0.72)], 0.022),
    ("m7", "min7", "7", [(0, 1.0), (3, 0.82), (7, 0.84), (10, 0.72)], 0.022),
    ("sus2", "sus2", "sus2", [(0, 1.0), (2, 0.84), (7, 0.90)], 0.012),
    ("sus4", "sus4", "sus4", [(0, 1.0), (5, 0.84), (7, 0.90)], 0.012),
    ("add9", "add9", "add9", [(0, 1.0), (4, 0.82), (7, 0.84), (2, 0.70)], 0.010),
    ("dim", "dim", None, [(0, 1.0), (3, 0.86), (6, 0.86)], 0.010),
    ("m7b5", "half_dim", "m7b5", [(0, 1.0), (3, 0.82), (6, 0.82), (10, 0.74)], 0.008),
    ("aug", "aug", "aug", [(0, 1.0), (4, 0.86), (8, 0.86)], 0.008),
    ("6", "sixth", "6", [(0, 1.0), (4, 0.82), (7, 0.84), (9, 0.72)], 0.010),
    ("9", "dom9", "9", [(0, 1.0), (4, 0.78), (7, 0.80), (10, 0.68), (2, 0.68)], 0.006),
    ("maj9", "maj9", "maj9", [(0, 1.0), (4, 0.78), (7, 0.80), (11, 0.68), (2, 0.68)], 0.006),
    ("m9", "min9", "9", [(0, 1.0), (3, 0.78), (7, 0.80), (10, 0.68), (2, 0.68)], 0.006),
    ("5", "power", "5", [(0, 1.0), (7, 0.95)], 0.002),
]

SUPPORTED_CHORD_QUALITIES = [
    "major", "minor", "dom7", "maj7", "min7", "sus2", "sus4", "add9",
    "dim", "half_dim", "aug", "sixth", "dom9", "maj9", "min9", "power", "slash",
]


def parse_chord_metadata(symbol: str) -> dict[str, Any]:
    """Parse any standard chord symbol (including all 15 qualities + slash inversions) into structured metadata."""
    clean = symbol.strip()
    if clean.upper() in ("N/C", "NC", "NONE", "UNKNOWN", ""):
        return {"symbol": "N/C", "root": "C", "quality": "uncertain", "extension": None, "bassNote": None}

    bass_note: str | None = None
    if "/" in clean:
        main_part, bass_part = clean.split("/", 1)
        clean = main_part.strip()
        m_bass = re.match(r"^([A-G][#b]?)$", bass_part.strip())
        if m_bass:
            bass_note = m_bass.group(1)

    m = re.match(r"^([A-G][#b]?)(.*)$", clean)
    if not m:
        return {"symbol": symbol.strip() or "N/C", "root": "C", "quality": "uncertain", "extension": None, "bassNote": bass_note}
    root = m.group(1)
    qual_raw = m.group(2).strip()
    ql = qual_raw.lower()

    if "m7b5" in ql or "ø" in ql or "halfdim" in ql:
        quality, ext = "half_dim", "m7b5"
    elif "maj9" in ql:
        quality, ext = "maj9", "maj9"
    elif "maj7" in ql:
        quality, ext = "maj7", "maj7"
    elif "m9" in ql or "min9" in ql:
        quality, ext = "min9", "9"
    elif "m7" in ql or "min7" in ql:
        quality, ext = "min7", "7"
    elif "m6" in ql or "min6" in ql:
        quality, ext = "minor", "6"
    elif "aug" in ql or "+" in ql:
        quality, ext = "aug", "aug"
    elif "dim" in ql or "°" in ql:
        quality, ext = "dim", None
    elif "sus4" in ql:
        quality, ext = "sus4", "sus4"
    elif "sus2" in ql:
        quality, ext = "sus2", "sus2"
    elif "add9" in ql:
        quality, ext = "add9", "add9"
    elif ql == "5":
        quality, ext = "power", "5"
    elif ql.startswith("m") and not ql.startswith("maj"):
        quality, ext = "minor", None
    elif "13" in ql:
        quality, ext = "dom7", "13"
    elif "9" in ql:
        quality, ext = "dom9", "9"
    elif "7" in ql:
        quality, ext = "dom7", "7"
    elif "6" in ql:
        quality, ext = "sixth", "6"
    else:
        quality, ext = "major", None

    full_sym = f"{root}{qual_raw}" + (f"/{bass_note}" if bass_note else "")
    return {
        "symbol": full_sym,
        "root": root,
        "quality": quality,
        "extension": ext,
        "bassNote": bass_note,
    }


def _load_resampled_mono(path: Path, target_sr: int = 12000, max_sec: float = 600.0) -> tuple[np.ndarray, dict[str, Any]]:
    info = sf.info(str(path))
    orig_sec = float(info.frames) / max(1, int(info.samplerate))
    max_frames = int(min(info.frames, max_sec * info.samplerate))
    data, sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    analyzed_sec = len(data) / max(1, int(sr))
    mono = data.mean(axis=1).astype(np.float64)
    if sr != target_sr and len(mono) > 0:
        g = math.gcd(int(sr), target_sr)
        mono = signal.resample_poly(mono, target_sr // g, int(sr) // g)
    coverage = {
        "originalDurationSec": round(orig_sec, 3),
        "analyzedDurationSec": round(analyzed_sec, 3),
        "coveragePct": round(min(100.0, (analyzed_sec / max(1e-6, orig_sec)) * 100.0), 2),
        "isComplete": analyzed_sec >= orig_sec - 0.15,
        "truncated": analyzed_sec < orig_sec - 0.15,
    }
    return np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0), coverage


def _chroma_frames(mono: np.ndarray, sr: int, lo_hz: float, hi_hz: float) -> tuple[np.ndarray, np.ndarray]:
    if len(mono) < 4096:
        return np.zeros((12, 1), dtype=np.float64), np.array([0.0])
    freqs, times, zxx = signal.stft(mono, fs=sr, nperseg=4096, noverlap=2048, boundary=None)
    power = np.abs(zxx) ** 2
    valid = (freqs >= lo_hz) & (freqs <= hi_hz)
    vf = freqs[valid]
    vp = power[valid]
    c = np.zeros((12, vp.shape[1]), dtype=np.float64)
    midi_bins = np.round(69.0 + 12.0 * np.log2(vf / 440.0)).astype(int)
    pcs = midi_bins % 12
    for pc in range(12):
        m = pcs == pc
        if np.any(m):
            c[pc] = vp[m].sum(axis=0)
    c = np.log1p(c * 140.0)
    norms = np.linalg.norm(c, axis=0, keepdims=True)
    c = np.where(norms > 1e-9, c / (norms + 1e-9), 0.0)
    return c, times


def extract_chord_timeline(
    full_audio_path: Path,
    *,
    bpm: float = 120.0,
    beat_offset_sec: float = 0.0,
    key_hint: str = "F minor",
    source_reference_id: str | None = None,
    bass_stem_path: Path | None = None,
    other_stem_path: Path | None = None,
    slice_beats: float = 1.0,
) -> list[dict[str, Any]]:
    """Extract full-length 15-quality sub-bar Chord Track with top-3 candidates, passing chords, and slash inversions."""
    sr = 12000
    use_stems = bool(bass_stem_path and bass_stem_path.is_file() and other_stem_path and other_stem_path.is_file())
    if use_stems:
        bass_mono, _ = _load_resampled_mono(bass_stem_path, sr)  # type: ignore[arg-type]
        other_mono, _ = _load_resampled_mono(other_stem_path, sr)  # type: ignore[arg-type]
        n_len = max(len(bass_mono), len(other_mono))
        if len(bass_mono) < n_len:
            bass_mono = np.pad(bass_mono, (0, n_len - len(bass_mono)))
        if len(other_mono) < n_len:
            other_mono = np.pad(other_mono, (0, n_len - len(other_mono)))
        harm_mono = other_mono + 0.72 * bass_mono
        harm_chroma, times = _chroma_frames(harm_mono, sr, 65.4, 2400.0)
        bass_chroma, _ = _chroma_frames(bass_mono, sr, 36.0, 240.0)
    else:
        full_mono, _ = _load_resampled_mono(full_audio_path, sr)
        harm_chroma, times = _chroma_frames(full_mono, sr, 65.4, 2400.0)
        bass_chroma, _ = _chroma_frames(full_mono, sr, 36.0, 240.0)

    duration_sec = float(times[-1]) if len(times) > 0 else 0.0
    if duration_sec < 0.4:
        return []

    use_flat = any(k in key_hint for k in ("F ", "Bb", "Eb", "Ab", "Db", "Gb", "C minor", "G minor", "D minor"))
    note_names = NOTE_NAMES_FLAT if use_flat else NOTE_NAMES_SHARP

    # Build 12 roots x 16 template variants = 192 templates covering all 15 chord qualities
    templates: list[dict[str, Any]] = []
    for root in range(12):
        for suffix, qual, ext, weights, prior in CHORD_TEMPLATES_SPEC:
            vec = np.zeros(12, dtype=np.float64)
            for iv, w in weights:
                vec[(root + iv) % 12] = w
            vec /= np.linalg.norm(vec)
            # Negative mask penalizing prominent non-chord tones so e.g. maj7 vs major or m7b5 vs dim separate cleanly!
            chord_pcs = {(root + iv) % 12 for iv, _ in weights}
            anti_vec = np.array([0.0 if pc in chord_pcs else 1.0 for pc in range(12)], dtype=np.float64)
            anti_vec /= max(1.0, float(np.linalg.norm(anti_vec)))
            templates.append(
                {
                    "rootPc": root,
                    "rootName": note_names[root],
                    "suffix": suffix,
                    "quality": qual,
                    "extension": ext,
                    "chordPcs": chord_pcs,
                    "vec": vec,
                    "antiVec": anti_vec,
                    "nTones": len(chord_pcs),
                    "prior": prior,
                }
            )

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    # Default 1.0 beat slice for adaptive passing-chord resolution; honor caller override if provided
    eff_slice = max(0.5, min(2.0, float(slice_beats)))
    step_sec = eff_slice * sec_per_beat
    total_slices = max(1, int(math.ceil(max(0.1, duration_sec - beat_offset_sec) / step_sec)))
    n_states = len(templates)
    vec_mat = np.stack([t["vec"] for t in templates], axis=0)          # (n_states, 12)
    anti_mat = np.stack([t["antiVec"] for t in templates], axis=0)     # (n_states, 12)
    priors = np.array([t["prior"] for t in templates], dtype=np.float64)

    score_mat = np.zeros((total_slices, n_states), dtype=np.float64)
    raw_sim_mat = np.zeros((total_slices, n_states), dtype=np.float64)
    bass_pcs: list[int | None] = []
    slice_energies: list[float] = []

    for s_idx in range(total_slices):
        t0 = beat_offset_sec + s_idx * step_sec
        t1 = min(duration_sec, t0 + step_sec)
        mask = (times >= t0) & (times < t1)
        if not np.any(mask):
            bass_pcs.append(None)
            slice_energies.append(0.0)
            continue
        h_seg = harm_chroma[:, mask].mean(axis=1)
        b_seg = bass_chroma[:, mask].mean(axis=1)
        h_norm = float(np.linalg.norm(h_seg))
        b_norm = float(np.linalg.norm(b_seg))
        slice_energies.append(h_norm)
        if h_norm < 1e-4:
            bass_pcs.append(None)
            continue
        h_u = h_seg / h_norm
        top_bass_pc = int(np.argmax(b_seg)) if b_norm > 0.14 and float(np.max(b_seg)) > 0.34 else None
        bass_pcs.append(top_bass_pc)

        pos_sims = vec_mat @ h_u
        neg_pen = (anti_mat @ h_u) * 0.18
        # Active tone coverage bonus: rewards templates whose chord tones are ALL energized (helps 7ths, 9ths, sus, add9, m7b5!)
        active_pcs = set(int(i) for i in np.where(h_u >= 0.24)[0])
        sims = pos_sims - neg_pen + priors
        for st_idx, tmpl in enumerate(templates):
            cov = len(tmpl["chordPcs"] & active_pcs) / float(tmpl["nTones"])
            s_val = float(sims[st_idx]) + 0.065 * cov
            # Penalize power chord unless ONLY 2 pitch classes are genuinely active
            if tmpl["quality"] == "power" and len(active_pcs) >= 3:
                s_val -= 0.12
            if top_bass_pc is not None:
                if top_bass_pc == tmpl["rootPc"]:
                    s_val += 0.12
                elif top_bass_pc in tmpl["chordPcs"]:
                    s_val += 0.045
                else:
                    s_val -= 0.07
            score_mat[s_idx, st_idx] = s_val
            raw_sim_mat[s_idx, st_idx] = float(np.clip(pos_sims[st_idx], 0.0, 0.99))

    # Viterbi decoding with tuned switch penalty: suppresses noisy flicker while allowing clear 1-beat passing chords!
    switch_penalty = 0.125 if eff_slice <= 1.05 else 0.095
    dp = np.zeros_like(score_mat)
    back = np.zeros((total_slices, n_states), dtype=np.int32)
    dp[0] = score_mat[0]
    for s_idx in range(1, total_slices):
        prev = dp[s_idx - 1]
        best_prev_idx = int(np.argmax(prev))
        best_prev_val = float(prev[best_prev_idx])
        switch_val = best_prev_val - switch_penalty
        stay_better = prev >= switch_val
        dp[s_idx] = np.where(stay_better, prev, switch_val) + score_mat[s_idx]
        back[s_idx] = np.where(stay_better, np.arange(n_states, dtype=np.int32), best_prev_idx)

    path = [0] * total_slices
    path[-1] = int(np.argmax(dp[-1]))
    for s_idx in range(total_slices - 2, -1, -1):
        path[s_idx] = int(back[s_idx + 1, path[s_idx + 1]])

    # Merge contiguous identical chord slices and collect top-3 candidates per chord region
    raw_regions: list[dict[str, Any]] = []
    for s_idx, st_idx in enumerate(path):
        start_b = round(s_idx * eff_slice, 4)
        end_b = round((s_idx + 1) * eff_slice, 4)
        if slice_energies[s_idx] < 0.045:
            continue
        tmpl = templates[st_idx]
        raw_conf = float(np.clip(raw_sim_mat[s_idx, st_idx], 0.0, 0.99))
        b_pc = bass_pcs[s_idx]
        bass_label = (
            note_names[b_pc]
            if (b_pc is not None and b_pc != tmpl["rootPc"] and b_pc in tmpl["chordPcs"])
            else None
        )
        is_uncertain = raw_conf < 0.56
        symbol = "N/C" if is_uncertain else f"{tmpl['rootName']}{tmpl['suffix']}" + (f"/{bass_label}" if bass_label else "")

        if raw_regions and raw_regions[-1]["symbol"] == symbol and abs(raw_regions[-1]["endBeat"] - start_b) < 0.05:
            raw_regions[-1]["endBeat"] = end_b
            raw_regions[-1]["sliceIndices"].append(s_idx)
            raw_regions[-1]["confList"].append(raw_conf)
        else:
            raw_regions.append(
                {
                    "symbol": symbol,
                    "stIdx": st_idx,
                    "isUncertain": is_uncertain,
                    "bassLabel": bass_label,
                    "startBeat": start_b,
                    "endBeat": end_b,
                    "sliceIndices": [s_idx],
                    "confList": [raw_conf],
                }
            )

    events: list[dict[str, Any]] = []
    for reg in raw_regions:
        tmpl = templates[reg["stIdx"]]
        is_uncertain = reg["isUncertain"]
        s_indices = reg["sliceIndices"]
        mean_scores = score_mat[s_indices].mean(axis=0)
        mean_raw = raw_sim_mat[s_indices].mean(axis=0)
        top_idxs = np.argsort(mean_scores)[::-1][:3]
        candidates: list[dict[str, Any]] = []
        for ci in top_idxs:
            ct = templates[int(ci)]
            c_sym = f"{ct['rootName']}{ct['suffix']}"
            candidates.append(
                {
                    "symbol": c_sym,
                    "root": ct["rootName"],
                    "quality": ct["quality"],
                    "confidence": round(float(np.clip(mean_raw[int(ci)], 0.0, 0.99)), 3),
                }
            )

        dur_b = round(reg["endBeat"] - reg["startBeat"], 4)
        mean_conf = round(float(np.mean(reg["confList"])), 3)
        events.append(
            {
                "id": make_id("chd"),
                "symbol": reg["symbol"],
                "root": tmpl["rootName"] if not is_uncertain else "C",
                "quality": "uncertain" if is_uncertain else tmpl["quality"],
                "extension": None if is_uncertain else tmpl["extension"],
                "bassNote": None if is_uncertain else reg["bassLabel"],
                "startBeat": reg["startBeat"],
                "endBeat": reg["endBeat"],
                "sourceReferenceId": source_reference_id,
                "confidence": mean_conf,
                "isEstimate": True,
                "isPassing": bool(not is_uncertain and dur_b <= 1.5),
                "candidates": candidates,
                "userCorrected": False,
                "locked": False,
            }
        )
    return events
