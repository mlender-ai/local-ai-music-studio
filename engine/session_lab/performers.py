"""Musical Performance Intelligence for AI Session & Loop Production (Phase 05.2 · Parts B & E).

Generates idiomatic, context-aware, non-robotic instrument performances that read the shared
`SessionContext` (Chord Timeline, Drums Kick/Snare Pocket, Occupied Registers, Motif Memory):
- Drums (D1 R&B Pocket Groove, D2 Syncopated Hip-hop, D3 Drum Fill & Transition)
- Bass (B1 Kick-Locked Pocket Bass, B2 Syncopated Octave Riff, B3 Melodic Fretless Bass)
- Piano / Rhodes (P1 Neo Soul Rootless Comping with Voice-Leading, P2 Piano Melody, P3 Jazz/Neo-Soul Solo)
- Guitar (G1 Funk Muted Riff, G2 Clean Melodic Phrase, G3 Expressive Solo with Pitch-Bends & Slides)
- Percussion (PC1 Subtle Shaker/Conga/Rim, PC2 Syncopated Cross-Rhythm Riff, PC3 Percussion Break)
- Synth (Lead Solo & Textural Pad)
- Structured Variation Engine (8 variation modes with preserved vs changed diff)
- Bridge & Musical Transition Composer (contrasting reharmonization + motif continuity + turnaround pickup)
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from engine.composition.midi_composer import chord_at_beat, parse_key_root_and_scale
from engine.daw_workspace.schema import make_id


def _mk_note(
    pitch: int,
    start_beat: float,
    dur_beats: float,
    velocity: int,
    *,
    bend: float | None = None,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "id": make_id("note"),
        "pitch": max(0, min(127, int(pitch))),
        "velocity": max(1, min(127, int(velocity))),
        "startBeat": round(max(0.0, float(start_beat)), 4),
        "durationBeats": round(max(0.05, float(dur_beats)), 4),
    }
    if bend is not None and abs(float(bend)) > 1e-3:
        ev["pitchBendSemitones"] = round(max(-12.0, min(12.0, float(bend))), 3)
    return ev


def _clamp_octave(pitch: int, lo: int, hi: int) -> int:
    while pitch < lo:
        pitch += 12
    while pitch > hi:
        pitch -= 12
    return max(lo, min(hi, pitch))


def _nearest_pitch_for_pc(pc: int, target: int, lo: int, hi: int) -> int:
    best = _clamp_octave(pc + 48, lo, hi)
    best_dist = 999
    for oct_base in range(0, 128, 12):
        cand = oct_base + (pc % 12)
        if lo <= cand <= hi:
            d = abs(cand - target)
            if d < best_dist:
                best_dist = d
                best = cand
    return best


def _scale_pitch(root_pc: int, scale_ints: list[int], degree: int, octave_base: int = 60) -> int:
    """Convert 1-based scale degree (can be negative or > len) to MIDI pitch."""
    idx = degree - 1
    n = len(scale_ints)
    oct_shift = idx // n
    rem = idx % n
    return octave_base + root_pc + scale_ints[rem] + 12 * oct_shift


def _resolve_chords(ctx: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], int, list[int], float]:
    bpb = float(ctx.get("beatsPerBar", 4.0))
    key_str = str(ctx.get("key") or "D minor")
    scale_str = str(ctx.get("scale") or "dorian")
    root_pc, scale_ints = parse_key_root_and_scale(key_str, scale_str)
    chord_tl = list(ctx.get("chordTimeline") or [])
    fallback = [str(c.get("symbol")) for c in chord_tl if c.get("symbol")] or ["Dm9", "G13", "Cmaj9", "A7"]
    return chord_tl, fallback, root_pc, scale_ints, bpb


# =============================================================================
# 1. DRUMS PERFORMANCE INTELLIGENCE (Section 12 · TEST D1, D2, D3)
# =============================================================================

def compose_drum_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "pocket_groove",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate expressive, non-repetitive R&B / Neo-Soul / Hip-hop drum performances."""
    rng = random.Random(seed)
    bpb = float(ctx.get("beatsPerBar", 4.0))
    notes: list[dict[str, Any]] = []

    KICK = 36
    RIM = 37
    SNARE = 38
    CLAP = 39
    CHH = 42
    PHH = 44
    OHH = 46
    TOM_LO = 41
    TOM_MID = 45
    TOM_HI = 48
    CRASH = 49
    RIDE = 51

    # Laid-back Neo-Soul pocket: snare sits ~14–20 ms late (0.022–0.030 beats at 90 BPM)
    laid_back = 0.024 if performance_type == "pocket_groove" else 0.014
    swing_16 = 0.036 if performance_type == "pocket_groove" else 0.026

    if performance_type == "drum_fill_transition":
        # Dedicated multi-bar groove ending with expressive turnaround fill
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            is_fill = bar == bars - 1
            if not is_fill:
                kicks = [0.0, 1.5, 2.5] if bar % 2 == 0 else [0.0, 1.75, 2.5]
                for k in kicks:
                    notes.append(_mk_note(KICK, base + k, 0.24, rng.randint(96, 108)))
                for s in (1.0, 3.0):
                    notes.append(_mk_note(SNARE, base + s + laid_back, 0.22, rng.randint(90, 102)))
                for i in range(8):
                    pos = i * 0.5 + (swing_16 if i % 2 == 1 else 0.0)
                    notes.append(_mk_note(CHH, base + pos, 0.16, 78 if i % 2 == 0 else 54))
            else:
                # Expressive buildup fill bar: pocket first half, tom/snare cascade second half
                notes.append(_mk_note(KICK, base + 0.0, 0.25, 104))
                notes.append(_mk_note(SNARE, base + 1.0 + laid_back, 0.22, 98))
                notes.append(_mk_note(CHH, base + 0.0, 0.16, 80))
                notes.append(_mk_note(CHH, base + 0.5 + swing_16, 0.16, 58))
                notes.append(_mk_note(OHH, base + 1.5, 0.35, 76))
                fill_seq = [
                    (2.0, SNARE, 66),
                    (2.25, SNARE, 54),
                    (2.5, SNARE, 82),
                    (2.75, SNARE, 90),
                    (3.0, TOM_HI, 94),
                    (3.25, TOM_HI, 84),
                    (3.5, TOM_MID, 96),
                    (3.75, TOM_LO, 102),
                    (3.875, KICK, 88),
                ]
                for pos, p, v in fill_seq:
                    notes.append(_mk_note(p, base + pos + rng.uniform(-0.005, 0.008), 0.18, v))
        return notes, {
            "feel": "fill_and_transition",
            "laidBackSnareBeats": laid_back,
            "turnaroundBars": [bars],
        }

    # 8 distinct bar templates so NO 2 bars are robotic copy-pastes!
    pocket_kicks_by_bar = [
        [0.0, 1.5, 2.5],                # Bar 1: establish deep pocket
        [0.0, 1.75, 2.5, 3.5],          # Bar 2: subtle pickup into Bar 3
        [0.0, 0.75, 2.5],               # Bar 3: warm double-kick anticipation
        [0.0, 1.5, 2.25, 2.75],         # Bar 4: mid-phrase turnaround bounce
        [0.0, 1.5, 2.5],                # Bar 5: B-half anchor with ride lift
        [0.0, 1.75, 2.75],              # Bar 6: late neo-soul syncopation
        [0.0, 0.75, 1.5, 2.5],          # Bar 7: forward push before turnaround
        [0.0, 1.5, 2.25],               # Bar 8: leaves room for bar-end fill
    ]
    hiphop_kicks_by_bar = [
        [0.0, 0.75, 2.0, 2.75],
        [0.0, 1.5, 2.5, 3.25],
        [0.0, 0.75, 1.75, 2.5],
        [0.0, 1.5, 2.25, 3.5],
        [0.0, 0.5, 2.0, 2.75],
        [0.0, 1.75, 2.5],               # deliberate space in Bar 6
        [0.0, 0.75, 2.25, 2.75],
        [0.0, 1.5, 2.0],
    ]
    kick_table = pocket_kicks_by_bar if performance_type == "pocket_groove" else hiphop_kicks_by_bar

    for bar in range(bars):
        base = start_beat_offset + bar * bpb
        kicks = kick_table[bar % len(kick_table)]

        # Subtle crash/ride entry on Bar 1 & Bar 5
        if bar == 0:
            notes.append(_mk_note(RIDE, base + 0.0, 0.65, 62))
        elif bar == 4:
            notes.append(_mk_note(OHH, base + 0.0, 0.35, 72))

        # Kick drum with natural velocity contour (downbeat strongest, syncopations rounder)
        for k in kicks:
            v = rng.randint(102, 112) if k == 0.0 else (rng.randint(84, 96) if k in (1.5, 2.5, 2.0) else rng.randint(70, 82))
            micro = rng.uniform(-0.004, 0.008) if k > 0 else 0.0
            notes.append(_mk_note(KICK, base + k + micro, 0.26, v))

        # Backbeat Snare (deliberately laid-back!) + subtle Rim/Clap texture on alternate bars
        snare_beats = [1.0, 3.0] if not (bar == bars - 1) else [1.0]
        for sb in snare_beats:
            s_vel = rng.randint(92, 104)
            s_micro = laid_back + rng.uniform(-0.004, 0.006)
            notes.append(_mk_note(SNARE, base + sb + s_micro, 0.24, s_vel))
            if bar in (1, 3, 5, 7) and sb == 3.0:
                notes.append(_mk_note(RIM, base + sb + s_micro + 0.006, 0.16, rng.randint(52, 66)))
            elif performance_type == "syncopated_hiphop" and bar % 2 == 1 and sb == 1.0:
                notes.append(_mk_note(CLAP, base + sb + s_micro + 0.008, 0.18, rng.randint(56, 68)))

        # Expressive ghost snare notes (quiet, breathing inside the pocket)
        ghost_slots = {
            0: [1.75, 3.75],
            1: [0.75, 2.25],
            2: [1.75, 2.75, 3.75],
            3: [0.75, 1.75],
            4: [1.75, 3.25],
            5: [0.75, 2.25, 3.75],
            6: [1.75, 2.75],
            7: [1.75],
        }[bar % 8]
        for g in ghost_slots:
            notes.append(_mk_note(SNARE, base + g + swing_16 * 0.5, 0.12, rng.randint(32, 46)))

        # Dynamic Hi-Hat / Ride pattern with intentional open->closed choke & velocity sculpting
        use_ride_tint = (bar >= 4 and performance_type == "pocket_groove")
        for step in range(8):
            pos = step * 0.5
            # Leave room during Bar 8 fill
            if bar == bars - 1 and pos >= 3.0:
                continue
            off_micro = (swing_16 + rng.uniform(-0.005, 0.006)) if step % 2 == 1 else rng.uniform(-0.003, 0.005)
            # Intentional open hi-hat breath before downbeat/turnaround (choked by next closed hat!)
            if (bar % 2 == 1 and step == 7) or (bar == 3 and step == 5):
                notes.append(_mk_note(OHH, base + pos + off_micro, 0.34, rng.randint(68, 78)))
            else:
                vel = rng.randint(74, 86) if step % 2 == 0 else rng.randint(46, 60)
                if step == 0 and bar > 0:
                    vel = min(92, vel + 6)
                hat_pitch = RIDE if (use_ride_tint and step % 2 == 0 and bar in (4, 5)) else CHH
                notes.append(_mk_note(hat_pitch, base + pos + off_micro, 0.16, vel))
            # Occasional delicate 16th-note hi-hat skip (never constant machine gun)
            if (bar in (1, 2, 5, 6) and step == 3) or (bar in (0, 4) and step == 6):
                notes.append(_mk_note(CHH, base + pos + 0.25 + swing_16 * 0.65, 0.10, rng.randint(36, 48)))

        # Musical Bar 4 micro-turnaround & Bar 8 real drum fill!
        if bar == 3 and bars >= 4:
            notes.append(_mk_note(SNARE, base + 3.5 + swing_16 * 0.4, 0.16, 66))
            notes.append(_mk_note(TOM_HI, base + 3.75 + swing_16 * 0.3, 0.18, 74))
        elif bar == bars - 1 and bars >= 4:
            fill_hits = [
                (2.75, SNARE, 72),
                (3.0 + laid_back * 0.5, SNARE, 94),
                (3.25 + swing_16 * 0.3, TOM_HI, 86),
                (3.5 + swing_16 * 0.4, TOM_MID, 90),
                (3.75 + swing_16 * 0.3, TOM_LO, 96),
                (3.75, PHH, 60),
            ]
            for f_pos, f_pitch, f_vel in fill_hits:
                notes.append(_mk_note(f_pitch, base + f_pos, 0.18, f_vel))

    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    return notes, {
        "feel": performance_type,
        "laidBackSnareBeats": laid_back,
        "swing16Beats": swing_16,
        "uniqueTurnaroundBars": [4, bars] if bars >= 8 else [bars],
    }


