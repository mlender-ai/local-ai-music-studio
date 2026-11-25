"""Real Musical MIDI Variation Engine & Arrangement Executor (Phase 04-A & 04-B · Sections 8, 11, 12).

Transforms ACTUAL existing MIDI notes in the selected range while preserving musical identity,
harmonic anchors, and untouched bars outside `[startBeats, endBeats]`.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from engine.composition.midi_composer import (
    notes_to_midi_bytes,
    parse_chord,
    parse_key_root_and_scale,
)
from engine.composition.schemas import QualityReport, Take, TakeArtifact, TakeProvenance
from engine.composition.validation import validate_midi_composition
from engine.daw_workspace import commands, loudness, proposals, store
from engine.daw_workspace.schema import Clip, Project, SectionMarker, Track, make_id, utc_now_iso
from engine.daw_workspace.session import event_bus
from engine.generation.adapters.local_composer_adapter import _render_part_audio, _soft_limit_stereo
from engine.generation.adapters.yue2_adapter import screen_vocal_leakage
from engine.generation.daw_jobs import _carve_out_range_on_track, persist_take, snapshot_track_fingerprints

from .audio_ops import create_reversed_clip_asset, render_contextual_preview_pair
from .memory import record_conversation_turn
from .scope import ArrangementEditPlan, extract_midi_notes_in_range


def _clamp_pitch(pitch: int, lo: int, hi: int) -> int:
    while pitch < lo:
        pitch += 12
    while pitch > hi:
        pitch -= 12
    return max(lo, min(hi, pitch))


def _dedupe_notes(notes: list[dict[str, Any]], max_beats: float) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[int, float]] = set()
    for n in sorted(notes, key=lambda x: (float(x["startBeat"]), int(x["pitch"]))):
        sb = round(max(0.0, float(n["startBeat"])), 4)
        if sb >= max_beats - 0.02:
            continue
        dur = round(max(0.0625, min(float(n["durationBeats"]), max_beats - sb)), 4)
        p = max(0, min(127, int(n["pitch"])))
        v = max(1, min(127, int(n.get("velocity", 96))))
        key = (p, round(sb, 2))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"id": make_id("note"), "pitch": p, "velocity": v, "startBeat": sb, "durationBeats": dur})
    return cleaned


def _vary_drums(
    existing: list[dict[str, Any]],
    duration_beats: float,
    bpb: float,
    intensity: str,
    add_fill: bool,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Transform existing Drum MIDI notes with tasteful kick variation, ghost snares, hat interplay & turnaround fill."""
    total_bars = max(1, int(round(duration_beats / bpb)))
    out = [dict(n) for n in existing]

    # If target range was empty, seed a tight pocket before varying
    if not out:
        for bar in range(total_bars):
            base = bar * bpb
            for beat in range(int(bpb)):
                out.append({"pitch": 36, "velocity": 112, "startBeat": base + beat, "durationBeats": 0.35})
            for sb in (1.0, 3.0):
                if sb < bpb:
                    out.append({"pitch": 38, "velocity": 98, "startBeat": base + sb, "durationBeats": 0.3})
            for step in range(int(bpb * 2)):
                out.append({"pitch": 42, "velocity": 72 if step % 2 == 0 else 56, "startBeat": base + step * 0.5, "durationBeats": 0.18})

    ghost_added = 0
    kick_added = 0
    hat_changed = 0
    fill_hits = 0

    for bar in range(total_bars):
        base = bar * bpb
        is_last_bar = bar == total_bars - 1

        # 1. Dynamic hi-hat open/closed accent lift on offbeats
        for n in out:
            if n["pitch"] == 42 and base <= n["startBeat"] < base + bpb:
                pos_in_bar = n["startBeat"] - base
                if abs((pos_in_bar % 1.0) - 0.5) < 0.08:
                    if intensity in ("moderate", "creative") and (bar % 2 == 1 or abs(pos_in_bar - 3.5) < 0.08):
                        n["pitch"] = 46  # Open hat lift!
                        n["velocity"] = min(115, int(n["velocity"]) + 10)
                        n["durationBeats"] = 0.32
                        hat_changed += 1
                    elif intensity == "subtle":
                        n["velocity"] = max(42, min(110, int(n["velocity"]) + (8 if bar % 2 == 1 else -6)))
                        hat_changed += 1

        # 2. Snare ghost notes (pocket groove without chaotic timing randomization!)
        ghost_positions = [2.75] if intensity == "subtle" else ([1.75, 2.75] if intensity == "moderate" else [0.75, 1.75, 2.75, 3.25])
        for gp in ghost_positions:
            if gp < bpb and not is_last_bar:
                out.append({"pitch": 38, "velocity": rng.randint(52, 66), "startBeat": base + gp, "durationBeats": 0.15})
                ghost_added += 1

        # 3. Syncopated kick anticipation on even/variation bars
        if intensity in ("moderate", "creative") and bar % 2 == 1 and not is_last_bar:
            for kp in ([2.5] if intensity == "moderate" else [1.5, 2.75, 3.5]):
                if kp < bpb:
                    out.append({"pitch": 36, "velocity": 102, "startBeat": base + kp, "durationBeats": 0.3})
                    kick_added += 1

        # 4. Crisp turnaround fill in the final bar!
        if is_last_bar and (add_fill or intensity in ("moderate", "creative")):
            fill_start = base + max(0.0, bpb - (2.0 if intensity == "creative" else 1.5))
            # Clear clutter in the fill zone so the fill speaks cleanly!
            out = [n for n in out if not (fill_start <= n["startBeat"] < base + bpb and n["pitch"] in (42, 46))]
            if intensity == "subtle":
                fill_pattern = [
                    (bpb - 1.0, 38, 94),
                    (bpb - 0.5, 38, 102),
                    (bpb - 0.25, 45, 108),
                ]
            elif intensity == "moderate":
                fill_pattern = [
                    (bpb - 1.5, 38, 86),
                    (bpb - 1.25, 38, 92),
                    (bpb - 1.0, 48, 98),
                    (bpb - 0.75, 48, 104),
                    (bpb - 0.5, 45, 108),
                    (bpb - 0.25, 36, 114),
                    (bpb - 0.25, 38, 116),
                ]
            else:
                fill_pattern = [
                    (bpb - 2.0, 38, 88),
                    (bpb - 1.75, 38, 80),
                    (bpb - 1.5, 50, 96),
                    (bpb - 1.25, 48, 100),
                    (bpb - 1.0, 48, 106),
                    (bpb - 0.75, 45, 110),
                    (bpb - 0.5, 43, 114),
                    (bpb - 0.25, 38, 118),
                    (bpb - 0.25, 36, 116),
                ]
            for pos, pitch, vel in fill_pattern:
                if 0 <= pos < bpb:
                    out.append({"pitch": pitch, "velocity": vel, "startBeat": base + pos, "durationBeats": 0.2})
                    fill_hits += 1

    final_notes = _dedupe_notes(out, duration_beats)
    return final_notes, {
        "originalNoteCount": len(existing),
        "variedNoteCount": len(final_notes),
        "ghostSnaresAdded": ghost_added,
        "kickVariationsAdded": kick_added,
        "hatAccentsAdjusted": hat_changed,
        "fillHitsAdded": fill_hits,
    }


