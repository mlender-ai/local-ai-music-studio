"""Shared Musical Session Context & Cryptographic Layer Protection (Phase 05.2 · Sections 4 & 22)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from engine.daw_workspace import commands, store
from engine.daw_workspace.schema import ChordEvent, Project, Track, utc_now_iso
from engine.production import load_production_policy

LAYER_STATES = ("Draft", "Generated", "Auditioned", "Approved", "Rejected", "Locked")
PROTECTED_STATES = frozenset(("Approved", "Locked"))

DEFAULT_LATE_NIGHT_CHORDS: list[dict[str, Any]] = [
    {"symbol": "Dm9", "root": "D", "quality": "min9", "startBeat": 0.0, "endBeat": 4.0, "locked": True},
    {"symbol": "G13", "root": "G", "quality": "dom7", "extension": "13", "startBeat": 4.0, "endBeat": 8.0, "locked": True},
    {"symbol": "Cmaj9", "root": "C", "quality": "maj9", "startBeat": 8.0, "endBeat": 12.0, "locked": True},
    {"symbol": "A7", "root": "A", "quality": "dom7", "startBeat": 12.0, "endBeat": 16.0, "locked": True},
    {"symbol": "Dm9", "root": "D", "quality": "min9", "startBeat": 16.0, "endBeat": 20.0, "locked": True},
    {"symbol": "G13", "root": "G", "quality": "dom7", "extension": "13", "startBeat": 20.0, "endBeat": 24.0, "locked": True},
    {"symbol": "Bbmaj7", "root": "Bb", "quality": "maj7", "startBeat": 24.0, "endBeat": 28.0, "locked": True},
    {"symbol": "A7", "root": "A", "quality": "dom7", "startBeat": 28.0, "endBeat": 32.0, "locked": True},
]


def _infer_track_role(trk: Track) -> str:
    low = f"{trk.name} {trk.stemLabel or ''} {trk.instrumentRef or ''}".lower()
    if any(k in low for k in ("perc", "shaker", "conga", "bongo", "퍼커션")):
        return "percussion"
    if any(k in low for k in ("drum", "드럼", "kit", "beat")):
        return "drums"
    if any(k in low for k in ("bass", "베이스")):
        return "bass"
    if any(k in low for k in ("guitar", "기타")):
        return "guitar"
    if any(k in low for k in ("rhodes", "piano", "keys", "ep", "건반", "피아노", "로즈")):
        return "keys"
    if any(k in low for k in ("synth", "lead", "hook", "pad", "신스", "솔로")):
        return "synth"
    return "audio_mix" if trk.type == "audio" else "other"


def compute_layer_integrity_hash(project: Project, track_id: str) -> str:
    """Deterministic SHA-256 fingerprint of a layer's audio assets, MIDI notes, instrument, FX, and timeline positions."""
    trk = next((t for t in project.tracks if t.id == track_id), None)
    if trk is None:
        return "missing"
    asset_hashes = {a.id: a.sha256 for a in project.assets}
    payload = {
        "id": trk.id,
        "type": trk.type,
        "instrumentRef": trk.instrumentRef,
        "instrumentConfig": trk.instrumentConfig,
        "effects": trk.effects,
        "sends": trk.sends,
        "gainDb": trk.gainDb,
        "pan": trk.pan,
        "clips": [
            {
                "id": c.id,
                "type": c.type,
                "assetId": c.assetId,
                "assetSha256": asset_hashes.get(c.assetId or "", ""),
                "start": c.timelineStartBeats,
                "dur": c.durationBeats,
                "offset": c.sourceOffsetSec,
                "notes": [n.model_dump() for n in c.notes],
            }
            for c in trk.clips
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]


def snapshot_protected_layers(project: Project, extra_track_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Snapshot every Approved/Locked (plus explicitly listed) track before any new generation mutates the project."""
    mem_states = dict((project.musicMemory or {}).get("layerStates") or {})
    protected_ids: set[str] = set(extra_track_ids or [])
    for t in project.tracks:
        st = str((mem_states.get(t.id) or {}).get("state") or "Draft")
        if st in PROTECTED_STATES or (t.stemMeta or {}).get("protectedFromMidiOverwrite"):
            protected_ids.add(t.id)
    snaps: dict[str, dict[str, Any]] = {}
    for tid in sorted(protected_ids):
        trk = next((t for t in project.tracks if t.id == tid), None)
        if trk:
            snaps[tid] = {
                "trackId": tid,
                "name": trk.name,
                "state": str((mem_states.get(tid) or {}).get("state") or "Protected"),
                "hash": compute_layer_integrity_hash(project, tid),
            }
    return snaps


def verify_protected_layers_unchanged(
    project: Project,
    before_snapshots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Verify cryptographically that zero protected layers were modified during layer generation."""
    violations: list[dict[str, Any]] = []
    verified_ids: list[str] = []
    for tid, snap in before_snapshots.items():
        after_hash = compute_layer_integrity_hash(project, tid)
        if after_hash != snap["hash"]:
            violations.append(
                {
                    "trackId": tid,
                    "name": snap["name"],
                    "expectedHash": snap["hash"],
                    "actualHash": after_hash,
                }
            )
        else:
            verified_ids.append(tid)
    return {
        "allProtectedIntact": len(violations) == 0,
        "verifiedProtectedTrackIds": verified_ids,
        "violations": violations,
    }


def set_layer_state(
    project_id: str,
    track_id: str,
    state: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Transition a track's Session Layer state (`Draft|Generated|Auditioned|Approved|Rejected|Locked`)."""
    if state not in LAYER_STATES:
        raise ValueError(f"Unsupported layer state '{state}'. Allowed: {LAYER_STATES}")
    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")
    mem = dict(proj.musicMemory or {})
    l_states = dict(mem.get("layerStates") or {})
    l_hash = compute_layer_integrity_hash(proj, track_id)
    l_states[track_id] = {
        "trackId": track_id,
        "trackName": trk.name,
        "role": _infer_track_role(trk),
        "state": state,
        "integrityHash": l_hash,
        "note": note,
        "updatedAt": utc_now_iso(),
    }
    mem["layerStates"] = l_states
    proj.musicMemory = mem
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "layerState": l_states[track_id],
    }


def ensure_session_chord_timeline(
    project_id: str,
    *,
    chords: list[dict[str, Any]] | None = None,
    key: str = "D minor",
    lock: bool = True,
) -> dict[str, Any]:
    """Ensure the session has an explicit, shared, locked Chord Timeline so layers never drift harmonically."""
    proj = store.load_project(project_id)
    if proj.chordTrack and not chords:
        if lock and not proj.chordTrackLocked:
            proj = commands.apply_command(proj, "chord.setLocked", {"locked": True})
            proj = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
        return {
            "projectId": proj.id,
            "revision": proj.revision,
            "chordTrack": [c.model_dump() for c in proj.chordTrack],
            "chordTrackLocked": proj.chordTrackLocked,
            "key": key,
        }

    src = chords or DEFAULT_LATE_NIGHT_CHORDS
    updated = commands.apply_command(proj, "chord.setTrack", {"chords": src, "locked": lock})
    mem = dict(updated.musicMemory or {})
    mem["sessionKey"] = key
    updated.musicMemory = mem
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "chordTrack": [c.model_dump() for c in saved.chordTrack],
        "chordTrackLocked": saved.chordTrackLocked,
        "key": key,
    }


def _extract_groove_from_tracks(project: Project, start_beat: float, end_beat: float) -> dict[str, Any]:
    """Analyze existing Drums (and Percussion) MIDI tracks to extract actual kick/snare pocket beats for Bass/Keys/Guitar."""
    bpb = project.timeSignature.beats_per_bar
    kick_in_bar: list[float] = []
    snare_in_bar: list[float] = []
    hat_count = 0
    total_bars_seen = max(1, int(round((end_beat - start_beat) / bpb)))

    for trk in project.tracks:
        if trk.mute:
            continue
        role = _infer_track_role(trk)
        if role != "drums" or trk.type != "midi":
            continue
        for clp in trk.clips:
            for n in clp.notes:
                ab = clp.timelineStartBeats + n.startBeat
                if not (start_beat - 0.05 <= ab < end_beat + 0.05):
                    continue
                pos = round((ab % bpb) * 4.0) / 4.0  # quantize to 16th-note grid for context summary
                if n.pitch in (35, 36):
                    kick_in_bar.append(pos)
                elif n.pitch in (37, 38, 39, 40) and n.velocity >= 70:
                    snare_in_bar.append(pos)
                elif n.pitch in (42, 44, 46):
                    hat_count += 1

    # Most common kick/snare anchors across bars
    def _top_positions(vals: list[float], default: list[float]) -> list[float]:
        if not vals:
            return default
        counts: dict[float, int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        thresh = max(1, int(total_bars_seen * 0.25))
        kept = sorted(k for k, c in counts.items() if c >= thresh)
        return kept or default

    kicks = _top_positions(kick_in_bar, [0.0, 1.5, 2.5])
    snares = _top_positions(snare_in_bar, [1.0, 3.0])
    # Open rhythmic pocket slots: 16th/8th slots NOT sitting directly on snare backbeats
    all_eighth = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    open_slots = [s for s in all_eighth if s not in snares]

    return {
        "hasExistingDrums": bool(kick_in_bar or snare_in_bar),
        "kickBeatsInBar": kicks,
        "snareBeatsInBar": snares,
        "hatHitsPerBar": round(hat_count / total_bars_seen, 1),
        "swingRatio": float((project.musicMemory or {}).get("swingRatio", 0.58)),
        "feel": str((project.musicMemory or {}).get("grooveFeel", "neo_soul_pocket")),
        "openPocketSlots": open_slots,
    }


def _extract_occupied_registers(project: Project, start_beat: float, end_beat: float) -> dict[str, dict[str, Any]]:
    """Compact pitch-register & rhythmic-density map of existing layers so new layers stay out of each other's way."""
    out: dict[str, dict[str, Any]] = {}
    for trk in project.tracks:
        if trk.mute:
            continue
        role = _infer_track_role(trk)
        pitches: list[int] = []
        for clp in trk.clips:
            if clp.type == "midi":
                for n in clp.notes:
                    ab = clp.timelineStartBeats + n.startBeat
                    if start_beat - 0.05 <= ab < end_beat + 0.05:
                        pitches.append(int(n.pitch))
        if pitches:
            out[role] = {
                "trackId": trk.id,
                "trackName": trk.name,
                "pitchMin": min(pitches),
                "pitchMax": max(pitches),
                "medianPitch": sorted(pitches)[len(pitches) // 2],
                "noteCount": len(pitches),
            }
    return out


def build_session_context(
    project: Project,
    *,
    section_range: dict[str, float] | None = None,
    focus_instrument: str | None = None,
) -> dict[str, Any]:
    """Build compact, shared SessionContext (Section 4) for context-efficient layered instrument generation."""
    bpb = project.timeSignature.beats_per_bar
    start_b = float((section_range or {}).get("startBeats", 0.0))
    default_end = min(float(project.lengthBeats), start_b + bpb * 8.0)
    end_b = float((section_range or {}).get("endBeats", max(bpb * 4.0, default_end)))

    mem = dict(project.musicMemory or {})
    layer_states = dict(mem.get("layerStates") or {})
    key = str(mem.get("sessionKey") or "D minor")
    scale = str(mem.get("sessionScale") or ("major" if "major" in key.lower() else "dorian"))

    chord_timeline = [c.model_dump() for c in project.chordTrack]
    if not chord_timeline and project.compositionPlans:
        last_hg = (project.compositionPlans[-1] or {}).get("harmonyAndGroove") or {}
        if last_hg.get("chordTimeline"):
            chord_timeline = list(last_hg["chordTimeline"])
        elif last_hg.get("chordProgression"):
            prog = list(last_hg["chordProgression"])
            n_bars = max(4, int(round((end_b - start_b) / bpb)))
            chord_timeline = [
                {"symbol": prog[i % len(prog)], "startBeat": start_b + i * bpb, "endBeat": start_b + (i + 1) * bpb}
                for i in range(n_bars)
            ]

    # Filter chord timeline to active section range for context efficiency
    scoped_chords = [
        c for c in chord_timeline if float(c.get("endBeat", 0.0)) > start_b and float(c.get("startBeat", 0.0)) < end_b
    ] or chord_timeline

    existing_tracks: list[dict[str, Any]] = []
    approved_layers: list[str] = []
    protected_layers: list[str] = []
    instrument_roles: dict[str, str] = {}

    for trk in project.tracks:
        role = _infer_track_role(trk)
        st = str((layer_states.get(trk.id) or {}).get("state") or ("Locked" if (trk.stemMeta or {}).get("protectedFromMidiOverwrite") else "Draft"))
        if st == "Approved":
            approved_layers.append(trk.id)
        if st in PROTECTED_STATES or (trk.stemMeta or {}).get("protectedFromMidiOverwrite"):
            protected_layers.append(trk.id)
        instrument_roles[trk.id] = role
        existing_tracks.append(
            {
                "trackId": trk.id,
                "name": trk.name,
                "type": trk.type,
                "role": role,
                "instrumentRef": trk.instrumentRef,
                "preset": (trk.instrumentConfig or {}).get("preset"),
                "mute": trk.mute,
                "solo": trk.solo,
                "fxCount": len(trk.effects or []),
                "clipCount": len(trk.clips),
                "takeLaneCount": len(trk.takeLanes),
                "layerState": st,
                "integrityHash": compute_layer_integrity_hash(project, trk.id),
            }
        )

    groove = _extract_groove_from_tracks(project, start_b, end_b)
    occupied_registers = _extract_occupied_registers(project, start_b, end_b)

    # Beat grid summary for active section
    n_beats = max(4, int(round(end_b - start_b)))
    beat_grid = [round(start_b + i, 3) for i in range(min(64, n_beats + 1))]

    # Compact musical motif memory
    motif = dict(mem.get("musicalMotif") or {})
    if not motif:
        motif = {
            "scaleDegrees": [5, 3, 4, 5, 7, 6, 5, 3],
            "rhythmicSignature": "syncopated_pickup_call_and_response",
            "concept": "Warm late-night neo-soul 2-bar question and breathing answer",
        }

    # Reference bindings summary (compact, never dumping huge raw JSON)
    ref_bindings = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "bpm": (r.get("blueprint") or {}).get("tempoMap", {}).get("bpm"),
            "key": (r.get("blueprint") or {}).get("harmonicCharacter", {}).get("key"),
            "selectedInfluences": r.get("selectedInfluences", []),
        }
        for r in (project.references or [])
    ]

    policy = load_production_policy()
    return {
        "sessionId": f"sess_{project.id}",
        "projectId": project.id,
        "projectName": project.name,
        "bpm": project.bpm,
        "timeSignature": f"{project.timeSignature.numerator}/{project.timeSignature.denominator}",
        "beatsPerBar": bpb,
        "tempoMap": [{"beat": 0.0, "bpm": project.bpm}],
        "key": key,
        "scale": scale,
        "chordTimeline": scoped_chords,
        "chordTrackLocked": project.chordTrackLocked,
        "grooveProfile": groove,
        "beatGrid": beat_grid,
        "sectionRange": {"startBeats": start_b, "endBeats": end_b, "bars": round((end_b - start_b) / bpb, 2)},
        "existingTracks": existing_tracks,
        "approvedLayers": approved_layers,
        "protectedLayers": protected_layers,
        "occupiedRegisters": occupied_registers,
        "musicalMotif": motif,
        "instrumentRoles": instrument_roles,
        "referenceBindings": ref_bindings,
        "soundProfile": dict(mem.get("soundProfile") or {"aesthetic": "warm late-night studio neo-soul, organic space"}),
        "productionPolicy": {
            "defaultFullMusicEngine": policy.get("defaultFullMusicEngine", "yue2-native"),
            "allowSilentMidiFallback": bool(policy.get("allowSilentMidiFallback", False)),
            "allowPreviewInstrumentsInProduction": bool(policy.get("allowPreviewInstrumentsInProduction", False)),
            "instrumentalByDefault": bool(policy.get("instrumentalByDefault", True)),
            "preserveNativeAudio": bool(policy.get("preserveNativeAudio", True)),
        },
        "focusInstrument": focus_instrument,
        "baseRevision": project.revision,
    }
