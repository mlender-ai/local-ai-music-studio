"""Shared Command Executor for AI-Native DAW (mirrors apps/daw/src/commands/)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schema import Clip, LoopRegion, MidiNote, Project, SectionMarker, TimeSignature, Track, make_id, utc_now_iso

TRACK_PALETTE = [
    "#6a997c",  # sage green
    "#867ca8",  # slate lavender
    "#b89458",  # warm ochre
    "#648ea8",  # steel blue
    "#9e7389",  # dusty mauve
    "#6a9999",  # muted teal
    "#9c8568",  # sandstone
]


def _find_track(project: Project, track_id: str) -> Track:
    for trk in project.tracks:
        if trk.id == track_id:
            return trk
    raise ValueError(f"Track not found: {track_id}")


def _find_clip(project: Project, clip_id: str) -> tuple[Track, Clip]:
    for trk in project.tracks:
        for clp in trk.clips:
            if clp.id == clip_id:
                return trk, clp
    raise ValueError(f"Clip not found: {clip_id}")


def apply_command(project: Project, cmd_type: str, payload: dict[str, Any]) -> Project:
    """Validate and execute a single state-mutating DAW command on a copy of Project."""
    p = deepcopy(project)

    if cmd_type == "project.rename":
        name = str(payload["name"]).strip()
        if not name:
            raise ValueError("Project name cannot be empty")
        p.name = name

    elif cmd_type == "project.setTempo":
        bpm = float(payload["bpm"])
        if not (30.0 <= bpm <= 300.0):
            raise ValueError("BPM must be between 30 and 300")
        p.bpm = round(bpm, 3)

    elif cmd_type == "project.setTimeSignature":
        p.timeSignature = TimeSignature(
            numerator=int(payload["numerator"]),
            denominator=int(payload["denominator"]),
        )

    elif cmd_type == "project.setLength":
        length_beats = float(payload["lengthBeats"])
        if length_beats < 4.0 or length_beats > 4096.0:
            raise ValueError("Project lengthBeats out of range")
        p.lengthBeats = length_beats

    elif cmd_type == "project.setMasterGain":
        gain = float(payload["gainDb"])
        p.masterGainDb = max(-60.0, min(6.0, gain))

    elif cmd_type == "transport.setLoop":
        enabled = bool(payload.get("enabled", p.loopRegion.enabled))
        start = float(payload.get("startBeats", p.loopRegion.startBeats))
        end = float(payload.get("endBeats", p.loopRegion.endBeats))
        p.loopRegion = LoopRegion(enabled=enabled, startBeats=start, endBeats=end)

    elif cmd_type == "track.add":
        trk_type = payload.get("type", "audio")
        color = payload.get("color") or TRACK_PALETTE[len(p.tracks) % len(TRACK_PALETTE)]
        trk = Track(
            id=payload.get("id") or make_id("trk"),
            name=str(payload.get("name") or f"Track {len(p.tracks) + 1}"),
            type=trk_type,
            color=color,
            stemLabel=payload.get("stemLabel"),
            instrumentRef=payload.get("instrumentRef") or ("basic-poly-synth" if trk_type == "midi" else None),
        )
        p.tracks.append(trk)

    elif cmd_type == "track.remove":
        track_id = str(payload["trackId"])
        before = len(p.tracks)
        # Never deletes underlying assets in p.assets!
        p.tracks = [t for t in p.tracks if t.id != track_id]
        if len(p.tracks) == before:
            raise ValueError(f"Track not found: {track_id}")

    elif cmd_type == "track.rename":
        trk = _find_track(p, str(payload["trackId"]))
        name = str(payload["name"]).strip()
        if not name:
            raise ValueError("Track name cannot be empty")
        trk.name = name

    elif cmd_type == "track.reorder":
        from_idx = int(payload["fromIndex"])
        to_idx = int(payload["toIndex"])
        if not (0 <= from_idx < len(p.tracks) and 0 <= to_idx < len(p.tracks)):
            raise ValueError("Track reorder indices out of bounds")
        item = p.tracks.pop(from_idx)
        p.tracks.insert(to_idx, item)

    elif cmd_type == "track.setColor":
        trk = _find_track(p, str(payload["trackId"]))
        trk.color = str(payload["color"])

    elif cmd_type == "track.setGain":
        trk = _find_track(p, str(payload["trackId"]))
        trk.gainDb = max(-60.0, min(6.0, float(payload["gainDb"])))

    elif cmd_type == "track.setPan":
        trk = _find_track(p, str(payload["trackId"]))
        trk.pan = max(-1.0, min(1.0, float(payload["pan"])))

    elif cmd_type == "track.setMute":
        trk = _find_track(p, str(payload["trackId"]))
        trk.mute = bool(payload["mute"])

    elif cmd_type == "track.setSolo":
        trk = _find_track(p, str(payload["trackId"]))
        trk.solo = bool(payload["solo"])

    elif cmd_type == "track.setInstrument":
        trk = _find_track(p, str(payload["trackId"]))
        inst = payload.get("instrumentRef")
        trk.instrumentRef = str(inst).strip() if inst else None

    elif cmd_type == "clip.add":
        trk = _find_track(p, str(payload["trackId"]))
        clip_data = dict(payload["clip"])
        clip_data.setdefault("id", make_id("clp"))
        clip = Clip(**clip_data)
        trk.clips.append(clip)

    elif cmd_type == "clip.move":
        clip_id = str(payload["clipId"])
        src_trk, clp = _find_clip(p, clip_id)
        new_start = max(0.0, float(payload["timelineStartBeats"]))
        target_track_id = payload.get("targetTrackId")
        clp.timelineStartBeats = new_start
        if target_track_id and target_track_id != src_trk.id:
            dst_trk = _find_track(p, str(target_track_id))
            if (dst_trk.type == "midi") != (clp.type == "midi"):
                raise ValueError("Cannot move MIDI clip to Audio track or vice versa")
            src_trk.clips = [c for c in src_trk.clips if c.id != clip_id]
            dst_trk.clips.append(clp)

    elif cmd_type == "clip.trim":
        _, clp = _find_clip(p, str(payload["clipId"]))
        if "timelineStartBeats" in payload:
            clp.timelineStartBeats = max(0.0, float(payload["timelineStartBeats"]))
        if "durationBeats" in payload:
            clp.durationBeats = max(0.25, float(payload["durationBeats"]))
        if "sourceOffsetSec" in payload:
            clp.sourceOffsetSec = max(0.0, float(payload["sourceOffsetSec"]))

    elif cmd_type == "clip.split":
        clip_id = str(payload["clipId"])
        split_beat = float(payload["splitBeat"])
        trk, clp = _find_clip(p, clip_id)
        rel_beat = split_beat - clp.timelineStartBeats
        if rel_beat <= 0.05 or rel_beat >= clp.durationBeats - 0.05:
            raise ValueError("Split beat must fall strictly inside clip bounds")
        sec_per_beat = 60.0 / p.bpm
        right_notes: list[MidiNote] = []
        left_notes: list[MidiNote] = []
        for n in clp.notes:
            note_end = n.startBeat + n.durationBeats
            if note_end <= rel_beat:
                left_notes.append(n)
            elif n.startBeat >= rel_beat:
                right_notes.append(
                    MidiNote(
                        id=make_id("note"),
                        pitch=n.pitch,
                        velocity=n.velocity,
                        startBeat=round(n.startBeat - rel_beat, 6),
                        durationBeats=n.durationBeats,
                    )
                )
            else:
                left_notes.append(
                    MidiNote(
                        id=n.id,
                        pitch=n.pitch,
                        velocity=n.velocity,
                        startBeat=n.startBeat,
                        durationBeats=round(rel_beat - n.startBeat, 6),
                    )
                )
                right_notes.append(
                    MidiNote(
                        id=make_id("note"),
                        pitch=n.pitch,
                        velocity=n.velocity,
                        startBeat=0.0,
                        durationBeats=round(note_end - rel_beat, 6),
                    )
                )

        right_clip = Clip(
            id=payload.get("rightClipId") or make_id("clp"),
            name=f"{clp.name} (2)",
            type=clp.type,
            assetId=clp.assetId,
            timelineStartBeats=round(split_beat, 6),
            durationBeats=round(clp.durationBeats - rel_beat, 6),
            sourceOffsetSec=round(clp.sourceOffsetSec + rel_beat * sec_per_beat, 6)
            if clp.type == "audio"
            else 0.0,
            sourceDurationSec=clp.sourceDurationSec,
            loop=clp.loop,
            loopLengthSec=clp.loopLengthSec,
            loopLengthBeats=clp.loopLengthBeats,
            gainDb=clp.gainDb,
            notes=right_notes,
        )
        clp.durationBeats = round(rel_beat, 6)
        clp.notes = left_notes
        trk.clips.append(right_clip)

    elif cmd_type == "clip.duplicate":
        trk, clp = _find_clip(p, str(payload["clipId"]))
        dup = deepcopy(clp)
        dup.id = payload.get("newClipId") or make_id("clp")
        dup.name = f"{clp.name} copy"
        dup.timelineStartBeats = round(
            float(payload.get("timelineStartBeats", clp.timelineStartBeats + clp.durationBeats)), 6
        )
        dup.notes = [MidiNote(**{**n.model_dump(), "id": make_id("note")}) for n in clp.notes]
        trk.clips.append(dup)

    elif cmd_type == "clip.delete":
        clip_id = str(payload["clipId"])
        trk, _ = _find_clip(p, clip_id)
        trk.clips = [c for c in trk.clips if c.id != clip_id]

    elif cmd_type == "clip.setGain":
        _, clp = _find_clip(p, str(payload["clipId"]))
        clp.gainDb = max(-24.0, min(12.0, float(payload["gainDb"])))

    elif cmd_type == "clip.setLoop":
        _, clp = _find_clip(p, str(payload["clipId"]))
        clp.loop = bool(payload["loop"])

    elif cmd_type == "clip.rename":
        _, clp = _find_clip(p, str(payload["clipId"]))
        name = str(payload["name"]).strip()
        if not name:
            raise ValueError("Clip name cannot be empty")
        clp.name = name

    elif cmd_type == "midi.addNote":
        _, clp = _find_clip(p, str(payload["clipId"]))
        if clp.type != "midi":
            raise ValueError("Target clip is not a MIDI clip")
        note_data = dict(payload["note"])
        note_data.setdefault("id", make_id("note"))
        clp.notes.append(MidiNote(**note_data))

    elif cmd_type == "midi.moveNote":
        _, clp = _find_clip(p, str(payload["clipId"]))
        note_id = str(payload["noteId"])
        for n in clp.notes:
            if n.id == note_id:
                n.pitch = max(0, min(127, int(payload["pitch"])))
                n.startBeat = max(0.0, float(payload["startBeat"]))
                break
        else:
            raise ValueError(f"MIDI note not found: {note_id}")

    elif cmd_type == "midi.resizeNote":
        _, clp = _find_clip(p, str(payload["clipId"]))
        note_id = str(payload["noteId"])
        for n in clp.notes:
            if n.id == note_id:
                n.durationBeats = max(0.0625, float(payload["durationBeats"]))
                break
        else:
            raise ValueError(f"MIDI note not found: {note_id}")

    elif cmd_type == "midi.setVelocity":
        _, clp = _find_clip(p, str(payload["clipId"]))
        note_id = str(payload["noteId"])
        for n in clp.notes:
            if n.id == note_id:
                n.velocity = max(1, min(127, int(payload["velocity"])))
                break
        else:
            raise ValueError(f"MIDI note not found: {note_id}")

    elif cmd_type == "midi.deleteNote":
        _, clp = _find_clip(p, str(payload["clipId"]))
        note_id = str(payload["noteId"])
        before = len(clp.notes)
        clp.notes = [n for n in clp.notes if n.id != note_id]
        if len(clp.notes) == before:
            raise ValueError(f"MIDI note not found: {note_id}")

    elif cmd_type == "section.add":
        sec = SectionMarker(**payload)
        p.sections.append(sec)
        p.sections.sort(key=lambda s: s.startBeats)

    elif cmd_type == "section.rename":
        sec_id = str(payload["sectionId"])
        for s in p.sections:
            if s.id == sec_id:
                s.name = str(payload["name"]).strip()
                break
        else:
            raise ValueError(f"Section not found: {sec_id}")

    elif cmd_type == "section.remove":
        sec_id = str(payload["sectionId"])
        p.sections = [s for s in p.sections if s.id != sec_id]

    else:
        raise ValueError(f"Unsupported DAW command: {cmd_type}")

    p.updatedAt = utc_now_iso()
    return Project.model_validate(p.model_dump())
