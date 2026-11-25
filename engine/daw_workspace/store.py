"""Local-first atomic project persistence, revision locking, and immutable asset storage."""

from __future__ import annotations

import fcntl
import hashlib
import json
import mimetypes
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from engine import paths as engine_paths

from .midi import parse_midi_bytes
from .schema import (
    SCHEMA_VERSION,
    Asset,
    Project,
    ProjectSummary,
    SectionMarker,
    Track,
    make_id,
    utc_now_iso,
)
from .waveforms import inspect_audio_file, load_or_compute_waveform

ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
ALLOWED_MIDI_EXTS = {".mid", ".midi"}
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{3,80}$")


class RevisionConflictError(Exception):
    """Raised when a save or command targets an outdated project revision."""

    def __init__(self, expected: int, actual: int, server_project: Project):
        self.expected = expected
        self.actual = actual
        self.server_project = server_project
        super().__init__(
            f"Revision conflict: expected revision {expected}, but server is at revision {actual}."
        )


def projects_root() -> Path:
    root = engine_paths.DATA / "daw" / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_project_id(project_id: str) -> str:
    if not SAFE_ID_RE.match(project_id):
        raise ValueError("Invalid project ID")
    return project_id


def project_dir(project_id: str) -> Path:
    _validate_project_id(project_id)
    root = projects_root().resolve()
    target = (root / project_id).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Project path escapes DAW storage root")
    return target


def _ensure_project_folders(pdir: Path) -> None:
    for rel in (
        "assets/audio",
        "assets/midi",
        "assets/references",
        "cache/waveforms",
        "cache/analysis",
        "cache/extracted",
        "takes",
        "versions",
        "exports",
    ):
        (pdir / rel).mkdir(parents=True, exist_ok=True)


@contextmanager
def _project_lock(pdir: Path):
    pdir.mkdir(parents=True, exist_ok=True)
    lock_path = pdir / ".project.lock"
    with lock_path.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    raw = json.dumps(payload, indent=2, ensure_ascii=False)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _sanitize_filename(name: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).name).strip("._")
    return stem or "asset.bin"


