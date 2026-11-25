"""Timeline Take Lanes & Selective Sub-Range Comping (Phase 04-C · Section 13)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.daw_workspace import commands, proposals, store
from engine.daw_workspace.schema import Clip, MidiNote, make_id, utc_now_iso
from engine.daw_workspace.session import event_bus
from engine.generation.daw_jobs import _carve_out_range_on_track


def _slice_clip_to_range(clip: Clip, start_beats: float, end_beats: float, bpm: float) -> Clip | None:
    """Extract only `[start_beats, end_beats]` portion of a Clip for selective Take Comping."""
    c0 = clip.timelineStartBeats
    c1 = c0 + clip.durationBeats
    s = max(c0, start_beats)
    e = min(c1, end_beats)
    if e - s <= 0.02:
        return None
    offset_beats = s - c0
    new_dur = round(e - s, 4)

    if clip.type == "audio":
        sec_per_beat = 60.0 / bpm
        return Clip(
            id=make_id("clp"),
            name=f"{clip.name} (Comp)",
            type="audio",
            assetId=clip.assetId,
            timelineStartBeats=round(s, 4),
            durationBeats=new_dur,
            sourceOffsetSec=round(clip.sourceOffsetSec + offset_beats * sec_per_beat, 4),
            sourceDurationSec=clip.sourceDurationSec,
            loop=clip.loop,
            loopLengthSec=clip.loopLengthSec,
            gainDb=clip.gainDb,
            fadeInBeats=0.05,
            fadeOutBeats=0.05,
        )

    sliced_notes: list[MidiNote] = []
    for n in clip.notes:
        n0 = c0 + n.startBeat
        n1 = n0 + n.durationBeats
        if n1 > s + 1e-4 and n0 < e - 1e-4:
            ns = max(n0, s)
            ne = min(n1, e)
            sliced_notes.append(
                MidiNote(
                    id=make_id("note"),
                    pitch=n.pitch,
                    velocity=n.velocity,
                    startBeat=round(ns - s, 4),
                    durationBeats=round(max(0.0625, ne - ns), 4),
                )
            )
    return Clip(
        id=make_id("clp"),
        name=f"{clip.name} (Comp)",
        type="midi",
        assetId=clip.assetId,
        timelineStartBeats=round(s, 4),
        durationBeats=new_dur,
        gainDb=clip.gainDb,
        notes=sliced_notes,
    )


def promote_take_lane(
    project_id: str,
    track_id: str,
    lane_id: str,
    comp_start_beats: float | None = None,
    comp_end_beats: float | None = None,
) -> dict[str, Any]:
    """Promote an entire Take Lane OR a selective sub-range onto the Track's main lane (1-click Undoable)."""
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if not trk:
        raise FileNotFoundError(f"Track not found: {track_id}")
    lane = next((ln for ln in trk.takeLanes if ln.get("id") == lane_id), None)
    if not lane:
        raise FileNotFoundError(f"Take lane not found: {lane_id}")

    proposals.record_undo_snapshot(proj)
    updated = deepcopy(proj)
    utrk = next(t for t in updated.tracks if t.id == track_id)

    lane_start = float(lane.get("startBeats", 0.0))
    lane_end = float(lane.get("endBeats", lane_start + 16.0))
    s = float(comp_start_beats if comp_start_beats is not None else lane_start)
    e = float(comp_end_beats if comp_end_beats is not None else lane_end)
    if e <= s:
        raise ValueError("Comp endBeats must be greater than startBeats")

    # Backup displaced main-lane clips into an Original Backup lane if not already backed up
    displaced = [
        c.model_dump()
        for c in utrk.clips
        if (c.timelineStartBeats + c.durationBeats) > s + 1e-4 and c.timelineStartBeats < e - 1e-4
    ]
    if displaced and not lane.get("isOriginalBackup") and not any(ln.get("isOriginalBackup") and abs(float(ln.get("startBeats", -1)) - s) < 0.05 for ln in utrk.takeLanes):
        updated = commands.apply_command(
            updated,
            "track.addTakeLane",
            {
                "trackId": track_id,
                "lane": {
                    "id": make_id("lane"),
                    "name": "Original (Backup)",
                    "startBeats": round(s, 4),
                    "endBeats": round(e, 4),
                    "clips": displaced,
                    "isOriginalBackup": True,
                    "active": False,
                    "createdAt": utc_now_iso(),
                },
            },
        )

    # Carve out `[s, e]` cleanly on main lane so unpromoted takes NEVER double-play!
    updated = _carve_out_range_on_track(updated, track_id, s, e)

    # Collect clips stored in the lane (either single `clip` or multi `clips` backup)
    raw_clips = list(lane.get("clips") or [])
    if lane.get("clip"):
        raw_clips = [lane["clip"]]

    inserted_ids: list[str] = []
    for rc in raw_clips:
        clip_obj = Clip.model_validate(rc)
        sliced = _slice_clip_to_range(clip_obj, s, e, updated.bpm)
        if sliced:
            updated = commands.apply_command(updated, "clip.add", {"trackId": track_id, "clip": sliced.model_dump()})
            inserted_ids.append(sliced.id)

    # Update active marker on lanes overlapping `[s, e]`
    utrk2 = next(t for t in updated.tracks if t.id == track_id)
    for ln in utrk2.takeLanes:
        ln["active"] = ln.get("id") == lane_id

    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"Take Lane 채택됨: {lane.get('name', lane_id)}",
            "project": saved.model_dump(),
        },
    )
    return {"promoted": True, "laneId": lane_id, "insertedClipIds": inserted_ids, "project": saved.model_dump(), "revision": saved.revision}


def restore_original_lane(project_id: str, track_id: str, lane_id: str | None = None) -> dict[str, Any]:
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if not trk:
        raise FileNotFoundError(f"Track not found: {track_id}")
    backup = (
        next((ln for ln in trk.takeLanes if ln.get("id") == lane_id), None)
        if lane_id
        else next((ln for ln in trk.takeLanes if ln.get("isOriginalBackup")), None)
    )
    if not backup:
        raise FileNotFoundError("No Original backup Take Lane found on this track")
    return promote_take_lane(project_id, track_id, backup["id"])


def rename_take_lane(project_id: str, track_id: str, lane_id: str, name: str) -> dict[str, Any]:
    proj = store.load_project(project_id)
    updated = commands.apply_command(proj, "track.renameTakeLane", {"trackId": track_id, "laneId": lane_id, "name": name})
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": f"Take Lane 이름 변경: {name}", "project": saved.model_dump()},
    )
    return {"renamed": True, "project": saved.model_dump(), "revision": saved.revision}
