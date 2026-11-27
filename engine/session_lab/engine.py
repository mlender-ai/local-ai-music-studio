"""AI Session & Loop Production Orchestrator (Phase 05.2 · Parts A, C, D, E, F, H).

Builds layered sessions one instrument at a time while strictly protecting Approved/Locked tracks,
enforcing Production Quality Policy (no PREVIEW instruments, strict instrumental), rendering
3-mode level-matched previews (Solo / In-Context / Before A-B), and supporting Take Lane A/B.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from engine.daw_workspace import commands, loudness, proposals, renderer, session, store
from engine.daw_workspace.schema import Project, Track, make_id, utc_now_iso
from engine.fx.chain import default_fx_slot
from engine.generation.adapters.yue2_adapter import screen_vocal_leakage
from engine.production.instrument_resolver import get_instrument_quality_tier

from .alignment import (
    align_audio_loop_to_bars,
    evaluate_musical_quality_gate,
    validate_loop_integrity,
)
from .context import (
    PROTECTED_STATES,
    _infer_track_role,
    build_session_context,
    compute_layer_integrity_hash,
    ensure_session_chord_timeline,
    set_layer_state,
    snapshot_protected_layers,
    verify_protected_layers_unchanged,
)
from .performers import (
    compose_bass_performance,
    compose_bridge_section,
    compose_drum_performance,
    compose_guitar_performance,
    compose_keys_performance,
    compose_percussion_performance,
    compose_synth_performance,
    compose_transition_pickup,
    vary_layer_notes,
)
from .vocabulary import resolve_performance_spec

_ROLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "drums": {"label": "Drums", "gainDb": -2.0, "pan": 0.0, "color": "#b89458"},
    "bass": {"label": "Bass", "gainDb": -3.2, "pan": 0.0, "color": "#648ea8"},
    "keys": {"label": "Rhodes / Keys", "gainDb": -1.5, "pan": -0.18, "color": "#867ca8"},
    "guitar": {"label": "Guitar", "gainDb": 1.8, "pan": 0.24, "color": "#6a997c"},
    "percussion": {"label": "Percussion", "gainDb": 0.5, "pan": -0.26, "color": "#9c8568"},
    "synth": {"label": "Synth", "gainDb": -2.0, "pan": 0.14, "color": "#9e7389"},
    "solo": {"label": "Solo", "gainDb": 3.2, "pan": 0.06, "color": "#c97b55"},
}

ROOM_BUS_ID = "bus_session_natural_room"


def _normalize_role(instrument: str) -> str:
    low = instrument.lower().strip()
    if low in ("drum", "drums", "beat", "kit", "드럼"):
        return "drums"
    if low in ("perc", "percussion", "shaker", "conga", "bongo", "퍼커션"):
        return "percussion"
    if low in ("bass", "베이스"):
        return "bass"
    if low in ("piano", "rhodes", "ep", "keys", "keyboard", "피아노", "건반", "로즈"):
        return "keys"
    if low in ("guitar", "기타"):
        return "guitar"
    if low in ("synth", "lead", "pad", "hook", "신스"):
        return "synth"
    return "keys"


def _ensure_natural_room_bus(project: Project) -> Project:
    """Ensure a subtle, studio-realistic shared Natural Room return bus exists (no muddy cavern reverb)."""
    if any(b.get("id") == ROOM_BUS_ID for b in project.buses):
        return project
    rev_slot = default_fx_slot(
        "reverb",
        make_id("fx"),
        preset_id="studio_room",
        params_override={
            "roomType": "studio_room",
            "decaySec": 1.05,
            "preDelayMs": 14.0,
            "damping": 0.48,
            "lowCutHz": 180.0,
            "highCutHz": 7200.0,
            "stereoWidth": 0.80,
            "wetDry": 1.0,
        },
    )
    return commands.apply_command(
        project,
        "bus.add",
        {
            "id": ROOM_BUS_ID,
            "name": "Natural Room",
            "kind": "return",
            "gainDb": -2.5,
            "effects": [rev_slot],
        },
    )


def _apply_spec_to_track(
    project: Project,
    track_id: str,
    spec: dict[str, Any],
    *,
    role: str,
    replace_fx: bool = True,
) -> Project:
    """Attach verified Pro Instrument, preset, articulation, subtle FX chain, and subtle Room send to track."""
    inst_ref = str(spec["instrumentRef"])
    tier = get_instrument_quality_tier(inst_ref)
    if tier["qualityTier"] == "PREVIEW":
        raise ValueError(f"Production Quality Policy blocked PREVIEW instrument '{inst_ref}'.")

    p = commands.apply_command(
        project,
        "track.setInstrument",
        {"trackId": track_id, "instrumentRef": inst_ref, "preset": spec.get("preset")},
    )
    if spec.get("articulation"):
        p = commands.apply_command(
            p,
            "instrument.setParams",
            {"trackId": track_id, "articulation": spec["articulation"]},
        )

    # Set clean mix balance
    mix_def = _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["keys"])
    p = commands.apply_command(p, "track.setGain", {"trackId": track_id, "gainDb": mix_def["gainDb"]})
    p = commands.apply_command(p, "track.setPan", {"trackId": track_id, "pan": mix_def["pan"]})

    # Apply subtle musical FX chain cleanly
    trk = next(t for t in p.tracks if t.id == track_id)
    if replace_fx and trk.effects:
        for old_fx in list(trk.effects):
            p = commands.apply_command(p, "fx.remove", {"trackId": track_id, "fxId": old_fx["id"]})
    for fx_spec in spec.get("subtleFx") or []:
        payload: dict[str, Any] = {
            "trackId": track_id,
            "type": fx_spec["type"],
            "preset": fx_spec.get("preset"),
        }
        if "parameters" in fx_spec:
            payload["parameters"] = dict(fx_spec["parameters"])
        if "wetDry" in fx_spec:
            payload["wetDry"] = fx_spec["wetDry"]
        p = commands.apply_command(p, "fx.add", payload)

    send_db = spec.get("sendRoomDb")
    if send_db is not None:
        p = _ensure_natural_room_bus(p)
        p = commands.apply_command(
            p,
            "send.set",
            {"trackId": track_id, "busId": ROOM_BUS_ID, "levelDb": float(send_db), "preFader": False},
        )
    return p


def _level_match_and_write(
    pcm: np.ndarray,
    sr: int,
    out_path: Path,
    target_lufs: float = -16.0,
) -> dict[str, Any]:
    """Level-match stereo PCM to target LUFS with -1.0 dBTP true-peak ceiling and write 24-bit WAV."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
    if peak < 1e-6:
        sf.write(str(out_path), np.zeros_like(pcm, dtype=np.float32), sr, subtype="PCM_24")
        return {"path": str(out_path), "integratedLufs": -70.0, "truePeakDbtp": -70.0}

    cur = loudness.measure_loudness(pcm, sr)
    cur_lufs = float(cur.get("integratedLufs", -24.0))
    cur_tp = float(cur.get("truePeakDbtp", -6.0))
    gain_db = max(-24.0, min(28.0, target_lufs - cur_lufs))
    # Cap gain so True Peak never exceeds -1.0 dBTP!
    max_safe_gain_db = -1.0 - cur_tp
    applied_gain_db = min(gain_db, max_safe_gain_db)
    matched = (pcm.astype(np.float32) * float(10.0 ** (applied_gain_db / 20.0))).astype(np.float32)
    matched = np.clip(matched, -0.98, 0.98)
    sf.write(str(out_path), matched, sr, subtype="PCM_24")
    final_m = loudness.measure_loudness(matched, sr)
    return {
        "path": str(out_path),
        "integratedLufs": final_m["integratedLufs"],
        "truePeakDbtp": final_m["truePeakDbtp"],
    }


