"""Shared Command Executor for AI-Native DAW (mirrors apps/daw/src/commands/)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .schema import ChordEvent, Clip, LoopRegion, MidiNote, Project, SectionMarker, TimeSignature, Track, make_id, utc_now_iso

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
            stemMeta=payload.get("stemMeta"),
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
        if "preset" in payload:
            trk.instrumentConfig = {**trk.instrumentConfig, "preset": payload["preset"]}
        if "parameters" in payload and isinstance(payload["parameters"], dict):
            cur_p = dict(trk.instrumentConfig.get("parameters") or {})
            cur_p.update(payload["parameters"])
            trk.instrumentConfig = {**trk.instrumentConfig, "parameters": cur_p}
        trk.freezeState = None

    elif cmd_type == "instrument.setPreset":
        trk = _find_track(p, str(payload["trackId"]))
        trk.instrumentConfig = {**trk.instrumentConfig, "preset": payload.get("preset")}
        if isinstance(payload.get("parameters"), dict):
            cur_p = dict(trk.instrumentConfig.get("parameters") or {})
            cur_p.update(payload["parameters"])
            trk.instrumentConfig["parameters"] = cur_p
        trk.freezeState = None

    elif cmd_type == "instrument.setParams":
        trk = _find_track(p, str(payload["trackId"]))
        cur_p = dict(trk.instrumentConfig.get("parameters") or {})
        cur_p.update(dict(payload.get("parameters") or {}))
        cfg = {**trk.instrumentConfig, "parameters": cur_p}
        if "articulation" in payload:
            cfg["articulation"] = str(payload["articulation"])
        if "samplerConfig" in payload and isinstance(payload["samplerConfig"], dict):
            cfg["samplerConfig"] = {**dict(cfg.get("samplerConfig") or {}), **payload["samplerConfig"]}
        if "drumRackConfig" in payload and isinstance(payload["drumRackConfig"], dict):
            cfg["drumRackConfig"] = {**dict(cfg.get("drumRackConfig") or {}), **payload["drumRackConfig"]}
        trk.instrumentConfig = cfg
        trk.freezeState = None

    elif cmd_type in ("fx.add", "fx.remove", "fx.move", "fx.setParams", "fx.setBypass", "fx.setWetDry"):
        from engine.fx.chain import default_fx_slot

        target_kind = str(payload.get("target") or "track")
        if target_kind == "master":
            fx_list = p.masterEffects
            owner_trk = None
        elif target_kind == "bus" or payload.get("busId"):
            bid = str(payload["busId"])
            bus_obj = next((b for b in p.buses if b.get("id") == bid), None)
            if bus_obj is None:
                raise ValueError(f"Bus not found: {bid}")
            bus_obj.setdefault("effects", [])
            fx_list = bus_obj["effects"]
            owner_trk = None
        else:
            owner_trk = _find_track(p, str(payload["trackId"]))
            fx_list = owner_trk.effects

        if cmd_type == "fx.add":
            slot_id = str(payload.get("id") or make_id("fx"))
            slot = default_fx_slot(
                str(payload["type"]),
                slot_id,
                preset_id=payload.get("preset"),
                params_override=payload.get("parameters"),
            )
            if "sidechainTrackId" in payload:
                slot["sidechainTrackId"] = payload["sidechainTrackId"]
            if "wetDry" in payload:
                slot["wetDry"] = max(0.0, min(1.0, float(payload["wetDry"])))
            idx_ins = payload.get("index")
            if isinstance(idx_ins, int) and 0 <= idx_ins <= len(fx_list):
                fx_list.insert(idx_ins, slot)
            else:
                fx_list.append(slot)
        elif cmd_type == "fx.remove":
            fx_id = str(payload["fxId"])
            before = len(fx_list)
            fx_list[:] = [f for f in fx_list if f.get("id") != fx_id]
            if len(fx_list) == before:
                raise ValueError(f"FX slot not found: {fx_id}")
        elif cmd_type == "fx.move":
            from_i = int(payload["fromIndex"])
            to_i = int(payload["toIndex"])
            if not (0 <= from_i < len(fx_list) and 0 <= to_i < len(fx_list)):
                raise ValueError("FX move indices out of bounds")
            item = fx_list.pop(from_i)
            fx_list.insert(to_i, item)
        elif cmd_type == "fx.setParams":
            fx_id = str(payload["fxId"])
            slot = next((f for f in fx_list if f.get("id") == fx_id), None)
            if slot is None:
                raise ValueError(f"FX slot not found: {fx_id}")
            cur_p = dict(slot.get("parameters") or {})
            cur_p.update(dict(payload.get("parameters") or {}))
            slot["parameters"] = cur_p
            if "preset" in payload:
                slot["preset"] = payload["preset"]
            if "wetDry" in payload:
                slot["wetDry"] = max(0.0, min(1.0, float(payload["wetDry"])))
                slot["parameters"]["wetDry"] = slot["wetDry"]
            if "sidechainTrackId" in payload:
                slot["sidechainTrackId"] = payload["sidechainTrackId"]
        elif cmd_type == "fx.setBypass":
            fx_id = str(payload["fxId"])
            slot = next((f for f in fx_list if f.get("id") == fx_id), None)
            if slot is None:
                raise ValueError(f"FX slot not found: {fx_id}")
            slot["bypass"] = bool(payload["bypass"])
        elif cmd_type == "fx.setWetDry":
            fx_id = str(payload["fxId"])
            slot = next((f for f in fx_list if f.get("id") == fx_id), None)
            if slot is None:
                raise ValueError(f"FX slot not found: {fx_id}")
            w = max(0.0, min(1.0, float(payload["wetDry"])))
            slot["wetDry"] = w
            slot.setdefault("parameters", {})["wetDry"] = w
        if owner_trk is not None:
            owner_trk.freezeState = None

    elif cmd_type == "bus.add":
        bid = str(payload.get("id") or make_id("bus"))
        bus_kind = str(payload.get("kind") or "return")
        if bus_kind not in ("return", "group"):
            raise ValueError("Bus kind must be 'return' or 'group'")
        bus = {
            "id": bid,
            "name": str(payload.get("name") or f"{bus_kind.title()} Bus {len(p.buses) + 1}"),
            "kind": bus_kind,
            "gainDb": max(-60.0, min(6.0, float(payload.get("gainDb", 0.0)))),
            "pan": max(-1.0, min(1.0, float(payload.get("pan", 0.0)))),
            "mute": False,
            "solo": False,
            "effects": list(payload.get("effects") or []),
        }
        p.buses = [b for b in p.buses if b.get("id") != bid] + [bus]

    elif cmd_type == "bus.remove":
        bid = str(payload["busId"])
        p.buses = [b for b in p.buses if b.get("id") != bid]
        for t in p.tracks:
            t.sends = [s for s in t.sends if s.get("busId") != bid]
            if t.outputBusId == bid:
                t.outputBusId = "master"

    elif cmd_type in ("bus.setGain", "bus.setPan", "bus.setMute", "bus.setSolo"):
        bid = str(payload["busId"])
        bus_obj = next((b for b in p.buses if b.get("id") == bid), None)
        if bus_obj is None:
            raise ValueError(f"Bus not found: {bid}")
        if cmd_type == "bus.setGain":
            bus_obj["gainDb"] = max(-60.0, min(6.0, float(payload["gainDb"])))
        elif cmd_type == "bus.setPan":
            bus_obj["pan"] = max(-1.0, min(1.0, float(payload["pan"])))
        elif cmd_type == "bus.setMute":
            bus_obj["mute"] = bool(payload["mute"])
        elif cmd_type == "bus.setSolo":
            bus_obj["solo"] = bool(payload["solo"])

    elif cmd_type == "track.setOutputBus":
        trk = _find_track(p, str(payload["trackId"]))
        bid = str(payload.get("busId") or "master")
        if bid != "master" and not any(b.get("id") == bid for b in p.buses):
            raise ValueError(f"Output bus not found: {bid}")
        trk.outputBusId = bid

    elif cmd_type == "send.set":
        trk = _find_track(p, str(payload["trackId"]))
        bid = str(payload["busId"])
        if not any(b.get("id") == bid for b in p.buses):
            raise ValueError(f"Send target bus not found: {bid}")
        lvl_db = max(-60.0, min(6.0, float(payload.get("levelDb", -12.0))))
        pre = bool(payload.get("preFader", False))
        en = bool(payload.get("enabled", True))
        existing = next((s for s in trk.sends if s.get("busId") == bid), None)
        if existing:
            existing["levelDb"] = lvl_db
            existing["preFader"] = pre
            existing["enabled"] = en
        else:
            trk.sends.append({"id": make_id("snd"), "busId": bid, "levelDb": lvl_db, "preFader": pre, "enabled": en})

    elif cmd_type == "send.remove":
        trk = _find_track(p, str(payload["trackId"]))
        bid = str(payload["busId"])
        trk.sends = [s for s in trk.sends if s.get("busId") != bid]

    elif cmd_type == "automation.upsertLane":
        trk = _find_track(p, str(payload["trackId"]))
        lane = dict(payload.get("lane") or payload)
        lane_id = str(lane.get("id") or make_id("auto"))
        norm_pts = sorted(
            [
                {
                    "id": str(pt.get("id") or make_id("apt")),
                    "beat": max(0.0, float(pt["beat"])),
                    "value": float(pt["value"]),
                    "interpolation": str(pt.get("interpolation") or "linear"),
                }
                for pt in (lane.get("points") or [])
            ],
            key=lambda x: x["beat"],
        )
        new_lane = {
            "id": lane_id,
            "targetType": str(lane.get("targetType") or "track"),
            "targetId": lane.get("targetId"),
            "parameterId": str(lane.get("parameterId") or "gainDb"),
            "enabled": bool(lane.get("enabled", True)),
            "points": norm_pts,
        }
        trk.automationLanes = [ln for ln in trk.automationLanes if ln.get("id") != lane_id] + [new_lane]
        trk.freezeState = None

    elif cmd_type == "automation.addPoint":
        trk = _find_track(p, str(payload["trackId"]))
        lid = str(payload["laneId"])
        lane = next((ln for ln in trk.automationLanes if ln.get("id") == lid), None)
        if lane is None:
            raise ValueError(f"Automation lane not found: {lid}")
        pt = {
            "id": str(payload.get("pointId") or make_id("apt")),
            "beat": max(0.0, float(payload["beat"])),
            "value": float(payload["value"]),
            "interpolation": str(payload.get("interpolation") or "linear"),
        }
        lane["points"] = sorted(list(lane.get("points") or []) + [pt], key=lambda x: x["beat"])
        trk.freezeState = None

    elif cmd_type == "automation.movePoint":
        trk = _find_track(p, str(payload["trackId"]))
        lid = str(payload["laneId"])
        pid_pt = str(payload["pointId"])
        lane = next((ln for ln in trk.automationLanes if ln.get("id") == lid), None)
        if lane is None:
            raise ValueError(f"Automation lane not found: {lid}")
        for pt in lane.get("points") or []:
            if pt.get("id") == pid_pt:
                pt["beat"] = max(0.0, float(payload["beat"]))
                pt["value"] = float(payload["value"])
                break
        else:
            raise ValueError(f"Automation point not found: {pid_pt}")
        lane["points"].sort(key=lambda x: x["beat"])
        trk.freezeState = None

    elif cmd_type == "automation.deletePoint":
        trk = _find_track(p, str(payload["trackId"]))
        lid = str(payload["laneId"])
        pid_pt = str(payload["pointId"])
        lane = next((ln for ln in trk.automationLanes if ln.get("id") == lid), None)
        if lane is None:
            raise ValueError(f"Automation lane not found: {lid}")
        lane["points"] = [pt for pt in (lane.get("points") or []) if pt.get("id") != pid_pt]
        trk.freezeState = None

    elif cmd_type == "automation.removeLane":
        trk = _find_track(p, str(payload["trackId"]))
        lid = str(payload["laneId"])
        trk.automationLanes = [ln for ln in trk.automationLanes if ln.get("id") != lid]
        trk.freezeState = None

    elif cmd_type == "track.addTakeLane":
        trk = _find_track(p, str(payload["trackId"]))
        lane = dict(payload["lane"])
        lane.setdefault("id", make_id("lane"))
        lane.setdefault("createdAt", utc_now_iso())
        trk.takeLanes = [ln for ln in trk.takeLanes if ln.get("id") != lane["id"]] + [lane]

    elif cmd_type == "track.renameTakeLane":
        trk = _find_track(p, str(payload["trackId"]))
        lane_id = str(payload["laneId"])
        new_name = str(payload["name"]).strip()
        if not new_name:
            raise ValueError("Take lane name cannot be empty")
        for ln in trk.takeLanes:
            if ln.get("id") == lane_id:
                ln["name"] = new_name
                break
        else:
            raise ValueError(f"Take lane not found: {lane_id}")

    elif cmd_type == "track.removeTakeLane":
        trk = _find_track(p, str(payload["trackId"]))
        lane_id = str(payload["laneId"])
        trk.takeLanes = [ln for ln in trk.takeLanes if ln.get("id") != lane_id]

    elif cmd_type == "clip.setFades":
        _, clp = _find_clip(p, str(payload["clipId"]))
        if "fadeInBeats" in payload:
            clp.fadeInBeats = max(0.0, min(64.0, float(payload["fadeInBeats"])))
        if "fadeOutBeats" in payload:
            clp.fadeOutBeats = max(0.0, min(64.0, float(payload["fadeOutBeats"])))

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

    elif cmd_type == "chord.setTrack":
        raw_chords = payload.get("chords") or []
        p.chordTrack = [ChordEvent(**c) for c in raw_chords]
        p.chordTrack.sort(key=lambda c: (c.startBeat, c.endBeat))
        if "locked" in payload:
            p.chordTrackLocked = bool(payload["locked"])

    elif cmd_type == "chord.upsert":
        c_data = dict(payload.get("chord") or payload)
        c_data.setdefault("id", make_id("chd"))
        ev = ChordEvent(**c_data)
        p.chordTrack = [c for c in p.chordTrack if c.id != ev.id] + [ev]
        p.chordTrack.sort(key=lambda c: (c.startBeat, c.endBeat))

    elif cmd_type == "chord.delete":
        cid = str(payload["chordId"])
        p.chordTrack = [c for c in p.chordTrack if c.id != cid]

    elif cmd_type == "chord.split":
        cid = str(payload["chordId"])
        split_beat = float(payload["splitBeat"])
        idx = next((i for i, c in enumerate(p.chordTrack) if c.id == cid), None)
        if idx is None:
            raise ValueError(f"ChordEvent not found: {cid}")
        orig = p.chordTrack[idx]
        if split_beat <= orig.startBeat + 0.125 or split_beat >= orig.endBeat - 0.125:
            raise ValueError("splitBeat must fall strictly inside chord bounds")
        right_symbol = str(payload.get("rightSymbol") or orig.symbol).strip()
        right_root = str(payload.get("rightRoot") or orig.root)
        right_quality = str(payload.get("rightQuality") or orig.quality)
        right_ev = ChordEvent(
            id=payload.get("rightChordId") or make_id("chd"),
            symbol=right_symbol,
            root=right_root,
            quality=right_quality,
            extension=payload.get("rightExtension", orig.extension),
            bassNote=payload.get("rightBassNote", orig.bassNote),
            startBeat=round(split_beat, 4),
            endBeat=orig.endBeat,
            sourceReferenceId=orig.sourceReferenceId,
            confidence=orig.confidence,
            isEstimate=False,
            userCorrected=True,
            locked=orig.locked,
        )
        orig.endBeat = round(split_beat, 4)
        orig.userCorrected = True
        p.chordTrack.insert(idx + 1, right_ev)
        p.chordTrack.sort(key=lambda c: (c.startBeat, c.endBeat))

    elif cmd_type == "chord.merge":
        left_id = str(payload["leftChordId"])
        right_id = str(payload["rightChordId"])
        left = next((c for c in p.chordTrack if c.id == left_id), None)
        right = next((c for c in p.chordTrack if c.id == right_id), None)
        if not left or not right or left.id == right.id:
            raise ValueError("Valid distinct leftChordId and rightChordId are required")
        first, second = (left, right) if left.startBeat <= right.startBeat else (right, left)
        first.endBeat = max(first.endBeat, second.endBeat)
        if payload.get("symbol"):
            first.symbol = str(payload["symbol"]).strip()
        first.userCorrected = True
        first.isPassing = False
        p.chordTrack = [c for c in p.chordTrack if c.id != second.id]
        p.chordTrack.sort(key=lambda c: (c.startBeat, c.endBeat))

    elif cmd_type == "chord.setLocked":
        if payload.get("chordId"):
            cid = str(payload["chordId"])
            for c in p.chordTrack:
                if c.id == cid:
                    c.locked = bool(payload["locked"])
                    break
            else:
                raise ValueError(f"ChordEvent not found: {cid}")
        else:
            p.chordTrackLocked = bool(payload["locked"])

    else:
        raise ValueError(f"Unsupported DAW command: {cmd_type}")

    p.updatedAt = utc_now_iso()
    return Project.model_validate(p.model_dump())
