"""Agent-agnostic DAW MCP tool implementations (shared across Antigravity, Claude Code, Codex)."""

from __future__ import annotations

from typing import Any

from engine.arrangement import (
    ArrangementEditPlan,
    create_arrangement_edit_plan as _build_arrangement_plan,
    create_reversed_clip_asset as _reverse_clip_asset,
    ensure_music_memory as _ensure_music_memory,
    execute_arrangement_edit_plan as _exec_arrangement_plan,
    promote_take_lane as _promote_take_lane,
    restore_original_lane as _restore_original_lane,
)
from engine.composition import create_composition_plan as _build_plan
from engine.composition.schemas import CompositionPlan
from engine.generation import (
    apply_take as _apply_take,
    detect_generation_engines,
    generation_jobs,
    get_composition_plan as _get_plan,
    get_take as _get_take,
    list_takes as _list_takes,
    reject_take as _reject_take,
    save_composition_plan as _save_plan,
)
from engine.instruments import list_instruments as _list_instruments
from engine.providers import get_provider_summary
from engine.runtime import get_runtime_registry
from engine.transcription import (
    build_yue2_abc_from_reference as _build_ref_abc,
    reconstruct_reference_to_project as _reconstruct_ref,
)

from . import analysis, commands, proposals, reaper, references, session, store


def _resolve_project_id(project_id: str | None) -> str:
    if project_id:
        return project_id
    active = session.get_active_session()
    if active.get("projectId"):
        return str(active["projectId"])
    all_projs = store.list_projects()
    if all_projs:
        return all_projs[0].id
    raise FileNotFoundError("No active DAW project found")


def get_capabilities() -> dict[str, Any]:
    return {
        "product": "AI-Native DAW",
        "phase": "04",
        "referencePhase": "03.2",
        "schemaVersion": "1.4.0",
        "supported": {
            "projectReadWrite": True,
            "revisionConflictGuard": True,
            "stagedChangeProposals": True,
            "mcpDefaultSafeStaging": True,
            "undoRedo": True,
            "trackEdit": ["add", "remove", "rename", "reorder", "gain", "pan", "mute", "solo", "setInstrument", "takeLanes"],
            "clipEdit": ["add", "move", "trim", "split", "duplicate", "delete", "gain", "loop", "fades", "reverse"],
            "midiEdit": ["addNote", "moveNote", "resizeNote", "setVelocity", "deleteNote"],
            "sectionMarkers": ["add", "rename", "remove", "extend"],
            "chordTrack": ["setTrack", "upsert", "delete", "setLocked"],
            "referenceIntelligence": [
                "import_audio_video",
                "url_metadata_probe",
                "bs1770_4_loudness_and_true_peak",
                "half_double_time_tempo_resolution",
                "reference_blueprint_v2",
                "normalized_audio_comparison",
            ],
            "advancedReferenceIntelligence": [
                "demucs_mps_4stem_separation",
                "basic_pitch_onnx_polyphonic_transcription",
                "multiband_drum_and_microtiming_groove_extraction",
                "sub_bar_chord_and_inversion_tracking",
                "ten_feature_reference_lock_matrix",
                "mode_a_reconstruct_to_editable_session",
                "mode_b_reference_conditioned_composition",
                "mode_c_reference_reinterpretation",
                "yue2_instrumental_abc_score_generation",
                "five_state_feature_consumption_verification",
            ],
            "aiComposition": [
                "composition_plan",
                "reference_guided_composition",
                "full_music_multitrack",
                "instrument_session",
                "loop_and_midi_composition",
                "take_level_matched_preview",
                "transactional_take_apply",
                "six_voice_multi_timbre_instruments",
            ],
            "aiArrangement": [
                "selective_bar_variation",
                "midi_drum_hook_bass_harmony_variation",
                "non_destructive_audio_reverse_and_fades",
                "audio_seam_validation",
                "timeline_take_lanes_and_selective_comping",
                "in_context_and_original_ab_preview",
                "project_music_memory",
            ],
            "stereoWavExport": True,
        },
        "unsupported": {
            "fxRackEqCompReverb": "Planned for Phase 05",
            "externalPluginsAuVst3": "Planned for Phase 05",
            "aiMixingMastering": "Planned for Phase 06",
            "vocalSynthesisAndLyrics": "Planned for Phase 07 (Instrumental-only policy in Phase 03/04)",
            "audioTimeStretchWarp": "Planned for later phase",
        },
        "providers": get_provider_summary(),
        "generationEngines": detect_generation_engines(),
        "runtimeRegistry": get_runtime_registry(),
        "instruments": _list_instruments(),
        "reaperBridge": reaper.detect_reaper(),
    }


