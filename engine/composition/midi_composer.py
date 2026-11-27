"""Motif-based, genre-adaptive MIDI Composer & SMF writer (Phase 03-C/E).

Generates genuinely musical Drums, Bass, Synth Hook, Keys, Guitar, and Pad MIDI parts
with Motif A -> A' variation -> B contrast -> Cadence resolution (never monotonous copy-paste loops).
"""

from __future__ import annotations

import random
import re
import struct
from typing import Any

from engine.daw_workspace.schema import make_id

from .schemas import CompositionPlan

NOTE_TO_PC: dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

SCALE_INTERVALS: dict[str, list[int]] = {
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
}


def parse_key_root_and_scale(key_str: str, scale_hint: str = "natural_minor") -> tuple[int, list[int]]:
    parts = key_str.strip().split()
    root_name = parts[0] if parts else "F"
    pc = NOTE_TO_PC.get(root_name, 5)
    mode_word = parts[1].lower() if len(parts) > 1 else ""
    if "maj" in mode_word:
        return pc, SCALE_INTERVALS["major"]
    if "dor" in mode_word:
        return pc, SCALE_INTERVALS["dorian"]
    return pc, SCALE_INTERVALS.get(scale_hint, SCALE_INTERVALS["natural_minor"])


def parse_chord(chord_symbol: str, fallback_root_pc: int = 5) -> tuple[int, list[int]]:
    """Return (root_pc, intervals_in_semitones) for all 15 standard chord qualities + slash chords."""
    clean = chord_symbol.strip().split("/", 1)[0].strip()
    m = re.match(r"^([A-G][#b]?)(.*)$", clean)
    if not m:
        return fallback_root_pc, [0, 3, 7, 10]
    root_pc = NOTE_TO_PC.get(m.group(1), fallback_root_pc)
    qual = m.group(2).lower().strip()
    if "m7b5" in qual or "ø" in qual:
        return root_pc, [0, 3, 6, 10]
    if "maj9" in qual:
        return root_pc, [0, 4, 7, 11, 14]
    if "maj7" in qual:
        return root_pc, [0, 4, 7, 11]
    if "m9" in qual or "min9" in qual:
        return root_pc, [0, 3, 7, 10, 14]
    if "m7" in qual or "min7" in qual:
        return root_pc, [0, 3, 7, 10]
    if "aug" in qual or "+" in qual:
        return root_pc, [0, 4, 8]
    if "dim" in qual or "°" in qual:
        return root_pc, [0, 3, 6]
    if "sus4" in qual:
        return root_pc, [0, 5, 7]
    if "sus2" in qual:
        return root_pc, [0, 2, 7]
    if "add9" in qual:
        return root_pc, [0, 4, 7, 14]
    if qual == "5":
        return root_pc, [0, 7]
    if qual.startswith("m") and not qual.startswith("maj"):
        return root_pc, [0, 3, 7]
    if "13" in qual:
        return root_pc, [0, 4, 7, 10, 14]
    if "9" in qual:
        return root_pc, [0, 4, 7, 10, 14]
    if "7" in qual:
        return root_pc, [0, 4, 7, 10]
    if "6" in qual:
        return root_pc, [0, 4, 7, 9]
    return root_pc, [0, 4, 7]


