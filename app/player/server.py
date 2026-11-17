"""Loopback-only player with same-origin write protection and range audio."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field
from engine import jobs, store, service
from engine.paths import audio_path, ROOT
from engine.schema import Generate, Strict

app = FastAPI(title="Local AI Music Studio", docs_url=None, redoc_url=None)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)


@app.middleware("http")
async def local_writes(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if request.headers.get("x-studio-request") != "1" or (
            origin and origin != expected
        ):
            return JSONResponse(
                {"error": "Same-origin studio request required."}, status_code=403
            )
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid_request(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(OSError)
async def file_error(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/")
def index():
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/api/state")
def state():
    required = [
        "acestep-v15-turbo/model.safetensors",
        "vae/diffusion_pytorch_model.safetensors",
        "Qwen3-Embedding-0.6B/model.safetensors",
        "vae/config.json",
    ]
    ready = all(
        (ROOT / ".runtime/models/checkpoints" / name).is_file() for name in required
    )
    return dict(**store.list_versions(), **jobs.status(), generation_ready=ready)


@app.get("/audio/{version_id}")
def audio_file(version_id: str):
    version = store.get_version(version_id)
    return FileResponse(audio_path(version["path"]), media_type="audio/wav")


@app.post("/api/generate")
def generate(command: Generate):
    return jobs.submit(command)


class Production(Strict):
    version_id: str
    instruction: str = Field(min_length=1, max_length=2000)


@app.post("/api/produce")
def produce(command: Production):
    return service.produce(command.version_id, command.instruction)


class Version(Strict):
    version_id: str


@app.post("/api/restore")
def restore(command: Version):
    return store.restore(command.version_id)


@app.post("/api/export")
def export(command: Version):
    return service.export(command.version_id)


@app.get("/api/compare")
def compare(original_id: str, modified_id: str):
    return service.compare_versions(original_id, modified_id)
