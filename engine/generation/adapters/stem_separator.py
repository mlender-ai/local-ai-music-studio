"""Real Demucs Stem Separation Adapter with Apple Silicon MPS, Content Cache & Process-Group Cancellation."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from engine.generation.process_guard import run_cancellable_guarded
from engine.runtime import get_runtime_registry, record_engine_verification

STEM_LABELS: dict[str, tuple[str, str]] = {
    "drums": ("Drums (Stem)", "#6a997c"),
    "bass": ("Bass (Stem)", "#867ca8"),
    "other": ("Other (Stem)", "#b89458"),
    "vocals": ("Vocals (Stem)", "#9e7389"),
    "guitar": ("Guitar (Stem)", "#c2925a"),
    "piano": ("Piano (Stem)", "#648ea8"),
}


def probe_demucs() -> dict[str, Any]:
    reg = get_runtime_registry()
    return next(e for e in reg["engines"] if e["id"] == "demucs-htdemucs")


def separate_stems_demucs(
    audio_path: Path,
    out_dir: Path,
    model_name: str = "htdemucs",
    timeout_sec: float = 360.0,
    cancel_event: threading.Event | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Run real Demucs (`htdemucs` / `htdemucs_6s`) under shared lock & real cancellation using soundfile + MPS."""
    info = probe_demucs()
    if not info["available"]:
        raise RuntimeError(
            "Demucs is not installed on this machine. Real stem separation cannot run without Demucs."
        )

    stem_dir = out_dir / model_name / audio_path.stem
    stem_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = stem_dir / "manifest.json"

    # Reuse cached stem WAVs if already separated (conserves 16 GB Apple Silicon RAM & time!)
    if use_cache and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cached_stems: list[dict[str, Any]] = []
            for item in manifest.get("stems", []):
                role = str(item.get("role", ""))
                wav = stem_dir / str(item.get("filename", f"{role}.wav"))
                if role and wav.is_file():
                    label, color = STEM_LABELS.get(role, (f"{role.title()} (Stem)", "#7a869a"))
                    cached_stems.append(
                        {
                            "role": role,
                            "name": label,
                            "color": color,
                            "wavPath": wav,
                            "rmsDbfs": item.get("rmsDbfs"),
                            "sampleRate": item.get("sampleRate", 44100),
                            "durationSec": item.get("durationSec", 0.0),
                            "device": manifest.get("device", "cached"),
                            "fromCache": True,
                        }
                    )
            if cached_stems:
                return cached_stems
        except Exception:
            pass

    cmd = [
        sys.executable,
        "-m",
        "engine.generation.adapters._demucs_runner",
        "--input",
        str(audio_path),
        "--out-dir",
        str(stem_dir),
        "--model",
        model_name,
    ]

    run_cancellable_guarded(
        cmd,
        out_dir / "demucs.log",
        cancel_event=cancel_event,
        timeout_sec=timeout_sec,
    )

    stems: list[dict[str, Any]] = []
    manifest_data: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest_data = {}

    rms_map = {str(s.get("role")): s for s in manifest_data.get("stems", [])}
    for stem_key, (label, color) in STEM_LABELS.items():
        wav = stem_dir / f"{stem_key}.wav"
        if wav.is_file():
            meta = rms_map.get(stem_key, {})
            stems.append(
                {
                    "role": stem_key,
                    "name": label,
                    "color": color,
                    "wavPath": wav,
                    "rmsDbfs": meta.get("rmsDbfs"),
                    "sampleRate": meta.get("sampleRate", 44100),
                    "durationSec": meta.get("durationSec", 0.0),
                    "device": manifest_data.get("device", "mps"),
                    "fromCache": False,
                }
            )

    if not stems:
        record_engine_verification("demucs-htdemucs", False, error=f"No stems produced under {stem_dir}")
        raise RuntimeError(f"Demucs completed but no stem WAVs found under {stem_dir}")

    record_engine_verification(
        "demucs-htdemucs",
        True,
        wav_path=str(stems[0]["wavPath"]),
        details={"model": model_name, "device": manifest_data.get("device"), "stemCount": len(stems)},
    )
    return stems