def chord_at_beat(
    beat: float,
    chord_timeline: list[dict[str, Any]] | None,
    fallback_chords: list[str],
    bpb: float,
    fallback_root_pc: int,
) -> tuple[str, int, list[int], int | None]:
    """Resolve the EXACT active chord (including sub-bar changes & bass inversions) at `beat`!"""
    if chord_timeline:
        valid_tl = [c for c in chord_timeline if c.get("symbol") and c["symbol"] != "N/C"]
        if valid_tl:
            tl_span = max(float(c.get("endBeat", bpb)) for c in valid_tl)
            q_beat = beat if beat < tl_span else (beat % max(bpb, tl_span))
            for ev in valid_tl:
                if float(ev.get("startBeat", 0.0)) - 1e-4 <= q_beat < float(ev.get("endBeat", 0.0)) - 1e-4:
                    sym = str(ev["symbol"])
                    c_root, c_ints = parse_chord(sym, fallback_root_pc)
                    bass_note = ev.get("bassNote")
                    bass_pc = NOTE_TO_PC.get(str(bass_note)) if bass_note else None
                    return sym, c_root, c_ints, bass_pc
    bar_idx = int(beat // max(1.0, bpb))
    sym = fallback_chords[bar_idx % len(fallback_chords)] if fallback_chords else "Fm7"
    c_root, c_ints = parse_chord(sym, fallback_root_pc)
    bass_pc = None
    if "/" in sym:
        bass_pc = NOTE_TO_PC.get(sym.split("/", 1)[1].strip())
    return sym, c_root, c_ints, bass_pc


def _clamp_midi(pitch: int, lo: int, hi: int) -> int:
    while pitch < lo:
        pitch += 12
    while pitch > hi:
        pitch -= 12
    return max(lo, min(hi, pitch))


def _apply_swing(beat_in_bar: float, swing_ratio: float) -> float:
    """Apply subtle musical swing ONLY to offbeat 16th/8th grid positions."""
    if swing_ratio <= 0.505:
        return beat_in_bar
    offset = (swing_ratio - 0.5) * 0.42
    frac = beat_in_bar - int(beat_in_bar)
    if abs(frac - 0.5) < 0.02:
        return round(beat_in_bar + offset * 0.6, 4)
    if abs(frac - 0.75) < 0.02:
        return round(beat_in_bar + offset * 0.35, 4)
    return beat_in_bar


def _note(pitch: int, start_beat: float, dur_beats: float, velocity: int) -> dict[str, Any]:
    return {
        "id": make_id("note"),
        "pitch": max(0, min(127, int(pitch))),
        "velocity": max(1, min(127, int(velocity))),
        "startBeat": round(max(0.0, float(start_beat)), 4),
        "durationBeats": round(max(0.0625, float(dur_beats)), 4),
    }


def _bar_context(plan: CompositionPlan, bar_idx: int) -> tuple[dict[str, Any], float, bool, bool]:
    """Return (section_dict, energy, is_section_start, is_section_end) for 0-based bar_idx."""
    bar_num = bar_idx + 1
    for sec in plan.arrangement:
        if sec.startBar <= bar_num <= sec.endBar:
            return (
                sec.model_dump(),
                float(sec.energy),
                bar_num == sec.startBar,
                bar_num == sec.endBar,
            )
    if plan.arrangement:
        last = plan.arrangement[-1]
        return last.model_dump(), float(last.energy), bar_idx == 0, False
    return {"name": "GROOVE", "activeRoles": ["drums", "bass", "keys", "synth_hook"]}, 0.8, bar_idx == 0, False


def _compose_drums(
    plan: CompositionPlan,
    total_bars: int,
    bpb: float,
    genre: str,
    swing: float,
    rng: random.Random,
    force_active: bool,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    groove_pat = plan.harmonyAndGroove.get("drumGroovePattern") or {}
    full_perf = list(groove_pat.get("fullPerformanceNotes") or [])
    raw_perf = list(groove_pat.get("rawPerformanceNotes") or [])
    template_2bar = list(groove_pat.get("template2Bar") or [])
    groove_lock = str(groove_pat.get("lockMode") or "free")
    bpm = float(plan.musicalIdentity.get("tempoBpm") or 128.0)
    sec_per_beat = 60.0 / max(30.0, bpm)

    # PHASE 03.2.1 STRICT BAR-BY-BAR DRUM LOCK:
    # NEVER collapse a full bar-by-bar reference drum performance into a 2-bar loop!
    # Preserves every bar's unique kick/snare/hat pattern, fills, breakdowns, ghost notes & microtiming!
    if groove_lock == "locked" and (full_perf or raw_perf):
        src_notes = full_perf or raw_perf
        max_src_beat = max((float(h.get("startBeat", 0.0)) for h in src_notes), default=bpb)
        src_bars = max(int(groove_pat.get("totalBars") or 0), int(max_src_beat // bpb) + 1)
        by_bar: dict[int, list[dict[str, Any]]] = {b: [] for b in range(src_bars)}
        for h in src_notes:
            sb = float(h.get("startBeat", 0.0))
            b_idx = int(sb // bpb)
            if 0 <= b_idx < src_bars:
                by_bar[b_idx].append(h)

        for bar in range(total_bars):
            src_bar = bar % src_bars  # Full song-length cycle ONLY if target is longer than reference!
            base = bar * bpb
            for hit in by_bar.get(src_bar, []):
                rel_b = float(hit.get("startBeat", 0.0)) - src_bar * bpb
                mt_ms = max(-32.0, min(32.0, float(hit.get("microtimingOffsetMs", hit.get("timingDeviationMs", 0.0)))))
                mt_beats = (mt_ms / 1000.0) / sec_per_beat
                pos = max(0.0, min(bpb - 0.02, rel_b + mt_beats))
                vel = max(24, min(127, int(hit.get("velocity", hit.get("velocityEstimate", 96)))))
                pitch = int(hit.get("pitch", hit.get("midiPitch", 36)))
                dur_b = float(hit.get("durationBeats", 0.25))
                notes.append(_note(pitch, base + pos, dur_b, vel))
        if notes:
            return notes

    # REFERENCE MODE (or locked fallback if only 2-bar template exists):
    if (full_perf or template_2bar) and groove_lock in ("locked", "reference"):
        use_full = bool(full_perf)
        if use_full:
            max_src_beat = max((float(h.get("startBeat", 0.0)) for h in full_perf), default=bpb)
            src_bars = max(int(groove_pat.get("totalBars") or 0), int(max_src_beat // bpb) + 1)
            by_bar_ref: dict[int, list[dict[str, Any]]] = {b: [] for b in range(src_bars)}
            for h in full_perf:
                b_idx = int(float(h.get("startBeat", 0.0)) // bpb)
                if 0 <= b_idx < src_bars:
                    by_bar_ref[b_idx].append(h)
            for bar in range(total_bars):
                sec, energy, _, is_end = _bar_context(plan, bar)
                if not force_active and "drums" not in sec.get("activeRoles", []):
                    continue
                src_bar = bar % src_bars
                base = bar * bpb
                vel_scale = 0.86 + 0.18 * energy
                for hit in by_bar_ref.get(src_bar, []):
                    rel_b = float(hit.get("startBeat", 0.0)) - src_bar * bpb
                    mt_ms = max(-28.0, min(28.0, float(hit.get("microtimingOffsetMs", 0.0))))
                    mt_beats = (mt_ms / 1000.0) / sec_per_beat
                    pos = max(0.0, min(bpb - 0.05, rel_b + mt_beats))
                    vel = max(28, min(125, int(round(int(hit.get("velocity", 96)) * vel_scale))))
                    notes.append(_note(int(hit.get("pitch", 36)), base + pos, float(hit.get("durationBeats", 0.25)), vel))
                if groove_lock == "reference" and is_end and bpb >= 4.0:
                    notes.append(_note(38, base + bpb - 0.5, 0.22, 96))
                    notes.append(_note(45, base + bpb - 0.25, 0.22, 102))
            if notes:
                return notes

        tpl_span = bpb * 2.0 if any(float(h.get("startBeat", 0.0)) >= bpb - 0.05 for h in template_2bar) else bpb
        for bar in range(total_bars):
            sec, energy, _, is_end = _bar_context(plan, bar)
            if not force_active and "drums" not in sec.get("activeRoles", []):
                continue
            base = bar * bpb
            bar_in_tpl = (bar % 2) * bpb if tpl_span > bpb + 0.1 else 0.0
            vel_scale = 1.0 if groove_lock == "locked" else (0.86 + 0.18 * energy)
            for hit in template_2bar:
                hb = float(hit.get("startBeat", 0.0))
                if bar_in_tpl - 1e-4 <= hb < bar_in_tpl + bpb - 1e-4:
                    rel_b = hb - bar_in_tpl
                    mt_ms = max(-28.0, min(28.0, float(hit.get("microtimingOffsetMs", 0.0))))
                    mt_beats = (mt_ms / 1000.0) / sec_per_beat
                    pos = max(0.0, min(bpb - 0.05, rel_b + mt_beats))
                    vel = max(32, min(125, int(round(int(hit.get("velocity", 96)) * vel_scale))))
                    notes.append(_note(int(hit["pitch"]), base + pos, float(hit.get("durationBeats", 0.25)), vel))
            if groove_lock == "reference" and is_end and bpb >= 4.0:
                notes.append(_note(38, base + bpb - 0.5, 0.22, 96))
                notes.append(_note(45, base + bpb - 0.25, 0.22, 102))
        if notes:
            return notes

    for bar in range(total_bars):
        sec, energy, is_start, is_end = _bar_context(plan, bar)
        if not force_active and "drums" not in sec.get("activeRoles", []):
            continue
        base = bar * bpb
        vel_scale = 0.78 + 0.25 * energy

        if is_start and energy >= 0.75:
            notes.append(_note(49, base, 1.5, int(92 * vel_scale)))  # Crash on high-energy downbeat

        if genre == "house":
            # Classic 4-on-the-floor kick
            for beat in range(int(bpb)):
                notes.append(_note(36, base + beat, 0.4, int((114 if beat == 0 else 108) * vel_scale)))
            # Clap + layered snare on beats 1 and 3
            if energy >= 0.45:
                for beat in (1.0, 3.0):
                    if beat < bpb:
                        notes.append(_note(39, base + beat, 0.35, int(100 * vel_scale)))
                        notes.append(_note(38, base + beat, 0.25, int(74 * vel_scale)))
            # Offbeat open hat + swung 16th closed hat shaker pocket
            for beat in range(int(bpb)):
                if energy >= 0.55:
                    notes.append(_note(46, base + _apply_swing(beat + 0.5, swing), 0.32, int(86 * vel_scale)))
                notes.append(_note(42, base + beat, 0.18, int(52 * vel_scale)))
                if energy >= 0.70:
                    notes.append(_note(42, base + _apply_swing(beat + 0.25, swing), 0.14, int(46 * vel_scale)))
                    notes.append(_note(42, base + _apply_swing(beat + 0.75, swing), 0.14, int(58 * vel_scale)))
            # Turnaround fill on every 4th bar or section end
            if is_end or (bar + 1) % 4 == 0:
                notes.append(_note(36, base + 3.5, 0.25, int(98 * vel_scale)))
                notes.append(_note(38, base + 3.75, 0.2, int(88 * vel_scale)))
                if is_end:
                    notes.append(_note(48, base + 3.25, 0.22, int(84 * vel_scale)))
                    notes.append(_note(45, base + 3.5, 0.22, int(90 * vel_scale)))

        elif genre in ("lofi", "hiphop"):
            # Boom-bap / chill pocket
            kick_beats = [0.0, 1.75, 2.5] if bar % 2 == 0 else [0.0, 1.5, 2.5, 3.25]
            for kb in kick_beats:
                if kb < bpb:
                    notes.append(_note(36, base + _apply_swing(kb, swing), 0.4, int(108 * vel_scale)))
            for sb in (1.0, 3.0):
                if sb < bpb:
                    notes.append(_note(38, base + sb, 0.35, int(98 * vel_scale)))
            if bar % 2 == 1:
                notes.append(_note(38, base + _apply_swing(3.75, swing), 0.2, int(62 * vel_scale)))
            for step in range(int(bpb * 2)):
                pos = _apply_swing(step * 0.5, swing)
                vel = int((76 if step % 2 == 0 else 58) * vel_scale + rng.randint(-5, 5))
                notes.append(_note(42, base + pos, 0.2, vel))
            if is_end:
                notes.append(_note(46, base + 3.5, 0.45, int(82 * vel_scale)))

        elif genre == "synthwave":
            for kb in (0.0, 2.0, 2.5):
                if kb < bpb:
                    notes.append(_note(36, base + kb, 0.4, int(112 * vel_scale)))
            for sb in (1.0, 3.0):
                if sb < bpb:
                    notes.append(_note(38, base + sb, 0.4, int(106 * vel_scale)))
            for step in range(int(bpb * 2)):
                notes.append(_note(42, base + step * 0.5, 0.2, int((74 if step % 2 == 0 else 60) * vel_scale)))
            if is_end:
                for idx, p in enumerate((50, 48, 45, 43)):
                    notes.append(_note(p, base + 3.0 + idx * 0.25, 0.22, int(95 * vel_scale)))

        elif genre == "ambient":
            # Minimal organic pulse
            if energy >= 0.5:
                notes.append(_note(36, base, 0.5, int(74 * vel_scale)))
                notes.append(_note(42, base + 2.0, 0.25, int(44 * vel_scale)))
        else:
            # Modern Pop
            kick_beats = [0.0, 1.5, 2.5] if bar % 2 == 0 else [0.0, 0.75, 2.0, 2.5]
            for kb in kick_beats:
                notes.append(_note(36, base + kb, 0.4, int(110 * vel_scale)))
            for sb in (1.0, 3.0):
                notes.append(_note(38, base + sb, 0.35, int(100 * vel_scale)))
                notes.append(_note(39, base + sb, 0.3, int(75 * vel_scale)))
            for step in range(int(bpb * 2)):
                notes.append(_note(42, base + step * 0.5, 0.18, int((76 if step % 2 == 0 else 58) * vel_scale)))
            if is_end:
                notes.append(_note(46, base + 3.5, 0.4, int(86 * vel_scale)))

    return notes


def _compose_bass(
    plan: CompositionPlan,
    total_bars: int,
    bpb: float,
    genre: str,
    chords: list[str],
    root_pc: int,
    swing: float,
    force_active: bool,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    chord_tl = plan.harmonyAndGroove.get("chordTimeline") or None
    bass_pat = plan.harmonyAndGroove.get("bassGroovePattern") or {}
    ref_bass_notes = list(bass_pat.get("notes") or [])
    bass_lock = str(bass_pat.get("lockMode") or "free")
    bass_lock_mode = str(bass_pat.get("bassLockMode") or "rhythm_and_duration")

    # PHASE 03.2.1 FULL-LENGTH BAR-BY-BAR BASS PERFORMANCE LOCK / REFERENCE:
    # Preserves ALL bars (timing, note lengths, rests, octave jumps) without collapsing to 2 bars!
    if ref_bass_notes and bass_lock in ("locked", "reference"):
        max_b = max(float(rn.get("quantizedStartBeat", rn.get("startBeat", 0.0))) for rn in ref_bass_notes)
        src_bars = max(int(bass_pat.get("totalBars") or 0), int(max_b // bpb) + 1)
        by_bar_bass: dict[int, list[dict[str, Any]]] = {b: [] for b in range(src_bars)}
        pitches_all = [int(rn.get("pitch", 40)) for rn in ref_bass_notes]
        med_pitch = sorted(pitches_all)[len(pitches_all) // 2] if pitches_all else 40
        for rn in ref_bass_notes:
            sb = float(rn.get("quantizedStartBeat", rn.get("startBeat", 0.0)))
            b_idx = int(sb // bpb)
            if 0 <= b_idx < src_bars:
                by_bar_bass[b_idx].append(rn)

        for bar in range(total_bars):
            sec, energy, _, _ = _bar_context(plan, bar)
            if bass_lock != "locked" and not force_active and "bass" not in sec.get("activeRoles", []):
                continue
            src_bar = bar % src_bars
            base = bar * bpb
            bar_rns = by_bar_bass.get(src_bar, [])
            for rn in bar_rns:
                orig_sb = float(rn.get("quantizedStartBeat", rn.get("startBeat", 0.0)))
                rel_pos = max(0.0, orig_sb - src_bar * bpb)
                if rel_pos >= bpb - 0.02:
                    continue
                dur = max(0.0625, min(bpb - rel_pos, float(rn.get("quantizedDurationBeats", rn.get("durationBeats", 0.5)))))
                vel = max(32, min(125, int(rn.get("velocity", 102))))
                orig_pitch = int(rn.get("pitch", 40))
                if bass_lock_mode == "full":
                    p = orig_pitch
                else:
                    # Preserve rhythm, note lengths, rests & octave contour while aligning pitch to active Chord Track!
                    _, c_root, c_ints, bass_pc = chord_at_beat(base + rel_pos, chord_tl, chords, bpb, root_pc)
                    eff_root = bass_pc if bass_pc is not None else c_root
                    is_oct = (orig_pitch - med_pitch) >= 9 or bool(rn.get("isOctaveJump"))
                    # Map non-root contour intervals gently onto nearest chord tone when pitch_only/rhythm_and_duration
                    chord_pcs = [(eff_root + iv) % 12 for iv in c_ints[:3]]
                    if bass_lock_mode == "pitch_only":
                        p = orig_pitch
                    else:
                        # Prefer root on downbeats, preserve octave jump & 5th/3rd motion on passing notes
                        if rel_pos < 0.1 or abs(orig_pitch - med_pitch) <= 2:
                            target_pc = eff_root
                        else:
                            target_pc = min(chord_pcs, key=lambda pc: min((pc - (orig_pitch % 12)) % 12, ((orig_pitch % 12) - pc) % 12))
                        p = _clamp_midi(36 + target_pc + (12 if is_oct else 0), 28, 56)
                notes.append(_note(p, base + rel_pos, dur, vel))
        if notes:
            return notes

    for bar in range(total_bars):
        sec, energy, _, is_end = _bar_context(plan, bar)
        if not force_active and "bass" not in sec.get("activeRoles", []):
            continue
        base = bar * bpb
        vel_base = int(96 + 18 * energy)

        # Beat-accurate chord lookup (honors sub-bar harmonic changes & slash-chord bass inversions!)
        _, c_root, c_ints, bass_pc = chord_at_beat(base, chord_tl, chords, bpb, root_pc)
        _, n_root, _, n_bass_pc = chord_at_beat(base + bpb, chord_tl, chords, bpb, root_pc)
        eff_root = bass_pc if bass_pc is not None else c_root
        eff_next = n_bass_pc if n_bass_pc is not None else n_root

        chords_locked = bool(plan.harmonyAndGroove.get("chordsLocked")) or bool(chord_tl)
        bass_root = _clamp_midi(36 + eff_root, 31, 44)
        fifth = _clamp_midi(bass_root + 7, 34, 51)
        octave = _clamp_midi(bass_root + 12, 43, 55)
        third = _clamp_midi(bass_root + c_ints[1], 33, 49)
        next_bass = _clamp_midi(36 + eff_next, 31, 44)
        approach = fifth if chords_locked else (next_bass - 1 if next_bass > bass_root else next_bass + 2)

        if genre == "house":
            if bar % 2 == 0:
                pattern = [
                    (0.0, 0.65, bass_root, vel_base),
                    (0.75, 0.55, bass_root, vel_base - 8),
                    (1.5, 0.42, octave, vel_base - 6),
                    (2.0, 0.65, bass_root, vel_base),
                    (2.75, 0.55, fifth, vel_base - 10),
                    (3.5, 0.42, third if not is_end else approach, vel_base - 4),
                ]
            else:
                pattern = [
                    (0.0, 0.65, bass_root, vel_base),
                    (0.75, 0.45, fifth, vel_base - 10),
                    (1.5, 0.42, bass_root, vel_base - 6),
                    (2.0, 0.55, octave, vel_base - 4),
                    (2.75, 0.45, fifth, vel_base - 8),
                    (3.5, 0.22, third, vel_base - 8),
                    (3.75, 0.22, approach, vel_base - 2),
                ]
        elif genre == "synthwave":
            pattern = []
            for step in range(int(bpb * 2)):
                p = octave if (step % 4 == 2 and energy >= 0.7) else bass_root
                if step == 7:
                    p = approach
                pattern.append((step * 0.5, 0.42, p, vel_base if step % 2 == 0 else vel_base - 12))
        elif genre in ("lofi", "hiphop"):
            pattern = [
                (0.0, 1.6, bass_root, vel_base - 4),
                (2.5, 0.75, fifth if bar % 2 == 0 else third, vel_base - 12),
                (3.5, 0.45, approach if bar % 2 == 1 else bass_root, vel_base - 10),
            ]
        elif genre == "ambient":
            pattern = [(0.0, bpb - 0.1, bass_root, int(74 + 14 * energy))]
        else:
            pattern = [
                (0.0, 1.2, bass_root, vel_base),
                (1.5, 0.45, bass_root, vel_base - 10),
                (2.0, 0.9, fifth, vel_base - 6),
                (3.0, 0.5, octave if bar % 2 == 1 else third, vel_base - 8),
                (3.5, 0.45, approach, vel_base - 6),
            ]

        for pos, dur, p, vel in pattern:
            if pos < bpb:
                # Re-anchor note to sub-bar chord root if chord changes mid-bar (e.g., beat >= 2.0)!
                if chord_tl and pos >= 1.5:
                    _, sub_root, _, sub_bass_pc = chord_at_beat(base + pos, chord_tl, chords, bpb, root_pc)
                    sub_eff = sub_bass_pc if sub_bass_pc is not None else sub_root
                    if sub_eff != eff_root:
                        p = _clamp_midi(36 + sub_eff, 31, 44)
                notes.append(_note(p, base + _apply_swing(pos, swing), min(dur, bpb - pos), vel))
    return notes


def _compose_synth_hook(
    plan: CompositionPlan,
    total_bars: int,
    bpb: float,
    genre: str,
    chords: list[str],
    root_pc: int,
    scale_ints: list[int],
    swing: float,
    rng: random.Random,
    force_active: bool,
) -> list[dict[str, Any]]:
    """Compose a memorable Motif A -> A' -> B -> Cadence Synth Hook locked to chords & scale."""
    notes: list[dict[str, Any]] = []
    scale_pool = [root_pc + iv + 12 * octv for octv in (5, 6) for iv in scale_ints]
    scale_pool = [p for p in scale_pool if 60 <= p <= 84]

    def nearest_scale(target_pitch: int) -> int:
        return min(scale_pool, key=lambda p: abs(p - target_pitch))

    # Build motif pitch-offset signature from plan's scaleDegrees
    raw_degrees = plan.signatureMotif.get("scaleDegrees") or [1, 3, 5, 4, 3, 2, 1, 7]
    deg_offsets = [int(d) - 1 for d in raw_degrees]

    # Genre-specific rhythmic cells for Motif A, A', B, Cadence (preventing flat monotony!)
    if genre == "house":
        cells = {
            "A": [(0.0, 0.45), (0.75, 0.42), (1.5, 0.42), (2.25, 0.45), (3.0, 0.55)],
            "A_prime": [(0.0, 0.45), (0.75, 0.35), (1.25, 0.45), (2.0, 0.42), (2.75, 0.45), (3.5, 0.4)],
            "B": [(0.0, 0.65), (0.75, 0.45), (1.5, 0.65), (2.5, 0.45), (3.25, 0.6)],
            "cadence": [(0.0, 0.45), (0.75, 0.45), (1.5, 0.85), (2.5, 1.25)],
        }
    elif genre in ("lofi", "hiphop"):
        cells = {
            "A": [(0.5, 0.65), (1.5, 0.45), (2.25, 0.65), (3.25, 0.55)],
            "A_prime": [(0.0, 0.55), (1.0, 0.45), (1.75, 0.65), (2.75, 0.75)],
            "B": [(0.5, 0.75), (1.5, 0.75), (2.5, 0.65), (3.5, 0.45)],
            "cadence": [(0.5, 0.75), (1.75, 0.85), (2.75, 1.0)],
        }
    else:
        cells = {
            "A": [(0.0, 0.45), (0.5, 0.45), (1.5, 0.65), (2.5, 0.45), (3.0, 0.65)],
            "A_prime": [(0.0, 0.45), (0.75, 0.45), (1.5, 0.45), (2.25, 0.45), (3.0, 0.75)],
            "B": [(0.0, 0.7), (1.0, 0.45), (1.5, 0.7), (2.5, 0.45), (3.0, 0.85)],
            "cadence": [(0.0, 0.65), (1.0, 0.65), (2.0, 1.6)],
        }

    chord_tl = plan.harmonyAndGroove.get("chordTimeline") or None
    for bar in range(total_bars):
        sec, energy, _, _ = _bar_context(plan, bar)
        if not force_active and "synth_hook" not in sec.get("activeRoles", []):
            continue
        base = bar * bpb

        phrase_pos = bar % 4
        if phrase_pos == 0:
            cell_key = "A"
            octave_lift = 0
        elif phrase_pos == 1:
            cell_key = "A_prime"
            octave_lift = 0
        elif phrase_pos == 2:
            cell_key = "B"
            octave_lift = 5 if energy >= 0.85 else 2  # melodic lift for contrast!
        else:
            cell_key = "cadence"
            octave_lift = 0

        cell = cells[cell_key]
        prev_end = -1.0
        for idx, (pos, dur) in enumerate(cell):
            if pos >= bpb:
                continue
            # Beat-accurate chord tone lookup (respects locked Chord Track & sub-bar chord changes!)
            _, c_root, c_ints, _ = chord_at_beat(base + pos, chord_tl, chords, bpb, root_pc)
            chord_tones = [_clamp_midi(60 + c_root + iv, 62, 79) for iv in c_ints[:4]]
            # Anchor strong beats on chord tones, passing beats on scale degrees
            if idx == 0 or idx == len(cell) - 1 or (chord_tl and idx == len(cell) // 2):
                anchor = chord_tones[0 if idx == len(cell) - 1 and phrase_pos == 3 else (idx + phrase_pos) % len(chord_tones)]
                pitch = anchor if chord_tl else nearest_scale(anchor + (12 if energy >= 0.95 and phrase_pos == 2 and idx == 0 else 0))
            else:
                deg = deg_offsets[(idx + bar) % len(deg_offsets)]
                scale_idx = max(0, min(len(scale_pool) - 1, (deg % len(scale_ints)) + (2 if octave_lift else 1)))
                pitch = nearest_scale(scale_pool[scale_idx] + octave_lift)

            swung_pos = _apply_swing(pos, swing)
            if swung_pos < prev_end + 0.02:
                swung_pos = round(prev_end + 0.02, 4)
            if swung_pos >= bpb:
                continue
            final_dur = min(dur, bpb - swung_pos - 0.02)
            if final_dur < 0.1:
                continue
            vel = int((98 if idx in (0, 2) else 84) * (0.82 + 0.2 * energy) + rng.randint(-4, 4))
            notes.append(_note(pitch, base + swung_pos, final_dur, vel))
            prev_end = swung_pos + final_dur

    return notes


def _compose_keys_or_pad(
    plan: CompositionPlan,
    role: str,
    total_bars: int,
    bpb: float,
    genre: str,
    chords: list[str],
    root_pc: int,
    swing: float,
    force_active: bool,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    chord_tl = plan.harmonyAndGroove.get("chordTimeline") or None
    for bar in range(total_bars):
        sec, energy, _, _ = _bar_context(plan, bar)
        if not force_active and role not in sec.get("activeRoles", []):
            continue
        base = bar * bpb
        _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, chords, bpb, root_pc)

        # Voice-lead chords cleanly into C3–C5 (MIDI 50–72)
        voicing = sorted({_clamp_midi(48 + c_root + iv, 52, 71) for iv in c_ints[:4]})

        if role == "pad":
            vel = int(58 + 22 * energy)
            # Split pad cleanly across ANY sub-bar chord changes (supports 1-beat passing chords & half-bar changes!)
            if chord_tl:
                beat_segments: list[tuple[float, float, int, list[int]]] = []
                b_steps = int(round(bpb))
                for bs in range(b_steps):
                    _, s_root, s_ints, _ = chord_at_beat(base + bs, chord_tl, chords, bpb, root_pc)
                    if beat_segments and beat_segments[-1][2] == s_root and beat_segments[-1][3] == s_ints:
                        prev_s, prev_d, pr, pi = beat_segments[-1]
                        beat_segments[-1] = (prev_s, prev_d + 1.0, pr, pi)
                    else:
                        beat_segments.append((float(bs), 1.0, s_root, s_ints))
                for seg_start, seg_dur, s_root, s_ints in beat_segments:
                    seg_voicing = sorted({_clamp_midi(48 + s_root + iv, 52, 71) for iv in s_ints[:4]})
                    for p in seg_voicing:
                        notes.append(_note(p, base + seg_start, max(0.2, seg_dur - 0.06), vel))
            else:
                for p in voicing:
                    notes.append(_note(p, base, bpb - 0.08, vel))
        elif role == "guitar":
            # Rhythmic clean guitar plucks / arpeggios in MIDI 55–76 (beat-accurate per pluck!)
            if genre == "house":
                hits = [(0.5, 0.3), (1.5, 0.25), (2.25, 0.3), (3.5, 0.35)]
            elif genre in ("lofi", "pop"):
                hits = [(0.0, 0.45), (0.75, 0.35), (1.5, 0.45), (2.5, 0.45), (3.25, 0.45)]
            else:
                hits = [(0.0, 0.65), (1.0, 0.65), (2.0, 0.65), (3.0, 0.65)]
            for idx, (pos, dur) in enumerate(hits):
                sw = _apply_swing(pos, swing)
                if sw >= bpb:
                    continue
                _, h_root, h_ints, _ = chord_at_beat(base + sw, chord_tl, chords, bpb, root_pc)
                h_voicing = sorted({_clamp_midi(48 + h_root + iv, 52, 71) for iv in h_ints[:4]})
                guitar_voicing = sorted({_clamp_midi(p + 5, 55, 76) for p in h_voicing})
                if idx % 2 == 0:
                    # 2-note dyad pluck
                    for p in guitar_voicing[-2:]:
                        notes.append(_note(p, base + sw, min(dur, bpb - sw), int(78 + 14 * energy)))
                else:
                    p = guitar_voicing[(idx + bar) % len(guitar_voicing)]
                    notes.append(_note(p, base + sw, min(dur, bpb - sw), int(72 + 14 * energy)))
        else:
            # Electric Piano / Keys comping (beat-accurate chord lookup on EVERY stab!)
            if genre == "house":
                stabs = [(0.0, 0.42), (0.75, 0.38), (1.5, 0.45), (2.5, 0.42), (3.25, 0.45)]
                if bar % 2 == 1:
                    stabs = [(0.0, 0.42), (0.75, 0.38), (1.75, 0.42), (2.5, 0.55), (3.5, 0.38)]
            elif genre == "lofi":
                stabs = [(0.0, 1.75), (2.0, 1.65)]
            elif genre == "synthwave":
                stabs = [(0.0, 0.85), (1.0, 0.85), (2.0, 0.85), (3.0, 0.85)]
            else:
                stabs = [(0.0, 1.4), (1.5, 0.9), (2.5, 1.3)]
            for idx, (pos, dur) in enumerate(stabs):
                sw = _apply_swing(pos, swing)
                if sw >= bpb:
                    continue
                _, s_root, s_ints, _ = chord_at_beat(base + sw, chord_tl, chords, bpb, root_pc)
                stab_voicing = sorted({_clamp_midi(48 + s_root + iv, 52, 71) for iv in s_ints[:4]})
                vel = int((76 if idx == 0 else 66) + 14 * energy)
                for n_i, p in enumerate(stab_voicing):
                    roll = 0.015 * n_i if genre == "lofi" else 0.0
                    notes.append(_note(p, base + sw + roll, min(dur, bpb - sw - roll), vel))
    return notes


def compose_midi_part(
    plan: CompositionPlan,
    role: str,
    seed: int = 42,
    bpb: float = 4.0,
    force_active: bool = False,
) -> list[dict[str, Any]]:
    """Generate a single musical MIDI role for the given CompositionPlan."""
    rng = random.Random(seed + sum(ord(c) for c in role))
    ident = plan.musicalIdentity
    hg = plan.harmonyAndGroove
    total_bars = int(ident.get("barCount") or 4)
    genre = str(ident.get("genre") or "house")
    key_str = str(hg.get("key") or ident.get("key") or "F minor")
    scale_name = str(hg.get("scale") or ident.get("scale") or "natural_minor")
    chords = list(hg.get("chordProgression") or ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"])
    swing = float(hg.get("swingRatio") or 0.52)
    root_pc, scale_ints = parse_key_root_and_scale(key_str, scale_name)

    if role == "drums":
        return _compose_drums(plan, total_bars, bpb, genre, swing, rng, force_active=force_active)
    if role == "bass":
        return _compose_bass(plan, total_bars, bpb, genre, chords, root_pc, swing, force_active=force_active)
    if role == "synth_hook":
        return _compose_synth_hook(plan, total_bars, bpb, genre, chords, root_pc, scale_ints, swing, rng, force_active=force_active)
    return _compose_keys_or_pad(plan, role, total_bars, bpb, genre, chords, root_pc, swing, force_active=force_active)


def compose_multitrack_parts(
    plan: CompositionPlan,
    seed: int = 42,
    bpb: float = 4.0,
) -> dict[str, list[dict[str, Any]]]:
    """Compose all instrument roles declared in a CompositionPlan."""
    is_single = len(plan.instrumentRoles) == 1
    out: dict[str, list[dict[str, Any]]] = {}
    for idx, role_info in enumerate(plan.instrumentRoles):
        rk = str(role_info["role"])
        out[rk] = compose_midi_part(plan, rk, seed=seed + idx * 17, bpb=bpb, force_active=is_single)
    return out


def _encode_vlq(val: int) -> bytes:
    val = max(0, int(val))
    buf = [val & 0x7F]
    val >>= 7
    while val:
        buf.append((val & 0x7F) | 0x80)
        val >>= 7
    return bytes(reversed(buf))


def notes_to_midi_bytes(
    notes: list[dict[str, Any]],
    bpm: float = 128.0,
    ppq: int = 480,
    track_name: str = "AI Track",
    channel: int = 0,
) -> bytes:
    """Serialize DAW MIDI notes to a standard SMF Type-0 `.mid` file."""
    events: list[tuple[int, int, bytes]] = []
    # Meta: track name
    name_bytes = track_name.encode("utf-8", errors="ignore")[:60]
    events.append((0, 0, b"\xff\x03" + _encode_vlq(len(name_bytes)) + name_bytes))
    # Meta: set tempo
    us_per_quarter = max(100000, int(round(60_000_000.0 / max(30.0, float(bpm)))))
    events.append((0, 1, b"\xff\x51\x03" + us_per_quarter.to_bytes(3, "big")))

    ch = max(0, min(15, int(channel)))
    for n in notes:
        s_tick = max(0, int(round(float(n["startBeat"]) * ppq)))
        d_tick = max(1, int(round(float(n["durationBeats"]) * ppq)))
        pitch = max(0, min(127, int(n["pitch"])))
        vel = max(1, min(127, int(n.get("velocity", 100))))
        events.append((s_tick, 3, bytes([0x90 | ch, pitch, vel])))
        events.append((s_tick + d_tick, 2, bytes([0x80 | ch, pitch, 0])))

    events.sort(key=lambda item: (item[0], item[1]))
    track_data = bytearray()
    last_tick = 0
    for tick, _, payload in events:
        delta = max(0, tick - last_tick)
        track_data.extend(_encode_vlq(delta))
        track_data.extend(payload)
        last_tick = tick
    track_data.extend(b"\x00\xff\x2f\x00")

    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq)
    track_chunk = b"MTrk" + struct.pack(">I", len(track_data)) + bytes(track_data)
    return header + track_chunk