# =============================================================================
# 2. BASS PERFORMANCE INTELLIGENCE (Section 13 · TEST B1, B2, B3)
# =============================================================================

def compose_bass_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "pocket_groove",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compose kick-locked, harmonically grounded, non-robotic Bass performance (E1–G3)."""
    rng = random.Random(seed)
    chord_tl, fallback, root_pc, scale_ints, bpb = _resolve_chords(ctx)
    groove = ctx.get("grooveProfile") or {}
    kick_beats = sorted(float(k) for k in (groove.get("kickBeatsInBar") or [0.0, 1.5, 2.5]))
    swing = 0.025

    notes: list[dict[str, Any]] = []
    LO, HI = 36, 56  # C2..G#3 (clean warm electric bass pocket, never muddy below 36)

    for bar in range(bars):
        base = start_beat_offset + bar * bpb
        sym, c_root, c_ints, bass_pc = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
        next_sym, next_root, _, next_bass_pc = chord_at_beat(base + bpb, chord_tl, fallback, bpb, root_pc)

        anchor_pc = bass_pc if bass_pc is not None else c_root
        next_anchor_pc = next_bass_pc if next_bass_pc is not None else next_root
        root_p = _clamp_octave(36 + anchor_pc, 36, 48)  # C2–C3 warm low root
        fifth_p = _clamp_octave(root_p + 7, LO, HI)
        third_p = _clamp_octave(root_p + (c_ints[1] if len(c_ints) > 1 else 3), LO, HI)
        sev_p = _clamp_octave(root_p + (c_ints[3] if len(c_ints) > 3 else 10), LO, HI)
        oct_p = min(HI, root_p + 12)
        next_root_p = _clamp_octave(36 + next_anchor_pc, 36, 48)
        approach_p = next_root_p - 1 if abs(next_root_p - root_p) >= 2 else next_root_p + 2
        approach_p = max(LO, min(HI, approach_p))

        if performance_type == "pocket_groove":
            # Lock directly to kick beats + leave clean snare breath at beat 1.0 / 3.0!
            slide_in = -1.0 if bar in (0, 4) else None
            # Downbeat anchor (locked to Kick 0.0)
            notes.append(_mk_note(root_p, base + 0.0, 0.82, rng.randint(94, 104), bend=slide_in))

            # Second anchor aligned to first syncopated kick (e.g. 1.5 or 1.75)
            k2 = next((k for k in kick_beats if 1.2 <= k <= 2.0), 1.5)
            if bar % 4 == 0:
                notes.append(_mk_note(root_p, base + k2 + swing, 0.42, rng.randint(82, 92)))
                notes.append(_mk_note(fifth_p, base + 2.5 + swing, 0.46, rng.randint(84, 94)))
                notes.append(_mk_note(sev_p, base + 3.5 + swing, 0.36, rng.randint(76, 86)))
            elif bar % 4 == 1:
                notes.append(_mk_note(fifth_p, base + k2 + swing, 0.38, rng.randint(80, 90)))
                notes.append(_mk_note(root_p, base + 2.5 + swing, 0.52, rng.randint(88, 96)))
                notes.append(_mk_note(approach_p, base + 3.75, 0.22, rng.randint(74, 84)))
            elif bar % 4 == 2:
                # Subtle rhythmic anticipation + octave breath
                notes.append(_mk_note(root_p, base + 0.75 + swing * 0.5, 0.18, rng.randint(62, 72)))
                notes.append(_mk_note(third_p, base + 1.5 + swing, 0.45, rng.randint(82, 92)))
                notes.append(_mk_note(fifth_p, base + 2.5 + swing, 0.40, rng.randint(84, 92)))
                notes.append(_mk_note(sev_p, base + 3.25, 0.28, rng.randint(76, 86)))
                notes.append(_mk_note(approach_p, base + 3.75, 0.22, rng.randint(78, 86)))
            else:
                # Bar 4 / Bar 8 turnaround bass walk back to Bar 1!
                notes.append(_mk_note(root_p, base + 1.5 + swing, 0.36, rng.randint(84, 92)))
                notes.append(_mk_note(fifth_p, base + 2.25, 0.32, rng.randint(82, 90)))
                notes.append(_mk_note(sev_p, base + 2.75 + swing * 0.4, 0.24, rng.randint(78, 88)))
                notes.append(_mk_note(oct_p if bar == 3 else third_p, base + 3.25, 0.28, rng.randint(86, 94), bend=-1.0))
                notes.append(_mk_note(approach_p, base + 3.75, 0.23, rng.randint(80, 88)))

        elif performance_type == "syncopated_riff":
            # Funky syncopated octave pops + dead ghost notes
            notes.append(_mk_note(root_p, base + 0.0, 0.42, 102, bend=-1.0 if bar % 2 == 0 else None))
            notes.append(_mk_note(root_p, base + 0.75, 0.14, 58))  # muted thumb ghost
            notes.append(_mk_note(oct_p, base + 1.5 + swing, 0.24, 92))
            notes.append(_mk_note(sev_p, base + 1.75 + swing * 0.5, 0.22, 82))
            notes.append(_mk_note(fifth_p, base + 2.5 + swing, 0.34, 88))
            if bar % 2 == 0:
                notes.append(_mk_note(root_p, base + 3.25, 0.20, 74))
                notes.append(_mk_note(oct_p, base + 3.5 + swing, 0.28, 90))
            else:
                notes.append(_mk_note(third_p, base + 3.25, 0.24, 82))
                notes.append(_mk_note(fifth_p, base + 3.5 + swing, 0.20, 86))
                notes.append(_mk_note(approach_p, base + 3.75, 0.22, 84))

        else:
            # melodic_bassline: expressive lyrical neo-soul/fretless phrases
            ninth_p = _clamp_octave(root_p + 14, LO, HI + 4)
            notes.append(_mk_note(root_p, base + 0.0, 1.15, 94, bend=-1.0 if bar % 2 == 0 else None))
            notes.append(_mk_note(fifth_p, base + 1.5 + swing, 0.65, 84))
            if bar % 2 == 0:
                notes.append(_mk_note(sev_p, base + 2.5 + swing, 0.45, 86))
                notes.append(_mk_note(ninth_p, base + 3.0, 0.48, 88, bend=-1.0))
                notes.append(_mk_note(sev_p, base + 3.5 + swing, 0.38, 78))
            else:
                notes.append(_mk_note(third_p, base + 2.25, 0.42, 82))
                notes.append(_mk_note(fifth_p, base + 2.75, 0.36, 84))
                notes.append(_mk_note(sev_p, base + 3.25, 0.32, 86))
                notes.append(_mk_note(approach_p, base + 3.75, 0.24, 80))

    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    return notes, {
        "performanceType": performance_type,
        "lockedToKickBeats": kick_beats,
        "registerMidi": [LO, HI],
    }


# =============================================================================
# 3. PIANO / RHODES PERFORMANCE INTELLIGENCE (Section 11 · TEST P1, P2, P3)
# =============================================================================

def _build_rootless_voicing(
    c_root: int,
    c_ints: list[int],
    prev_center: float,
    *,
    lo: int = 52,
    hi: int = 74,
) -> list[int]:
    """Build smooth voice-led 4-note Neo-Soul rootless voicing (3, 5/13, 7, 9)."""
    third_int = c_ints[1] if len(c_ints) > 1 else 3
    fifth_int = c_ints[2] if len(c_ints) > 2 else 7
    sev_int = c_ints[3] if len(c_ints) > 3 else 10
    nine_int = 14  # 9th adds instant neo-soul warmth
    # Use 13th (+9) on dominant chords instead of plain 5th!
    color_int = 9 if (third_int == 4 and sev_int == 10) else fifth_int

    pcs = [(c_root + third_int) % 12, (c_root + color_int) % 12, (c_root + sev_int) % 12, (c_root + nine_int) % 12]
    chosen: list[int] = []
    for pc in pcs:
        p = _nearest_pitch_for_pc(pc, int(round(prev_center)), lo, hi)
        # Avoid unison/semitone cluster collisions in voicing
        while any(abs(p - existing) <= 1 for existing in chosen):
            if p + 12 <= hi:
                p += 12
            elif p - 12 >= lo:
                p -= 12
            else:
                break
        chosen.append(p)
    return sorted(chosen)


def compose_keys_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "neo_soul_comping",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compose expressive Neo-Soul Rootless Rhodes Comping, Piano Melody, or Improvised Solo."""
    rng = random.Random(seed)
    chord_tl, fallback, root_pc, scale_ints, bpb = _resolve_chords(ctx)
    notes: list[dict[str, Any]] = []
    swing = 0.025

    if performance_type == "neo_soul_comping":
        center = 63.0  # Eb4 sweet spot for warm Rhodes tine register (stays above Bass!)
        comp_rhythms = [
            [(0.0, 2.25, "roll", 76), (2.5 + swing, 0.95, "stab", 64)],
            [(0.0, 1.40, "roll", 72), (1.75, 0.35, "grace", 58), (2.5 + swing, 1.20, "roll", 74)],
            [(0.0, 2.60, "roll", 78), (3.5 + swing, 0.45, "anticipation", 68)],
            [(0.0, 1.75, "roll", 74), (2.0, 0.65, "stab", 66), (3.0, 0.85, "roll", 72)],
            [(0.0, 2.35, "roll", 80), (2.75, 0.85, "stab", 66)],
            [(0.0, 1.50, "roll", 74), (2.5 + swing, 0.50, "stab", 64), (3.25, 0.65, "roll", 70)],
            [(0.0, 2.75, "roll", 78), (3.5 + swing, 0.42, "anticipation", 70)],
            [(0.0, 1.80, "roll", 76), (2.5 + swing, 1.15, "roll", 72)],
        ]
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            sym, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
            voicing = _build_rootless_voicing(c_root, c_ints, center, lo=52, hi=75)
            center = sum(voicing) / max(1, len(voicing))

            # Optional warm low-hand anchor root/7th shell on beat 0 for richness on Bars 1, 5
            if bar in (0, 4):
                low_anchor = _nearest_pitch_for_pc(c_root, 50, 48, 57)
                if all(abs(low_anchor - v) >= 2 for v in voicing):
                    notes.append(_mk_note(low_anchor, base + 0.0, 2.1, 68))

            for hit_pos, hit_dur, kind, base_vel in comp_rhythms[bar % len(comp_rhythms)]:
                # On anticipation hit (beat 3.5), voice-lead into NEXT bar's chord for authentic Neo-Soul magic!
                if kind == "anticipation":
                    _, n_root, n_ints, _ = chord_at_beat(base + bpb, chord_tl, fallback, bpb, root_pc)
                    v_use = _build_rootless_voicing(n_root, n_ints, center, lo=52, hi=75)
                else:
                    v_use = voicing

                for idx, p in enumerate(v_use):
                    # Subtle human roll across fingers + top-voice melodic prominence
                    roll_dt = (idx * 0.022) if kind == "roll" else (idx * 0.008)
                    vel = base_vel + (6 if idx == len(v_use) - 1 else rng.randint(-5, 3))
                    if kind == "grace" and idx < len(v_use) - 2:
                        continue
                    notes.append(_mk_note(p, base + hit_pos + roll_dt, max(0.22, hit_dur - roll_dt), vel))

                # Delicate upper grace-note ornament (2nd->3rd or 9th->3rd) on Bars 2, 6
                if kind == "roll" and hit_pos == 0.0 and bar in (1, 5):
                    top = v_use[-1]
                    grace_p = top - 2
                    notes.append(_mk_note(grace_p, base + 1.25, 0.16, 56))
                    notes.append(_mk_note(top, base + 1.42, 0.45, 70))

        notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
        return notes, {"performanceType": performance_type, "voicingStyle": "rootless_9th_13th_voice_led"}

    if performance_type == "piano_melody":
        # Memorable, singable upper-register piano motif with rests & call-and-response
        motif_degs = list((ctx.get("musicalMotif") or {}).get("scaleDegrees") or [5, 3, 4, 5, 7, 6, 5, 3])
        phrase_templates = [
            # Bar 1: clear motif question
            [(0.5, 0.45, 0, 82), (1.0, 0.90, 1, 88), (2.25, 0.25, 2, 74), (2.5, 1.15, 3, 90)],
            # Bar 2: gentle answer + rest on beats 2.5–4.0
            [(0.25, 0.35, 4, 80), (0.75, 0.65, 5, 86), (1.5, 1.10, 6, 82)],
            # Bar 3: varied motif lifting higher
            [(0.5, 0.35, 0, 80), (1.0, 0.45, 2, 86), (1.5, 0.95, 4, 94), (2.75, 0.75, 3, 84)],
            # Bar 4: cadential phrase breath
            [(0.5, 0.50, 5, 82), (1.25, 0.35, 6, 76), (1.75, 1.35, 7, 88)],
        ]
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
            chord_pcs = {(c_root + i) % 12 for i in c_ints} | {(c_root + 14) % 12}
            tpl = phrase_templates[bar % 4]
            oct_lift = 12 if bar in (4, 5) else 0
            for pos, dur, d_idx, vel in tpl:
                deg = motif_degs[d_idx % len(motif_degs)]
                raw_p = _scale_pitch(root_pc, scale_ints, deg, octave_base=60 + oct_lift)
                raw_p = _clamp_octave(raw_p, 64, 84)
                # Snap long sustained notes gently to nearest chord tone or 9th so harmony shines!
                if dur >= 0.75 and (raw_p % 12) not in chord_pcs:
                    for shift in (1, -1, 2, -2):
                        if ((raw_p + shift) % 12) in chord_pcs:
                            raw_p += shift
                            break
                notes.append(_mk_note(raw_p, base + pos + (swing if pos % 1.0 == 0.5 else 0.0), dur, vel + rng.randint(-4, 4)))
        notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
        return notes, {"performanceType": performance_type, "motifDegrees": motif_degs}

    # piano_solo (TEST P3): 4-phrase structured Jazz / Neo-Soul solo arc
    solo_phrases = [
        # Phrase 1 (Bars 0-1): Calm lyrical opening + rest
        (0, [(0.5, 0.42, 5, 82), (1.0, 0.85, 7, 88), (2.0, 0.35, 6, 76), (2.5, 1.10, 5, 86)]),
        (1, [(0.5, 0.32, 4, 78), (1.0, 0.40, 3, 82), (1.5, 1.25, 1, 86)]),
        # Phrase 2 (Bars 2-3): Syncopated rhythmic call-and-response + grace run
        (2, [(0.75, 0.25, 3, 76), (1.0, 0.45, 5, 86), (1.75, 0.22, 6, 80), (2.0, 0.22, 7, 84), (2.25, 0.65, 8, 92), (3.25, 0.55, 7, 84)]),
        (3, [(0.25, 0.22, 6, 78), (0.5, 0.45, 5, 86), (1.25, 0.90, 4, 88), (3.0, 0.35, 5, 76), (3.5, 0.45, 7, 84)]),
        # Phrase 3 (Bars 4-5): Register climax with expressive 16th-note dorian flourish
        (4, [(0.0, 0.85, 8, 96), (1.0, 0.35, 9, 92), (1.5, 0.24, 10, 96), (1.75, 0.24, 9, 88), (2.0, 0.24, 8, 90), (2.25, 0.95, 11, 100)]),
        (5, [(0.5, 0.35, 10, 92), (1.0, 0.25, 9, 86), (1.25, 0.25, 8, 88), (1.5, 0.80, 7, 94), (2.75, 0.65, 5, 84)]),
        # Phrase 4 (Bars 6-7): Warm descending soulful resolution
        (6, [(0.5, 0.45, 7, 86), (1.25, 0.35, 6, 82), (1.75, 0.75, 5, 88), (2.75, 0.35, 4, 80), (3.25, 0.55, 3, 84)]),
        (7, [(0.0, 0.65, 2, 82), (0.75, 0.45, 3, 86), (1.5, 1.95, 1, 90)]),
    ]
    for bar in range(bars):
        base = start_beat_offset + bar * bpb
        _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
        chord_pcs = {(c_root + i) % 12 for i in c_ints} | {(c_root + 14) % 12}
        _, events = solo_phrases[bar % len(solo_phrases)]
        for pos, dur, deg, vel in events:
            p = _clamp_octave(_scale_pitch(root_pc, scale_ints, deg, octave_base=60), 62, 88)
            if dur >= 0.75 and (p % 12) not in chord_pcs:
                for shift in (1, -1, 2, -2):
                    if ((p + shift) % 12) in chord_pcs:
                        p += shift
                        break
            notes.append(_mk_note(p, base + pos, dur, vel + rng.randint(-3, 3)))
    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    return notes, {"performanceType": performance_type, "phraseArc": ["statement", "response", "climax", "resolution"]}


