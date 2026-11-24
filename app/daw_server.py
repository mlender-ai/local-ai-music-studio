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
    return {
        "status": "ok",
        "product": "AI-Native DAW",
        "phase": "03",
        "port": 8796,
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
            "messageKo": f"변경 제안이 생성되었습니다: {prop['summary']}. 확인 후 '적용'을 눌러 반영하세요.",
            "messageEn": f"Change proposal staged: {prop['summary']}. Click Apply to commit.",
        }
    if routed.get("action") == "composition_plan":
        plan = create_composition_plan(
            project=proj,
            instruction=body.instruction,
            reference_ids=[body.activeReferenceId] if body.activeReferenceId else None,
            selection=body.selection,
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
    selection: dict[str, Any] | None = None
    providerId: str | None = None
    enginePreference: str = "auto"


class StartGenerationBody(BaseModel):
    planId: str | None = None
    instruction: str | None = None
    mode: str | None = None
    targetInstrument: str | None = None
    referenceIds: list[str] | None = None
    selectedInfluences: list[str] | None = None
    selection: dict[str, Any] | None = None
    engine: str = "auto"
    seed: int | None = None
    sync: bool = False


class ApplyTakeBody(BaseModel):
    applyMode: str = "new_tracks"  # new_tracks | selected_range | new_project | keep_take
    targetTrackId: str | None = None
    startBeats: float | None = None
    addSectionMarkers: bool = True
    expectedRevision: int | None = None


class SeparateStemsBody(BaseModel):
    assetId: str = Field(min_length=1)
    modelName: str = "htdemucs"
    sync: bool = False


@app.get("/api/providers")
def api_get_providers() -> dict[str, Any]:
    return get_provider_summary()


@app.post("/api/providers/select")
def api_select_provider(body: SelectProviderBody) -> dict[str, Any]:
    return select_provider(body.providerId, model=body.model)


@app.get("/api/instruments")
def api_get_instruments() -> dict[str, Any]:
    return {"instruments": list_instruments()}


@app.get("/api/generation/engines")
def api_get_generation_engines() -> dict[str, Any]:
    return {"engines": detect_generation_engines()}


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
        )
    return generation_jobs.start_composition_job(
        project_id=project_id,
        plan=plan,
        engine_choice=body.engine,
        seed=body.seed,
        sync=body.sync,
    )


@app.get("/api/projects/{project_id}/generation/jobs")
def api_list_project_generation_jobs(project_id: str) -> dict[str, Any]:
    return {"jobs": generation_jobs.list_jobs(project_id)}


@app.get("/api/generation/jobs/{job_id}")
def api_get_generation_job(job_id: str) -> dict[str, Any]:
    return generation_jobs.get_job(job_id)


@app.post("/api/generation/jobs/{job_id}/cancel")
def api_cancel_generation_job(job_id: str) -> dict[str, Any]:
    return generation_jobs.cancel_job(job_id)


@app.get("/api/projects/{project_id}/takes")
def api_list_takes(project_id: str) -> dict[str, Any]:
    return {"takes": list_takes(project_id)}


@app.get("/api/projects/{project_id}/takes/{take_id}")
def api_get_take(project_id: str, take_id: str) -> dict[str, Any]:
    return {"take": get_take(project_id, take_id)}


@app.get("/api/projects/{project_id}/takes/{take_id}/audio")
def api_get_take_audio(project_id: str, take_id: str):
    take, abs_path = resolve_take_preview_audio(project_id, take_id)
    return FileResponse(abs_path, media_type="audio/wav", filename=f"{take_id}_preview.wav")


@app.post("/api/projects/{project_id}/takes/{take_id}/apply")
def api_apply_take(project_id: str, take_id: str, body: ApplyTakeBody) -> dict[str, Any]:
    return apply_take(
        project_id=project_id,
        take_id=take_id,
        apply_mode=body.applyMode,
        target_track_id=body.targetTrackId,
        start_beats=body.startBeats,
        add_section_markers=body.addSectionMarkers,
        expected_revision=body.expectedRevision,
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
        model_name=body.modelName,
        sync=body.sync,
    )


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
