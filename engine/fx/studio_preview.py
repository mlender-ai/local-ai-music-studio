"""Studio Preview Engine & Honest Playback Parity Status (Phase 05.1 · Section 10).

Solves the divergence between Realtime Web Audio playback and Studio WAV Export:
- Computes a deterministic project render fingerprint (`renderHash`) covering tracks, clips, notes,
  instruments, FX chains, sends, return/group buses, automation lanes, and master FX.
- Tracks explicit Preview Status:
  - `Original Audio`   : Pure untouched Native Audio track(s) with zero active FX/MIDI (plays directly!)
  - `Studio Preview`   : Up-to-date rendered Studio Preview WAV matching current project revision & FX 100%
  - `Realtime Preview` : Active FX / Pro Instruments / Sends present; Studio Preview not yet rendered
  - `Rendering`        : Studio Preview render currently in progress
  - `Outdated Preview` : Project was modified after the last Studio Preview render (stale render never presented as fresh!)
  - `Failed`           : Last Studio Preview render failed
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from engine.daw_workspace import loudness, renderer, store
from engine.daw_workspace.schema import Project, utc_now_iso

_preview_lock = threading.Lock()
_rendering_projects: set[str] = set()
_failed_projects: dict[str, str] = {}


def _preview_dir(project_id: str) -> Path:
    d = store.project_dir(project_id) / "cache" / "studio_preview"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(project_id: str) -> Path:
    return _preview_dir(project_id) / "meta.json"


def _wav_path(project_id: str) -> Path:
    return _preview_dir(project_id) / "studio_preview.wav"


def _has_active_fx_or_midi(project: Project) -> bool:
    """Return True if project needs Studio Render processing beyond raw audio playback."""
    active_trks = renderer.active_tracks(project.tracks)
    if any(fx.get("enabled", True) and not fx.get("bypass", False) for fx in (project.masterEffects or [])):
        return True
    for bus in project.buses or []:
        if not bus.get("mute", False) and any(
            fx.get("enabled", True) and not fx.get("bypass", False) for fx in (bus.get("effects") or [])
        ):
            return True
    for trk in active_trks:
        if trk.type == "midi" and any(c.notes for c in trk.clips):
            return True
        if any(fx.get("enabled", True) and not fx.get("bypass", False) for fx in (trk.effects or [])):
            return True
        if any(s.get("enabled", True) for s in (trk.sends or [])):
            return True
        if any(ln.get("enabled", True) and ln.get("points") for ln in (trk.automationLanes or [])):
            return True
    return False


def _is_pure_native_audio_project(project: Project) -> bool:
    active_trks = renderer.active_tracks(project.tracks)
    populated = [t for t in active_trks if t.clips]
    if not populated:
        return False
    if _has_active_fx_or_midi(project):
        return False
    return all(t.type in ("audio", "stem") for t in populated)


def compute_studio_preview_hash(project: Project) -> str:
    """Compute a deterministic fingerprint of every audible parameter affecting Studio WAV Render."""
    payload = {
        "bpm": project.bpm,
        "sampleRate": project.sampleRate,
        "lengthBeats": project.lengthBeats,
        "masterGainDb": project.masterGainDb,
        "masterEffects": project.masterEffects or [],
        "buses": project.buses or [],
        "tracks": [
            {
                "id": t.id,
                "type": t.type,
                "mute": t.mute,
                "solo": t.solo,
                "gainDb": t.gainDb,
                "pan": t.pan,
                "outputBusId": getattr(t, "outputBusId", "master"),
                "instrumentRef": t.instrumentRef,
                "instrumentConfig": getattr(t, "instrumentConfig", {}),
                "effects": t.effects or [],
                "sends": getattr(t, "sends", []),
                "automationLanes": getattr(t, "automationLanes", []),
                "clips": [
                    {
                        "id": c.id,
                        "type": c.type,
                        "assetId": c.assetId,
                        "start": c.timelineStartBeats,
                        "dur": c.durationBeats,
                        "offset": c.sourceOffsetSec,
                        "gainDb": c.gainDb,
                        "loop": c.loop,
                        "reversed": getattr(c, "reversed", False),
                        "fadeIn": getattr(c, "fadeInBeats", 0.0),
                        "fadeOut": getattr(c, "fadeOutBeats", 0.0),
                        "notes": [n.model_dump() for n in c.notes],
                    }
                    for c in t.clips
                ],
            }
            for t in project.tracks
        ],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _load_meta(project_id: str) -> dict[str, Any] | None:
    p = _meta_path(project_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_studio_preview_status(project_id: str) -> dict[str, Any]:
    """Return exact, revision-honest Studio Preview status for `project_id`."""
    proj = store.load_project(project_id)
    cur_hash = compute_studio_preview_hash(proj)
    meta = _load_meta(project_id)
    wav_exists = _wav_path(project_id).is_file()
    pure_native = _is_pure_native_audio_project(proj)
    needs_studio_render = _has_active_fx_or_midi(proj)

    with _preview_lock:
        is_rendering = project_id in _rendering_projects
        last_err = _failed_projects.get(project_id)

    if is_rendering:
        status = "Rendering"
        note_ko = "스튜디오 프리뷰를 렌더링하는 중입니다..."
    elif last_err and (not meta or meta.get("renderHash") != cur_hash):
        status = "Failed"
        note_ko = f"마지막 스튜디오 프리뷰 렌더 실패: {last_err}"
    elif wav_exists and meta and meta.get("renderHash") == cur_hash:
        status = "Studio Preview"
        note_ko = "현재 프로젝트의 모든 트랙·악기·FX·센드·마스터가 반영된 최신 Studio Preview입니다 (Export WAV와 100% 동일 경로)."
    elif pure_native:
        status = "Original Audio"
        note_ko = "활성 FX/MIDI 레이어 없이 원본 네이티브 오디오가 그대로 재생됩니다 (Original Audio)."
    elif wav_exists and meta and meta.get("renderHash") != cur_hash:
        status = "Outdated Preview"
        note_ko = "마지막 스튜디오 프리뷰 이후 트랙·FX·믹스가 변경되었습니다. 최신 사운드를 들으려면 Studio Preview를 다시 렌더링하세요."
    else:
        status = "Realtime Preview"
        note_ko = "활성 FX·가상악기·센드가 있어 브라우저 실시간 재생과 최종 Export WAV가 다를 수 있습니다. 정확한 청취를 위해 Studio Preview 렌더를 권장합니다."

    return {
        "projectId": project_id,
        "projectRevision": proj.revision,
        "previewStatus": status,
        "needsStudioRender": needs_studio_render,
        "currentRenderHash": cur_hash,
        "upToDate": status in ("Studio Preview", "Original Audio"),
        "audioAvailable": wav_exists,
        "audioUrl": f"/api/projects/{project_id}/studio-preview/audio?v={meta.get('renderHash', cur_hash)}" if wav_exists else None,
        "lastRender": meta,
        "error": last_err if status == "Failed" else None,
        "noteKo": note_ko,
    }


def render_studio_preview(
    project_id: str,
    *,
    start_beats: float = 0.0,
    end_beats: float | None = None,
    filename_export_copy: str | None = None,
) -> dict[str, Any]:
    """Render an exact 3-pass Studio Preview WAV matching Studio Export 1:1 (cached by renderHash)."""
    proj = store.load_project(project_id)
    cur_hash = compute_studio_preview_hash(proj)
    existing_meta = _load_meta(project_id)
    wav_p = _wav_path(project_id)

    if (
        start_beats == 0.0
        and end_beats is None
        and filename_export_copy is None
        and wav_p.is_file()
        and existing_meta
        and existing_meta.get("renderHash") == cur_hash
    ):
        st = get_studio_preview_status(project_id)
        st["fromCache"] = True
        return st

    with _preview_lock:
        _rendering_projects.add(project_id)
        _failed_projects.pop(project_id, None)

    try:
        audio, sr, meters = renderer.render_project_to_array(
            proj,
            start_beats=start_beats,
            end_beats=end_beats,
            return_meters=True,
        )
        raw_loud = loudness.measure_loudness(audio, sr)
        raw_peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0

        # Protect 24-bit PCM preview from digital clipping if floating-point sum exceeds -0.3 dBFS
        headroom_trim_db = 0.0
        out_audio = audio.copy()
        if raw_peak > 0.966:  # -0.3 dBFS
            gain = 0.944 / raw_peak  # target -0.5 dBFS safe headroom
            headroom_trim_db = round(20.0 * math.log10(gain), 2)
            out_audio = (out_audio * gain).astype(np.float32)

        out_audio = np.clip(out_audio, -1.0, 1.0)
        final_loud = loudness.measure_loudness(out_audio, sr)

        tmp_wav = wav_p.with_suffix(".tmp.wav")
        sf.write(str(tmp_wav), out_audio, sr, subtype="PCM_24")
        os.replace(tmp_wav, wav_p)

        export_rel_path: str | None = None
        if filename_export_copy:
            exp_dir = store.project_dir(project_id) / "exports"
            exp_dir.mkdir(parents=True, exist_ok=True)
            safe_fn = filename_export_copy if filename_export_copy.lower().endswith(".wav") else f"{filename_export_copy}.wav"
            exp_dst = (exp_dir / safe_fn).resolve()
            if exp_dst.is_relative_to(exp_dir.resolve()):
                sf.write(str(exp_dst), out_audio, sr, subtype="PCM_24")
                export_rel_path = f"exports/{safe_fn}"

        meta = {
            "projectId": project_id,
            "projectRevision": proj.revision,
            "renderHash": cur_hash,
            "renderedAt": utc_now_iso(),
            "sampleRate": sr,
            "channels": 2,
            "durationSec": round(len(out_audio) / max(1, sr), 3),
            "rawTruePeakDbtp": raw_loud["truePeakDbtp"],
            "headroomTrimDb": headroom_trim_db,
            "integratedLufs": final_loud["integratedLufs"],
            "truePeakDbtp": final_loud["truePeakDbtp"],
            "loudnessRangeLu": final_loud["loudnessRangeLu"],
            "crestFactorDb": final_loud["crestFactorDb"],
            "relativePath": "cache/studio_preview/studio_preview.wav",
            "exportCopyRelativePath": export_rel_path,
            "bytes": wav_p.stat().st_size,
        }
        tmp_meta = _meta_path(project_id).with_suffix(".json.tmp")
        tmp_meta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_meta, _meta_path(project_id))

        with _preview_lock:
            _rendering_projects.discard(project_id)

        st = get_studio_preview_status(project_id)
        st["fromCache"] = False
        return st
    except Exception as exc:
        with _preview_lock:
            _failed_projects[project_id] = str(exc)
        raise
    finally:
        with _preview_lock:
            _rendering_projects.discard(project_id)


def resolve_studio_preview_file(project_id: str) -> tuple[dict[str, Any], Path]:
    p = _wav_path(project_id)
    if not p.is_file():
        raise FileNotFoundError(f"Studio Preview WAV has not been rendered yet for project {project_id}")
    return get_studio_preview_status(project_id), p
