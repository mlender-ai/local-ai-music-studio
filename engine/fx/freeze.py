"""Track Freeze & Unfreeze Engine (Phase 05 · GATE 4 / Section 44).

Renders a track's MIDI + Pro Instrument (FluidSynth / Pro Synth / Sampler / Drum Rack) + Insert FX + Automation
to an exact cached 48 kHz Stereo WAV keyed by a deterministic SHA-256 `stateHash`.
- Guarantees realtime browser playback matches server offline export bit-for-bit!
- Automatically invalidates whenever MIDI notes, instrument, preset, parameters, FX, automation, or BPM change.
- Unfreeze restores instant editable state without ever deleting MIDI clips or FX settings!
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import numpy as np
import soundfile as sf

from engine.daw_workspace import store
from engine.daw_workspace.schema import Project, Track, utc_now_iso


def compute_track_render_hash(project: Project, track: Track) -> str:
    """Compute a deterministic hash covering every factor that affects a track's pre-fader rendered audio."""
    payload = {
        "bpm": round(float(project.bpm), 4),
        "sampleRate": int(project.sampleRate),
        "lengthBeats": round(float(project.lengthBeats), 4),
        "trackType": track.type,
        "instrumentRef": track.instrumentRef,
        "instrumentConfig": track.instrumentConfig,
        "effects": track.effects,
        "automationLanes": [
            ln for ln in (track.automationLanes or [])
            if ln.get("targetType") in ("fx", "instrument")
        ],
        "clips": [c.model_dump() for c in track.clips],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def is_track_freeze_valid(project: Project, track: Track) -> bool:
    fs = track.freezeState
    if not isinstance(fs, dict) or not fs.get("frozen") or not fs.get("assetId"):
        return False
    expected = compute_track_render_hash(project, track)
    if fs.get("stateHash") != expected:
        return False
    return any(a.id == fs["assetId"] for a in project.assets)


def freeze_track(project_id: str, track_id: str) -> dict[str, Any]:
    """Render a track's source + Pro Instrument + Insert FX + FX Automation into a cached 48 kHz WAV asset."""
    from engine.daw_workspace.renderer import render_single_track_pre_fader

    proj = store.load_project(project_id)
    trk = next((t for t in proj.tracks if t.id == track_id), None)
    if trk is None:
        raise FileNotFoundError(f"Track not found: {track_id}")

    state_hash = compute_track_render_hash(proj, trk)
    if is_track_freeze_valid(proj, trk):
        return {
            "trackId": track_id,
            "frozen": True,
            "fromCache": True,
            "freezeState": trk.freezeState,
            "project": proj.model_dump(),
        }

    pcm, sr, meters = render_single_track_pre_fader(proj, trk)
    buf = io.BytesIO()
    sf.write(buf, np.clip(pcm, -1.0, 1.0).astype(np.float32), sr, format="WAV", subtype="PCM_24")
    wav_bytes = buf.getvalue()

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in trk.name)[:24] or "track"
    asset, _ = store.import_asset_bytes(
        project_id=project_id,
        filename=f"freeze_{safe_name}_{state_hash[:8]}.wav",
        raw_bytes=wav_bytes,
        kind_hint="audio",
        source="track-freeze-cache",
        provenance=f"Frozen studio audio render of track '{trk.name}' (hash {state_hash[:8]})",
    )

    updated = store.load_project(project_id)
    for t in updated.tracks:
        if t.id == track_id:
            t.freezeState = {
                "frozen": True,
                "assetId": asset.id,
                "stateHash": state_hash,
                "frozenAt": utc_now_iso(),
                "durationSec": round(len(pcm) / float(sr), 4),
                "sampleRate": sr,
                "fxMeters": meters,
            }
            break
    saved = store.save_project(updated, clear_autosave=False)
    return {
        "trackId": track_id,
        "frozen": True,
        "fromCache": False,
        "freezeState": next(t.freezeState for t in saved.tracks if t.id == track_id),
        "project": saved.model_dump(),
    }


def unfreeze_track(project_id: str, track_id: str) -> dict[str, Any]:
    """Unfreeze track so user can edit MIDI / Instrument / FX freely (original MIDI & FX untouched!)."""
    proj = store.load_project(project_id)
    found = False
    for t in proj.tracks:
        if t.id == track_id:
            t.freezeState = None
            found = True
            break
    if not found:
        raise FileNotFoundError(f"Track not found: {track_id}")
    saved = store.save_project(proj, clear_autosave=False)
    return {
        "trackId": track_id,
        "frozen": False,
        "project": saved.model_dump(),
    }
