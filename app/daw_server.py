"""Local-first FastAPI server for AI-Native DAW Phase 01 (127.0.0.1:8796)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from engine import paths as engine_paths
from engine.arrangement import (
    ArrangementEditPlan,
    create_arrangement_edit_plan,
    create_reversed_clip_asset,
    ensure_music_memory,
    execute_arrangement_edit_plan,
    promote_take_lane,
    rename_take_lane,
    restore_original_lane,
    update_project_music_memory,
)
from engine.composition import create_composition_plan, list_library_catalog
from engine.composition.schemas import CompositionPlan
from engine.daw_workspace import analysis, commands, mcp_tools, proposals, reaper, references, renderer, session, store
from engine.daw_workspace.schema import CommandRequest, Project
from engine.generation import (
    apply_take,
    detect_generation_engines,
    generation_jobs,
    get_composition_plan,
    get_take,
    list_takes,
    reject_take,
    resolve_take_preview_audio,
    save_composition_plan,
)
from engine.instruments import list_instruments
from engine.providers import get_provider_summary, select_provider
from engine.runtime import get_runtime_registry, save_local_runtime_overrides
from engine.transcription import (
    build_yue2_abc_from_reference,
    reconstruct_reference_to_project,
)

DIST_DIR = engine_paths.ROOT / "apps" / "daw" / "dist"

app = FastAPI(title="AI-Native DAW Workspace", docs_url=None, redoc_url=None)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver"],
)


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and not (
            origin.startswith("http://127.0.0.1:")
            or origin.startswith("http://localhost:")
            or origin in ("http://127.0.0.1", "http://localhost")
        ):
            return JSONResponse({"error": "Only loopback origins are allowed."}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(FileNotFoundError)
async def not_found_handler(request: Request, exc: FileNotFoundError):
    return JSONResponse({"error": str(exc)}, status_code=404)


@app.exception_handler(store.RevisionConflictError)
async def revision_conflict_handler(request: Request, exc: store.RevisionConflictError):
    return JSONResponse(
        {
            "error": str(exc),
            "code": "REVISION_CONFLICT",
            "expectedRevision": exc.expected,
            "serverRevision": exc.actual,
            "serverProject": exc.server_project.model_dump(),
        },
        status_code=409,
    )


class CreateProjectBody(BaseModel):
    name: str = Field(default="Untitled 01", min_length=1, max_length=120)
    bpm: float = Field(default=128.0, ge=30.0, le=300.0)
    numerator: int = Field(default=4, ge=1, le=16)
    denominator: int = Field(default=4)
    lengthBeats: float = Field(default=64.0, ge=4.0, le=4096.0)
    withDefaultTracks: bool = True


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SaveAsBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project: Project | None = None


class ExportServerBody(BaseModel):
    filename: str | None = None
    startBeats: float = Field(default=0.0, ge=0.0)
    endBeats: float | None = Field(default=None, gt=0.0)


@app.get("/api/health")
def health() -> dict[str, Any]:
    from engine.production import load_production_policy

    pol = load_production_policy()
    return {
        "status": "ok",
        "product": "AI-Native DAW",
        "phase": "05.1",
        "port": 8796,
        "defaultFullMusicEngine": pol.get("defaultFullMusicEngine", "yue2-native"),
        "allowSilentMidiFallback": bool(pol.get("allowSilentMidiFallback", False)),
        "reaper": reaper.detect_reaper(),
        "uiBuilt": (DIST_DIR / "index.html").is_file(),
    }


@app.get("/api/projects")
def get_projects() -> dict[str, Any]:
    return {"projects": [item.model_dump() for item in store.list_projects()]}


@app.post("/api/projects")
def post_project(body: CreateProjectBody) -> dict[str, Any]:
    proj = store.create_project(
        name=body.name,
        bpm=body.bpm,
        numerator=body.numerator,
        denominator=body.denominator,
        length_beats=body.lengthBeats,
        with_default_tracks=body.withDefaultTracks,
    )
    return proj.model_dump()


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return store.load_project(project_id).model_dump()


@app.put("/api/projects/{project_id}")
def put_project(
    project_id: str,
    project: Project,
    expectedRevision: int | None = None,
) -> dict[str, Any]:
    if project.id != project_id:
        raise ValueError("Project payload ID does not match URL project_id")
    saved = store.save_project(project, expected_revision=expectedRevision)
    return saved.model_dump()


@app.post("/api/projects/{project_id}/autosave")
def post_autosave(
    project_id: str,
    project: Project,
    expectedRevision: int | None = None,
) -> dict[str, Any]:
    if project.id != project_id:
        raise ValueError("Project payload ID does not match URL project_id")
    return store.autosave_project(project, expected_revision=expectedRevision)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, body: RenameBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    updated = commands.apply_command(proj, "project.rename", {"name": body.name})
    return store.save_project(updated, expected_revision=proj.revision).model_dump()


@app.post("/api/projects/{project_id}/save-as")
def post_save_as(project_id: str, body: SaveAsBody) -> dict[str, Any]:
    cloned = store.save_as_project(project_id, body.name, state=body.project)
    return cloned.model_dump()


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    store.delete_project(project_id)
    return {"deleted": project_id}


@app.post("/api/projects/{project_id}/commands")
def execute_command(project_id: str, req: CommandRequest) -> dict[str, Any]:
    proj = store.load_project(project_id)
    if req.expectedRevision is not None and proj.revision != req.expectedRevision:
        raise store.RevisionConflictError(req.expectedRevision, proj.revision, proj)
    updated = commands.apply_command(proj, req.type, req.payload)
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    return {"command": req.type, "project": saved.model_dump()}


@app.post("/api/projects/{project_id}/assets/{asset_id}/relink")
async def relink_asset(
    project_id: str,
    asset_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise ValueError("Uploaded file is empty")
    asset, rev = store.relink_asset_bytes(project_id, asset_id, file.filename or "relinked.wav", raw)
    return {"asset": asset.model_dump(), "projectRevision": rev}


@app.post("/api/projects/{project_id}/assets/import")
async def import_asset(
    project_id: str,
    file: UploadFile = File(...),
    kind: str | None = Form(default=None),
    source: str = Form(default="imported"),
    provenance: str = Form(default=""),
) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise ValueError("Uploaded file is empty")
    asset, extra = store.import_asset_bytes(
        project_id=project_id,
        filename=file.filename or "imported.wav",
        raw_bytes=raw,
        kind_hint=kind,
        source=source,
        provenance=provenance,
    )
    return {"asset": asset.model_dump(), **extra}


@app.get("/api/projects/{project_id}/assets/{asset_id}/file")
def get_asset_file(project_id: str, asset_id: str):
    asset, abs_path = store.resolve_asset_file(project_id, asset_id)
    return FileResponse(abs_path, media_type=asset.mimeType, filename=asset.name)


@app.get("/api/projects/{project_id}/assets/{asset_id}/waveform")
def get_asset_waveform(project_id: str, asset_id: str, bins: int = 1024) -> dict[str, Any]:
    safe_bins = max(64, min(4096, bins))
    return store.get_asset_waveform(project_id, asset_id, bins=safe_bins)


@app.post("/api/projects/{project_id}/exports")
async def upload_export(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) < 44 or raw[:4] != b"RIFF":
        raise ValueError("Export payload must be a valid RIFF/WAV file")
    return store.save_export_bytes(project_id, file.filename or "export.wav", raw)


@app.post("/api/projects/{project_id}/export/server")
def server_export(project_id: str, body: ExportServerBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    return renderer.export_project_wav(
        proj,
        filename=body.filename,
        start_beats=body.startBeats,
        end_beats=body.endBeats,
    )


@app.get("/api/projects/{project_id}/exports/{filename}")
def download_export(project_id: str, filename: str):
    pdir = store.project_dir(project_id).resolve()
    exports_dir = (pdir / "exports").resolve()
    target = (exports_dir / filename).resolve()
    if not target.is_relative_to(exports_dir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(target, media_type="audio/wav", filename=target.name)


@app.get("/api/library/assets")
def list_studio_library() -> dict[str, Any]:
    """List reusable local studio audio/MIDI files in outputs/daw/library/."""
    lib_dir = engine_paths.DATA / "daw" / "library"
    items: list[dict[str, Any]] = []
    if lib_dir.is_dir():
        for f in sorted(lib_dir.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext in store.ALLOWED_AUDIO_EXTS or ext in store.ALLOWED_MIDI_EXTS:
                rel = f.relative_to(lib_dir).as_posix()
                items.append(
                    {
                        "id": rel,
                        "name": f.name,
                        "category": f.parent.name if f.parent != lib_dir else "studio",
                        "kind": "midi" if ext in store.ALLOWED_MIDI_EXTS else "audio",
                        "sizeBytes": f.stat().st_size,
                    }
                )
    return {"items": items}


class ImportLibraryBody(BaseModel):
    libraryId: str = Field(min_length=1)
    kind: str | None = None


class ReferenceUrlBody(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


class BlueprintUpdateBody(BaseModel):
    selectedInfluences: list[str] | None = None
    sectionRenames: dict[str, str] | None = None


class ReferenceCompareBody(BaseModel):
    targetKind: str = "project_mix"
    targetId: str | None = None


class ReferenceLocksBody(BaseModel):
    featureLocks: dict[str, str] | None = None
    chordCorrections: list[dict[str, Any]] | None = None
    sectionRenames: dict[str, str] | None = None


class ReferenceReconstructBody(BaseModel):
    importChords: bool = True
    importDrumsMidi: bool = True
    importBassMidi: bool = True
    importMelodyMidi: bool = True
    importStems: bool = False
    importSections: bool = True
    useQuantizedDrums: bool = True
    applyBpm: bool = True


class SetChordTrackBody(BaseModel):
    chords: list[dict[str, Any]] = Field(default_factory=list)
    locked: bool | None = None


@app.post("/api/projects/{project_id}/references/import")
async def import_reference(
    project_id: str,
    file: UploadFile = File(...),
    attachToRefId: str | None = Form(default=None),
) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise ValueError("Uploaded reference file is empty")
    ref, rev = references.import_reference_file(
        project_id,
        file.filename or "reference.wav",
        raw,
        attach_to_ref_id=attachToRefId,
    )
    return {"reference": ref, "projectRevision": rev}


@app.post("/api/projects/{project_id}/references/url")
def register_reference_url(project_id: str, body: ReferenceUrlBody) -> dict[str, Any]:
    ref, rev = references.add_reference_url(project_id, body.url)
    return {"reference": ref, "projectRevision": rev}


@app.delete("/api/projects/{project_id}/references/{ref_id}")
def remove_reference(project_id: str, ref_id: str) -> dict[str, Any]:
    rev = references.delete_reference(project_id, ref_id)
    return {"deleted": ref_id, "projectRevision": rev}


@app.get("/api/projects/{project_id}/references/{ref_id}/audio")
def get_reference_audio(project_id: str, ref_id: str):
    ref, abs_path = references.resolve_reference_audio_path(project_id, ref_id)
    return FileResponse(abs_path, media_type="audio/wav", filename=ref.get("filename") or "reference.wav")


@app.post("/api/projects/{project_id}/references/{ref_id}/analyze")
def analyze_reference(project_id: str, ref_id: str, sync: bool = False) -> dict[str, Any]:
    if sync:
        ref, rev = references.run_reference_analysis_sync(project_id, ref_id)
        return {"reference": ref, "projectRevision": rev, "status": "completed"}
    job = references.start_reference_analysis_job(project_id, ref_id)
    return {"job": job}


@app.get("/api/analysis/jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict[str, Any]:
    return analysis.analysis_jobs.get(job_id)


@app.post("/api/analysis/jobs/{job_id}/cancel")
def cancel_analysis_job(job_id: str) -> dict[str, Any]:
    return analysis.analysis_jobs.cancel(job_id)


@app.patch("/api/projects/{project_id}/references/{ref_id}/blueprint")
def patch_reference_blueprint(project_id: str, ref_id: str, body: BlueprintUpdateBody) -> dict[str, Any]:
    ref, rev = references.update_reference_blueprint(
        project_id,
        ref_id,
        selected_influences=body.selectedInfluences,
        section_renames=body.sectionRenames,
    )
    return {"reference": ref, "projectRevision": rev}


@app.post("/api/projects/{project_id}/references/{ref_id}/compare")
def compare_reference(project_id: str, ref_id: str, body: ReferenceCompareBody) -> dict[str, Any]:
    return references.compare_reference_with_target(
        project_id,
        ref_id,
        target_kind=body.targetKind,
        target_id=body.targetId,
    )


# --- Phase 03.2 Advanced Reference Intelligence Endpoints ---

@app.post("/api/projects/{project_id}/references/{ref_id}/transcribe")
def transcribe_reference(
    project_id: str,
    ref_id: str,
    sync: bool = False,
    useDemucs: bool = True,
    demucsModel: str = "htdemucs",
) -> dict[str, Any]:
    if sync:
        ref, rev = references.run_reference_transcription_sync(
            project_id,
            ref_id,
            use_demucs=useDemucs,
            demucs_model=demucsModel,
        )
        return {"reference": ref, "projectRevision": rev, "status": "completed"}
    job = references.start_reference_transcription_job(
        project_id,
        ref_id,
        use_demucs=useDemucs,
        demucs_model=demucsModel,
    )
    return {"job": job}


@app.get("/api/projects/{project_id}/references/{ref_id}/stems/{role}/audio")
def get_reference_stem_audio(project_id: str, ref_id: str, role: str):
    stem_meta, abs_path = references.resolve_reference_stem_audio(project_id, ref_id, role)
    return FileResponse(abs_path, media_type="audio/wav", filename=f"{ref_id}_{role}.wav")


@app.patch("/api/projects/{project_id}/references/{ref_id}/locks")
def patch_reference_locks(project_id: str, ref_id: str, body: ReferenceLocksBody) -> dict[str, Any]:
    ref, rev = references.update_reference_locks_and_corrections(
        project_id,
        ref_id,
        feature_locks=body.featureLocks,
        chord_corrections=body.chordCorrections,
        section_renames=body.sectionRenames,
    )
    return {"reference": ref, "projectRevision": rev}


@app.post("/api/projects/{project_id}/references/{ref_id}/reconstruct")
def reconstruct_reference(project_id: str, ref_id: str, body: ReferenceReconstructBody) -> dict[str, Any]:
    return reconstruct_reference_to_project(
        project_id,
        ref_id,
        import_chords=body.importChords,
        import_drums_midi=body.importDrumsMidi,
        import_bass_midi=body.importBassMidi,
        import_melody_midi=body.importMelodyMidi,
        import_stems=body.importStems,
        import_sections=body.importSections,
        use_quantized_drums=body.useQuantizedDrums,
        apply_bpm=body.applyBpm,
    )


@app.get("/api/projects/{project_id}/references/{ref_id}/abc")
def get_reference_abc(project_id: str, ref_id: str, mode: str = "reference_compose") -> dict[str, Any]:
    proj = store.load_project(project_id)
    ref = next((r for r in proj.references if r.get("id") == ref_id), None)
    if not ref:
        raise FileNotFoundError(f"Reference not found: {ref_id}")
    bp = ref.get("blueprint") or {}
    tr = ref.get("transcription") or {}
    chords = bp.get("chordTimeline") or tr.get("chordTimeline") or []
    melody_notes = (bp.get("melodyEvents") or tr.get("melody") or {}).get("notes") or []
    sections = bp.get("arrangementMap") or tr.get("arrangementMap") or []
    key_str = str((bp.get("harmonicCharacter") or {}).get("key") or tr.get("key") or "F minor")
    bpm = float((bp.get("tempoMap") or {}).get("bpm") or tr.get("bpm") or proj.bpm)
    abc_res = build_yue2_abc_from_reference(
        chord_timeline=chords,
        melody_notes=melody_notes,
        sections=sections,
        key_str=key_str,
        bpm=bpm,
        bpb=proj.timeSignature.beats_per_bar,
        production_mode=mode if mode in ("reconstruct", "reference_compose", "reinterpret") else "reference_compose",
    )
    return {"projectId": project_id, "referenceId": ref_id, "abcScore": abc_res}


@app.get("/api/projects/{project_id}/chords")
def get_project_chords(project_id: str) -> dict[str, Any]:
    proj = store.load_project(project_id)
    return {
        "projectId": proj.id,
        "revision": proj.revision,
        "chordTrack": [c.model_dump() for c in proj.chordTrack],
        "chordTrackLocked": proj.chordTrackLocked,
    }


@app.put("/api/projects/{project_id}/chords")
def put_project_chords(project_id: str, body: SetChordTrackBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    proposals.record_undo_snapshot(proj)
    payload: dict[str, Any] = {"chords": body.chords}
    if body.locked is not None:
        payload["locked"] = body.locked
    updated = commands.apply_command(proj, "chord.setTrack", payload)
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    return {
        "projectId": saved.id,
        "revision": saved.revision,
        "chordTrack": [c.model_dump() for c in saved.chordTrack],
        "chordTrackLocked": saved.chordTrackLocked,
        "project": saved.model_dump(),
    }


# --- Phase 02-B Agent Bridge: Session Sync, Proposals, Producer Router & Live SSE ---

class SessionUpdateBody(BaseModel):
    sessionId: str = Field(min_length=3, max_length=80)
    projectId: str | None = None
    revision: int | None = None
    selection: dict[str, Any] | None = None
    activeReferenceId: str | None = None
    locale: str = "ko"
    claimActive: bool = True


class ProposalCreateBody(BaseModel):
    summary: str = Field(min_length=1, max_length=240)
    operations: list[dict[str, Any]]
    baseRevision: int | None = None
    sourceAgent: str = "external-agent"


class ProducerInstructBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=1000)
    selection: dict[str, Any] | None = None
    activeReferenceId: str | None = None
    baseRevision: int | None = None


@app.get("/api/capabilities")
def get_capabilities() -> dict[str, Any]:
    return mcp_tools.get_capabilities()


@app.post("/api/session/state")
def post_session_state(body: SessionUpdateBody) -> dict[str, Any]:
    return session.update_session(
        session_id=body.sessionId,
        project_id=body.projectId,
        revision=body.revision,
        selection=body.selection,
        active_reference_id=body.activeReferenceId,
        locale=body.locale,
        claim_active=body.claimActive,
    )


@app.get("/api/session/state")
def get_session_state(sessionId: str | None = None) -> dict[str, Any]:
    return session.get_active_session(sessionId)


@app.get("/api/session/list")
def get_sessions_list() -> dict[str, Any]:
    return session.list_sessions()


@app.get("/api/projects/{project_id}/proposals")
def get_proposals(project_id: str, status: str | None = None) -> dict[str, Any]:
    return {"proposals": proposals.list_proposals(project_id, status=status)}


@app.post("/api/projects/{project_id}/proposals")
def post_proposal(project_id: str, body: ProposalCreateBody) -> dict[str, Any]:
    prop = proposals.create_proposal(
        project_id,
        summary=body.summary,
        operations=body.operations,
        base_revision=body.baseRevision,
        source_agent=body.sourceAgent,
    )
    return {"proposal": prop}


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/apply")
def post_apply_proposal(project_id: str, proposal_id: str) -> dict[str, Any]:
    prop, saved = proposals.apply_proposal(project_id, proposal_id)
    return {"proposal": prop, "project": saved.model_dump()}


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/reject")
def post_reject_proposal(project_id: str, proposal_id: str) -> dict[str, Any]:
    prop = proposals.reject_proposal(project_id, proposal_id)
    return {"proposal": prop}


@app.post("/api/projects/{project_id}/undo")
def post_undo(project_id: str) -> dict[str, Any]:
    saved = proposals.undo_project(project_id)
    return {"project": saved.model_dump()}


@app.post("/api/projects/{project_id}/redo")
def post_redo(project_id: str) -> dict[str, Any]:
    saved = proposals.redo_project(project_id)
    return {"project": saved.model_dump()}


@app.post("/api/projects/{project_id}/producer/instruct")
def post_producer_instruct(project_id: str, body: ProducerInstructBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    if body.baseRevision is not None and proj.revision != body.baseRevision:
        raise store.RevisionConflictError(body.baseRevision, proj.revision, proj)
    routed = proposals.interpret_producer_instruction(
        proj,
        body.instruction,
        selection=body.selection,
        active_reference_id=body.activeReferenceId,
    )
    if routed.get("action") == "stage_proposal":
        prop = proposals.create_proposal(
            project_id,
            summary=routed["summary"],
            operations=routed["operations"],
            base_revision=proj.revision,
            source_agent="local-producer-router",
        )
        return {
            "supported": True,
            "action": "proposal_created",
            "proposal": prop,
            "diagnosis": routed.get("diagnosis"),
            "soundDesignPlan": routed.get("soundDesignPlan"),
            "messageKo": f"변경 제안이 생성되었습니다: {prop['summary']}. 확인 후 '적용'을 눌러 반영하세요.",
            "messageEn": f"Change proposal staged: {prop['summary']}. Click Apply to commit.",
        }
    if routed.get("action") == "sound_design_advisory":
        return {
            "supported": True,
            "action": "sound_design_advisory",
            "diagnosis": routed.get("diagnosis"),
            "soundDesignPlan": routed.get("soundDesignPlan"),
            "messageKo": routed.get("messageKo"),
            "messageEn": routed.get("messageEn"),
        }
    if routed.get("action") == "arrangement_edit_plan":
        arr_plan = create_arrangement_edit_plan(
            project=proj,
            instruction=body.instruction,
            selection=body.selection,
        )
        return {
            "supported": True,
            "action": "arrangement_edit_plan_created",
            "arrangementPlan": arr_plan.model_dump(),
            "projectRevision": proj.revision,
            "messageKo": arr_plan.summaryKo,
            "messageEn": arr_plan.summaryEn,
        }
    if routed.get("action") == "transcribe_reference":
        ref_id = str(routed["referenceId"])
        job = references.start_reference_transcription_job(project_id, ref_id)
        return {
            "supported": True,
            "action": "transcription_started",
            "referenceId": ref_id,
            "job": job,
            "messageKo": "레퍼런스 정밀 채보(Demucs + Basic Pitch ONNX + 코드·드럼 분석)를 시작했습니다.",
            "messageEn": "Started precision reference transcription (Demucs + Basic Pitch ONNX + Chord/Drum analysis).",
        }
    if routed.get("action") == "import_reference_chords":
        ref_id = str(routed["referenceId"])
        res = reconstruct_reference_to_project(
            project_id,
            ref_id,
            import_chords=True,
            import_drums_midi=False,
            import_bass_midi=False,
            import_melody_midi=False,
            import_stems=False,
            import_sections=False,
            apply_bpm=False,
        )
        return {
            "supported": True,
            "action": "reference_reconstructed",
            "referenceId": ref_id,
            "reconstructResult": res,
            "project": res["project"],
            "messageKo": f"레퍼런스 코드 진행을 타임라인 Chord Track으로 가져왔습니다 ({', '.join(res.get('importedItems', []))}).",
            "messageEn": f"Imported reference chord progression to Timeline Chord Track ({', '.join(res.get('importedItems', []))}).",
        }
    if routed.get("action") == "reconstruct_reference":
        ref_id = str(routed["referenceId"])
        res = reconstruct_reference_to_project(
            project_id,
            ref_id,
            import_chords=True,
            import_drums_midi=True,
            import_bass_midi=True,
            import_melody_midi=True,
            import_stems=False,
            import_sections=True,
        )
        return {
            "supported": True,
            "action": "reference_reconstructed",
            "referenceId": ref_id,
            "reconstructResult": res,
            "project": res["project"],
            "messageKo": f"편집 가능한 MIDI 세션으로 재구성했습니다: {', '.join(res.get('importedItems', []))}. (1클릭 Undo 지원)",
            "messageEn": f"Reconstructed editable MIDI session: {', '.join(res.get('importedItems', []))}. (1-click Undo supported)",
        }
    if routed.get("action") == "composition_plan":
        ref_id = routed.get("referenceId") or body.activeReferenceId
        plan = create_composition_plan(
            project=proj,
            instruction=body.instruction,
            reference_ids=[ref_id] if ref_id else None,
            selection=body.selection,
            feature_locks=routed.get("featureLocks"),
            reference_mode=str(routed.get("referenceMode") or "reference_compose"),
            use_project_chord_track=bool(routed.get("useProjectChordTrack", False)),
        )
        saved_plan, rev = save_composition_plan(project_id, plan)
        return {
            "supported": True,
            "action": "composition_plan_created",
            "plan": saved_plan,
            "projectRevision": rev,
            "messageKo": f"작곡 계획이 생성되었습니다: {plan.summaryKo}",
            "messageEn": f"Composition plan created: {plan.summaryEn}",
        }
    return routed


# --- Phase 03: AI Providers, Instruments, Library Intelligence, Composition Plans, Generation Jobs & Takes ---

class SelectProviderBody(BaseModel):
    providerId: str = Field(min_length=1, max_length=64)
    model: str | None = None


class CreateCompositionPlanBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=1500)
    mode: str | None = None
    targetInstrument: str | None = None
    referenceIds: list[str] | None = None
    selectedInfluences: list[str] | None = None
    featureLocks: dict[str, str] | None = None
    featureSourceMap: dict[str, str] | None = None
    bassLockMode: str = "rhythm_and_duration"
    referenceMode: str = "reference_compose"
    useProjectChordTrack: bool = False
    selection: dict[str, Any] | None = None
    providerId: str | None = None
    enginePreference: str = "auto"
    productionMode: str | None = None
    allowPreviewInstruments: bool = False


class StartGenerationBody(BaseModel):
    planId: str | None = None
    instruction: str | None = None
    mode: str | None = None
    targetInstrument: str | None = None
    referenceIds: list[str] | None = None
    selectedInfluences: list[str] | None = None
    featureLocks: dict[str, str] | None = None
    featureSourceMap: dict[str, str] | None = None
    bassLockMode: str = "rhythm_and_duration"
    referenceMode: str = "reference_compose"
    useProjectChordTrack: bool = False
    selection: dict[str, Any] | None = None
    engine: str = "auto"
    productionMode: str | None = None
    allowPreviewInstruments: bool = False
    seed: int | None = None
    sync: bool = False


class ApplyTakeBody(BaseModel):
    applyMode: str = "add"  # add | new_tracks | replace_range | selected_range | alternative_take | extend | new_project | keep_take
    targetTrackId: str | None = None
    startBeats: float | None = None
    addSectionMarkers: bool = False
    replaceSections: bool = False
    expectedRevision: int | None = None
    forceReapply: bool = False


class SeparateStemsBody(BaseModel):
    assetId: str = Field(min_length=1)
    sourceTrackId: str | None = None
    modelName: str = "htdemucs"
    sync: bool = False


class RuntimeOverridesBody(BaseModel):
    overrides: dict[str, Any]


@app.get("/api/runtime")
def api_get_runtime() -> dict[str, Any]:
    return get_runtime_registry()


@app.post("/api/runtime/config")
def api_save_runtime_config(body: RuntimeOverridesBody) -> dict[str, Any]:
    save_local_runtime_overrides(body.overrides)
    return get_runtime_registry()


@app.get("/api/providers")
def api_get_providers() -> dict[str, Any]:
    return get_provider_summary()


@app.post("/api/providers/select")
def api_select_provider(body: SelectProviderBody) -> dict[str, Any]:
    return select_provider(body.providerId, model=body.model)


@app.get("/api/instruments")
def api_get_instruments() -> dict[str, Any]:
    return {"instruments": list_instruments()}


@app.get("/api/instruments/catalog")
def api_get_instruments_catalog() -> dict[str, Any]:
    from engine.instruments import get_instrument_catalog, probe_fluidsynth_engine

    return {
        "instruments": get_instrument_catalog(),
        "fluidsynth": probe_fluidsynth_engine(),
    }


class InstrumentPreviewBody(BaseModel):
    instrumentRef: str = Field(min_length=1, max_length=120)
    presetId: str | None = None
    parameters: dict[str, Any] | None = None


@app.post("/api/instruments/preview")
def api_preview_instrument(body: InstrumentPreviewBody):
    import io
    import numpy as np
    import soundfile as sf
    from fastapi.responses import Response
    from engine.instruments import render_instrument_preview

    pcm = render_instrument_preview(
        body.instrumentRef,
        preset_id=body.presetId,
        params=body.parameters,
        sr=44100,
    )
    buf = io.BytesIO()
    sf.write(buf, np.clip(pcm, -1.0, 1.0), 44100, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/api/plugins/scan")
def api_scan_host_plugins(probeExternal: bool = True) -> dict[str, Any]:
    from engine.instruments import scan_host_plugins

    return scan_host_plugins(probe_external=probeExternal)


@app.get("/api/fx/catalog")
def api_get_fx_catalog() -> dict[str, Any]:
    from engine.fx import list_fx_catalog

    return {"effects": list_fx_catalog()}


class EqCurveBody(BaseModel):
    bands: list[dict[str, Any]]
    outputGainDb: float = 0.0
    sampleRate: int = 48000


@app.post("/api/fx/eq-curve")
def api_compute_eq_curve(body: EqCurveBody) -> dict[str, Any]:
    from engine.fx import compute_eq_response_curve

    return compute_eq_response_curve(body.bands, output_gain_db=body.outputGainDb, sr=body.sampleRate)


@app.post("/api/projects/{project_id}/tracks/{track_id}/freeze")
def api_freeze_track(project_id: str, track_id: str) -> dict[str, Any]:
    from engine.fx import freeze_track

    res = freeze_track(project_id, track_id)
    session.event_bus.publish("project.updated", {"projectId": project_id, "revision": res["project"]["revision"], "source": "freeze"})
    return res


@app.post("/api/projects/{project_id}/tracks/{track_id}/unfreeze")
def api_unfreeze_track(project_id: str, track_id: str) -> dict[str, Any]:
    from engine.fx import unfreeze_track

    res = unfreeze_track(project_id, track_id)
    session.event_bus.publish("project.updated", {"projectId": project_id, "revision": res["project"]["revision"], "source": "unfreeze"})
    return res


@app.post("/api/projects/{project_id}/tracks/{track_id}/diagnose")
def api_diagnose_track(project_id: str, track_id: str) -> dict[str, Any]:
    from engine.sound_design import diagnose_track_audio

    proj = store.load_project(project_id)
    return diagnose_track_audio(proj, track_id)


class ServerExportBody(BaseModel):
    useLoopRange: bool = False


@app.post("/api/projects/{project_id}/export/studio-wav")
def api_server_export_wav(project_id: str, body: ServerExportBody):
    from fastapi.responses import Response
    from engine.daw_workspace import loudness as daw_loudness
    from engine.daw_workspace.renderer import export_project_wav
    import soundfile as sf

    proj = store.load_project(project_id)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in proj.name).strip("_") or "mix"
    filename = f"{safe_name}_studio_48k.wav"
    start_b = proj.loopRegion.startBeats if (body.useLoopRange and proj.loopRegion.enabled) else 0.0
    end_b = proj.loopRegion.endBeats if (body.useLoopRange and proj.loopRegion.enabled) else proj.lengthBeats
    meta = export_project_wav(proj, filename=filename, start_beats=start_b, end_beats=end_b)
    out_path = store.project_dir(project_id) / meta["relativePath"]
    pcm, sr = sf.read(str(out_path), dtype="float32")
    lufs = float(daw_loudness.measure_loudness(pcm, sr).get("integratedLufs", -60.0))
    wav_bytes = out_path.read_bytes()
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Export-Filename": meta["filename"],
            "X-Export-Duration-Sec": f"{float(meta.get('durationSec', 0.0)):.3f}",
            "X-Export-Peak-Dbfs": f"{float(meta.get('peakDbfs', -96.0)):.2f}",
            "X-Export-Lufs": f"{lufs:.2f}",
        },
    )


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/compare-sound")
def api_compare_proposal_sound(project_id: str, proposal_id: str) -> dict[str, Any]:
    from engine.sound_design import compare_before_after_proposal

    proj = store.load_project(project_id)
    props = proposals.list_proposals(project_id)
    prop = next((p for p in props if p.get("id") == proposal_id), None)
    if prop is None:
        raise FileNotFoundError(f"Proposal not found: {proposal_id}")
    return compare_before_after_proposal(proj, list(prop.get("operations") or []))


class SamplerSliceBody(BaseModel):
    assetId: str = Field(min_length=1)
    sensitivity: float = Field(default=0.55, ge=0.1, le=0.95)
    createMidiClip: bool = True


@app.post("/api/projects/{project_id}/tracks/{track_id}/sampler/slice")
def api_sampler_slice(project_id: str, track_id: str, body: SamplerSliceBody) -> dict[str, Any]:
    from engine.instruments import slice_audio_by_transients

    proj = store.load_project(project_id)
    _, abs_path = store.resolve_asset_file(project_id, body.assetId)
    sliced = slice_audio_by_transients(abs_path, bpm=proj.bpm, sensitivity=body.sensitivity)
    updated = commands.apply_command(
        proj,
        "track.setInstrument",
        {"trackId": track_id, "instrumentRef": "pro-sampler", "preset": "transient-slice"},
    )
    updated = commands.apply_command(
        updated,
        "instrument.setParams",
        {
            "trackId": track_id,
            "parameters": {},
            "samplerConfig": {
                "audioAssetId": body.assetId,
                "samplePath": str(abs_path),
                "playbackMode": "one_shot",
                "slices": sliced["slices"],
            },
        },
    )
    if body.createMidiClip and sliced["midiNotes"]:
        bpb = updated.timeSignature.beats_per_bar
        max_b = max(n["startBeat"] + n["durationBeats"] for n in sliced["midiNotes"])
        dur_b = max(bpb, float(int((max_b + bpb - 0.01) // bpb) * bpb))
        updated = commands.apply_command(
            updated,
            "clip.add",
            {
                "trackId": track_id,
                "clip": {
                    "name": f"{abs_path.stem[:24]} (Sliced)",
                    "type": "midi",
                    "timelineStartBeats": 0.0,
                    "durationBeats": dur_b,
                    "notes": sliced["midiNotes"],
                },
            },
        )
    saved = store.save_project(updated, clear_autosave=False)
    session.event_bus.publish("project.updated", {"projectId": project_id, "revision": saved.revision, "source": "sampler_slice"})
    return {"sliceResult": sliced, "project": saved.model_dump()}


@app.get("/api/generation/engines")
def api_get_generation_engines() -> dict[str, Any]:
    return {"engines": detect_generation_engines()}


@app.get("/api/generation/golden-references")
def api_get_golden_references() -> dict[str, Any]:
    from engine.generation.golden_references import YUE2_RECOVERY_GUIDE, list_golden_references

    return {
        "goldenReferences": list_golden_references(),
        "yue2RecoveryGuide": YUE2_RECOVERY_GUIDE,
    }


class HybridLayerBody(BaseModel):
    goldenReferenceId: str | None = None
    sourceAssetId: str | None = None
    layerRoles: list[str] | None = None
    instruction: str = "원본 네이티브 오디오를 보존하면서 어울리는 MIDI 레이어를 추가해줘"
    bars: int = Field(default=8, ge=2, le=64)


@app.post("/api/projects/{project_id}/hybrid/layer")
def api_create_hybrid_layer(project_id: str, body: HybridLayerBody) -> dict[str, Any]:
    from engine.generation.golden_references import create_hybrid_session

    return create_hybrid_session(
        project_id=project_id,
        golden_reference_id=body.goldenReferenceId,
        source_asset_id=body.sourceAssetId,
        layer_roles=body.layerRoles,
        instruction=body.instruction,
        bars=body.bars,
    )


@app.get("/api/library/catalog")
def api_get_library_catalog(projectBpm: float | None = None) -> dict[str, Any]:
    return {"items": list_library_catalog(project_bpm=projectBpm)}


@app.post("/api/projects/{project_id}/composition/plan")
def api_create_composition_plan(project_id: str, body: CreateCompositionPlanBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    plan = create_composition_plan(
        project=proj,
        instruction=body.instruction,
        mode=body.mode,
        target_instrument=body.targetInstrument,
        reference_ids=body.referenceIds,
        selected_influences=body.selectedInfluences,
        selection=body.selection,
        provider_id=body.providerId,
        engine_preference=body.enginePreference,
        production_mode=body.productionMode,
        allow_preview_instruments=body.allowPreviewInstruments,
        feature_locks=body.featureLocks,
        feature_source_map=body.featureSourceMap,
        bass_lock_mode=body.bassLockMode,
        reference_mode=body.referenceMode,
        use_project_chord_track=body.useProjectChordTrack,
    )
    saved_plan, rev = save_composition_plan(project_id, plan)
    return {"plan": saved_plan, "projectRevision": rev}


@app.get("/api/projects/{project_id}/composition/plans")
def api_list_composition_plans(project_id: str) -> dict[str, Any]:
    proj = store.load_project(project_id)
    return {"plans": list(reversed(proj.compositionPlans))}


@app.post("/api/projects/{project_id}/generation/jobs")
def api_start_generation_job(project_id: str, body: StartGenerationBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    if body.planId:
        raw = get_composition_plan(project_id, body.planId)
        if not raw:
            raise FileNotFoundError(f"CompositionPlan not found: {body.planId}")
        plan = CompositionPlan.model_validate(raw)
    else:
        if not body.instruction:
            raise ValueError("Either planId or instruction is required")
        plan = create_composition_plan(
            project=proj,
            instruction=body.instruction,
            mode=body.mode,
            target_instrument=body.targetInstrument,
            reference_ids=body.referenceIds,
            selected_influences=body.selectedInfluences,
            selection=body.selection,
            engine_preference=body.engine,
            production_mode=body.productionMode,
            allow_preview_instruments=body.allowPreviewInstruments,
            feature_locks=body.featureLocks,
            feature_source_map=body.featureSourceMap,
            bass_lock_mode=body.bassLockMode,
            reference_mode=body.referenceMode,
            use_project_chord_track=body.useProjectChordTrack,
        )
    return generation_jobs.start_composition_job(
        project_id=project_id,
        plan=plan,
        engine_choice=body.engine,
        production_mode=body.productionMode,
        seed=body.seed,
        sync=body.sync,
    )


# --- Phase 05.1 Permanent Production Policy, Taste Profile, Instrument Resolver & Studio Preview ---

class TasteUpdateBody(BaseModel):
    globalPatch: dict[str, Any] | None = None
    projectId: str | None = None
    projectPatch: dict[str, Any] | None = None


class TasteFeedbackBody(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    verdict: str = "feedback"
    tags: list[str] = Field(default_factory=list)
    projectName: str | None = None
    projectId: str | None = None


class TasteResetBody(BaseModel):
    projectId: str | None = None


class ResolveInstrumentBody(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    genre: str = "rnb_neosoul"
    instruction: str = ""
    allowPreviewInstruments: bool = False
    explicitInstrumentRef: str | None = None


class ValidateInstrumentBody(BaseModel):
    instrumentRef: str = Field(min_length=1, max_length=120)
    productionMode: bool = True
    allowPreviewInstruments: bool = False
    explicitUserRequest: bool = False


class StudioPreviewRenderBody(BaseModel):
    startBeats: float = Field(default=0.0, ge=0.0)
    endBeats: float | None = Field(default=None, gt=0.0)
    exportCopyFilename: str | None = None


@app.get("/api/production/policy")
def api_get_production_policy() -> dict[str, Any]:
    from engine.production import get_full_production_policy_snapshot

    return get_full_production_policy_snapshot()


@app.get("/api/production/taste")
def api_get_taste_profile(projectId: str | None = None) -> dict[str, Any]:
    from engine.production import get_taste_profile

    return get_taste_profile(project_id=projectId)


@app.patch("/api/production/taste")
def api_patch_taste_profile(body: TasteUpdateBody) -> dict[str, Any]:
    from engine.production import update_taste_profile

    return update_taste_profile(
        global_patch=body.globalPatch,
        project_id=body.projectId,
        project_patch=body.projectPatch,
    )


@app.post("/api/production/taste/feedback")
def api_record_taste_feedback(body: TasteFeedbackBody) -> dict[str, Any]:
    from engine.production import record_user_feedback

    return record_user_feedback(
        note=body.note,
        verdict=body.verdict,
        tags=body.tags,
        project_name=body.projectName,
        project_id=body.projectId,
    )


@app.post("/api/production/taste/reset")
def api_reset_taste_profile(body: TasteResetBody | None = None) -> dict[str, Any]:
    from engine.production import reset_taste_profile

    return reset_taste_profile(project_id=(body.projectId if body else None))


@app.post("/api/production/instruments/resolve")
def api_resolve_production_instrument(body: ResolveInstrumentBody) -> dict[str, Any]:
    from engine.production import get_taste_profile, resolve_production_instrument

    taste = get_taste_profile().get("effectiveForProject") or {}
    return resolve_production_instrument(
        body.role,
        genre=body.genre,
        instruction=body.instruction,
        allow_preview=body.allowPreviewInstruments,
        explicit_instrument_ref=body.explicitInstrumentRef,
        taste_profile=taste,
    )


@app.post("/api/production/instruments/validate")
def api_validate_instrument_selection(body: ValidateInstrumentBody) -> dict[str, Any]:
    from engine.production import validate_instrument_selection

    return validate_instrument_selection(
        body.instrumentRef,
        production_mode=body.productionMode,
        allow_preview=body.allowPreviewInstruments,
        explicit_user_request=body.explicitUserRequest,
    )


@app.get("/api/projects/{project_id}/studio-preview/status")
def api_get_studio_preview_status(project_id: str) -> dict[str, Any]:
    from engine.fx.studio_preview import get_studio_preview_status

    return get_studio_preview_status(project_id)


@app.post("/api/projects/{project_id}/studio-preview/render")
def api_render_studio_preview(project_id: str, body: StudioPreviewRenderBody | None = None) -> dict[str, Any]:
    from engine.fx.studio_preview import render_studio_preview

    b = body or StudioPreviewRenderBody()
    return render_studio_preview(
        project_id,
        start_beats=b.startBeats,
        end_beats=b.endBeats,
        filename_export_copy=b.exportCopyFilename,
    )


@app.get("/api/projects/{project_id}/studio-preview/audio")
def api_get_studio_preview_audio(project_id: str):
    from engine.fx.studio_preview import resolve_studio_preview_file

    _, abs_path = resolve_studio_preview_file(project_id)
    return FileResponse(abs_path, media_type="audio/wav", filename="studio_preview.wav")


@app.get("/api/projects/{project_id}/generation/jobs")
def api_list_project_generation_jobs(project_id: str) -> dict[str, Any]:
    return {"jobs": generation_jobs.list_jobs(project_id)}


@app.get("/api/generation/jobs/{job_id}")
def api_get_generation_job(job_id: str) -> dict[str, Any]:
    return generation_jobs.get_job(job_id)


@app.post("/api/generation/jobs/{job_id}/cancel")
def api_cancel_generation_job(job_id: str) -> dict[str, Any]:
    return generation_jobs.cancel_job(job_id)


@app.post("/api/generation/jobs/{job_id}/retry")
def api_retry_generation_job(job_id: str, sync: bool = False) -> dict[str, Any]:
    return generation_jobs.retry_job(job_id, sync=sync)


@app.get("/api/projects/{project_id}/takes")
def api_list_takes(project_id: str) -> dict[str, Any]:
    return {"takes": list_takes(project_id)}


@app.get("/api/projects/{project_id}/takes/{take_id}")
def api_get_take(project_id: str, take_id: str) -> dict[str, Any]:
    return {"take": get_take(project_id, take_id)}


@app.get("/api/projects/{project_id}/takes/{take_id}/audio")
def api_get_take_audio(project_id: str, take_id: str, variant: str = "solo"):
    take, abs_path = resolve_take_preview_audio(project_id, take_id, variant=variant)
    return FileResponse(abs_path, media_type="audio/wav", filename=f"{take_id}_{variant}.wav")


@app.post("/api/projects/{project_id}/takes/{take_id}/apply")
def api_apply_take(project_id: str, take_id: str, body: ApplyTakeBody) -> dict[str, Any]:
    return apply_take(
        project_id=project_id,
        take_id=take_id,
        apply_mode=body.applyMode,
        target_track_id=body.targetTrackId,
        start_beats=body.startBeats,
        add_section_markers=body.addSectionMarkers,
        replace_sections=body.replaceSections,
        expected_revision=body.expectedRevision,
        force_reapply=body.forceReapply,
    )


@app.post("/api/projects/{project_id}/takes/{take_id}/reject")
def api_reject_take(project_id: str, take_id: str) -> dict[str, Any]:
    take, rev = reject_take(project_id, take_id)
    return {"take": take, "projectRevision": rev}


@app.post("/api/projects/{project_id}/stems/separate")
def api_separate_stems(project_id: str, body: SeparateStemsBody) -> dict[str, Any]:
    return generation_jobs.start_stem_separation_job(
        project_id=project_id,
        asset_id=body.assetId,
        source_track_id=body.sourceTrackId,
        model_name=body.modelName,
        sync=body.sync,
    )


# --- Phase 04: Selective Arrangement, Musical Variation, Take Lanes, Audio Reverse & Music Memory ---

class ArrangementPlanBody(BaseModel):
    instruction: str = Field(min_length=1, max_length=1500)
    selection: dict[str, Any] | None = None
    intensity: str | None = None
    targetTrackId: str | None = None
    startBeats: float | None = None
    endBeats: float | None = None
    providerId: str | None = None


class ArrangementExecuteBody(BaseModel):
    plan: dict[str, Any] | None = None
    instruction: str | None = None
    selection: dict[str, Any] | None = None
    intensity: str | None = None
    targetTrackId: str | None = None
    startBeats: float | None = None
    endBeats: float | None = None
    seed: int = 42


class PromoteTakeLaneBody(BaseModel):
    startBeats: float | None = None
    endBeats: float | None = None


class RestoreOriginalLaneBody(BaseModel):
    laneId: str | None = None


class ReverseClipBody(BaseModel):
    expectedRevision: int | None = None


class PatchMemoryBody(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/projects/{project_id}/arrangement/plan")
def api_create_arrangement_plan(project_id: str, body: ArrangementPlanBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    plan = create_arrangement_edit_plan(
        project=proj,
        instruction=body.instruction,
        selection=body.selection,
        intensity=body.intensity,
        target_track_id=body.targetTrackId,
        start_beats=body.startBeats,
        end_beats=body.endBeats,
        provider_id=body.providerId,
    )
    return {"plan": plan.model_dump(), "projectRevision": proj.revision}


@app.post("/api/projects/{project_id}/arrangement/execute")
def api_execute_arrangement_plan(project_id: str, body: ArrangementExecuteBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    if body.plan:
        plan = ArrangementEditPlan.model_validate(body.plan)
        if body.intensity in ("subtle", "moderate", "creative"):
            plan.intensity = body.intensity  # type: ignore[assignment]
    else:
        if not body.instruction:
            raise ValueError("Either plan or instruction is required")
        plan = create_arrangement_edit_plan(
            project=proj,
            instruction=body.instruction,
            selection=body.selection,
            intensity=body.intensity,
            target_track_id=body.targetTrackId,
            start_beats=body.startBeats,
            end_beats=body.endBeats,
        )
    return execute_arrangement_edit_plan(project_id, plan, seed=body.seed)


@app.post("/api/projects/{project_id}/tracks/{track_id}/take-lanes/{lane_id}/promote")
def api_promote_take_lane(
    project_id: str,
    track_id: str,
    lane_id: str,
    body: PromoteTakeLaneBody | None = None,
) -> dict[str, Any]:
    b = body or PromoteTakeLaneBody()
    return promote_take_lane(
        project_id,
        track_id,
        lane_id,
        comp_start_beats=b.startBeats,
        comp_end_beats=b.endBeats,
    )


@app.post("/api/projects/{project_id}/tracks/{track_id}/take-lanes/restore-original")
def api_restore_original_lane(
    project_id: str,
    track_id: str,
    body: RestoreOriginalLaneBody | None = None,
) -> dict[str, Any]:
    b = body or RestoreOriginalLaneBody()
    return restore_original_lane(project_id, track_id, lane_id=b.laneId)


@app.patch("/api/projects/{project_id}/tracks/{track_id}/take-lanes/{lane_id}")
def api_rename_take_lane(project_id: str, track_id: str, lane_id: str, body: RenameBody) -> dict[str, Any]:
    return rename_take_lane(project_id, track_id, lane_id, body.name)


@app.post("/api/projects/{project_id}/clips/{clip_id}/reverse")
def api_reverse_clip(
    project_id: str,
    clip_id: str,
    body: ReverseClipBody | None = None,
) -> dict[str, Any]:
    b = body or ReverseClipBody()
    return create_reversed_clip_asset(project_id, clip_id, expected_revision=b.expectedRevision)


@app.get("/api/projects/{project_id}/memory")
def api_get_music_memory(project_id: str) -> dict[str, Any]:
    proj = store.load_project(project_id)
    return {"projectId": project_id, "musicMemory": ensure_music_memory(proj)}


@app.patch("/api/projects/{project_id}/memory")
def api_patch_music_memory(project_id: str, body: PatchMemoryBody) -> dict[str, Any]:
    mem = update_project_music_memory(project_id, patch=body.patch)
    return {"projectId": project_id, "musicMemory": mem}


@app.get("/api/events")
async def sse_events(request: Request, projectId: str | None = None):
    """Server-Sent Events stream for real-time Agent Bridge & external MCP synchronization."""
    loop = asyncio.get_running_loop()
    q = session.event_bus.subscribe(loop)

    async def stream():
        last_seen_rev: int | None = None
        last_seen_prop_sig: str = ""
        if projectId:
            try:
                last_seen_rev = store.load_project(projectId).revision
                last_seen_prop_sig = json.dumps(proposals.list_proposals(projectId, status="pending"), sort_keys=True)
            except Exception:
                pass
        try:
            yield f"data: {json.dumps({'type': 'connected', 'payload': {'projectId': projectId}})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    if msg.get("type") == "project.updated" and msg.get("payload", {}).get("projectId") == projectId:
                        last_seen_rev = msg["payload"].get("revision")
                except asyncio.TimeoutError:
                    # Also detect external STDIO MCP process writes on disk!
                    if projectId:
                        try:
                            cur = store.load_project(projectId)
                            if last_seen_rev is not None and cur.revision != last_seen_rev:
                                last_seen_rev = cur.revision
                                evt = {
                                    "type": "project.updated",
                                    "payload": {
                                        "projectId": projectId,
                                        "revision": cur.revision,
                                        "reason": "External agent update",
                                        "project": cur.model_dump(),
                                    },
                                }
                                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                            pend = proposals.list_proposals(projectId, status="pending")
                            sig = json.dumps(pend, sort_keys=True)
                            if sig != last_seen_prop_sig:
                                last_seen_prop_sig = sig
                                evt = {
                                    "type": "proposals.synced",
                                    "payload": {"projectId": projectId, "proposals": pend},
                                }
                                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                        except Exception:
                            pass
                    yield ": keepalive\n\n"
        finally:
            session.event_bus.unsubscribe(loop, q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/projects/{project_id}/assets/import-library")
def import_from_library(project_id: str, body: ImportLibraryBody) -> dict[str, Any]:
    lib_dir = (engine_paths.DATA / "daw" / "library").resolve()
    target = (lib_dir / body.libraryId).resolve()
    if not target.is_relative_to(lib_dir) or not target.is_file():
        raise FileNotFoundError(f"Library asset not found: {body.libraryId}")
    asset, extra = store.import_asset_bytes(
        project_id=project_id,
        filename=target.name,
        raw_bytes=target.read_bytes(),
        kind_hint=body.kind,
        source="studio-library",
        provenance=f"Studio library ({body.libraryId})",
    )
    return {"asset": asset.model_dump(), **extra}


# Serve built frontend assets when apps/daw/dist exists
if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="daw-assets")


@app.get("/")
def serve_index():
    index_html = DIST_DIR / "index.html"
    if index_html.is_file():
        return FileResponse(index_html)
    return JSONResponse(
        {
            "message": "AI-Native DAW API is running. Build apps/daw (`cd apps/daw && npm run build`) or run Vite dev server (`npm run dev`)."
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI-Native DAW local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8796)
    args = parser.parse_args()
    engine_paths.initialize()
    uvicorn.run("app.daw_server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
