"""Reference track lifecycle: import audio/video/URL, analyze, store Blueprint, compare."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import soundfile as sf

from . import analysis, blueprint, comparison, media, renderer, store
from .schema import make_id, utc_now_iso


def _find_ref(proj, ref_id: str) -> dict[str, Any]:
    for ref in proj.references:
        if ref.get("id") == ref_id:
            return ref
    raise FileNotFoundError(f"Reference not found: {ref_id}")


def import_reference_file(
    project_id: str,
    filename: str,
    raw_bytes: bytes,
    source: str = "imported-reference",
    attach_to_ref_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Import an audio or video file as a Reference (never added to project export tracks)."""
    ext = Path(filename).suffix.lower()
    if ext not in media.SUPPORTED_REFERENCE_EXTS:
        raise ValueError(
            f"Unsupported reference format '{ext}'. Supported: {sorted(media.SUPPORTED_REFERENCE_EXTS)}"
        )

    proj = store.load_project(project_id)
    pdir = store.project_dir(project_id)
    refs_dir = pdir / "assets/references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(raw_bytes).hexdigest()
    ref_id = attach_to_ref_id or make_id("ref")
    safe_name = store._sanitize_filename(filename)
    rel_src = f"assets/references/{ref_id}_{safe_name}"
    abs_src = (pdir / rel_src).resolve()
    if not abs_src.is_relative_to(pdir.resolve()):
        raise ValueError("Invalid reference target path")

    tmp = abs_src.with_suffix(abs_src.suffix + ".tmp")
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, abs_src)

    # Extract readable audio if video/m4a (preserves original immutable file!)
    extracted_path = media.extract_audio_for_analysis(abs_src, pdir / "cache/extracted", digest)
    info = sf.info(str(extracted_path))
    duration_sec = round(float(info.frames / info.samplerate), 3) if info.samplerate > 0 else 0.0
    rel_playable = extracted_path.resolve().relative_to(pdir.resolve()).as_posix()

    if attach_to_ref_id:
        ref = _find_ref(proj, attach_to_ref_id)
        ref.update(
            {
                "filename": Path(filename).name,
                "relativePath": rel_src,
                "playableRelativePath": rel_playable,
                "isVideo": ext in media.VIDEO_EXTS,
                "audioAvailable": True,
                "sha256": digest,
                "sampleRate": int(info.samplerate),
                "channels": int(info.channels),
                "durationSec": duration_sec,
                "analysisStatus": "pending",
                "noticeKo": None,
                "noticeEn": None,
                "updatedAt": utc_now_iso(),
            }
        )
    else:
        ref = {
            "id": ref_id,
            "name": Path(filename).stem,
            "filename": Path(filename).name,
            "kind": "video" if ext in media.VIDEO_EXTS else "audio",
            "source": source,
            "relativePath": rel_src,
            "playableRelativePath": rel_playable,
            "isVideo": ext in media.VIDEO_EXTS,
            "audioAvailable": True,
            "url": None,
            "sha256": digest,
            "sampleRate": int(info.samplerate),
            "channels": int(info.channels),
            "durationSec": duration_sec,
            "analysisStatus": "pending",
            "analysis": None,
            "blueprint": None,
            "selectedInfluences": [i["id"] for i in blueprint.DEFAULT_INFLUENCES if i["selected"]],
            "createdAt": utc_now_iso(),
            "updatedAt": utc_now_iso(),
        }
        proj.references.append(ref)

    saved = store.save_project(proj, clear_autosave=False)
    return ref, saved.revision


def add_reference_url(project_id: str, url: str) -> tuple[dict[str, Any], int]:
    """Register an external reference URL with safe metadata only (no fake audio analysis)."""
    meta = media.probe_reference_url(url)
    proj = store.load_project(project_id)
    ref = {
        "id": make_id("ref"),
        "name": meta["title"],
        "filename": None,
        "kind": "url",
        "source": meta["provider"],
        "url": meta["url"],
        "author": meta["author"],
        "relativePath": None,
        "playableRelativePath": None,
        "isVideo": False,
        "audioAvailable": False,
        "sha256": hashlib.sha256(meta["url"].encode("utf-8")).hexdigest()[:16],
        "sampleRate": 0,
        "channels": 0,
        "durationSec": 0.0,
        "analysisStatus": "audio_required",
        "noticeKo": meta["noticeKo"],
        "noticeEn": meta["noticeEn"],
        "analysis": None,
        "blueprint": None,
        "selectedInfluences": [i["id"] for i in blueprint.DEFAULT_INFLUENCES if i["selected"]],
        "createdAt": utc_now_iso(),
        "updatedAt": utc_now_iso(),
    }
    proj.references.append(ref)
    saved = store.save_project(proj, clear_autosave=False)
    return ref, saved.revision


def delete_reference(project_id: str, ref_id: str) -> int:
    proj = store.load_project(project_id)
    before = len(proj.references)
    proj.references = [r for r in proj.references if r.get("id") != ref_id]
    if len(proj.references) == before:
        raise FileNotFoundError(f"Reference not found: {ref_id}")
    saved = store.save_project(proj, clear_autosave=False)
    return saved.revision


def resolve_reference_audio_path(project_id: str, ref_id: str) -> tuple[dict[str, Any], Path]:
    proj = store.load_project(project_id)
    ref = _find_ref(proj, ref_id)
    if not ref.get("audioAvailable") or not ref.get("playableRelativePath"):
        raise ValueError(media.URL_AUDIO_REQUIRED_KO)
    pdir = store.project_dir(project_id).resolve()
    abs_path = (pdir / str(ref["playableRelativePath"])).resolve()
    if not abs_path.is_relative_to(pdir) or not abs_path.is_file():
        raise FileNotFoundError("Reference audio file missing on disk")
    return ref, abs_path


