"""Local-first FastAPI server for AI-Native DAW Phase 01 (127.0.0.1:8796)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from engine import paths as engine_paths
from engine.daw_workspace import commands, reaper, renderer, store
from engine.daw_workspace.schema import CommandRequest, Project

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
        "phase": "01",
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
def put_project(project_id: str, project: Project) -> dict[str, Any]:
    if project.id != project_id:
        raise ValueError("Project payload ID does not match URL project_id")
    saved = store.save_project(project)
    return saved.model_dump()


@app.post("/api/projects/{project_id}/autosave")
def post_autosave(project_id: str, project: Project) -> dict[str, Any]:
    if project.id != project_id:
        raise ValueError("Project payload ID does not match URL project_id")
    return store.autosave_project(project)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, body: RenameBody) -> dict[str, Any]:
    proj = store.load_project(project_id)
    updated = commands.apply_command(proj, "project.rename", {"name": body.name})
    return store.save_project(updated).model_dump()


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
    updated = commands.apply_command(proj, req.type, req.payload)
    saved = store.save_project(updated, clear_autosave=False)
    return {"command": req.type, "project": saved.model_dump()}


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