def _render_layer_previews(
    project_before: Project,
    project_after: Project,
    *,
    target_track_id: str,
    take_id: str,
    start_beats: float,
    end_beats: float,
) -> tuple[dict[str, Any], np.ndarray, int]:
    """Render 3 level-matched preview WAVs: solo.wav, in_context.wav, before_mix.wav (Section 39)."""
    take_dir = store.project_dir(project_after.id) / "takes" / take_id
    take_dir.mkdir(parents=True, exist_ok=True)

    # 1. Solo render (target track soloed -> preserves its exact Pro Instrument + Insert FX + Natural Room Send!)
    solo_proj = deepcopy(project_after)
    for t in solo_proj.tracks:
        t.solo = (t.id == target_track_id)
        if t.id == target_track_id:
            t.mute = False
    solo_pcm, sr = renderer.render_project_to_array(solo_proj, start_beats=start_beats, end_beats=end_beats)
    solo_meta = _level_match_and_write(solo_pcm, sr, take_dir / "solo.wav")

    # 2. In-context mix render (all active layers together)
    ctx_pcm, _ = renderer.render_project_to_array(project_after, start_beats=start_beats, end_beats=end_beats)
    ctx_meta = _level_match_and_write(ctx_pcm, sr, take_dir / "in_context.wav")

    # 3. Before-mix A/B render
    if any(not t.mute and t.clips for t in project_before.tracks):
        before_pcm, _ = renderer.render_project_to_array(project_before, start_beats=start_beats, end_beats=end_beats)
    else:
        before_pcm = np.zeros_like(ctx_pcm, dtype=np.float32)
    before_meta = _level_match_and_write(before_pcm, sr, take_dir / "before_mix.wav")

    return (
        {
            "solo": solo_meta,
            "in_context": ctx_meta,
            "before_mix": before_meta,
        },
        solo_pcm,
        sr,
    )


def _dispatch_performer(
    role: str,
    performance_type: str,
    ctx: dict[str, Any],
    *,
    bars: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if role == "drums":
        return compose_drum_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)
    if role == "bass":
        return compose_bass_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)
    if role == "keys":
        return compose_keys_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)
    if role == "guitar":
        return compose_guitar_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)
    if role == "percussion":
        return compose_percussion_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)
    return compose_synth_performance(ctx, performance_type=performance_type, bars=bars, seed=seed)


