"""Real Demucs Stem Separation Adapter with Process-Group Cancellation & Shared Lock (Phase 03.1 / 04)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from engine.generation.process_guard import run_cancellable_guarded
from engine.runtime import get_runtime_registry, record_engine_verification


def probe_demucs() -> dict[str, Any]:
    reg = get_runtime_registry()
    return next(e for e in reg["engines"] if e["id"] == "demucs-htdemucs")


def separate_stems_demucs(
    audio_path: Path,
    out_dir: Path,
    model_name: str = "htdemucs",
    timeout_sec: float = 360.0,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, Any]]:
    """Run real Demucs separation under shared lock & real cancellation; raises honestly if uninstalled."""
    info = probe_demucs()
    if not info["available"]:
        raise RuntimeError(
            "Demucs is not installed on this machine. Real stem separation cannot run without Demucs."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cli_path = info.get("binaryPath")
    if cli_path and Path(cli_path).is_file():
        cmd = [cli_path, "-n", model_name, "-o", str(out_dir), str(audio_path)]
    else:
        cmd = ["python", "-m", "demucs", "-n", model_name, "-o", str(out_dir), str(audio_path)]

    run_cancellable_guarded(
        cmd,
        out_dir / "demucs.log",
        cancel_event=cancel_event,
        timeout_sec=timeout_sec,
    )

    stem_dir = out_dir / model_name / audio_path.stem
    stems: list[dict[str, Any]] = []
    label_colors = {
        "drums": ("Drums (Stem)", "#6a997c"),
        "bass": ("Bass (Stem)", "#867ca8"),
        "other": ("Other (Stem)", "#b89458"),
        "vocals": ("Vocals (Stem)", "#9e7389"),
    }
    for stem_key, (label, color) in label_colors.items():
        wav = stem_dir / f"{stem_key}.wav"
        if wav.is_file():
            stems.append({"role": stem_key, "name": label, "color": color, "wavPath": wav})
    if not stems:
        record_engine_verification("demucs-htdemucs", False, error=f"No stems produced under {stem_dir}")
        raise RuntimeError(f"Demucs completed but no stem WAVs found under {stem_dir}")
    record_engine_verification("demucs-htdemucs", True, wav_path=str(stems[0]["wavPath"]))
    return stems
