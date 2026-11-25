"""EditScope & ArrangementEditPlan builder reading actual MIDI/clip context (Phase 04-A · Section 6)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.daw_workspace.schema import Project, Track, make_id, utc_now_iso
from engine.providers import invoke_llm_json

from .memory import ensure_music_memory, resolve_contextual_reference


class ArrModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class EditScope(ArrModel):
    projectId: str
    baseRevision: int
    targetTrackIds: list[str] = Field(default_factory=list)
    targetClipIds: list[str] = Field(default_factory=list)
    startBeats: float = Field(ge=0.0)
    endBeats: float = Field(gt=0.0)
    startBar: int = Field(ge=1)
    endBarInclusive: int = Field(ge=1)
    selectionType: Literal["range", "clip", "section", "track"] = "range"
    requestedOperation: str = "replace_range"
    preservedTrackIds: list[str] = Field(default_factory=list)
    preservedSections: list[str] = Field(default_factory=list)
    harmonicContext: dict[str, Any] = Field(default_factory=dict)
    adjacentContext: dict[str, Any] = Field(default_factory=dict)


class ArrangementEditPlan(ArrModel):
    id: str = Field(default_factory=lambda: make_id("aedit"))
    createdAt: str = Field(default_factory=utc_now_iso)
    instruction: str
    operation: Literal[
        "replace_range",
        "alternative_take",
        "add_layer",
        "strip_to_tracks",
        "extend_section",
        "audio_reverse",
        "audio_fade",
    ] = "replace_range"
    variationKind: Literal[
        "drum_variation",
        "hook_variation",
        "bass_variation",
        "harmony_variation",
        "rhythm_only",
        "velocity_only",
        "arrangement_variation",
        "audio_edit",
    ] = "drum_variation"
    intensity: Literal["subtle", "moderate", "creative"] = "moderate"
    scope: EditScope
    preservePitch: bool = False
    preserveHarmony: bool = True
    preserveFirstHalf: bool = False
    addTurnaroundFill: bool = False
    keepTrackIds: list[str] = Field(default_factory=list)
    extendBars: int = 0
    changes: list[str] = Field(default_factory=list)
    providerProvenance: dict[str, Any] = Field(default_factory=dict)
    summaryKo: str = ""
    summaryEn: str = ""


def extract_midi_notes_in_range(
    track: Track,
    start_beats: float,
    end_beats: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read actual MIDI note events inside `[start_beats, end_beats]` (relative to `start_beats`) + adjacent context."""
    in_range: list[dict[str, Any]] = []
    before_notes: list[dict[str, Any]] = []
    after_notes: list[dict[str, Any]] = []
    span = max(0.25, end_beats - start_beats)

    for clp in track.clips:
        if clp.type != "midi":
            continue
        loop_len = clp.loopLengthBeats or max(
            4.0,
            max((n.startBeat + n.durationBeats for n in clp.notes), default=4.0),
        )
        reps = int((clp.durationBeats + loop_len - 1e-6) // loop_len) if clp.loop else 1
        for rep in range(max(1, reps)):
            rep_off = rep * loop_len
            for n in clp.notes:
                rel_in_clip = rep_off + n.startBeat
                if rel_in_clip >= clp.durationBeats - 1e-6:
                    continue
                abs_start = clp.timelineStartBeats + rel_in_clip
                abs_dur = min(n.durationBeats, clp.durationBeats - rel_in_clip)
                abs_end = abs_start + abs_dur
                if abs_end > start_beats + 1e-4 and abs_start < end_beats - 1e-4:
                    clipped_s = max(abs_start, start_beats)
                    clipped_e = min(abs_end, end_beats)
                    in_range.append(
                        {
                            "id": n.id,
                            "pitch": int(n.pitch),
                            "velocity": int(n.velocity),
                            "startBeat": round(clipped_s - start_beats, 4),
                            "durationBeats": round(max(0.0625, clipped_e - clipped_s), 4),
                            "clippedAtBoundary": (abs_start < start_beats - 1e-4) or (abs_end > end_beats + 1e-4),
                        }
                    )
                elif start_beats - 8.0 <= abs_start < start_beats:
                    before_notes.append({"pitch": int(n.pitch), "beat": round(abs_start, 3), "vel": int(n.velocity)})
                elif end_beats <= abs_start < end_beats + 8.0:
                    after_notes.append({"pitch": int(n.pitch), "beat": round(abs_start, 3), "vel": int(n.velocity)})

    in_range.sort(key=lambda item: (item["startBeat"], item["pitch"]))
    adjacent = {
        "beforeNoteCount": len(before_notes),
        "afterNoteCount": len(after_notes),
        "beforeLastPitch": before_notes[-1]["pitch"] if before_notes else None,
        "afterFirstPitch": after_notes[0]["pitch"] if after_notes else None,
        "inRangeNoteCount": len(in_range),
        "inRangePitchMin": min((n["pitch"] for n in in_range), default=None),
        "inRangePitchMax": max((n["pitch"] for n in in_range), default=None),
        "spanBeats": round(span, 3),
    }
    return in_range, adjacent


def _detect_intensity(text: str, explicit: str | None = None) -> Literal["subtle", "moderate", "creative"]:
    if explicit in ("subtle", "moderate", "creative"):
        return explicit  # type: ignore[return-value]
    low = text.lower()
    if any(k in low for k in ("조금만", "살짝", "약간", "미세", "조금", "subtle", "slightly", "minor tweak", "lightly")):
        return "subtle"
    if any(k in low for k in ("완전히 새", "과감", "크게", "확 바꿔", "강렬", "creative", "bold", "dramatic", "completely new")):
        return "creative"
    return "moderate"


def _infer_variation_kind(track: Track | None, text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("velocity", "벨로시티", "강약만", "다이나믹만")):
        return "velocity_only"
    if any(k in low for k in ("리듬만", "rhythm only", "타이밍만")):
        return "rhythm_only"
    if track and track.type != "midi":
        if any(k in low for k in ("리버스", "거꾸로", "reverse", "페이드", "fade", "크로스페이드", "crossfade")):
            return "audio_edit"
    name_and_inst = f"{track.name if track else ''} {track.instrumentRef if track else ''} {low}".lower()
    if any(k in name_and_inst for k in ("drum", "드럼", "필인", "fill", "킥", "스네어", "하이햇")):
        return "drum_variation"
    if any(k in name_and_inst for k in ("bass", "베이스", "서브")):
        return "bass_variation"
    if any(k in name_and_inst for k in ("key", "piano", "ep", "chord", "건반", "피아노", "코드", "보이싱", "화성")):
        return "harmony_variation"
    return "hook_variation"


def create_arrangement_edit_plan(
    project: Project,
    instruction: str,
    selection: dict[str, Any] | None = None,
    intensity: str | None = None,
    target_track_id: str | None = None,
    start_beats: float | None = None,
    end_beats: float | None = None,
    provider_id: str | None = None,
) -> ArrangementEditPlan:
    """Create a strict, scope-bounded ArrangementEditPlan reading actual tracks, clips & MIDI notes."""
    text = instruction.strip()
    low = text.lower()
    bpb = project.timeSignature.beats_per_bar
    mem = ensure_music_memory(project)
    resolved = resolve_contextual_reference(project, text, selection=selection)

    resolved_tid = target_track_id or resolved.get("targetTrackId")
    target_trk = next((t for t in project.tracks if t.id == resolved_tid), None)
    if not target_trk and project.tracks:
        target_trk = project.tracks[0]
        resolved_tid = target_trk.id

    sb = float(start_beats if start_beats is not None else (resolved.get("startBeats") or 0.0))
    eb = float(end_beats if end_beats is not None else (resolved.get("endBeats") or (sb + bpb * 4)))
    if eb <= sb:
        eb = sb + bpb * 4

    start_bar = int(sb // bpb) + 1
    end_bar_inc = max(start_bar, int(max(sb, eb - 0.001) // bpb) + 1)

    # Detect structural arrangement commands vs musical track variations
    operation: str = "replace_range"
    variation_kind = _infer_variation_kind(target_trk, text)
    keep_track_ids: list[str] = []
    extend_bars = 0
    changes: list[str] = []

    if any(k in low for k in ("늘려", "연장", "extend", "longer")) and any(
        k in low for k in ("브레이크", "브리지", "후렴", "클라이맥스", "구간", "breakdown", "bridge", "chorus", "section")
    ):
        operation = "extend_section"
        variation_kind = "arrangement_variation"
        m_b = re.search(r"(\d+)\s*(?:마디|bars?)", low)
        extend_bars = int(m_b.group(1)) if m_b else 4
        changes = [f"extend_section_by_{extend_bars}_bars", "shift_subsequent_clips_and_sections"]
    elif any(k in low for k in ("만 남겨", "only leave", "leave only", "만 남기", "드럼과 베이스만", "베이스와 드럼만")):
        operation = "strip_to_tracks"
        variation_kind = "arrangement_variation"
        for trk in project.tracks:
            tn = trk.name.lower()
            if (
                (("드럼" in low or "drum" in low) and "drum" in tn)
                or (("베이스" in low or "bass" in low) and "bass" in tn)
                or (("기타" in low or "guitar" in low) and ("guitar" in tn or "gtr" in tn))
                or (("신스" in low or "synth" in low) and "synth" in tn)
                or (("건반" in low or "key" in low) and ("key" in tn or "piano" in tn))
            ):
                keep_track_ids.append(trk.id)
        changes = ["carve_other_tracks_in_range", "preserve_kept_rhythm_section"]
    elif any(k in low for k in ("리버스", "거꾸로", "reverse")) and target_trk and target_trk.type != "midi":
        operation = "audio_reverse"
        variation_kind = "audio_edit"
        changes = ["non_destructive_reverse_audio_clip"]
    elif any(k in low for k in ("페이드", "크로스페이드", "fade", "crossfade")) and target_trk and target_trk.type != "midi":
        operation = "audio_fade"
        variation_kind = "audio_edit"
        changes = ["apply_clip_fade_in_out"]
    elif any(k in low for k in ("레이어 추가", "새로운 신스 레이어", "add layer", "새 레이어")):
        operation = "add_layer"
        variation_kind = "hook_variation"
        changes = ["add_new_climax_counter_layer", "preserve_all_existing_tracks"]

    eff_intensity = _detect_intensity(text, explicit=intensity)
    preserve_first_half = any(
        k in low for k in ("후반부만", "뒷부분만", "메인 멜로디는 유지", "앞부분은 유지", "second half", "tail only", "keep main melody")
    )
    preserve_pitch = variation_kind == "rhythm_only" or any(k in low for k in ("음정 유지", "리듬만", "keep pitch", "rhythm only"))
    preserve_harmony = not any(k in low for k in ("코드 진행 바꿔", "화성 바꿔", "reharmonize", "change chords"))
    add_fill = any(k in low for k in ("필인", "필 인", "fill", "turnaround", "드럼 필")) or (
        variation_kind == "drum_variation" and eff_intensity in ("moderate", "creative")
    )

    if not changes:
        if variation_kind == "drum_variation":
            changes = ["kick_pattern_variation", "snare_ghost_notes", "hihat_open_close_dynamics"]
            if add_fill:
                changes.append("turnaround_fill_end_of_range")
        elif variation_kind == "hook_variation":
            changes = (
                ["preserve_first_half_motif", "vary_second_half_cadence_and_lift", "expressive_response_phrase"]
                if preserve_first_half
                else ["motif_rhythmic_variation", "octave_or_cadence_lift", "dynamic_phrasing"]
            )
        elif variation_kind == "bass_variation":
            changes = ["preserve_harmonic_roots", "syncopated_funky_pocket", "octave_and_passing_lead_ins"]
        elif variation_kind == "harmony_variation":
            changes = ["voicing_color_extensions_add9_maj7", "comping_rhythm_refresh"]
        elif variation_kind == "rhythm_only":
            changes = ["preserve_exact_pitches", "syncopate_rhythm_grid"]
        elif variation_kind == "velocity_only":
            changes = ["preserve_exact_pitch_and_timing", "sculpt_dynamic_velocity_curve"]

    # Read ACTUAL notes & adjacent context from target track!
    in_range_notes: list[dict[str, Any]] = []
    adjacent_ctx: dict[str, Any] = {}
    target_clip_ids: list[str] = []
    if target_trk:
        for clp in target_trk.clips:
            if clp.timelineStartBeats + clp.durationBeats > sb + 1e-4 and clp.timelineStartBeats < eb - 1e-4:
                target_clip_ids.append(clp.id)
        if target_trk.type == "midi":
            in_range_notes, adjacent_ctx = extract_midi_notes_in_range(target_trk, sb, eb)

    preserved_track_ids = (
        [t.id for t in project.tracks if t.id in keep_track_ids]
        if operation == "strip_to_tracks"
        else [t.id for t in project.tracks if t.id != resolved_tid]
    )
    target_track_ids = (
        [t.id for t in project.tracks if t.id not in keep_track_ids]
        if operation == "strip_to_tracks"
        else ([resolved_tid] if resolved_tid else [])
    )
    preserved_sections = [s.name for s in project.sections if s.endBeats <= sb or s.startBeats >= eb]

    # Optional real AI Producer refinement (isolated `--tools ""` JSON call)
    llm_patch, prov_meta = invoke_llm_json(
        system_prompt=(
            "You are a concise Korean AI Music Producer in a DAW. Summarize the selective arrangement plan. "
            "Return ONLY valid JSON with keys `summaryKo` (1 concise Korean sentence stating exact target track, bars, and preserved tracks) "
            "and `changes` (array of 2–4 concise musical change identifiers)."
        ),
        user_prompt=(
            f"Instruction: {text}\nTarget: {target_trk.name if target_trk else 'none'}, Bars {start_bar}-{end_bar_inc}, "
            f"Operation: {operation}, Variation: {variation_kind}, Intensity: {eff_intensity}, "
            f"Existing notes in range: {len(in_range_notes)}, Preserved tracks: {[t.name for t in project.tracks if t.id in preserved_track_ids]}"
        ),
        provider_id=provider_id,
    )
    if isinstance(llm_patch, dict) and isinstance(llm_patch.get("changes"), list) and llm_patch["changes"]:
        ai_ch = [str(x).strip() for x in llm_patch["changes"] if str(x).strip()][:5]
        if ai_ch:
            changes = ai_ch

    preserved_names = [t.name for t in project.tracks if t.id in preserved_track_ids]
    default_ko = (
        f"{target_trk.name if target_trk else '선택 트랙'} {start_bar}–{end_bar_inc}마디를 {eff_intensity} 강도로 편곡/변주합니다"
        + (f" ({', '.join(preserved_names[:3])} 유지)." if preserved_names else ".")
    )
    summary_ko = (
        str(llm_patch.get("summaryKo")).strip()
        if isinstance(llm_patch, dict) and llm_patch.get("summaryKo")
        else default_ko
    )
    summary_en = (
        f"{operation} ({variation_kind}, {eff_intensity}) on {target_trk.name if target_trk else 'track'} "
        f"bars {start_bar}–{end_bar_inc}; preserving {', '.join(preserved_names[:4]) or 'all other tracks'}."
    )

    scope = EditScope(
        projectId=project.id,
        baseRevision=project.revision,
        targetTrackIds=target_track_ids,
        targetClipIds=target_clip_ids,
        startBeats=round(sb, 4),
        endBeats=round(eb, 4),
        startBar=start_bar,
        endBarInclusive=end_bar_inc,
        selectionType="section" if resolved.get("sectionId") else "range",
        requestedOperation=operation,
        preservedTrackIds=preserved_track_ids,
        preservedSections=preserved_sections,
        harmonicContext={
            "key": mem.get("key", "F minor"),
            "chords": mem.get("chords", ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"]),
            "bpm": project.bpm,
        },
        adjacentContext={
            **adjacent_ctx,
            "actualNotesSample": in_range_notes[:16],
        },
    )

    return ArrangementEditPlan(
        instruction=text,
        operation=operation,  # type: ignore[arg-type]
        variationKind=variation_kind,  # type: ignore[arg-type]
        intensity=eff_intensity,
        scope=scope,
        preservePitch=preserve_pitch,
        preserveHarmony=preserve_harmony,
        preserveFirstHalf=preserve_first_half,
        addTurnaroundFill=add_fill,
        keepTrackIds=keep_track_ids,
        extendBars=extend_bars,
        changes=changes,
        providerProvenance=prov_meta,
        summaryKo=summary_ko,
        summaryEn=summary_en,
    )