# =============================================================================
# 4. GUITAR PERFORMANCE INTELLIGENCE (Section 10 · TEST G1, G2, G3)
# =============================================================================

def _guitar_upper_triad(c_root: int, c_ints: list[int], lo: int = 62, hi: int = 79) -> list[int]:
    """Build tight 3-string upper-neck funk/neo-soul guitar voicing (sits cleanly ABOVE Rhodes mud!)."""
    third_int = c_ints[1] if len(c_ints) > 1 else 3
    sev_int = c_ints[3] if len(c_ints) > 3 else 10
    nine_int = 14
    pcs = [(c_root + sev_int) % 12, (c_root + nine_int) % 12, (c_root + third_int) % 12]
    center = (lo + hi) // 2
    out: list[int] = []
    for pc in pcs:
        p = _nearest_pitch_for_pc(pc, center, lo, hi)
        while any(abs(p - x) <= 1 for x in out) and p + 12 <= hi:
            p += 12
        out.append(p)
    return sorted(out)


def compose_guitar_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "funk_riff",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate idiomatic Guitar performances: G1 Funk Muted Riff, G2 Clean Melodic Phrase, G3 Expressive Solo."""
    rng = random.Random(seed)
    chord_tl, fallback, root_pc, scale_ints, bpb = _resolve_chords(ctx)
    notes: list[dict[str, Any]] = []
    swing = 0.022

    # Carve register around existing Keys/Rhodes to prevent midrange masking!
    keys_reg = (ctx.get("occupiedRegisters") or {}).get("keys") or {}
    keys_med = int(keys_reg.get("medianPitch", 63))
    funk_lo = max(62, keys_med + 2)
    funk_hi = min(81, funk_lo + 15)

    if performance_type == "funk_riff":
        # TEST G1: Tight 16th-note palm-muted chucks + crisp syncopated upper-triad stabs + rests!
        bar_patterns = [
            # (beat, dur, kind, vel) -> kind: 'stab' (3-note chord), 'chuck' (1-note muted scratch), 'double' (2-note slide)
            [(0.5 + swing, 0.24, "stab", 92), (0.75, 0.14, "chuck", 62), (1.5 + swing, 0.26, "stab", 96), (2.25, 0.14, "chuck", 58), (2.75, 0.24, "double", 88), (3.5 + swing, 0.22, "stab", 90)],
            [(0.5 + swing, 0.22, "stab", 88), (1.25, 0.14, "chuck", 60), (1.5 + swing, 0.28, "double", 94), (2.5 + swing, 0.22, "stab", 90), (3.25, 0.14, "chuck", 62), (3.75, 0.22, "double", 92)],
            [(0.25, 0.14, "chuck", 58), (0.5 + swing, 0.26, "stab", 94), (1.5 + swing, 0.22, "stab", 88), (1.75, 0.15, "chuck", 60), (2.75, 0.30, "double", 94), (3.5 + swing, 0.20, "chuck", 66)],
            [(0.5 + swing, 0.24, "stab", 92), (1.5 + swing, 0.24, "double", 90), (2.25, 0.15, "chuck", 62), (2.5 + swing, 0.24, "stab", 96), (3.25, 0.20, "single", 86), (3.5 + swing, 0.22, "single", 90), (3.75, 0.22, "double", 96)],
        ]
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
            triad = _guitar_upper_triad(c_root, c_ints, lo=funk_lo, hi=funk_hi)
            pat = bar_patterns[bar % 4]
            for pos, dur, kind, vel in pat:
                v_jit = vel + rng.randint(-4, 4)
                if kind == "stab":
                    # Fast crisp guitar down-up strum (7ms stagger)
                    for idx, p in enumerate(triad):
                        notes.append(_mk_note(p, base + pos + idx * 0.010, dur, v_jit - (4 if idx == 0 else 0)))
                elif kind == "double":
                    # Funky Neo-Soul 2-string hammer/slide double-stop
                    bend_val = -1.0 if (pos >= 2.5 or bar % 2 == 1) else None
                    for idx, p in enumerate(triad[-2:]):
                        notes.append(_mk_note(p, base + pos + idx * 0.008, dur, v_jit, bend=bend_val if idx == 1 else None))
                elif kind == "single":
                    notes.append(_mk_note(triad[-1], base + pos, dur, v_jit))
                else:
                    # Percussive muted scratch note (short, low velocity)
                    notes.append(_mk_note(triad[0], base + pos, dur, v_jit))
        notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
        return notes, {
            "performanceType": "funk_riff",
            "registerMidi": [funk_lo, funk_hi],
            "techniques": ["palm_mute_chucks", "upper_triad_stabs", "double_stop_slides", "snare_pocket_rests"],
        }

    if performance_type == "clean_melodic":
        # TEST G2: Sparse, warm clean hollow-body guitar arpeggios & double-stop answers in Rhodes gaps
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
            triad = _guitar_upper_triad(c_root, c_ints, lo=57, hi=76)
            root_hi = _nearest_pitch_for_pc(c_root, 64, 57, 72)

            if bar % 4 == 0:
                # Warm arpeggiated pickup + gentle singing hold + breathing space!
                notes.append(_mk_note(root_hi, base + 0.5 + swing, 0.55, 74))
                notes.append(_mk_note(triad[0], base + 1.0, 0.50, 78))
                notes.append(_mk_note(triad[1], base + 1.5 + swing, 0.65, 82))
                notes.append(_mk_note(triad[2], base + 2.25, 1.15, 86, bend=-1.0))
            elif bar % 4 == 1:
                # Sparse neo-soul double-stop response on beat 1.5 and beat 3.0 (leaves Bar 2 open!)
                notes.append(_mk_note(triad[0], base + 1.5 + swing, 0.85, 76))
                notes.append(_mk_note(triad[2], base + 1.51 + swing, 0.85, 82, bend=-1.0))
                notes.append(_mk_note(triad[1], base + 2.75, 0.70, 74))
            elif bar % 4 == 2:
                # Lyrical descending answer phrase
                notes.append(_mk_note(triad[2], base + 0.75, 0.45, 80))
                notes.append(_mk_note(triad[1], base + 1.25, 0.45, 78))
                notes.append(_mk_note(triad[0], base + 1.75, 0.95, 84, bend=-1.0))
                notes.append(_mk_note(root_hi, base + 3.25, 0.65, 76))
            else:
                # Warm double-stop turnaround slide leading back to Bar 1
                notes.append(_mk_note(triad[0], base + 1.0, 0.70, 78))
                notes.append(_mk_note(triad[1], base + 1.01, 0.70, 82))
                notes.append(_mk_note(triad[2], base + 2.5 + swing, 0.45, 84))
                notes.append(_mk_note(triad[1], base + 3.0, 0.85, 86, bend=-1.0))
        notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
        return notes, {
            "performanceType": "clean_melodic",
            "techniques": ["broken_arpeggio", "double_stop_slides", "spacious_call_and_response"],
        }

    # TEST G3: Expressive Soulful Guitar Solo (bends, slides, sustained notes, 16th bursts, breath/rests, climax arc!)
    # Format per bar: list of (start_beat, dur_beats, scale_degree, velocity, pitch_bend_semitones)
    solo_bars = [
        # Bar 1 (Phrase 1: lyrical slide-in opening + breathing sustain)
        [(0.75, 0.24, 3, 78, None), (1.0, 0.45, 4, 84, None), (1.5, 1.45, 5, 92, -1.0)],
        # Bar 2 (Answer with soulful whole-step string bend + 1.25-beat rest!)
        [(0.5, 0.25, 6, 82, None), (0.75, 1.35, 7, 94, 1.0), (2.25, 0.55, 5, 80, None)],
        # Bar 3 (Phrase 2: bluesy 16th pickup burst -> bent hold)
        [(0.5, 0.22, 4, 80, None), (0.75, 0.22, 5, 86, None), (1.0, 0.22, 6, 88, None), (1.25, 1.15, 7, 96, 2.0), (2.75, 0.65, 5, 84, None)],
        # Bar 4 (Gentle vocal-like dip & breath before high-neck climb)
        [(0.5, 0.40, 4, 82, None), (1.0, 0.90, 3, 86, -1.0), (2.25, 0.65, 5, 80, None)],
        # Bar 5 (Phrase 3 Climax: high-register singing bend!)
        [(0.25, 0.24, 7, 86, None), (0.5, 0.45, 8, 94, None), (1.0, 1.65, 9, 102, 2.0), (3.0, 0.45, 8, 90, None)],
        # Bar 6 (Expressive descending blues/dorian cascade)
        [(0.0, 0.60, 10, 98, -1.0), (0.75, 0.24, 9, 88, None), (1.0, 0.24, 8, 90, None), (1.25, 0.24, 7, 86, None), (1.5, 1.10, 5, 92, 1.0)],
        # Bar 7 (Phrase 4: tender double-phrase call back home)
        [(0.5, 0.40, 6, 84, None), (1.0, 0.65, 5, 88, None), (2.0, 0.40, 4, 82, None), (2.5, 0.95, 3, 86, -1.0)],
        # Bar 8 (Warm soulful cadence landing cleanly on root/5th with long resonant decay)
        [(0.5, 0.35, 2, 80, None), (1.0, 0.45, 3, 86, None), (1.5, 2.15, 1, 92, -1.0)],
    ]
    for bar in range(bars):
        base = start_beat_offset + bar * bpb
        _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
        chord_pcs = {(c_root + i) % 12 for i in c_ints} | {(c_root + 14) % 12}
        for pos, dur, deg, vel, bend in solo_bars[bar % len(solo_bars)]:
            p = _clamp_octave(_scale_pitch(root_pc, scale_ints, deg, octave_base=60), 60, 86)
            # Only snap non-bent long sustain notes to chord/tension tone so bends stay authentic!
            if bend is None and dur >= 0.85 and (p % 12) not in chord_pcs:
                for shift in (1, -1, 2, -2):
                    if ((p + shift) % 12) in chord_pcs:
                        p += shift
                        break
            notes.append(_mk_note(p, base + pos, dur, vel + rng.randint(-3, 3), bend=bend))
    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    return notes, {
        "performanceType": "solo",
        "phraseArc": ["lyrical_entry", "syncopated_question", "high_neck_bend_climax", "warm_resolution"],
        "usesPitchBend": True,
    }


# =============================================================================
# 5. PERCUSSION PERFORMANCE INTELLIGENCE (Section 14 · TEST PC1, PC2, PC3)
# =============================================================================

def compose_percussion_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "syncopated_riff",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compose distinct GM Percussion layer (Shaker/Conga/Bongo/Rim/Tambourine/Cabasa) strictly in drum pocket gaps!"""
    rng = random.Random(seed)
    bpb = float(ctx.get("beatsPerBar", 4.0))
    notes: list[dict[str, Any]] = []
    swing = 0.028

    RIM = 37
    TAMB = 54
    BONGO_HI = 60
    BONGO_LO = 61
    CONGA_MUTE = 62
    CONGA_OPEN = 63
    CONGA_LO = 64
    CABASA = 69
    SHAKER = 70
    CLAVES = 75

    for bar in range(bars):
        base = start_beat_offset + bar * bpb

        # 1. Silky push-pull 16th/8th Shaker or Cabasa texture (sculpted groove envelope, NEVER mechanical!)
        if performance_type in ("subtle_layer", "syncopated_riff"):
            for i in range(16):
                pos = i * 0.25 + (swing * 0.55 if i % 2 == 1 else 0.0)
                # Leave breathing gaps on selected snare hits in syncopated_riff
                if performance_type == "syncopated_riff" and i in (4, 12) and bar % 2 == 1:
                    continue
                accent_map = [74, 42, 60, 48, 66, 40, 58, 52, 72, 44, 62, 50, 68, 42, 60, 54]
                vel = accent_map[i] + rng.randint(-5, 4)
                p = CABASA if (bar >= 4 and i % 4 == 2) else SHAKER
                notes.append(_mk_note(p, base + pos, 0.14, max(28, min(90, vel))))

        if performance_type == "subtle_layer":
            # Subtle conga + rim responses strictly in drum gaps (never clashing with snare 1.0/3.0)
            if bar % 2 == 0:
                notes.append(_mk_note(CONGA_MUTE, base + 0.75, 0.18, 66))
                notes.append(_mk_note(CONGA_OPEN, base + 1.5 + swing, 0.24, 72))
                notes.append(_mk_note(RIM, base + 2.75, 0.16, 58))
            else:
                notes.append(_mk_note(CONGA_MUTE, base + 0.5 + swing, 0.18, 64))
                notes.append(_mk_note(CONGA_LO, base + 2.25, 0.26, 74))
                notes.append(_mk_note(TAMB, base + 3.5 + swing, 0.28, 62))

        elif performance_type == "syncopated_riff":
            # Distinctive Neo-Soul / Afro-Latin interlocking conga + bongo + clave cross-rhythm!
            conga_bar = [
                [(0.5 + swing, CONGA_MUTE, 72), (0.75, CONGA_OPEN, 80), (1.75, CONGA_LO, 82), (2.25, BONGO_HI, 76), (2.75, BONGO_LO, 78), (3.5 + swing, CONGA_OPEN, 84)],
                [(0.25, BONGO_HI, 68), (0.75, CONGA_MUTE, 74), (1.5 + swing, CONGA_OPEN, 82), (2.5 + swing, CONGA_LO, 84), (3.25, BONGO_HI, 78), (3.75, BONGO_LO, 82)],
                [(0.5 + swing, CONGA_MUTE, 70), (1.25, CLAVES, 74), (1.75, CONGA_OPEN, 82), (2.25, CONGA_MUTE, 68), (2.75, CONGA_LO, 86), (3.5 + swing, BONGO_HI, 80)],
                [(0.5 + swing, CONGA_OPEN, 78), (1.5 + swing, BONGO_HI, 80), (1.75, BONGO_LO, 76), (2.5 + swing, CONGA_LO, 84), (3.25, BONGO_HI, 84), (3.5 + swing, CONGA_OPEN, 88), (3.75, CONGA_LO, 90)],
            ][bar % 4]
            for pos, p, v in conga_bar:
                notes.append(_mk_note(p, base + pos, 0.22, v + rng.randint(-4, 4)))
            # Subtle Tambourine shimmer on Bar 4 & Bar 8 turnarounds
            if bar in (3, 7):
                notes.append(_mk_note(TAMB, base + 3.0, 0.45, 72))

        else:
            # TEST PC3: Percussion Break / Solo feature
            seq = [
                (0.0, CONGA_OPEN, 88), (0.5 + swing, BONGO_HI, 80), (0.75, BONGO_LO, 84),
                (1.25, CONGA_MUTE, 74), (1.5 + swing, CONGA_LO, 90), (2.0, CLAVES, 82),
                (2.25, BONGO_HI, 86), (2.5 + swing, BONGO_HI, 78), (2.75, BONGO_LO, 88),
                (3.25, CONGA_OPEN, 92), (3.5 + swing, CONGA_LO, 94), (3.75, RIM, 84),
            ]
            for pos, p, v in seq:
                if bar % 2 == 1 and pos in (1.25, 2.5 + swing):
                    continue
                notes.append(_mk_note(p, base + pos, 0.20, v + rng.randint(-5, 5)))
            notes.append(_mk_note(SHAKER, base + 0.0, 0.20, 68))
            notes.append(_mk_note(TAMB, base + 2.0, 0.35, 72))

    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    return notes, {
        "performanceType": performance_type,
        "usesDrumKitKickSnare": False,
        "percussionVoices": ["shaker", "cabasa", "congas", "bongos", "claves", "tambourine", "rim"],
    }