def run_reference_analysis_sync(project_id: str, ref_id: str) -> tuple[dict[str, Any], int]:
    """Synchronously analyze a reference and persist both analysis and ReferenceBlueprint."""
    ref, audio_path = resolve_reference_audio_path(project_id, ref_id)
    pdir = store.project_dir(project_id)
    proj_cur = store.load_project(project_id)
    result = analysis.analyze_audio_file(
        audio_path=audio_path,
        source_asset_id=ref_id,
        sha256=str(ref["sha256"]),
        cache_dir=pdir / "cache/analysis",
        project_bpm=proj_cur.bpm,
    )
    bp = blueprint.build_reference_blueprint(result, existing_influences=ref.get("selectedInfluences"))

    proj = store.load_project(project_id)
    target = _find_ref(proj, ref_id)
    target["analysisStatus"] = "completed"
    target["analysis"] = result
    target["blueprint"] = bp
    target["updatedAt"] = utc_now_iso()
    saved = store.save_project(proj, clear_autosave=False)
    return target, saved.revision


def start_reference_analysis_job(
    project_id: str,
    ref_id: str,
    on_saved: Any = None,
) -> dict[str, Any]:
    """Start async single-worker analysis job so DAW playback is never blocked."""
    ref, audio_path = resolve_reference_audio_path(project_id, ref_id)
    pdir = store.project_dir(project_id)

    proj_cur = store.load_project(project_id)

    def work(progress_cb, cancel_ev):
        return analysis.analyze_audio_file(
            audio_path=audio_path,
            source_asset_id=ref_id,
            sha256=str(ref["sha256"]),
            cache_dir=pdir / "cache/analysis",
            progress_cb=progress_cb,
            cancel_event=cancel_ev,
            project_bpm=proj_cur.bpm,
        )

    def on_done(result: dict[str, Any]):
        proj = store.load_project(project_id)
        target = _find_ref(proj, ref_id)
        bp = blueprint.build_reference_blueprint(result, existing_influences=target.get("selectedInfluences"))
        target["analysisStatus"] = "completed"
        target["analysis"] = result
        target["blueprint"] = bp
        target["updatedAt"] = utc_now_iso()
        saved = store.save_project(proj, clear_autosave=False)
        if on_saved:
            on_saved(saved)

    return analysis.analysis_jobs.submit(project_id, ref_id, work, on_complete=on_done)


def update_reference_blueprint(
    project_id: str,
    ref_id: str,
    selected_influences: list[str] | None = None,
    section_renames: dict[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Update user-selected Blueprint influences and/or renamed section labels."""
    proj = store.load_project(project_id)
    ref = _find_ref(proj, ref_id)

    if selected_influences is not None:
        valid_ids = {item["id"] for item in blueprint.DEFAULT_INFLUENCES}
        cleaned = sorted(i for i in selected_influences if i in valid_ids)
        ref["selectedInfluences"] = cleaned
        if isinstance(ref.get("blueprint"), dict):
            ref["blueprint"]["selectedInfluences"] = cleaned

    if section_renames and isinstance(ref.get("analysis"), dict):
        for sec in ref["analysis"].get("arrangement", {}).get("sections", []):
            if sec.get("id") in section_renames and section_renames[sec["id"]].strip():
                sec["label"] = section_renames[sec["id"]].strip()[:48]
                sec["isEstimatedRole"] = False
        if isinstance(ref.get("blueprint"), dict):
            ref["blueprint"]["arrangementTimeline"] = ref["analysis"]["arrangement"]["sections"]

    ref["updatedAt"] = utc_now_iso()
    saved = store.save_project(proj, clear_autosave=False)
    return ref, saved.revision


def compare_reference_with_target(
    project_id: str,
    ref_id: str,
    target_kind: str = "project_mix",
    target_id: str | None = None,
) -> dict[str, Any]:
    """Compare an analyzed Reference against the current project mix or a specific audio asset."""
    proj = store.load_project(project_id)
    ref = _find_ref(proj, ref_id)
    if not ref.get("analysis"):
        ref, _ = run_reference_analysis_sync(project_id, ref_id)

    pdir = store.project_dir(project_id)
    if target_kind == "asset" and target_id:
        asset, abs_path = store.resolve_asset_file(project_id, target_id)
        if asset.kind == "midi":
            raise ValueError("Cannot run acoustic comparison directly on a MIDI file; compare against project mix instead.")
        readable = media.extract_audio_for_analysis(abs_path, pdir / "cache/extracted", asset.sha256)
        tgt_analysis = analysis.analyze_audio_file(
            audio_path=readable,
            source_asset_id=asset.id,
            sha256=asset.sha256,
            cache_dir=pdir / "cache/analysis",
        )
        return comparison.compare_analyses(ref["name"], ref["analysis"], asset.name, tgt_analysis)

    # Render current project mix to a temporary WAV and analyze it!
    audio_arr, sr = renderer.render_project_to_array(proj)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sf.write(str(tmp_path), audio_arr, sr, subtype="PCM_24")
        digest = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
        tgt_analysis = analysis.analyze_audio_file(
            audio_path=tmp_path,
            source_asset_id=f"mix:{proj.id}:rev{proj.revision}",
            sha256=digest,
            cache_dir=pdir / "cache/analysis",
            project_bpm=proj.bpm,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return comparison.compare_analyses(ref["name"], ref["analysis"], f"{proj.name} (Mix)", tgt_analysis)