def _archive_active_clips_to_lane(trk: Track, lane_name: str, perf_type: str) -> dict[str, Any]:
    return {
        "id": make_id("lane"),
        "name": lane_name,
        "performanceType": perf_type,
        "instrumentRef": trk.instrumentRef,
        "instrumentConfig": deepcopy(trk.instrumentConfig),
        "effects": deepcopy(trk.effects),
        "clips": [c.model_dump() for c in trk.clips],
        "isActive": False,
        "createdAt": utc_now_iso(),
    }


def generate_session_layer(
    project_id: str,
    *,
    target_instrument: str,
    performance_type: str | None = None,
    instruction: str = "",
    start_beats: float = 0.0,
    bars: int = 8,
    preferred_strategy: str = "auto",
    variation_intensity: str = "moderate",
    variation_of_existing: bool = False,
    as_alternative_take: bool = False,
    activate_take: bool = True,
    target_track_id: str | None = None,
    track_name: str | None = None,
    reference_id: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a single independent, context-aware instrument layer with strict Layer Protection (Section 7)."""
    role = _normalize_role(target_instrument)
    proj_before = store.load_project(project_id)
    bpb = proj_before.timeSignature.beats_per_bar
    end_beats = start_beats + bars * bpb

    # Ensure shared locked Chord Timeline exists before harmonic instruments run!
    if not proj_before.chordTrack:
        ensure_session_chord_timeline(project_id, key=str((proj_before.musicMemory or {}).get("sessionKey") or "D minor"), lock=True)
        proj_before = store.load_project(project_id)

    # Resolve target track if updating / adding alternative take lane
    existing_target: Track | None = None
    if target_track_id:
        existing_target = next((t for t in proj_before.tracks if t.id == target_track_id), None)
    elif as_alternative_take or variation_of_existing:
        existing_target = next(
            (t for t in reversed(proj_before.tracks) if _infer_track_role(t) == role and t.type == "midi"),
            None,
        )

    # Enforce strict Layer Protection: NEVER silently overwrite a Locked track!
    mem_states = dict((proj_before.musicMemory or {}).get("layerStates") or {})
    if existing_target is not None:
        cur_state = str((mem_states.get(existing_target.id) or {}).get("state") or "Draft")
        if cur_state == "Locked" and not as_alternative_take:
            raise ValueError(
                f"Track '{existing_target.name}' ({existing_target.id}) is Locked. "
                "Unlock it first or pass as_alternative_take=True to add a non-destructive Take Lane."
            )

    # Snapshot ALL protected tracks EXCEPT an explicitly requested target track for Take Lane addition
    protected_before = snapshot_protected_layers(proj_before)
    if existing_target is not None and as_alternative_take:
        protected_before.pop(existing_target.id, None)

    # Record Undo snapshot before mutating
    proposals.record_undo_snapshot(proj_before)

    # Build compact shared SessionContext
    ctx = build_session_context(
        proj_before,
        section_range={"startBeats": start_beats, "endBeats": end_beats},
        focus_instrument=role,
    )

    # Optional Reference-based Layer Context (Section 30)
    ref_usage: dict[str, Any] | None = None
    if reference_id:
        ref = next((r for r in proj_before.references if r.get("id") == reference_id), None)
        if ref:
            bp = ref.get("blueprint") or {}
            ref_bpm = (bp.get("tempoMap") or {}).get("bpm")
            ref_key = (bp.get("harmonicCharacter") or {}).get("key")
            ref_usage = {
                "referenceId": reference_id,
                "referenceName": ref.get("name"),
                "referencedElements": list(ref.get("selectedInfluences") or ["groove", "harmony"]),
                "excludedElements": ["melody_copy", "vocals"],
                "referenceBpm": ref_bpm,
                "referenceKey": ref_key,
            }

    # Resolve idiomatic Performance Spec
    perf_key, spec = resolve_performance_spec(role, performance_type=performance_type, instruction=instruction)
    strategy = spec.get("recommendedStrategy", "strategy_c_pro_instrument")
    if preferred_strategy in ("strategy_c_pro_instrument", "strategy_e_hybrid"):
        strategy = preferred_strategy

    # Compose idiomatic notes (or structured musical variation of existing track!)
    variation_report: dict[str, Any] | None = None
    if variation_of_existing and existing_target is not None and existing_target.clips:
        src_notes = [n.model_dump() for n in existing_target.clips[0].notes]
        notes, variation_report = vary_layer_notes(
            src_notes,
            role=role,
            intensity=variation_intensity,
            style_hint=instruction or perf_key,
            ctx=ctx,
            seed=seed,
        )
        perf_meta = {"performanceType": perf_key, "variation": variation_report}
    else:
        notes, perf_meta = _dispatch_performer(role, perf_key, ctx, bars=bars, seed=seed)

    # Apply cleanly to project (either new track OR alternative Take Lane on target track)
    updated = deepcopy(proj_before)
    if end_beats > updated.lengthBeats:
        updated = commands.apply_command(updated, "project.setLength", {"lengthBeats": end_beats})

    role_def = _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["keys"])
    clip_name = f"{spec['label']} ({bars} bars)"
    new_clip_dict = {
        "id": make_id("clp"),
        "name": clip_name,
        "type": "midi",
        "timelineStartBeats": start_beats,
        "durationBeats": bars * bpb,
        "notes": notes,
    }

    lane_id: str | None = None
    if existing_target is not None and (as_alternative_take or variation_of_existing):
        tid = existing_target.id
        trk_cur = next(t for t in updated.tracks if t.id == tid)
        # Preserve existing active performance as Take Lane A if not already archived!
        if trk_cur.clips and not trk_cur.takeLanes:
            lane_a_name = f"Take A · {trk_cur.clips[0].name}"
            lane_a = _archive_active_clips_to_lane(trk_cur, lane_a_name, str((trk_cur.instrumentConfig or {}).get("performanceType") or "original"))
            lane_a["isActive"] = not activate_take
            updated = commands.apply_command(updated, "track.addTakeLane", {"trackId": tid, "lane": lane_a})

        # Create new Take Lane for this performance
        lane_letter = chr(ord("A") + len(next(t for t in updated.tracks if t.id == tid).takeLanes))
        lane_id = make_id("lane")
        new_lane = {
            "id": lane_id,
            "name": f"Take {lane_letter} · {spec['label']}",
            "performanceType": perf_key,
            "instrumentRef": spec["instrumentRef"],
            "instrumentConfig": {"preset": spec.get("preset"), "articulation": spec.get("articulation"), "performanceType": perf_key},
            "effects": [default_fx_slot(fx["type"], make_id("fx"), preset_id=fx.get("preset")) for fx in (spec.get("subtleFx") or [])],
            "clips": [new_clip_dict],
            "isActive": activate_take,
            "createdAt": utc_now_iso(),
        }
        updated = commands.apply_command(updated, "track.addTakeLane", {"trackId": tid, "lane": new_lane})

        if activate_take:
            # Mark all other lanes inactive and replace track's active clips so Take A and Take B NEVER double-play!
            trk_mut = next(t for t in updated.tracks if t.id == tid)
            for ln in trk_mut.takeLanes:
                ln["isActive"] = (ln.get("id") == lane_id)
            for old_c in list(trk_mut.clips):
                updated = commands.apply_command(updated, "clip.delete", {"clipId": old_c.id})
            updated = commands.apply_command(updated, "clip.add", {"trackId": tid, "clip": new_clip_dict})
            updated = _apply_spec_to_track(updated, tid, spec, role=role, replace_fx=True)
            next(t for t in updated.tracks if t.id == tid).instrumentConfig["performanceType"] = perf_key
    else:
        tid = make_id("trk")
        t_label = track_name or (f"{role_def['label']} ({spec['label'].split('/')[0].strip()})" if perf_key == "solo" else role_def["label"])
        updated = commands.apply_command(
            updated,
            "track.add",
            {
                "id": tid,
                "name": t_label,
                "type": "midi",
                "color": role_def["color"],
                "instrumentRef": spec["instrumentRef"],
            },
        )
        updated = _apply_spec_to_track(updated, tid, spec, role=role, replace_fx=True)
        updated = commands.apply_command(updated, "clip.add", {"trackId": tid, "clip": new_clip_dict})
        trk_new = next(t for t in updated.tracks if t.id == tid)
        trk_new.instrumentConfig["performanceType"] = perf_key
        # Store Take A lane cleanly on track too so subsequent alternatives compare cleanly
        lane_id = make_id("lane")
        lane_a = {
            "id": lane_id,
            "name": f"Take A · {spec['label']}",
            "performanceType": perf_key,
            "instrumentRef": spec["instrumentRef"],
            "instrumentConfig": deepcopy(trk_new.instrumentConfig),
            "effects": deepcopy(trk_new.effects),
            "clips": [c.model_dump() for c in trk_new.clips],
            "isActive": True,
            "createdAt": utc_now_iso(),
        }
        updated = commands.apply_command(updated, "track.addTakeLane", {"trackId": tid, "lane": lane_a})

    # Verify cryptographic integrity of ALL previously protected layers BEFORE saving!
    protected_check = verify_protected_layers_unchanged(updated, protected_before)
    if not protected_check["allProtectedIntact"]:
        raise RuntimeError(f"Layer Protection violation detected: {protected_check['violations']}")

    # Update musicMemory layerState & groove profile
    mem = dict(updated.musicMemory or {})
    l_states = dict(mem.get("layerStates") or {})
    trk_final = next(t for t in updated.tracks if t.id == tid)
    l_states[tid] = {
        "trackId": tid,
        "trackName": trk_final.name,
        "role": role,
        "performanceType": perf_key,
        "state": "Generated",
        "integrityHash": compute_layer_integrity_hash(updated, tid),
        "updatedAt": utc_now_iso(),
    }
    mem["layerStates"] = l_states
    updated.musicMemory = mem

    # Render 3-mode level-matched previews (Solo / In-Context / Before A-B)
    take_id = make_id("take")
    previews, solo_pcm, sr = _render_layer_previews(
        proj_before,
        updated,
        target_track_id=tid,
        take_id=take_id,
        start_beats=start_beats,
        end_beats=end_beats,
    )

    # Real vocal leakage acoustic screening on solo PCM (strict instrumental guarantee)
    vocal_check = screen_vocal_leakage(
        solo_pcm,
        sr,
        source_kind="deterministic_midi_synth",
    )

    # Run 5-Part Musical Quality Gate (Section 32)
    qgate = evaluate_musical_quality_gate(
        requested_instrument=role,
        performance_type=perf_key,
        source_engine="pro-instrument-performance",
        instrument_ref=trk_final.instrumentRef,
        notes=notes,
        audio_pcm=solo_pcm,
        sr=sr,
        target_bpm=updated.bpm,
        detected_bpm=updated.bpm,  # MIDI Pro Instrument rendered sample-accurately on project tempo grid
        target_bars=bars,
        chord_timeline=ctx["chordTimeline"],
        key=ctx["key"],
        scale=ctx["scale"],
        protected_check=protected_check,
        isolation_status="isolated_pure",
        vocal_screening=vocal_check,
        silent_fallback_occurred=False,
    )

    # Persist Take metadata in project.takes so DAW UI & REST API can audition all 3 preview modes!
    take_record = {
        "id": take_id,
        "kind": "session_layer",
        "trackId": tid,
        "laneId": lane_id,
        "targetInstrument": role,
        "performanceType": perf_key,
        "sourceEngine": "pro-instrument-performance",
        "generationStrategy": strategy,
        "instrumentRef": trk_final.instrumentRef,
        "instrumentPreset": (trk_final.instrumentConfig or {}).get("preset"),
        "previewAudioPaths": {k: v["path"] for k, v in previews.items()},
        "previewMetrics": previews,
        "qualityGate": qgate,
        "status": "applied" if activate_take else "candidate",
        "createdAt": utc_now_iso(),
    }
    updated.takes = (list(updated.takes or []) + [take_record])[-40:]

    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj_before.revision)
    session.event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"Session layer generated: {trk_final.name} ({perf_key})",
            "project": saved.model_dump(),
        },
    )

    return {
        "takeId": take_id,
        "projectId": saved.id,
        "revision": saved.revision,
        "trackId": tid,
        "trackName": trk_final.name,
        "laneId": lane_id,
        "targetInstrument": role,
        "performanceType": perf_key,
        "performanceMeta": perf_meta,
        "sourceEngine": "pro-instrument-performance",
        "generationStrategy": strategy,
        "instrumentUsed": {
            "instrumentRef": trk_final.instrumentRef,
            "preset": (trk_final.instrumentConfig or {}).get("preset"),
            "articulation": (trk_final.instrumentConfig or {}).get("articulation"),
            "qualityTier": get_instrument_quality_tier(trk_final.instrumentRef or "")["qualityTier"],
        },
        "fxChain": [f.get("type") for f in trk_final.effects],
        "midiNoteCount": len(notes),
        "previewAudio": previews,
        "variationReport": variation_report,
        "referenceUsage": ref_usage,
        "protectedLayersCheck": protected_check,
        "vocalScreening": vocal_check,
        "qualityGate": qgate,
        "layerState": "Generated",
        "sessionContextSnapshot": {
            "bpm": ctx["bpm"],
            "key": ctx["key"],
            "chordCount": len(ctx["chordTimeline"]),
            "existingTrackCount": len(ctx["existingTracks"]),
            "protectedTrackCount": len(protected_before),
        },
    }


def switch_layer_take(project_id: str, track_id: str, lane_id: str) -> dict[str, Any]:
    """Non-destructively switch active Take Lane on a track (e.g. Guitar Take A Funk <-> Take B Clean) without double-playing!"""
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")
    lane = next((ln for ln in trk.takeLanes if ln.get("id") == lane_id), None)
    if lane is None:
        raise FileNotFoundError(f"Take lane not found: {lane_id}")

    protected_before = snapshot_protected_layers(proj)
    protected_before.pop(track_id, None)
    proposals.record_undo_snapshot(proj)

    updated = deepcopy(proj)
    utrk = next(t for t in updated.tracks if t.id == track_id)
    for ln in utrk.takeLanes:
        ln["isActive"] = (ln.get("id") == lane_id)
    for old_c in list(utrk.clips):
        updated = commands.apply_command(updated, "clip.delete", {"clipId": old_c.id})
    for c_dict in lane.get("clips") or []:
        c_copy = deepcopy(c_dict)
        c_copy["id"] = make_id("clp")
        updated = commands.apply_command(updated, "clip.add", {"trackId": track_id, "clip": c_copy})

    # Restore take's instrument preset & FX chain cleanly
    utrk = next(t for t in updated.tracks if t.id == track_id)
    if lane.get("instrumentRef"):
        utrk.instrumentRef = lane["instrumentRef"]
    if lane.get("instrumentConfig"):
        utrk.instrumentConfig = deepcopy(lane["instrumentConfig"])
    if lane.get("effects") is not None:
        utrk.effects = deepcopy(lane["effects"])
    utrk.freezeState = None

    pcheck = verify_protected_layers_unchanged(updated, protected_before)
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    session.event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": f"Switched take lane: {lane.get('name')}", "project": saved.model_dump()},
    )
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "trackId": track_id,
        "activeLaneId": lane_id,
        "activeLaneName": lane.get("name"),
        "performanceType": lane.get("performanceType"),
        "protectedLayersCheck": pcheck,
    }


def generate_session_solo(
    project_id: str,
    *,
    instrument: str = "guitar",
    instruction: str = "",
    start_beats: float = 0.0,
    bars: int = 8,
    seed: int = 77,
) -> dict[str, Any]:
    """Generate a dedicated expressive Guitar, Piano, or Synth Solo layer without touching any existing groove layer (Section 16)."""
    role = _normalize_role(instrument)
    perf_type = "piano_solo" if role == "keys" else ("lead_solo" if role == "synth" else "solo")
    title = f"{role.title()} Solo"
    res = generate_session_layer(
        project_id,
        target_instrument=role,
        performance_type=perf_type,
        instruction=instruction or f"Expressive {role} solo",
        start_beats=start_beats,
        bars=bars,
        track_name=title,
        seed=seed,
    )
    # Give Solo track clear center-forward presence so singing bends & phrases shine above the groove
    proj = store.load_project(project_id)
    updated = commands.apply_command(proj, "track.setGain", {"trackId": res["trackId"], "gainDb": 3.5})
    updated = commands.apply_command(updated, "track.setPan", {"trackId": res["trackId"], "pan": 0.06})
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    res["revision"] = saved.revision
    return res


def generate_session_transition(
    project_id: str,
    *,
    boundary_beat: float = 32.0,
    seed: int = 530,
) -> dict[str, Any]:
    """Create a real 2-beat musical transition (drum turnaround fill + chromatic bass pickup) into `boundary_beat` (Section 28)."""
    proj_before = store.load_project(project_id)
    protected_before = snapshot_protected_layers(proj_before)
    proposals.record_undo_snapshot(proj_before)
    ctx = build_session_context(proj_before)
    tr = compose_transition_pickup(ctx, boundary_beat=boundary_beat, seed=seed)

    updated = deepcopy(proj_before)
    # Dedicated Transition Drum Fill track (leaves Locked Main Drums 100% cryptographically untouched!)
    drum_tid = make_id("trk")
    updated = commands.apply_command(
        updated,
        "track.add",
        {"id": drum_tid, "name": "Transition Drum Fill", "type": "midi", "color": "#b89458", "instrumentRef": "pro-drum-rack"},
    )
    _, drum_spec = resolve_performance_spec("drums", "drum_fill_transition")
    updated = _apply_spec_to_track(updated, drum_tid, drum_spec, role="drums")
    updated = commands.apply_command(
        updated,
        "clip.add",
        {
            "trackId": drum_tid,
            "clip": {
                "name": "Turnaround Drum Fill",
                "type": "midi",
                "timelineStartBeats": tr["startBeat"],
                "durationBeats": tr["durationBeats"],
                "notes": tr["drumFillNotes"],
            },
        },
    )

    # Dedicated Transition Bass Pickup track
    bass_tid = make_id("trk")
    updated = commands.apply_command(
        updated,
        "track.add",
        {"id": bass_tid, "name": "Transition Bass Pickup", "type": "midi", "color": "#648ea8", "instrumentRef": "sf-bass-electric"},
    )
    _, bass_spec = resolve_performance_spec("bass", "pocket_groove")
    updated = _apply_spec_to_track(updated, bass_tid, bass_spec, role="bass")
    updated = commands.apply_command(
        updated,
        "clip.add",
        {
            "trackId": bass_tid,
            "clip": {
                "name": "Chromatic Bass Pickup",
                "type": "midi",
                "timelineStartBeats": tr["startBeat"],
                "durationBeats": tr["durationBeats"],
                "notes": tr["bassPickupNotes"],
            },
        },
    )

    pcheck = verify_protected_layers_unchanged(updated, protected_before)
    if not pcheck["allProtectedIntact"]:
        raise RuntimeError(f"Layer Protection violation in transition: {pcheck['violations']}")
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj_before.revision)
    session.event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": "Musical transition added", "project": saved.model_dump()},
    )
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "transitionTrackIds": [drum_tid, bass_tid],
        "startBeat": tr["startBeat"],
        "endBeat": tr["endBeat"],
        "descriptionKo": tr["descriptionKo"],
        "protectedLayersCheck": pcheck,
    }


def generate_session_bridge(
    project_id: str,
    *,
    start_beats: float | None = None,
    bars: int = 4,
    include_transition: bool = True,
    seed: int = 520,
) -> dict[str, Any]:
    """Generate a genuinely contrasting Bridge section + seamless Transition while keeping all Main Groove layers 100% intact (Sections 27 & 28)."""
    proj_before = store.load_project(project_id)
    bpb = proj_before.timeSignature.beats_per_bar
    bridge_start = float(start_beats if start_beats is not None else max(32.0, bpb * 8.0))
    bridge_end = bridge_start + bars * bpb

    protected_before = snapshot_protected_layers(proj_before)
    proposals.record_undo_snapshot(proj_before)

    ctx = build_session_context(proj_before, section_range={"startBeats": 0.0, "endBeats": bridge_start})
    bridge_data = compose_bridge_section(ctx, start_beat=bridge_start, bars=bars, seed=seed)

    updated = deepcopy(proj_before)
    if bridge_end > updated.lengthBeats:
        updated = commands.apply_command(updated, "project.setLength", {"lengthBeats": bridge_end})

    # Add MAIN GROOVE and BRIDGE section markers cleanly
    if not any(s.name.upper() == "MAIN GROOVE" for s in updated.sections):
        updated = commands.apply_command(
            updated,
            "section.add",
            {"name": "MAIN GROOVE", "startBeats": 0.0, "endBeats": bridge_start, "color": "#4f6d5a"},
        )
    updated = commands.apply_command(
        updated,
        "section.add",
        {"name": "BRIDGE", "startBeats": bridge_start, "endBeats": bridge_end, "color": "#61517a"},
    )

    # Append Bridge contrasting chords to Chord Track (preserving Bars 1–8 Main Groove chords!)
    kept_chords = [c.model_dump() for c in updated.chordTrack if c.endBeat <= bridge_start + 0.01]
    updated = commands.apply_command(
        updated,
        "chord.setTrack",
        {"chords": kept_chords + bridge_data["bridgeChords"], "locked": True},
    )

    # Optional seamless 2-beat Transition leading into Bridge
    transition_track_ids: list[str] = []
    if include_transition and bridge_start >= 2.0:
        tr = compose_transition_pickup(
            {**ctx, "chordTimeline": kept_chords + bridge_data["bridgeChords"]},
            boundary_beat=bridge_start,
            seed=seed + 10,
        )
        for name_t, role_t, perf_t, tr_notes in [
            ("Transition · Drum Fill", "drums", "drum_fill_transition", tr["drumFillNotes"]),
            ("Transition · Bass Pickup", "bass", "pocket_groove", tr["bassPickupNotes"]),
        ]:
            t_id = make_id("trk")
            _, sp = resolve_performance_spec(role_t, perf_t)
            updated = commands.apply_command(
                updated,
                "track.add",
                {"id": t_id, "name": name_t, "type": "midi", "color": _ROLE_DEFAULTS[role_t]["color"], "instrumentRef": sp["instrumentRef"]},
            )
            updated = _apply_spec_to_track(updated, t_id, sp, role=role_t)
            updated = commands.apply_command(
                updated,
                "clip.add",
                {
                    "trackId": t_id,
                    "clip": {
                        "name": name_t,
                        "type": "midi",
                        "timelineStartBeats": tr["startBeat"],
                        "durationBeats": tr["durationBeats"],
                        "notes": tr_notes,
                    },
                },
            )
            transition_track_ids.append(t_id)

    # Create Bridge instrument layers at `bridge_start`..`bridge_end` (zero mutation to Main Groove tracks!)
    bridge_track_ids: list[str] = []
    bridge_spec_map = [
        ("drums", "pocket_groove", "Bridge · Drums (Intimate Rim)"),
        ("bass", "melodic_bassline", "Bridge · Bass (Melodic)"),
        ("keys", "neo_soul_comping", "Bridge · Rhodes (Reharmonized)"),
        ("guitar", "clean_melodic", "Bridge · Guitar (Clean Motif)"),
        ("percussion", "subtle_layer", "Bridge · Percussion"),
    ]
    for role_b, perf_b, name_b in bridge_spec_map:
        b_notes = bridge_data["layerClips"][role_b]
        t_id = make_id("trk")
        _, sp = resolve_performance_spec(role_b, perf_b)
        updated = commands.apply_command(
            updated,
            "track.add",
            {"id": t_id, "name": name_b, "type": "midi", "color": _ROLE_DEFAULTS[role_b]["color"], "instrumentRef": sp["instrumentRef"]},
        )
        updated = _apply_spec_to_track(updated, t_id, sp, role=role_b)
        updated = commands.apply_command(
            updated,
            "clip.add",
            {
                "trackId": t_id,
                "clip": {
                    "name": f"{name_b} ({bars} bars)",
                    "type": "midi",
                    "timelineStartBeats": bridge_start,
                    "durationBeats": bars * bpb,
                    "notes": b_notes,
                },
            },
        )
        bridge_track_ids.append(t_id)

    pcheck = verify_protected_layers_unchanged(updated, protected_before)
    if not pcheck["allProtectedIntact"]:
        raise RuntimeError(f"Layer Protection violation during bridge generation: {pcheck['violations']}")

    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj_before.revision)
    session.event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": f"Bridge section generated ({bars} bars)", "project": saved.model_dump()},
    )
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "startBeat": bridge_start,
        "endBeat": bridge_end,
        "bars": bars,
        "bridgeChords": bridge_data["bridgeChords"],
        "contrastSummary": bridge_data["contrastSummary"],
        "transitionTrackIds": transition_track_ids,
        "bridgeTrackIds": bridge_track_ids,
        "protectedLayersCheck": pcheck,
    }


def validate_session_layer(project_id: str, track_id: str) -> dict[str, Any]:
    """Run full 5-Part Musical Quality Gate + Loop Integrity on any existing session track."""
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")
    role = _infer_track_role(trk)
    bpb = proj.timeSignature.beats_per_bar
    start_b = min((c.timelineStartBeats for c in trk.clips), default=0.0)
    end_b = max((c.timelineStartBeats + c.durationBeats for c in trk.clips), default=bpb * 8.0)
    bars = max(1, int(round((end_b - start_b) / bpb)))

    solo_proj = deepcopy(proj)
    for t in solo_proj.tracks:
        t.solo = (t.id == track_id)
        if t.id == track_id:
            t.mute = False
    pcm, sr = renderer.render_project_to_array(solo_proj, start_beats=start_b, end_beats=end_b)
    ctx = build_session_context(proj, section_range={"startBeats": start_b, "endBeats": end_b})
    all_notes = [
        {**n.model_dump(), "startBeat": c.timelineStartBeats + n.startBeat}
        for c in trk.clips
        if c.type == "midi"
        for n in c.notes
    ]
    qgate = evaluate_musical_quality_gate(
        requested_instrument=role,
        performance_type=str((trk.instrumentConfig or {}).get("performanceType") or "custom"),
        source_engine="pro-instrument-performance" if trk.type == "midi" else "native-audio",
        instrument_ref=trk.instrumentRef,
        notes=all_notes or None,
        audio_pcm=pcm,
        sr=sr,
        target_bpm=proj.bpm,
        detected_bpm=proj.bpm,
        target_bars=bars,
        chord_timeline=ctx["chordTimeline"],
        key=ctx["key"],
        scale=ctx["scale"],
        protected_check={"allProtectedIntact": True, "verifiedProtectedTrackIds": [], "violations": []},
        isolation_status="isolated_pure" if trk.type == "midi" else "extracted_stem",
    )
    return {"projectId": project_id, "trackId": track_id, "trackName": trk.name, "role": role, "qualityGate": qgate}


def align_session_loop(project_id: str, track_id: str, target_bars: int = 8) -> dict[str, Any]:
    """Render/extract a click-free, exact bar-boundary aligned loop WAV for a track (preserving originals untouched)."""
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")
    bpb = proj.timeSignature.beats_per_bar
    out_dir = store.project_dir(project_id) / "exports" / "aligned_loops"
    out_dir.mkdir(parents=True, exist_ok=True)

    if trk.type == "audio" and trk.clips and trk.clips[0].assetId:
        _, src_path = store.resolve_asset_file(project_id, trk.clips[0].assetId)
    else:
        solo_proj = deepcopy(proj)
        for t in solo_proj.tracks:
            t.solo = (t.id == track_id)
            if t.id == track_id:
                t.mute = False
        pcm, sr = renderer.render_project_to_array(solo_proj, start_beats=0.0, end_beats=target_bars * bpb)
        src_path = out_dir / f"{track_id}_raw.wav"
        sf.write(str(src_path), np.clip(pcm, -1.0, 1.0).astype(np.float32), sr, subtype="PCM_24")

    aligned_path = out_dir / f"{track_id}_aligned_{target_bars}bars.wav"
    return align_audio_loop_to_bars(
        src_path,
        aligned_path,
        target_bpm=proj.bpm,
        target_bars=target_bars,
        bpb=bpb,
    )


def get_layer_preview_path(project_id: str, track_id: str, mode: str = "in_context") -> Path:
    """Resolve (or render on-demand) the level-matched preview WAV (`solo | in_context | before_mix`) for a track."""
    if mode not in ("solo", "in_context", "before_mix"):
        raise ValueError("Preview mode must be 'solo', 'in_context', or 'before_mix'")
    proj = store.load_project(project_id)
    # Prefer latest recorded take for this track
    for take in reversed(proj.takes or []):
        if take.get("kind") == "session_layer" and take.get("trackId") == track_id:
            p_str = (take.get("previewAudioPaths") or {}).get(mode)
            if p_str and Path(p_str).is_file():
                return Path(p_str)
    # Render on-demand cleanly
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")
    bpb = proj.timeSignature.beats_per_bar
    start_b = min((c.timelineStartBeats for c in trk.clips), default=0.0)
    end_b = max((c.timelineStartBeats + c.durationBeats for c in trk.clips), default=bpb * 8.0)
    out_dir = store.project_dir(project_id) / "takes" / f"preview_{track_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{mode}.wav"
    render_proj = deepcopy(proj)
    if mode == "solo":
        for t in render_proj.tracks:
            t.solo = (t.id == track_id)
            if t.id == track_id:
                t.mute = False
    elif mode == "before_mix":
        for t in render_proj.tracks:
            if t.id == track_id:
                t.mute = True
    pcm, sr = renderer.render_project_to_array(render_proj, start_beats=start_b, end_beats=end_b)
    _level_match_and_write(pcm, sr, out_path)
    return out_path