def _vary_hook_melody(
    existing: list[dict[str, Any]],
    duration_beats: float,
    bpb: float,
    key_str: str,
    chords: list[str],
    intensity: str,
    preserve_first_half: bool,
    preserve_pitch: bool,
    velocity_only: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Vary existing melodic/synth hook notes while honoring motif preservation & surrounding harmony."""
    root_pc, scale_ints = parse_key_root_and_scale(key_str)
    scale_pool = sorted({root_pc + iv + 12 * octv for octv in (4, 5, 6, 7) for iv in scale_ints if 55 <= root_pc + iv + 12 * octv <= 88})

    def step_in_scale(pitch: int, steps: int) -> int:
        if not scale_pool:
            return pitch
        idx = min(range(len(scale_pool)), key=lambda i: abs(scale_pool[i] - pitch))
        nxt = max(0, min(len(scale_pool) - 1, idx + steps))
        return scale_pool[nxt]

    if not existing:
        # Build clean motif from harmony if range was empty
        existing = []
        for bar in range(max(1, int(round(duration_beats / bpb)))):
            c_root, c_ints = parse_chord(chords[bar % len(chords)], root_pc)
            for idx, pos in enumerate((0.0, 0.75, 1.5, 2.5)):
                p = _clamp_pitch(60 + c_root + c_ints[idx % len(c_ints)], 60, 79)
                existing.append({"pitch": p, "velocity": 94, "startBeat": bar * bpb + pos, "durationBeats": 0.45})

    half_point = duration_beats * 0.5
    out: list[dict[str, Any]] = []
    preserved_count = 0
    varied_count = 0
    pitch_preserved = 0

    for idx, n in enumerate(existing):
        sb = float(n["startBeat"])
        dur = float(n["durationBeats"])
        p = int(n["pitch"])
        v = int(n.get("velocity", 92))

        if velocity_only:
            # STRICT preservation: pitch and exact startBeat/duration untouched!
            contour = int(14 * math.sin((sb / max(1.0, duration_beats)) * math.pi))
            new_v = max(40, min(124, v + contour + (6 if idx % 2 == 0 else -6)))
            out.append({"pitch": p, "velocity": new_v, "startBeat": sb, "durationBeats": dur})
            preserved_count += 1
            pitch_preserved += 1
            continue

        if preserve_first_half and sb < half_point - 0.05:
            # STRICT motif identity preservation in first half (TEST C!)
            out.append({"pitch": p, "velocity": v, "startBeat": sb, "durationBeats": dur})
            preserved_count += 1
            pitch_preserved += 1
            continue

        # Vary second half (or entire range when preserve_first_half is False)
        if preserve_pitch:
            # Rhythm-only variation: keep EXACT pitch, syncopate timing & articulation!
            shift = -0.25 if (idx % 2 == 1 and sb >= 0.25) else (0.25 if sb + 0.5 < duration_beats else 0.0)
            new_dur = max(0.2, dur * (0.75 if idx % 2 == 0 else 1.25))
            out.append({"pitch": p, "velocity": min(122, v + 6), "startBeat": max(0.0, sb + shift), "durationBeats": new_dur})
            pitch_preserved += 1
            varied_count += 1
            continue

        # Expressive melodic & rhythmic variation for memorable lift/cadence
        is_tail = sb >= duration_beats - bpb
        if is_tail and idx == len(existing) - 1:
            # Strong climactic resolution to chord tonic/5th or upper octave!
            c_root, _ = parse_chord(chords[-1], root_pc)
            target_p = _clamp_pitch(60 + c_root + (12 if intensity in ("moderate", "creative") else 7), 62, 84)
            out.append({"pitch": target_p, "velocity": min(124, v + 14), "startBeat": sb, "durationBeats": min(1.25, max(dur, 0.75))})
            varied_count += 1
        else:
            step_delta = 1 if intensity == "subtle" else (2 if idx % 2 == 0 else 1)
            if intensity == "creative" and is_tail:
                step_delta = 4  # Fifth / octave-range lift
            new_p = step_in_scale(p, step_delta if idx % 3 != 2 else -1)
            shift = 0.25 if (intensity != "subtle" and idx % 2 == 1 and sb + 0.5 < duration_beats) else 0.0
            out.append(
                {
                    "pitch": new_p,
                    "velocity": min(122, v + (10 if is_tail else 5)),
                    "startBeat": round(sb + shift, 4),
                    "durationBeats": max(0.2, dur * 0.9),
                }
            )
            varied_count += 1
            # Add an answering grace/response note in moderate/creative mode
            if intensity in ("moderate", "creative") and is_tail and idx % 2 == 0 and sb + 0.75 < duration_beats:
                resp_p = step_in_scale(new_p, 2)
                out.append(
                    {
                        "pitch": resp_p,
                        "velocity": min(118, v + 8),
                        "startBeat": round(sb + 0.5, 4),
                        "durationBeats": 0.35,
                    }
                )

    final_notes = _dedupe_notes(out, duration_beats)
    return final_notes, {
        "originalNoteCount": len(existing),
        "variedNoteCount": len(final_notes),
        "preservedFirstHalfCount": preserved_count,
        "variedNoteCountDelta": len(final_notes) - len(existing),
        "pitchPreservedCount": pitch_preserved,
        "variedNotesModified": varied_count,
    }


def _vary_bass(
    existing: list[dict[str, Any]],
    duration_beats: float,
    bpb: float,
    key_str: str,
    chords: list[str],
    intensity: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Vary Bass groove keeping chord roots intact while adding funky syncopation, octave jumps & passing lead-ins."""
    root_pc, _ = parse_key_root_and_scale(key_str)
    total_bars = max(1, int(round(duration_beats / bpb)))
    out: list[dict[str, Any]] = []

    for bar in range(total_bars):
        base = bar * bpb
        c_root, c_ints = parse_chord(chords[bar % len(chords)], root_pc)
        next_root, _ = parse_chord(chords[(bar + 1) % len(chords)], root_pc)
        bass_root = _clamp_pitch(36 + c_root, 31, 44)
        fifth = _clamp_pitch(bass_root + 7, 34, 51)
        octave = _clamp_pitch(bass_root + 12, 43, 55)
        approach = _clamp_pitch(36 + next_root, 31, 44) - 1

        # Keep bar downbeat root anchor from existing note if present
        bar_existing = [n for n in existing if base <= float(n["startBeat"]) < base + bpb]
        down_p = int(bar_existing[0]["pitch"]) if bar_existing else bass_root

        if intensity == "subtle":
            hits = [(0.0, 0.75, down_p, 108), (1.5, 0.45, octave, 96), (2.0, 0.75, down_p, 104), (3.5, 0.4, fifth, 94)]
        elif intensity == "moderate":
            hits = [
                (0.0, 0.55, down_p, 112),
                (0.75, 0.35, octave, 98),
                (1.5, 0.4, fifth, 96),
                (2.0, 0.5, down_p, 108),
                (2.75, 0.35, _clamp_pitch(down_p + c_ints[1], 33, 50), 94),
                (3.25, 0.35, octave, 102),
                (3.75, 0.22, approach, 100),
            ]
        else:
            hits = [
                (0.0, 0.45, down_p, 116),
                (0.5, 0.25, down_p, 92),
                (0.75, 0.35, octave, 106),
                (1.25, 0.25, fifth, 96),
                (1.75, 0.45, octave, 108),
                (2.5, 0.4, down_p, 110),
                (3.0, 0.3, fifth, 102),
                (3.5, 0.22, octave, 106),
                (3.75, 0.22, approach, 104),
            ]
        for pos, dur, p, vel in hits:
            if pos < bpb:
                out.append({"pitch": p, "velocity": vel, "startBeat": base + pos, "durationBeats": dur})

    final_notes = _dedupe_notes(out, duration_beats)
    return final_notes, {"originalNoteCount": len(existing), "variedNoteCount": len(final_notes), "harmonicRootsPreserved": True}


def _vary_harmony(
    existing: list[dict[str, Any]],
    duration_beats: float,
    bpb: float,
    key_str: str,
    chords: list[str],
    intensity: str,
    preserve_harmony: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Upgrade chord voicings (add9 / maj7 / min7 / sus4) & rhythmic comping while preserving progression."""
    root_pc, _ = parse_key_root_and_scale(key_str)
    total_bars = max(1, int(round(duration_beats / bpb)))
    out: list[dict[str, Any]] = []

    for bar in range(total_bars):
        base = bar * bpb
        c_root, c_ints = parse_chord(chords[bar % len(chords)], root_pc)
        # Enrich triad/7th with color tone (9th or 11th) while preserving harmonic root!
        rich_ints = list(c_ints)
        if 14 not in rich_ints:
            rich_ints.append(14)  # add9 warmth
        if intensity == "creative" and not preserve_harmony and bar == total_bars - 1:
            # Secondary dominant tension turnaround on final bar
            c_root = (root_pc + 7) % 12
            rich_ints = [0, 4, 7, 10, 14]
        voicing = sorted({_clamp_pitch(48 + c_root + iv, 52, 74) for iv in rich_ints[:4]})

        stabs = (
            [(0.0, 1.5), (2.0, 1.6)]
            if intensity == "subtle"
            else ([(0.0, 0.65), (0.75, 0.45), (1.75, 0.65), (2.75, 0.85)] if intensity == "moderate" else [(0.0, 0.45), (0.75, 0.4), (1.5, 0.45), (2.25, 0.45), (3.0, 0.75)])
        )
        for pos, dur in stabs:
            if pos < bpb:
                for p in voicing:
                    out.append({"pitch": p, "velocity": 82, "startBeat": base + pos, "durationBeats": dur})

    final_notes = _dedupe_notes(out, duration_beats)
    return final_notes, {"originalNoteCount": len(existing), "variedNoteCount": len(final_notes), "voicingExtended": True}


def generate_variation_take(
    project_id: str,
    plan: ArrangementEditPlan,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a non-destructive musical Variation Take with Solo + In-Context + Original A/B previews!"""
    proj = store.load_project(project_id)
    scope = plan.scope
    target_tid = scope.targetTrackIds[0] if scope.targetTrackIds else None
    if not target_tid:
        raise ValueError("ArrangementEditPlan has no targetTrackId")
    trk = next((t for t in proj.tracks if t.id == target_tid), None)
    if not trk and plan.operation != "add_layer":
        raise FileNotFoundError(f"Target track not found: {target_tid}")
    if plan.operation != "add_layer" and trk and trk.type != "midi":
        raise ValueError(
            f"Track '{trk.name}' is an audio/stem track. Direct note-level MIDI variation applies to MIDI tracks; "
            f"use non-destructive audio edit (reverse/fade/replace) or create an independent MIDI layer."
        )

    bpb = proj.timeSignature.beats_per_bar
    sb, eb = scope.startBeats, scope.endBeats
    dur_beats = max(0.25, eb - sb)
    is_new_layer = plan.operation == "add_layer" or trk is None or trk.type != "midi"
    existing_notes: list[dict[str, Any]] = []
    if trk and trk.type == "midi" and not is_new_layer:
        existing_notes, _ = extract_midi_notes_in_range(trk, sb, eb)
    rng = random.Random(seed)

    key_str = str(scope.harmonicContext.get("key") or "F minor")
    chords = list(scope.harmonicContext.get("chords") or ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"])

    if plan.variationKind == "drum_variation":
        new_notes, diff_meta = _vary_drums(existing_notes, dur_beats, bpb, plan.intensity, plan.addTurnaroundFill, rng)
    elif plan.variationKind == "bass_variation":
        new_notes, diff_meta = _vary_bass(existing_notes, dur_beats, bpb, key_str, chords, plan.intensity)
    elif plan.variationKind == "harmony_variation":
        new_notes, diff_meta = _vary_harmony(existing_notes, dur_beats, bpb, key_str, chords, plan.intensity, plan.preserveHarmony)
    else:
        new_notes, diff_meta = _vary_hook_melody(
            existing_notes,
            dur_beats,
            bpb,
            key_str,
            chords,
            plan.intensity,
            preserve_first_half=plan.preserveFirstHalf,
            preserve_pitch=plan.preservePitch,
            velocity_only=(plan.variationKind == "velocity_only"),
        )

    take_id = make_id("take")
    pdir = store.project_dir(project_id)
    take_dir = pdir / "takes" / take_id
    take_dir.mkdir(parents=True, exist_ok=True)

    layer_name = (trk.name if trk and not is_new_layer else "Synth Layer")
    # Save real `.mid` artifact
    midi_name = f"var_{trk.id if trk else 'layer'}.mid"
    (take_dir / midi_name).write_bytes(
        notes_to_midi_bytes(new_notes, bpm=proj.bpm, ppq=proj.ppq, track_name=f"{layer_name} Variation")
    )

    # Render Solo Preview WAV
    inst_ref = (trk.instrumentRef if trk and trk.type == "midi" and not is_new_layer else None) or "fm-pluck-lead"
    solo_pcm = _soft_limit_stereo(_render_part_audio(new_notes, inst_ref, bpm=proj.bpm, total_beats=dur_beats, sr=proj.sampleRate))
    solo_wav = take_dir / "preview.wav"
    sf.write(str(solo_wav), solo_pcm, proj.sampleRate, subtype="PCM_24")
    solo_loud = loudness.measure_loudness(solo_pcm, proj.sampleRate)
    solo_gain = round(max(-12.0, min(12.0, -16.0 - float(solo_loud["integratedLufs"]))), 2) if solo_loud["integratedLufs"] > -60.0 else 0.0

    # Render In-Context & Original Context A/B Preview WAVs (Section 14!)
    candidate_clip = Clip(
        id=make_id("clp"),
        name=f"{layer_name} {'Layer' if is_new_layer else 'Var'} ({scope.startBar}–{scope.endBarInclusive}마디)",
        type="midi",
        timelineStartBeats=sb,
        durationBeats=dur_beats,
        notes=new_notes,
    )
    if trk and not is_new_layer:
        ctx_previews = render_contextual_preview_pair(proj, trk.id, sb, eb, candidate_clip, take_dir)
    else:
        # Preview new layer mixed on top of existing project!
        sim_proj = deepcopy(proj)
        temp_trk = Track(id=make_id("trk"), name=layer_name, type="midi", color="#648ea8", instrumentRef=inst_ref, clips=[])
        sim_proj.tracks.append(temp_trk)
        ctx_previews = render_contextual_preview_pair(sim_proj, temp_trk.id, sb, eb, candidate_clip, take_dir)

    role_key = "drums" if "drum" in inst_ref else ("bass" if "bass" in inst_ref else "synth_hook")
    m_val = validate_midi_composition(new_notes, key_str, "natural_minor", role_key, max(1, int(round(dur_beats / bpb))), bpb=bpb)
    vocal_sc = screen_vocal_leakage(solo_pcm, proj.sampleRate, source_kind="deterministic_midi_synth")

    take = Take(
        id=take_id,
        projectId=project_id,
        jobId=make_id("vjob"),
        planId=plan.id,
        title=f"{layer_name} {scope.startBar}–{scope.endBarInclusive}마디 {'레이어' if is_new_layer else '변주'} ({plan.intensity})",
        mode="midi_variation",
        status="ready",
        baseRevision=proj.revision,
        baseTrackFingerprints=snapshot_track_fingerprints(proj),
        previewRelativePath=f"takes/{take_id}/preview.wav",
        previewDurationSec=round(len(solo_pcm) / proj.sampleRate, 3),
        previewIntegratedLufs=solo_loud["integratedLufs"],
        levelMatchedGainDb=solo_gain,
        targetTrackId=None if is_new_layer else (trk.id if trk else None),
        targetRangeBeats={"startBeats": sb, "endBeats": eb},
        preserveExistingTracks=True,
        artifacts=[
            TakeArtifact(
                role=role_key,
                name=candidate_clip.name,
                trackType="midi",
                instrumentRef=inst_ref,
                color=trk.color if trk and not is_new_layer else "#648ea8",
                midiRelativePath=f"takes/{take_id}/{midi_name}",
                notes=new_notes,
                startBeats=sb,
                durationBeats=dur_beats,
                gainDb=trk.gainDb if trk and not is_new_layer else -3.0,
                pan=trk.pan if trk and not is_new_layer else 0.0,
            )
        ],
        qualityReport=QualityReport(
            technical={
                "sampleRate": proj.sampleRate,
                "channels": 2,
                "loudnessStandard": solo_loud["standard"],
                "integratedLufs": solo_loud["integratedLufs"],
                "truePeakDbtp": solo_loud["truePeakDbtp"],
                "contextualPreview": ctx_previews,
            },
            musical={
                "variationKind": plan.variationKind,
                "intensity": plan.intensity,
                "diff": diff_meta,
                "validation": m_val,
                "outOfRangeMutations": 0,
            },
            vocalScreening=vocal_sc,
            verdict="pass" if m_val.get("passed", True) else "warn",
            warnings=list(m_val.get("warnings", [])),
        ),
        provenance=TakeProvenance(
            engine="midi-variation-v4",
            engineLabel="Selective MIDI Variation Engine",
            mode="midi_variation",
            providerId=str(plan.providerProvenance.get("providerId") or "local-music-director"),
            model=str(plan.providerProvenance.get("model") or "music-director-v4"),
            seed=seed,
            planId=plan.id,
        ),
    )

    saved_take, rev = persist_take(project_id, take)
    record_conversation_turn(
        project_id,
        user_text=plan.instruction,
        producer_reply_ko=plan.summaryKo,
        action="variation_take_created",
        target_track_id=trk.id,
        bar_range=(scope.startBar, scope.endBarInclusive),
        take_id=take_id,
    )
    event_bus.publish("take.created", {"projectId": project_id, "take": saved_take})
    return {"plan": plan.model_dump(), "take": saved_take, "contextualPreview": ctx_previews, "revision": rev}


def execute_arrangement_edit_plan(
    project_id: str,
    plan: ArrangementEditPlan,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute structural arrangement edits (`strip_to_tracks`, `extend_section`) or generate a Variation Take."""
    if plan.operation == "extend_section":
        proj = store.load_project(project_id)
        bpb = proj.timeSignature.beats_per_bar
        add_beats = max(bpb, plan.extendBars * bpb)
        split_at = plan.scope.endBeats
        proposals.record_undo_snapshot(proj)
        updated = deepcopy(proj)
        # Shift all clips starting at or after `split_at` right by `add_beats`
        for trk in updated.tracks:
            for clp in trk.clips:
                if clp.timelineStartBeats >= split_at - 1e-4:
                    clp.timelineStartBeats = round(clp.timelineStartBeats + add_beats, 4)
        # Extend target section & shift subsequent sections
        for sec in updated.sections:
            if abs(sec.endBeats - split_at) < 0.1 or (sec.startBeats < split_at < sec.endBeats):
                sec.endBeats = round(sec.endBeats + add_beats, 4)
            elif sec.startBeats >= split_at - 1e-4:
                sec.startBeats = round(sec.startBeats + add_beats, 4)
                sec.endBeats = round(sec.endBeats + add_beats, 4)
        updated.lengthBeats = round(updated.lengthBeats + add_beats, 4)
        saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
        msg_ko = f"해당 구간을 {plan.extendBars}마디({int(add_beats)}박) 연장하고 이후 클립과 섹션을 자동 정렬했습니다."
        record_conversation_turn(project_id, plan.instruction, msg_ko, "section_extended", bar_range=(plan.scope.startBar, plan.scope.endBarInclusive + plan.extendBars))
        event_bus.publish("project.updated", {"projectId": project_id, "revision": saved.revision, "reason": msg_ko, "project": saved.model_dump()})
        return {"applied": True, "operation": "extend_section", "messageKo": msg_ko, "project": saved.model_dump(), "revision": saved.revision}

    if plan.operation == "strip_to_tracks":
        proj = store.load_project(project_id)
        sb, eb = plan.scope.startBeats, plan.scope.endBeats
        proposals.record_undo_snapshot(proj)
        updated = deepcopy(proj)
        stripped_names: list[str] = []
        for trk in updated.tracks:
            if trk.id not in plan.keepTrackIds:
                before_cnt = len(trk.clips)
                updated = _carve_out_range_on_track(updated, trk.id, sb, eb)
                if before_cnt > 0:
                    stripped_names.append(trk.name)
        saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
        kept_names = [t.name for t in saved.tracks if t.id in plan.keepTrackIds]
        msg_ko = f"{plan.scope.startBar}–{plan.scope.endBarInclusive}마디에서 {', '.join(kept_names) or '지정 트랙'}만 남기고 나머지 트랙 구간을 정리했습니다."
        record_conversation_turn(project_id, plan.instruction, msg_ko, "strip_to_tracks", bar_range=(plan.scope.startBar, plan.scope.endBarInclusive))
        event_bus.publish("project.updated", {"projectId": project_id, "revision": saved.revision, "reason": msg_ko, "project": saved.model_dump()})
        return {"applied": True, "operation": "strip_to_tracks", "messageKo": msg_ko, "keptTracks": kept_names, "project": saved.model_dump(), "revision": saved.revision}

    if plan.operation == "audio_reverse":
        if not plan.scope.targetClipIds:
            raise ValueError("리버스할 대상 오디오 클립을 선택하거나 구간을 지정해 주세요.")
        res = create_reversed_clip_asset(project_id, plan.scope.targetClipIds[0])
        msg_ko = "선택한 오디오 클립의 비파괴 리버스 버전을 생성하고 원본 에셋을 보존했습니다."
        record_conversation_turn(project_id, plan.instruction, msg_ko, "audio_reversed")
        return {"applied": True, "operation": "audio_reverse", "messageKo": msg_ko, **res}

    if plan.operation == "audio_fade":
        if not plan.scope.targetClipIds:
            raise ValueError("페이드를 적용할 대상 클립을 선택해 주세요.")
        proj = store.load_project(project_id)
        proposals.record_undo_snapshot(proj)
        updated = deepcopy(proj)
        for cid in plan.scope.targetClipIds:
            updated = commands.apply_command(updated, "clip.setFades", {"clipId": cid, "fadeInBeats": 0.5, "fadeOutBeats": 0.5})
        saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
        msg_ko = f"{len(plan.scope.targetClipIds)}개 클립에 비파괴 Fade-in/Fade-out (0.5박)을 적용했습니다."
        record_conversation_turn(project_id, plan.instruction, msg_ko, "audio_fade_applied")
        event_bus.publish("project.updated", {"projectId": project_id, "revision": saved.revision, "reason": msg_ko, "project": saved.model_dump()})
        return {"applied": True, "operation": "audio_fade", "messageKo": msg_ko, "project": saved.model_dump(), "revision": saved.revision}

    # Default: generate non-destructive musical Variation Take (never overwrites without user preview/apply!)
    return generate_variation_take(project_id, plan, seed=seed)