# =============================================================================
# 6. SYNTH PERFORMANCE INTELLIGENCE
# =============================================================================

def compose_synth_performance(
    ctx: dict[str, Any],
    *,
    performance_type: str = "lead_solo",
    bars: int = 8,
    seed: int = 42,
    start_beat_offset: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compose expressive Analog Synth Lead Solo or Warm Textural Pad."""
    chord_tl, fallback, root_pc, scale_ints, bpb = _resolve_chords(ctx)
    notes: list[dict[str, Any]] = []

    if performance_type == "textural_pad":
        center = 69.0
        for bar in range(bars):
            base = start_beat_offset + bar * bpb
            _, c_root, c_ints, _ = chord_at_beat(base, chord_tl, fallback, bpb, root_pc)
            voicing = _build_rootless_voicing(c_root, c_ints, center, lo=60, hi=80)[:3]
            center = sum(voicing) / max(1, len(voicing))
            for p in voicing:
                notes.append(_mk_note(p, base + 0.0, bpb - 0.15, 62))
        return notes, {"performanceType": "textural_pad"}

    # lead_solo: reuse lyrical guitar solo phrasing shifted to synth sweet spot
    lead_notes, meta = compose_guitar_performance(
        ctx, performance_type="solo", bars=bars, seed=seed + 7, start_beat_offset=start_beat_offset
    )
    meta["performanceType"] = "lead_solo"
    return lead_notes, meta


# =============================================================================
# 7. STRUCTURED VARIATION ENGINE (Section 26)
# =============================================================================

def vary_layer_notes(
    notes: list[dict[str, Any]],
    *,
    role: str,
    intensity: str = "moderate",
    style_hint: str = "",
    ctx: dict[str, Any] | None = None,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply structured musical variation while preserving core groove/harmony identity."""
    rng = random.Random(seed)
    low = style_hint.lower()
    preserved: list[str] = ["key_and_chord_alignment", "base_tempo_grid"]
    changed: list[str] = []

    # If style explicitly asks for a new idiomatic style (e.g. "펑키하게", "독특한 퍼커션"), regenerate using target performer!
    if ctx is not None:
        if role == "guitar" and any(k in low for k in ("펑키", "funk", "리프", "riff", "뮤트")):
            bars = max(4, int(round(float((ctx.get("sectionRange") or {}).get("bars", 8)))))
            new_notes, _ = compose_guitar_performance(ctx, performance_type="funk_riff", bars=bars, seed=seed)
            return new_notes, {
                "variationType": "funk_syncopation",
                "intensity": intensity,
                "preservedElements": ["session_chord_timeline", "drums_and_bass_pocket"],
                "changedElements": ["guitar_phrasing_to_funk_muted_riff", "upper_triad_syncopation"],
            }
        if role == "percussion" and any(k in low for k in ("독특", "syncop", "리프", "unique", "poly", "콩가")):
            bars = max(4, int(round(float((ctx.get("sectionRange") or {}).get("bars", 8)))))
            new_notes, _ = compose_percussion_performance(ctx, performance_type="syncopated_riff", bars=bars, seed=seed)
            return new_notes, {
                "variationType": "rhythmic_variation",
                "intensity": intensity,
                "preservedElements": ["drums_pocket_unmodified", "tempo_and_bar_length"],
                "changedElements": ["interlocking_conga_bongo_claves_cross_rhythm"],
            }

    varied = deepcopy(notes)
    prob = {"subtle": 0.25, "moderate": 0.45, "creative": 0.65}.get(intensity, 0.45)

    if role in ("drums", "percussion"):
        preserved.append("core_backbeat_anchor")
        for n in varied:
            # Never erase Beat 1 Kick or Beat 2/4 main Snare!
            b_in_bar = n["startBeat"] % 4.0
            if n["pitch"] == 36 and b_in_bar < 0.08:
                continue
            if n["pitch"] == 38 and (abs(b_in_bar - 1.0) < 0.08 or abs(b_in_bar - 3.0) < 0.08) and n["velocity"] >= 80:
                continue
            if rng.random() < prob:
                n["velocity"] = max(28, min(118, int(n["velocity"]) + rng.randint(-12, 12)))
        changed.append("dynamic_velocity_contour_and_ghost_variation")
    else:
        preserved.append("harmonic_root_anchor")
        chord_tl, fallback, root_pc, scale_ints, bpb = _resolve_chords(ctx or {})
        for idx, n in enumerate(varied):
            if idx % 3 == 0:
                continue  # keep phrase anchors intact
            if rng.random() < prob:
                # Subtle rhythmic anticipation or ending ornament
                if n["startBeat"] >= 0.5 and rng.random() < 0.5:
                    n["startBeat"] = round(max(0.0, n["startBeat"] - 0.25), 4)
                    if "rhythmic_syncopation" not in changed:
                        changed.append("rhythmic_syncopation")
                elif role in ("keys", "guitar", "synth"):
                    # Keep harmonically compatible octave/chord-tone lift
                    _, c_root, c_ints, _ = chord_at_beat(n["startBeat"], chord_tl, fallback, bpb, root_pc)
                    chord_pcs = [(c_root + i) % 12 for i in c_ints]
                    cand = _nearest_pitch_for_pc(rng.choice(chord_pcs), int(n["pitch"]), 52, 84)
                    n["pitch"] = cand
                    if "chord_tone_interval_variation" not in changed:
                        changed.append("chord_tone_interval_variation")
        if not changed:
            changed.append("subtle_expressive_velocity_nuance")

    return varied, {
        "variationType": "structured_musical_variation",
        "intensity": intensity,
        "preservedElements": preserved,
        "changedElements": changed,
    }


# =============================================================================
# 8. BRIDGE & TRANSITION COMPOSER (Sections 27 & 28)
# =============================================================================

DEFAULT_BRIDGE_CHORDS_DM: list[dict[str, Any]] = [
    {"symbol": "Bbmaj9", "root": "Bb", "quality": "maj9", "startBeat": 0.0, "endBeat": 4.0, "locked": True},
    {"symbol": "A7sus4", "root": "A", "quality": "sus4", "startBeat": 4.0, "endBeat": 8.0, "locked": True},
    {"symbol": "Gm9", "root": "G", "quality": "min9", "startBeat": 8.0, "endBeat": 12.0, "locked": True},
    {"symbol": "A7", "root": "A", "quality": "dom7", "startBeat": 12.0, "endBeat": 16.0, "locked": True},
]


def compose_bridge_section(
    ctx: dict[str, Any],
    *,
    start_beat: float,
    bars: int = 4,
    seed: int = 520,
) -> dict[str, Any]:
    """Compose a genuinely contrasting Bridge (reharmonized harmony, halftime/intimate groove, related motif) + Transition!"""
    bpb = float(ctx.get("beatsPerBar", 4.0))
    rng = random.Random(seed)
    bridge_chords = [
        {
            **ev,
            "startBeat": round(start_beat + i * bpb, 4),
            "endBeat": round(start_beat + (i + 1) * bpb, 4),
        }
        for i, ev in enumerate(DEFAULT_BRIDGE_CHORDS_DM[:bars])
    ]
    # Build bridge-scoped context so performers follow the contrasting Bridge harmony!
    bridge_ctx = {
        **ctx,
        "chordTimeline": bridge_chords,
        "sectionRange": {"startBeats": start_beat, "endBeats": start_beat + bars * bpb, "bars": bars},
    }

    # 1. Intimate contrasting Drums (rimshot pocket + sparse deep kick + gentle shaker/ride, ending with turnaround fill back to Main!)
    drum_notes: list[dict[str, Any]] = []
    for bar in range(bars):
        base = bar * bpb  # clip-relative!
        # Bar 1: warm crash/ride wash + halftime breath
        if bar == 0:
            drum_notes.append(_mk_note(49, base + 0.0, 1.2, 68))
        # Sparse deep kick
        for k in ([0.0, 2.5] if bar < bars - 1 else [0.0, 1.5]):
            drum_notes.append(_mk_note(36, base + k, 0.28, rng.randint(92, 102)))
        # Rimshot cross-stick pocket instead of heavy snare (instant emotional contrast!)
        drum_notes.append(_mk_note(37, base + 1.0 + 0.022, 0.20, rng.randint(76, 86)))
        if bar < bars - 1:
            drum_notes.append(_mk_note(37, base + 3.0 + 0.022, 0.20, rng.randint(80, 90)))
            drum_notes.append(_mk_note(38, base + 1.75, 0.12, 38))
        # Breathing ride/hat
        for s in range(4):
            drum_notes.append(_mk_note(51, base + s * 1.0, 0.35, 62 if s % 2 == 0 else 48))
        if bar == bars - 1:
            # Lift fill returning cleanly to main groove
            for pos, p, v in [(2.5, 38, 72), (2.75, 38, 82), (3.0, 48, 88), (3.25, 45, 90), (3.5, 41, 96), (3.75, 46, 82)]:
                drum_notes.append(_mk_note(p, base + pos, 0.18, v))

    # 2. Melodic Bridge Bass (smooth long sustained anchors + passing chromatic climb on Bar 4)
    bass_abs, _ = compose_bass_performance(bridge_ctx, performance_type="melodic_bassline", bars=bars, seed=seed + 1, start_beat_offset=start_beat)
    bass_notes = [{**n, "startBeat": round(n["startBeat"] - start_beat, 4)} for n in bass_abs]

    # 3. Spacious lush Rhodes Bridge chords (wide rolled chords with breathing space)
    keys_abs, _ = compose_keys_performance(bridge_ctx, performance_type="neo_soul_comping", bars=bars, seed=seed + 2, start_beat_offset=start_beat)
    keys_notes = [{**n, "startBeat": round(n["startBeat"] - start_beat, 4)} for n in keys_abs]

    # 4. Motif-connected lyrical Clean Guitar Bridge melody (same DNA, new harmonic color!)
    gtr_abs, _ = compose_guitar_performance(bridge_ctx, performance_type="clean_melodic", bars=bars, seed=seed + 3, start_beat_offset=start_beat)
    gtr_notes = [{**n, "startBeat": round(n["startBeat"] - start_beat, 4)} for n in gtr_abs]

    # 5. Subtle Bridge Percussion (delicate shaker/conga breath)
    perc_notes, _ = compose_percussion_performance(bridge_ctx, performance_type="subtle_layer", bars=bars, seed=seed + 4, start_beat_offset=0.0)

    return {
        "startBeat": start_beat,
        "endBeat": start_beat + bars * bpb,
        "bars": bars,
        "bridgeChords": bridge_chords,
        "contrastSummary": {
            "harmonyContrast": "Main (Dm9 -> G13 -> Cmaj9 -> A7) -> Bridge (Bbmaj9 -> A7sus4 -> Gm9 -> A7)",
            "grooveContrast": "Full laid-back snare pocket -> Intimate rimshot + ride breathing space -> Bar 4 turnaround fill",
            "motifContinuity": "Clean guitar & melodic bass preserve D-dorian late-night motif DNA over fresh VI-V-iv-V lift",
        },
        "layerClips": {
            "drums": drum_notes,
            "bass": bass_notes,
            "keys": keys_notes,
            "guitar": gtr_notes,
            "percussion": perc_notes,
        },
    }


def compose_transition_pickup(
    ctx: dict[str, Any],
    *,
    boundary_beat: float,
    seed: int = 530,
) -> dict[str, Any]:
    """Compose a real 2-beat musical transition (drum turnaround fill + bass pickup + passing chord) into `boundary_beat`."""
    chord_tl, fallback, root_pc, _, bpb = _resolve_chords(ctx)
    _, target_root, _, _ = chord_at_beat(boundary_beat, chord_tl, fallback, bpb, root_pc)
    target_bass = _clamp_octave(36 + target_root, 36, 48)
    pickup_start = max(0.0, boundary_beat - 2.0)

    # Clip-relative to pickup_start (2.0 beats duration ending right at boundary_beat!)
    drum_fill = [
        _mk_note(38, 0.25, 0.16, 68),
        _mk_note(38, 0.50, 0.16, 78),
        _mk_note(38, 0.75, 0.16, 86),
        _mk_note(48, 1.00, 0.18, 88),
        _mk_note(45, 1.25, 0.18, 92),
        _mk_note(41, 1.50, 0.20, 96),
        _mk_note(46, 1.75, 0.24, 82),
    ]
    bass_pickup = [
        _mk_note(max(36, target_bass - 3), 0.75, 0.35, 76),
        _mk_note(max(36, target_bass - 2), 1.25, 0.35, 84),
        _mk_note(max(36, target_bass - 1), 1.65, 0.32, 92, bend=-1.0),
    ]
    return {
        "startBeat": pickup_start,
        "endBeat": boundary_beat,
        "durationBeats": 2.0,
        "drumFillNotes": drum_fill,
        "bassPickupNotes": bass_pickup,
        "descriptionKo": f"{boundary_beat / bpb + 1:.0f}마디 진입 직전 2박 드럼 턴어라운드 필인 + 크로매틱 베이스 픽업 전환 생성",
    }