def migrate_project_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate older schema v1.0.0 / v1.1.0 / v1.2.0 project dictionaries cleanly into v1.3.0+."""
    out = dict(data)
    if "revision" not in out or not isinstance(out["revision"], int) or out["revision"] < 1:
        out["revision"] = 1
    if "references" not in out or not isinstance(out["references"], list):
        out["references"] = []
    if "compositionPlans" not in out or not isinstance(out["compositionPlans"], list):
        out["compositionPlans"] = []
    if "takes" not in out or not isinstance(out["takes"], list):
        out["takes"] = []
    if "musicMemory" not in out or not isinstance(out["musicMemory"], dict):
        out["musicMemory"] = {}
    for trk in out.get("tracks", []):
        if isinstance(trk, dict):
            trk.setdefault("takeLanes", [])
            trk.setdefault("stemMeta", None)
            for clp in trk.get("clips", []):
                if isinstance(clp, dict):
                    clp.setdefault("fadeInBeats", 0.0)
                    clp.setdefault("fadeOutBeats", 0.0)
                    clp.setdefault("reversed", False)
    out["schemaVersion"] = SCHEMA_VERSION
    return out


def list_projects() -> list[ProjectSummary]:
    root = projects_root()
    summaries: list[ProjectSummary] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        pfile = entry / "project.json"
        if not pfile.is_file():
            continue
        try:
            raw = json.loads(pfile.read_text(encoding="utf-8"))
            proj = Project.model_validate(migrate_project_dict(raw))
            summaries.append(
                ProjectSummary(
                    id=proj.id,
                    name=proj.name,
                    revision=proj.revision,
                    bpm=proj.bpm,
                    timeSignature=proj.timeSignature,
                    trackCount=len(proj.tracks),
                    assetCount=len(proj.assets),
                    lengthBeats=proj.lengthBeats,
                    updatedAt=proj.updatedAt,
                    createdAt=proj.createdAt,
                    hasAutosave=(entry / "project.autosave.json").is_file(),
                )
            )
        except Exception:
            continue
    summaries.sort(key=lambda item: item.updatedAt, reverse=True)
    return summaries


def create_project(
    name: str = "Untitled 01",
    bpm: float = 128.0,
    numerator: int = 4,
    denominator: int = 4,
    length_beats: float = 64.0,
    project_id: str | None = None,
    with_default_tracks: bool = True,
) -> Project:
    pid = _validate_project_id(project_id) if project_id else make_id("proj")
    pdir = project_dir(pid)
    _ensure_project_folders(pdir)

    tracks = (
        [
            Track(id=make_id("trk"), name="Drums", type="audio", color="#6a997c"),
            Track(id=make_id("trk"), name="Bass", type="audio", color="#867ca8"),
            Track(
                id=make_id("trk"),
                name="Synth",
                type="midi",
                color="#648ea8",
                instrumentRef="basic-poly-synth",
            ),
        ]
        if with_default_tracks
        else []
    )

    sections = [
        SectionMarker(id=make_id("sec"), name="INTRO", startBeats=0.0, endBeats=16.0, color="#49505e"),
        SectionMarker(id=make_id("sec"), name="GROOVE", startBeats=16.0, endBeats=32.0, color="#446256"),
        SectionMarker(id=make_id("sec"), name="BRIDGE", startBeats=32.0, endBeats=48.0, color="#554d6b"),
        SectionMarker(id=make_id("sec"), name="CLIMAX", startBeats=48.0, endBeats=64.0, color="#6d5645"),
    ]

    proj = Project(
        id=pid,
        revision=1,
        name=name.strip() or "Untitled 01",
        bpm=bpm,
        timeSignature={"numerator": numerator, "denominator": denominator},
        lengthBeats=length_beats,
        sections=sections,
        tracks=tracks,
    )
    return save_project(proj, expected_revision=None, bump_revision=False)


def _read_project_unlocked(pdir: Path, project_id: str) -> Project:
    pfile = pdir / "project.json"
    if not pfile.is_file():
        raise FileNotFoundError(f"Project not found: {project_id}")
    raw = json.loads(pfile.read_text(encoding="utf-8"))
    return Project.model_validate(migrate_project_dict(raw))


def load_project(project_id: str) -> Project:
    pdir = project_dir(project_id)
    with _project_lock(pdir):
        return _read_project_unlocked(pdir, project_id)


def save_project(
    project: Project,
    clear_autosave: bool = True,
    expected_revision: int | None = None,
    bump_revision: bool = True,
) -> Project:
    pdir = project_dir(project.id)
    _ensure_project_folders(pdir)
    with _project_lock(pdir):
        pfile = pdir / "project.json"
        current_rev = 0
        if pfile.is_file():
            existing = _read_project_unlocked(pdir, project.id)
            current_rev = existing.revision
            if expected_revision is not None and existing.revision != expected_revision:
                raise RevisionConflictError(expected_revision, existing.revision, existing)

        data = project.model_dump()
        data["schemaVersion"] = SCHEMA_VERSION
        if bump_revision and current_rev > 0:
            data["revision"] = current_rev + 1
        elif current_rev == 0:
            data["revision"] = max(1, int(data.get("revision", 1)))
        else:
            data["revision"] = max(1, current_rev)
        data["updatedAt"] = utc_now_iso()
        validated = Project.model_validate(data)
        _atomic_write_json(pfile, validated.model_dump())

        if clear_autosave:
            autosave = pdir / "project.autosave.json"
            if autosave.is_file():
                autosave.unlink()
        return validated


def autosave_project(project: Project, expected_revision: int | None = None) -> dict[str, Any]:
    pdir = project_dir(project.id)
    _ensure_project_folders(pdir)
    with _project_lock(pdir):
        pfile = pdir / "project.json"
        if pfile.is_file() and expected_revision is not None:
            existing = _read_project_unlocked(pdir, project.id)
            if existing.revision != expected_revision:
                raise RevisionConflictError(expected_revision, existing.revision, existing)
        validated = Project.model_validate(migrate_project_dict(project.model_dump()))
        _atomic_write_json(pdir / "project.autosave.json", validated.model_dump())
        return {"saved": True, "revision": validated.revision, "updatedAt": utc_now_iso()}


def save_as_project(source_project_id: str, new_name: str, state: Project | None = None) -> Project:
    src_dir = project_dir(source_project_id)
    base_proj = state if state is not None else load_project(source_project_id)
    new_id = make_id("proj")
    dst_dir = project_dir(new_id)
    shutil.copytree(src_dir, dst_dir)
    for removable in ("project.autosave.json", ".project.lock"):
        p = dst_dir / removable
        if p.is_file():
            p.unlink()
    cloned = Project.model_validate(migrate_project_dict(base_proj.model_dump()))
    cloned.id = new_id
    cloned.revision = 1
    cloned.name = new_name.strip() or f"{base_proj.name} Copy"
    cloned.createdAt = utc_now_iso()
    return save_project(cloned, expected_revision=None, bump_revision=False)


def delete_project(project_id: str) -> None:
    pdir = project_dir(project_id)
    if not pdir.is_dir():
        raise FileNotFoundError(f"Project not found: {project_id}")
    shutil.rmtree(pdir)


def import_asset_bytes(
    project_id: str,
    filename: str,
    raw_bytes: bytes,
    kind_hint: str | None = None,
    source: str = "imported",
    provenance: str = "",
) -> tuple[Asset, dict[str, Any]]:
    """Store an immutable audio or MIDI asset and extract real metadata."""
    proj = load_project(project_id)
    pdir = project_dir(project_id)
    _ensure_project_folders(pdir)

    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_MIDI_EXTS:
        kind = "midi"
        subdir = "assets/midi"
        mime = "audio/midi"
    elif ext in ALLOWED_AUDIO_EXTS:
        kind = "reference" if kind_hint == "reference" else "audio"
        subdir = "assets/references" if kind == "reference" else "assets/audio"
        mime = mimetypes.guess_type(filename)[0] or "audio/wav"
    else:
        raise ValueError(
            f"Unsupported asset format '{ext}'. Supported audio: {sorted(ALLOWED_AUDIO_EXTS)}, MIDI: .mid"
        )

    digest = hashlib.sha256(raw_bytes).hexdigest()

    for existing in proj.assets:
        if existing.sha256 == digest and existing.kind == kind:
            extra: dict[str, Any] = {"projectRevision": proj.revision}
            if kind == "midi":
                extra["midi"] = parse_midi_bytes(raw_bytes)
            return existing, extra

    asset_id = make_id("ast")
    safe_name = _sanitize_filename(filename)
    rel_path = f"{subdir}/{asset_id}_{safe_name}"
    abs_path = (pdir / rel_path).resolve()
    if not abs_path.is_relative_to(pdir.resolve()):
        raise ValueError("Invalid asset target path")

    tmp = abs_path.with_suffix(abs_path.suffix + ".tmp")
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, abs_path)

    extra_info: dict[str, Any] = {}
    sample_rate = 0
    channels = 0
    duration_sec = 0.0
    duration_samples = 0
    duration_beats: float | None = None

    if kind == "midi":
        parsed = parse_midi_bytes(raw_bytes)
        duration_beats = float(parsed["durationBeats"])
        extra_info["midi"] = parsed
    else:
        try:
            meta = inspect_audio_file(abs_path)
            sample_rate = meta["sampleRate"]
            channels = meta["channels"]
            duration_sec = meta["durationSec"]
            duration_samples = meta["durationSamples"]
            load_or_compute_waveform(abs_path, pdir / "cache/waveforms", digest)
        except Exception as exc:
            extra_info["decodeWarning"] = (
                f"Server PCM inspect unavailable ({exc}); Web Audio will decode client-side."
            )

    asset = Asset(
        id=asset_id,
        name=Path(filename).name,
        kind=kind,
        relativePath=rel_path,
        source=source,
        provenance=provenance or f"Imported {Path(filename).name}",
        sha256=digest,
        sampleRate=sample_rate,
        channels=channels,
        durationSec=duration_sec,
        durationSamples=duration_samples,
        durationBeats=duration_beats,
        mimeType=mime,
    )
    proj.assets.append(asset)
    saved = save_project(proj, clear_autosave=False)
    extra_info["projectRevision"] = saved.revision
    return asset, extra_info


def relink_asset_bytes(
    project_id: str,
    asset_id: str,
    filename: str,
    raw_bytes: bytes,
) -> tuple[Asset, int]:
    """Relink a missing or broken asset ID to a newly provided local file."""
    proj = load_project(project_id)
    pdir = project_dir(project_id)
    _ensure_project_folders(pdir)

    target = next((a for a in proj.assets if a.id == asset_id), None)
    if not target:
        raise FileNotFoundError(f"Asset not found: {asset_id}")

    ext = Path(filename).suffix.lower()
    if target.kind == "midi" and ext not in ALLOWED_MIDI_EXTS:
        raise ValueError("MIDI asset must be relinked to a .mid/.midi file")
    if target.kind != "midi" and ext not in ALLOWED_AUDIO_EXTS:
        raise ValueError(f"Audio asset must be relinked to a supported audio file ({sorted(ALLOWED_AUDIO_EXTS)})")

    digest = hashlib.sha256(raw_bytes).hexdigest()
    subdir = "assets/midi" if target.kind == "midi" else ("assets/references" if target.kind == "reference" else "assets/audio")
    safe_name = _sanitize_filename(filename)
    rel_path = f"{subdir}/{asset_id}_{safe_name}"
    abs_path = (pdir / rel_path).resolve()
    if not abs_path.is_relative_to(pdir.resolve()):
        raise ValueError("Invalid relink target path")

    tmp = abs_path.with_suffix(abs_path.suffix + ".tmp")
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, abs_path)

    target.name = Path(filename).name
    target.relativePath = rel_path
    target.sha256 = digest
    target.mimeType = mimetypes.guess_type(filename)[0] or target.mimeType
    target.provenance = f"Relinked from {Path(filename).name}"

    if target.kind != "midi":
        try:
            meta = inspect_audio_file(abs_path)
            target.sampleRate = meta["sampleRate"]
            target.channels = meta["channels"]
            target.durationSec = meta["durationSec"]
            target.durationSamples = meta["durationSamples"]
            load_or_compute_waveform(abs_path, pdir / "cache/waveforms", digest)
        except Exception:
            pass

    saved = save_project(proj, clear_autosave=False)
    return target, saved.revision


def resolve_asset_file(project_id: str, asset_id: str) -> tuple[Asset, Path]:
    proj = load_project(project_id)
    pdir = project_dir(project_id).resolve()
    for asset in proj.assets:
        if asset.id == asset_id:
            abs_path = (pdir / asset.relativePath).resolve()
            if not abs_path.is_relative_to(pdir) or not abs_path.is_file():
                raise FileNotFoundError(f"Asset file missing on disk: {asset.relativePath}")
            return asset, abs_path
    raise FileNotFoundError(f"Asset not found: {asset_id}")


def get_asset_waveform(project_id: str, asset_id: str, bins: int = 1024) -> dict[str, Any]:
    asset, abs_path = resolve_asset_file(project_id, asset_id)
    if asset.kind == "midi":
        raise ValueError("MIDI assets do not have PCM waveforms")
    pdir = project_dir(project_id)
    return load_or_compute_waveform(abs_path, pdir / "cache/waveforms", asset.sha256, bins=bins)


def save_export_bytes(project_id: str, filename: str, wav_bytes: bytes) -> dict[str, Any]:
    pdir = project_dir(project_id).resolve()
    exports_dir = (pdir / "exports").resolve()
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe = _sanitize_filename(filename)
    if not safe.lower().endswith(".wav"):
        safe += ".wav"
    out_path = (exports_dir / safe).resolve()
    if not out_path.is_relative_to(exports_dir):
        raise ValueError("Invalid export filename")
    tmp = out_path.with_suffix(".wav.tmp")
    tmp.write_bytes(wav_bytes)
    os.replace(tmp, out_path)
    return {
        "filename": safe,
        "relativePath": f"exports/{safe}",
        "bytes": len(wav_bytes),
        "sha256": hashlib.sha256(wav_bytes).hexdigest(),
    }