def list_projects() -> dict[str, Any]:
    return {"projects": [p.model_dump() for p in store.list_projects()]}


def get_active_project(session_id: str | None = None) -> dict[str, Any]:
    sess = session.get_active_session(session_id)
    pid = _resolve_project_id(sess.get("projectId"))
    proj = store.load_project(pid)
    return {
        "session": sess,
        "project": {
            "id": proj.id,
            "name": proj.name,
            "revision": proj.revision,
            "bpm": proj.bpm,
            "timeSignature": proj.timeSignature.model_dump(),
            "lengthBeats": proj.lengthBeats,
            "trackCount": len(proj.tracks),
            "referenceCount": len(proj.references),
        },
    }


def get_project(project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return store.load_project(pid).model_dump()


def get_selection(session_id: str | None = None) -> dict[str, Any]:
    sess = session.get_active_session(session_id)
    pid = _resolve_project_id(sess.get("projectId"))
    proj = store.load_project(pid)
    sel = sess.get("selection") or {}
    bpb = proj.timeSignature.beats_per_bar
    tr = sel.get("timeRangeBeats")
    bar_range = None
    if tr and "startBeats" in tr and "endBeats" in tr:
        bar_range = {
            "startBar": int(tr["startBeats"] // bpb) + 1,
            "endBar": max(int(tr["startBeats"] // bpb) + 1, int(-(-tr["endBeats"] // bpb))),
        }
    active_ref_id = sess.get("activeReferenceId") or (proj.references[0]["id"] if proj.references else None)
    active_bp = None
    if active_ref_id:
        ref = next((r for r in proj.references if r.get("id") == active_ref_id), None)
        if ref:
            active_bp = ref.get("blueprint")

    return {
        "sessionId": sess.get("sessionId"),
        "projectId": proj.id,
        "projectRevision": proj.revision,
        "bpm": proj.bpm,
        "timeSignature": proj.timeSignature.model_dump(),
        "selection": sel,
        "barRange": bar_range,
        "activeReferenceId": active_ref_id,
        "referenceBlueprint": active_bp,
    }


def get_tracks(project_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    return {
        "projectId": proj.id,
        "revision": proj.revision,
        "tracks": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "gainDb": t.gainDb,
                "pan": t.pan,
                "mute": t.mute,
                "solo": t.solo,
                "clipCount": len(t.clips),
            }
            for t in proj.tracks
        ],
    }


def get_clips(project_id: str | None = None, track_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    clips = []
    for t in proj.tracks:
        if track_id and t.id != track_id:
            continue
        for c in t.clips:
            clips.append({"trackId": t.id, "trackName": t.name, **c.model_dump(exclude={"notes"}), "noteCount": len(c.notes)})
    return {"projectId": proj.id, "revision": proj.revision, "clips": clips}


def get_sections(project_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    return {"projectId": proj.id, "revision": proj.revision, "sections": [s.model_dump() for s in proj.sections]}


def get_midi_notes(clip_id: str, project_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    for t in proj.tracks:
        for c in t.clips:
            if c.id == clip_id:
                if c.type != "midi":
                    raise ValueError(f"Clip {clip_id} is not a MIDI clip")
                return {
                    "projectId": proj.id,
                    "revision": proj.revision,
                    "trackId": t.id,
                    "clipId": c.id,
                    "notes": [n.model_dump() for n in c.notes],
                }
    raise FileNotFoundError(f"Clip not found: {clip_id}")


def get_reference_analysis(reference_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    ref = (
        next((r for r in proj.references if r.get("id") == reference_id), None)
        if reference_id
        else (proj.references[0] if proj.references else None)
    )
    if not ref:
        raise FileNotFoundError("Reference not found in project")
    return {
        "projectId": proj.id,
        "referenceId": ref["id"],
        "name": ref["name"],
        "audioAvailable": ref.get("audioAvailable", False),
        "analysisStatus": ref.get("analysisStatus"),
        "analysis": ref.get("analysis"),
    }


def get_reference_blueprint(reference_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(_resolve_project_id(project_id))
    ref = (
        next((r for r in proj.references if r.get("id") == reference_id), None)
        if reference_id
        else (proj.references[0] if proj.references else None)
    )
    if not ref:
        raise FileNotFoundError("Reference not found in project")
    return {
        "projectId": proj.id,
        "referenceId": ref["id"],
        "name": ref["name"],
        "selectedInfluences": ref.get("selectedInfluences", []),
        "blueprint": ref.get("blueprint"),
    }


def _direct_edit(
    cmd_type: str,
    payload: dict[str, Any],
    project_id: str | None = None,
    expected_revision: int | None = None,
    stage_only: bool = False,
    summary: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    if stage_only:
        prop = proposals.create_proposal(
            pid,
            summary or f"MCP {cmd_type}",
            [{"type": cmd_type, "payload": payload}],
            base_revision=expected_revision,
            source_agent="mcp-agent",
        )
        return {"staged": True, "proposal": prop}

    proj = store.load_project(pid)
    if expected_revision is not None and proj.revision != expected_revision:
        raise store.RevisionConflictError(expected_revision, proj.revision, proj)
    proposals.record_undo_snapshot(proj)
    updated = commands.apply_command(proj, cmd_type, payload)
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    session.event_bus.publish(
        "project.updated",
        {"projectId": pid, "revision": saved.revision, "reason": f"MCP {cmd_type}", "project": saved.model_dump()},
    )
    return {"applied": True, "command": cmd_type, "projectId": pid, "revision": saved.revision}


def add_track(name: str, track_type: str = "audio", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit("track.add", {"name": name, "type": track_type}, project_id, expected_revision, stage_only, f"Add {track_type} track '{name}'")


def move_clip(clip_id: str, timeline_start_beats: float, target_track_id: str | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {"clipId": clip_id, "timelineStartBeats": timeline_start_beats}
    if target_track_id:
        payload["targetTrackId"] = target_track_id
    return _direct_edit("clip.move", payload, project_id, expected_revision, stage_only, f"Move clip {clip_id} to beat {timeline_start_beats}")


def split_clip(clip_id: str, split_beat: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit("clip.split", {"clipId": clip_id, "splitBeat": split_beat}, project_id, expected_revision, stage_only, f"Split clip {clip_id} at beat {split_beat}")


def duplicate_clip(clip_id: str, timeline_start_beats: float | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {"clipId": clip_id}
    if timeline_start_beats is not None:
        payload["timelineStartBeats"] = timeline_start_beats
    return _direct_edit("clip.duplicate", payload, project_id, expected_revision, stage_only, f"Duplicate clip {clip_id}")


def set_track_gain(track_id: str, gain_db: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit("track.setGain", {"trackId": track_id, "gainDb": gain_db}, project_id, expected_revision, stage_only, f"Set track {track_id} gain to {gain_db} dB")


def set_track_pan(track_id: str, pan: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit("track.setPan", {"trackId": track_id, "pan": pan}, project_id, expected_revision, stage_only, f"Set track {track_id} pan to {pan}")


def set_track_mute(track_id: str, mute: bool, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit("track.setMute", {"trackId": track_id, "mute": mute}, project_id, expected_revision, stage_only, f"{'Mute' if mute else 'Unmute'} track {track_id}")


def edit_midi_notes(clip_id: str, operations: list[dict[str, Any]], project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    """Batch MIDI note edits (`midi.addNote`, `midi.moveNote`, `midi.resizeNote`, `midi.setVelocity`, `midi.deleteNote`)."""
    pid = _resolve_project_id(project_id)
    normalized = []
    for op in operations:
        op_type = str(op.get("type", ""))
        if not op_type.startswith("midi."):
            raise ValueError(f"edit_midi_notes only accepts midi.* commands, got {op_type}")
        payload = {"clipId": clip_id, **dict(op.get("payload", {}))}
        normalized.append({"type": op_type, "payload": payload})
    if stage_only:
        prop = proposals.create_proposal(pid, f"MIDI edit ({len(normalized)} ops)", normalized, base_revision=expected_revision, source_agent="mcp-agent")
        return {"staged": True, "proposal": prop}
    proj = store.load_project(pid)
    if expected_revision is not None and proj.revision != expected_revision:
        raise store.RevisionConflictError(expected_revision, proj.revision, proj)
    proposals.record_undo_snapshot(proj)
    updated = proj
    for op in normalized:
        updated = commands.apply_command(updated, op["type"], op["payload"])
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    session.event_bus.publish("project.updated", {"projectId": pid, "revision": saved.revision, "reason": "MCP MIDI edit", "project": saved.model_dump()})
    return {"applied": True, "projectId": pid, "revision": saved.revision, "operationCount": len(normalized)}


def add_section(name: str, start_beats: float, end_beats: float, color: str = "#4a5968", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict[str, Any]:
    return _direct_edit(
        "section.add",
        {"name": name, "startBeats": start_beats, "endBeats": end_beats, "color": color},
        project_id,
        expected_revision,
        stage_only,
        f"Add section '{name}'",
    )


def preview_changes(summary: str, operations: list[dict[str, Any]], project_id: str | None = None, base_revision: int | None = None, source_agent: str = "mcp-agent") -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return proposals.create_proposal(pid, summary, operations, base_revision=base_revision, source_agent=source_agent)


def apply_changes(proposal_id: str, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    prop, saved = proposals.apply_proposal(pid, proposal_id)
    return {"proposal": prop, "revision": saved.revision, "projectId": saved.id}


def reject_changes(proposal_id: str, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return proposals.reject_proposal(pid, proposal_id)


def undo(project_id: str | None = None) -> dict[str, Any]:
    saved = proposals.undo_project(_resolve_project_id(project_id))
    return {"undone": True, "projectId": saved.id, "revision": saved.revision}


def redo(project_id: str | None = None) -> dict[str, Any]:
    saved = proposals.redo_project(_resolve_project_id(project_id))
    return {"redone": True, "projectId": saved.id, "revision": saved.revision}


def analyze_reference(reference_id: str | None = None, project_id: str | None = None, sync: bool = True) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    if not rid:
        raise FileNotFoundError("No reference found in project")
    if sync:
        ref, rev = references.run_reference_analysis_sync(pid, rid)
        return {"status": "completed", "projectId": pid, "revision": rev, "reference": ref}
    return {"job": references.start_reference_analysis_job(pid, rid)}


def get_analysis_status(job_id: str) -> dict[str, Any]:
    return analysis.analysis_jobs.get(job_id)


def compare_audio(reference_id: str, target_kind: str = "project_mix", target_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return references.compare_reference_with_target(pid, reference_id, target_kind=target_kind, target_id=target_id)


# --- Phase 03 Composition, Generation, Stems, Takes & Providers MCP Tools ---

def create_composition_plan(
    instruction: str,
    mode: str | None = None,
    target_instrument: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    project_id: str | None = None,
    provider_id: str | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    use_project_chord_track: bool = False,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    sess = session.get_active_session()
    sel = sess.get("selection") if sess.get("projectId") == pid else None
    plan = _build_plan(
        project=proj,
        instruction=instruction,
        mode=mode,
        target_instrument=target_instrument,
        reference_ids=reference_ids,
        selected_influences=selected_influences,
        selection=sel,
        provider_id=provider_id,
        feature_locks=feature_locks,
        reference_mode=reference_mode,
        use_project_chord_track=use_project_chord_track,
    )
    saved_plan, rev = _save_plan(pid, plan)
    return {"projectId": pid, "revision": rev, "plan": saved_plan}


def get_composition_plan(plan_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    plan = _get_plan(pid, plan_id)
    if not plan:
        raise FileNotFoundError("No composition plan found in project")
    return {"projectId": pid, "plan": plan}


def _run_generation_helper(
    instruction: str | None,
    mode: str,
    target_instrument: str | None = None,
    plan_id: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    engine_choice: str = "auto",
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    use_project_chord_track: bool = False,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    if plan_id:
        raw_plan = _get_plan(pid, plan_id)
        if not raw_plan:
            raise FileNotFoundError(f"CompositionPlan not found: {plan_id}")
        plan = CompositionPlan.model_validate(raw_plan)
    else:
        sess = session.get_active_session()
        sel = sess.get("selection") if sess.get("projectId") == pid else None
        plan = _build_plan(
            project=proj,
            instruction=instruction or f"Create a {mode} arrangement",
            mode=mode,
            target_instrument=target_instrument,
            reference_ids=reference_ids,
            selected_influences=selected_influences,
            selection=sel,
            engine_preference=engine_choice,
            feature_locks=feature_locks,
            reference_mode=reference_mode,
            use_project_chord_track=use_project_chord_track,
        )
    return generation_jobs.start_composition_job(pid, plan, engine_choice=engine_choice, seed=seed, sync=sync)


def generate_music(
    instruction: str | None = None,
    plan_id: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    engine_choice: str = "auto",
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    use_project_chord_track: bool = False,
) -> dict[str, Any]:
    return _run_generation_helper(
        instruction,
        "full_music",
        None,
        plan_id,
        reference_ids,
        selected_influences,
        engine_choice,
        seed,
        sync,
        project_id,
        feature_locks=feature_locks,
        reference_mode=reference_mode,
        use_project_chord_track=use_project_chord_track,
    )


def generate_instrument(
    instruction: str,
    target_instrument: str = "synth_hook",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    return _run_generation_helper(
        instruction, "instrument_session", target_instrument, None, reference_ids, None, "auto", seed, sync, project_id
    )


def generate_loop(
    instruction: str,
    target_instrument: str = "drums",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    return _run_generation_helper(
        instruction, "loop_midi", target_instrument, None, reference_ids, None, "auto", seed, sync, project_id
    )


def generate_midi(
    instruction: str,
    target_instrument: str = "synth_hook",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    return _run_generation_helper(
        instruction, "loop_midi", target_instrument, None, reference_ids, None, "auto", seed, sync, project_id
    )


def separate_stems(asset_id: str, model_name: str = "htdemucs", sync: bool = False, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return generation_jobs.start_stem_separation_job(pid, asset_id, model_name=model_name, sync=sync)


def list_generation_jobs(project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id) if project_id else None
    return {"jobs": generation_jobs.list_jobs(pid)}


def get_generation_status(job_id: str) -> dict[str, Any]:
    return generation_jobs.get_job(job_id)


def cancel_generation(job_id: str) -> dict[str, Any]:
    return generation_jobs.cancel_job(job_id)


def get_generation_result(take_id: str, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return {"projectId": pid, "take": _get_take(pid, take_id)}


def preview_generation(take_id: str, project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    take = _get_take(pid, take_id)
    return {
        "projectId": pid,
        "takeId": take_id,
        "title": take.get("title"),
        "audioUrl": f"/api/projects/{pid}/takes/{take_id}/audio",
        "durationSec": take.get("previewDurationSec"),
        "integratedLufs": take.get("previewIntegratedLufs"),
        "levelMatchedGainDb": take.get("levelMatchedGainDb"),
        "qualityReport": take.get("qualityReport"),
        "provenance": take.get("provenance"),
    }


def stage_generation_import(
    take_id: str,
    apply_mode: str = "new_tracks",
    target_track_id: str | None = None,
    start_beats: float | None = None,
    project_id: str | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Apply (or keep) a generated Take transactionally with Undo snapshot & Revision check."""
    pid = _resolve_project_id(project_id)
    return _apply_take(
        project_id=pid,
        take_id=take_id,
        apply_mode=apply_mode,
        target_track_id=target_track_id,
        start_beats=start_beats,
        expected_revision=expected_revision,
    )


def list_takes(project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return {"projectId": pid, "takes": _list_takes(pid)}


def select_take(
    take_id: str,
    action: str = "apply",  # "apply" | "keep" | "reject"
    apply_mode: str = "new_tracks",
    target_track_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    if action == "reject":
        t, rev = _reject_take(pid, take_id)
        return {"projectId": pid, "revision": rev, "take": t}
    if action == "keep":
        return _apply_take(pid, take_id, apply_mode="keep_take")
    return _apply_take(pid, take_id, apply_mode=apply_mode, target_track_id=target_track_id)


def list_providers() -> dict[str, Any]:
    return get_provider_summary()


def list_instruments() -> dict[str, Any]:
    return {"instruments": _list_instruments(), "engines": detect_generation_engines()}


def get_runtime_status() -> dict[str, Any]:
    return get_runtime_registry()


# --- Phase 04: Selective Arrangement, Musical Variation, Take Comping, Audio Reverse & Music Memory MCP Tools ---

def create_arrangement_edit_plan(
    instruction: str,
    intensity: str | None = None,
    target_track_id: str | None = None,
    start_beats: float | None = None,
    end_beats: float | None = None,
    project_id: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    sess = session.get_active_session()
    sel = sess.get("selection") if sess.get("projectId") == pid else None
    plan = _build_arrangement_plan(
        project=proj,
        instruction=instruction,
        selection=sel,
        intensity=intensity,
        target_track_id=target_track_id,
        start_beats=start_beats,
        end_beats=end_beats,
        provider_id=provider_id,
    )
    return {"projectId": pid, "revision": proj.revision, "plan": plan.model_dump()}


def generate_variation(
    instruction: str | None = None,
    plan: dict[str, Any] | None = None,
    intensity: str | None = None,
    target_track_id: str | None = None,
    start_beats: float | None = None,
    end_beats: float | None = None,
    seed: int = 42,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    if plan:
        arr_plan = ArrangementEditPlan.model_validate(plan)
    else:
        if not instruction:
            raise ValueError("Either instruction or plan is required")
        sess = session.get_active_session()
        sel = sess.get("selection") if sess.get("projectId") == pid else None
        arr_plan = _build_arrangement_plan(
            project=proj,
            instruction=instruction,
            selection=sel,
            intensity=intensity,
            target_track_id=target_track_id,
            start_beats=start_beats,
            end_beats=end_beats,
        )
    return _exec_arrangement_plan(pid, arr_plan, seed=seed)


def promote_take_lane(
    track_id: str,
    lane_id: str,
    start_beats: float | None = None,
    end_beats: float | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return _promote_take_lane(pid, track_id, lane_id, comp_start_beats=start_beats, comp_end_beats=end_beats)


def restore_original_take_lane(
    track_id: str,
    lane_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return _restore_original_lane(pid, track_id, lane_id=lane_id)


def reverse_audio_clip(
    clip_id: str,
    project_id: str | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    return _reverse_clip_asset(pid, clip_id, expected_revision=expected_revision)


def get_music_memory(project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    return {"projectId": pid, "revision": proj.revision, "musicMemory": _ensure_music_memory(proj)}


# --- Phase 03.2: Advanced Reference Intelligence MCP Tools ---

def transcribe_reference(
    reference_id: str | None = None,
    use_demucs: bool = True,
    demucs_model: str = "htdemucs",
    sync: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    if not rid:
        raise FileNotFoundError("No reference found in project")
    if sync:
        ref, rev = references.run_reference_transcription_sync(
            pid,
            rid,
            use_demucs=use_demucs,
            demucs_model=demucs_model,
        )
        return {"status": "completed", "projectId": pid, "revision": rev, "reference": ref}
    return {"job": references.start_reference_transcription_job(pid, rid, use_demucs=use_demucs, demucs_model=demucs_model)}


def get_chord_track(project_id: str | None = None) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    return {
        "projectId": proj.id,
        "revision": proj.revision,
        "chordTrack": [c.model_dump() for c in proj.chordTrack],
        "chordTrackLocked": proj.chordTrackLocked,
    }


def set_chord_track(
    chords: list[dict[str, Any]],
    locked: bool | None = None,
    project_id: str | None = None,
    expected_revision: int | None = None,
    stage_only: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"chords": chords}
    if locked is not None:
        payload["locked"] = locked
    return _direct_edit(
        "chord.setTrack",
        payload,
        project_id,
        expected_revision,
        stage_only,
        f"Update Chord Track ({len(chords)} chords)",
    )


def update_reference_locks(
    reference_id: str | None = None,
    feature_locks: dict[str, str] | None = None,
    chord_corrections: list[dict[str, Any]] | None = None,
    section_renames: dict[str, str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    if not rid:
        raise FileNotFoundError("No reference found in project")
    ref, rev = references.update_reference_locks_and_corrections(
        pid,
        rid,
        feature_locks=feature_locks,
        chord_corrections=chord_corrections,
        section_renames=section_renames,
    )
    return {"projectId": pid, "revision": rev, "reference": ref}


def import_reference_transcription(
    reference_id: str | None = None,
    import_chords: bool = True,
    import_drums_midi: bool = False,
    import_bass_midi: bool = False,
    import_melody_midi: bool = False,
    import_stems: bool = False,
    import_sections: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    if not rid:
        raise FileNotFoundError("No reference found in project")
    return _reconstruct_ref(
        pid,
        rid,
        import_chords=import_chords,
        import_drums_midi=import_drums_midi,
        import_bass_midi=import_bass_midi,
        import_melody_midi=import_melody_midi,
        import_stems=import_stems,
        import_sections=import_sections,
        apply_bpm=False,
    )


def reconstruct_from_reference(
    reference_id: str | None = None,
    import_stems: bool = False,
    use_quantized_drums: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    if not rid:
        raise FileNotFoundError("No reference found in project")
    return _reconstruct_ref(
        pid,
        rid,
        import_chords=True,
        import_drums_midi=True,
        import_bass_midi=True,
        import_melody_midi=True,
        import_stems=import_stems,
        import_sections=True,
        use_quantized_drums=use_quantized_drums,
        apply_bpm=True,
    )


def get_reference_abc_score(
    reference_id: str | None = None,
    mode: str = "reference_compose",
    project_id: str | None = None,
) -> dict[str, Any]:
    pid = _resolve_project_id(project_id)
    proj = store.load_project(pid)
    rid = reference_id or (proj.references[0]["id"] if proj.references else None)
    ref = next((r for r in proj.references if r.get("id") == rid), None)
    if not ref:
        raise FileNotFoundError("No reference found in project")
    bp = ref.get("blueprint") or {}
    tr = ref.get("transcription") or {}
    chords = bp.get("chordTimeline") or tr.get("chordTimeline") or []
    melody_notes = (bp.get("melodyEvents") or tr.get("melody") or {}).get("notes") or []
    sections = bp.get("arrangementMap") or tr.get("arrangementMap") or []
    key_str = str((bp.get("harmonicCharacter") or {}).get("key") or tr.get("key") or "F minor")
    bpm = float((bp.get("tempoMap") or {}).get("bpm") or tr.get("bpm") or proj.bpm)
    abc_res = _build_ref_abc(
        chord_timeline=chords,
        melody_notes=melody_notes,
        sections=sections,
        key_str=key_str,
        bpm=bpm,
        bpb=proj.timeSignature.beats_per_bar,
        production_mode=mode if mode in ("reconstruct", "reference_compose", "reinterpret") else "reference_compose",
    )
    return {"projectId": pid, "referenceId": rid, "abcScore": abc_res}
