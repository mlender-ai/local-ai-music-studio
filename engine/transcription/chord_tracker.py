"""Sub-Bar Chord Track & Bass Inversion Analyzer (Phase 03.2 · Section 5).

Operates on separated harmonic stems (`bass.wav` + `other.wav`) when Demucs is available (or HPSS
harmonic component on full mix fallback), evaluates 2-beat (half-bar) slices so mid-bar chord
changes are faithfully preserved, applies Viterbi transition smoothing to suppress noisy jitter,
and detects real slash-chord bass inversions (`bassNote`) from the isolated bass register.
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

CHORD_TEMPLATES_SPEC: list[tuple[str, str, str | None, list[tuple[int, float]]]] = [
    ("", "major", None, [(0, 1.0), (4, 0.82), (7, 0.90)]),
    ("m", "minor", None, [(0, 1.0), (3, 0.82), (7, 0.90)]),
    ("maj7", "maj7", "maj7", [(0, 1.0), (4, 0.80), (7, 0.85), (11, 0.65)]),
    ("m7", "min7", "7", [(0, 1.0), (3, 0.80), (7, 0.85), (10, 0.65)]),
    ("7", "dom7", "7", [(0, 1.0), (4, 0.80), (7, 0.85), (10, 0.65)]),
    ("sus4", "sus4", "sus4", [(0, 1.0), (5, 0.80), (7, 0.90)]),
    ("dim", "dim", None, [(0, 1.0), (3, 0.85), (6, 0.85)]),
]


def parse_chord_metadata(symbol: str) -> dict[str, Any]:
    """Parse a user-entered or analyzed chord symbol like `Fm7`, `Dbmaj7/F`, `G13` into structured fields."""
    clean = symbol.strip()
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
    if "maj9" in ql:
        quality, ext = "maj7", "maj9"
    elif "maj7" in ql:
        quality, ext = "maj7", "maj7"
    elif "m9" in ql or "min9" in ql:
        quality, ext = "min7", "9"
    elif "m7" in ql or "min7" in ql:
        quality, ext = "min7", "7"
    elif ql.startswith("m") and not ql.startswith("maj"):
        quality, ext = "minor", None
    elif "dim" in ql:
        quality, ext = "dim", None
    elif "sus4" in ql:
        quality, ext = "sus4", "sus4"
    elif "sus2" in ql:
        quality, ext = "sus2", "sus2"
    elif "add9" in ql:
        quality, ext = "major", "add9"
    elif "13" in ql:
        quality, ext = "dom7", "13"
    elif "7" in ql:
        quality, ext = "dom7", "7"
    elif "6" in ql:
        quality, ext = "major", "6"
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


def _load_resampled_mono(path: Path, target_sr: int = 12000, max_sec: float = 240.0) -> np.ndarray:
    info = sf.info(str(path))
    max_frames = int(min(info.frames, max_sec * info.samplerate))
    data, sr = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float64)
    if sr != target_sr and len(mono) > 0:
        g = math.gcd(int(sr), target_sr)
        mono = signal.resample_poly(mono, target_sr // g, int(sr) // g)
    return np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)


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
    c = np.log1p(c * 120.0)
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
    slice_beats: float = 2.0,
) -> list[dict[str, Any]]:
    """Extract sub-bar Chord Track events (2-beat slices merged smoothly across sustained harmonies)."""
    sr = 12000
    use_stems = bool(bass_stem_path and bass_stem_path.is_file() and other_stem_path and other_stem_path.is_file())
    if use_stems:
        bass_mono = _load_resampled_mono(bass_stem_path, sr)  # type: ignore[arg-type]
        other_mono = _load_resampled_mono(other_stem_path, sr)  # type: ignore[arg-type]
        n_len = max(len(bass_mono), len(other_mono))
        if len(bass_mono) < n_len:
            bass_mono = np.pad(bass_mono, (0, n_len - len(bass_mono)))
        if len(other_mono) < n_len:
            other_mono = np.pad(other_mono, (0, n_len - len(other_mono)))
        harm_mono = other_mono + 0.7 * bass_mono
        harm_chroma, times = _chroma_frames(harm_mono, sr, 65.4, 2200.0)
        bass_chroma, _ = _chroma_frames(bass_mono, sr, 36.0, 240.0)
    else:
        full_mono = _load_resampled_mono(full_audio_path, sr)
        harm_chroma, times = _chroma_frames(full_mono, sr, 65.4, 2200.0)
        bass_chroma, _ = _chroma_frames(full_mono, sr, 36.0, 220.0)

    duration_sec = float(times[-1]) if len(times) > 0 else 0.0
    if duration_sec < 0.5:
        return []

    use_flat = any(k in key_hint for k in ("F ", "Bb", "Eb", "Ab", "Db", "Gb", "C minor", "G minor", "D minor"))
    note_names = NOTE_NAMES_FLAT if use_flat else NOTE_NAMES_SHARP

    # Build chord template library (12 roots x 7 qualities = 84 templates)
    templates: list[dict[str, Any]] = []
    for root in range(12):
        for suffix, qual, ext, weights in CHORD_TEMPLATES_SPEC:
            vec = np.zeros(12, dtype=np.float64)
            for iv, w in weights:
                vec[(root + iv) % 12] = w
            vec /= np.linalg.norm(vec)
            # Slight parsimony prior favoring triads/7ths over rare dim/sus when scores tie closely
            prior = 0.025 if qual in ("major", "minor") else (0.015 if qual in ("min7", "maj7", "dom7") else 0.0)
            templates.append(
                {
                    "rootPc": root,
                    "rootName": note_names[root],
                    "suffix": suffix,
                    "quality": qual,
                    "extension": ext,
                    "chordPcs": {(root + iv) % 12 for iv, _ in weights},
                    "vec": vec,
                    "prior": prior,
                }
            )

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    step_sec = slice_beats * sec_per_beat
    total_slices = min(256, max(1, int(math.ceil(max(0.1, duration_sec - beat_offset_sec) / step_sec))))
    n_states = len(templates)
    score_mat = np.zeros((total_slices, n_states), dtype=np.float64)
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
        top_bass_pc = int(np.argmax(b_seg)) if b_norm > 0.15 and float(np.max(b_seg)) > 0.35 else None
        bass_pcs.append(top_bass_pc)

        for st_idx, tmpl in enumerate(templates):
            sim = float(h_u @ tmpl["vec"]) + tmpl["prior"]
            if top_bass_pc is not None:
                if top_bass_pc == tmpl["rootPc"]:
                    sim += 0.11  # Strong root-position bass anchor!
                elif top_bass_pc in tmpl["chordPcs"]:
                    sim += 0.04  # Valid chord inversion bass!
                else:
                    sim -= 0.06
            score_mat[s_idx, st_idx] = sim

    # Lightweight Viterbi smoothing (penalizes spurious 2-beat flicker while keeping real mid-bar chord changes!)
    switch_penalty = 0.095
    dp = np.zeros_like(score_mat)
    back = np.zeros((total_slices, n_states), dtype=np.int32)
    dp[0] = score_mat[0]
    for s_idx in range(1, total_slices):
        prev = dp[s_idx - 1]
        best_prev_idx = int(np.argmax(prev))
        best_prev_val = float(prev[best_prev_idx])
        for st_idx in range(n_states):
            stay_val = float(prev[st_idx])
            switch_val = best_prev_val - switch_penalty
            if stay_val >= switch_val:
                dp[s_idx, st_idx] = stay_val + score_mat[s_idx, st_idx]
                back[s_idx, st_idx] = st_idx
            else:
                dp[s_idx, st_idx] = switch_val + score_mat[s_idx, st_idx]
                back[s_idx, st_idx] = best_prev_idx

    path = [0] * total_slices
    path[-1] = int(np.argmax(dp[-1]))
    for s_idx in range(total_slices - 2, -1, -1):
        path[s_idx] = int(back[s_idx + 1, path[s_idx + 1]])

    # Merge contiguous identical chord slices into clean ChordEvents (preserving real mid-bar boundaries!)
    events: list[dict[str, Any]] = []
    for s_idx, st_idx in enumerate(path):
        start_b = round(s_idx * slice_beats, 4)
        end_b = round((s_idx + 1) * slice_beats, 4)
        if slice_energies[s_idx] < 0.05:
            continue
        tmpl = templates[st_idx]
        raw_conf = float(np.clip(score_mat[s_idx, st_idx] - tmpl["prior"], 0.0, 0.99))
        b_pc = bass_pcs[s_idx]
        # Only mark slash-chord inversion if bass is strongly a non-root chord tone
        bass_label = (
            note_names[b_pc]
            if (b_pc is not None and b_pc != tmpl["rootPc"] and b_pc in tmpl["chordPcs"])
            else None
        )
        is_uncertain = raw_conf < 0.56
        symbol = "N/C" if is_uncertain else f"{tmpl['rootName']}{tmpl['suffix']}" + (f"/{bass_label}" if bass_label else "")

        if events and events[-1]["symbol"] == symbol and abs(events[-1]["endBeat"] - start_b) < 0.05:
            events[-1]["endBeat"] = end_b
            events[-1]["confidence"] = round(0.5 * (events[-1]["confidence"] + raw_conf), 3)
        else:
            events.append(
                {
                    "id": make_id("chd"),
                    "symbol": symbol,
                    "root": tmpl["rootName"] if not is_uncertain else "C",
                    "quality": "uncertain" if is_uncertain else tmpl["quality"],
                    "extension": None if is_uncertain else tmpl["extension"],
                    "bassNote": None if is_uncertain else bass_label,
                    "startBeat": start_b,
                    "endBeat": end_b,
                    "sourceReferenceId": source_reference_id,
                    "confidence": round(raw_conf, 3),
                    "isEstimate": True,
                    "userCorrected": False,
                    "locked": False,
                }
            )
    return events
