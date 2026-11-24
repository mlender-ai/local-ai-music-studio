"""Real Demucs Stem Separation Adapter (Phase 03-E).

Honestly reports unavailable when `demucs` is not installed; NEVER fakes separated stems.
When installed, separates into Drums, Bass, Other, Vocals and preserves Original Mix muted.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any


def probe_demucs() -> dict[str, Any]:
    cli = shutil.which("demucs")
    pkg = importlib.util.find_spec("demucs") is not None
    available = bool(cli or pkg)
    return {
        "id": "demucs-htdemucs",
        "name": "Demucs Stem Separation (htdemucs)",
        "kind": "stem-separation",
        "available": available,
        "cliPath": cli,
        "modes": ["stem_separation"],
        "stems": ["drums", "bass", "other", "vocals"],
        "statusNoteKo": (
            "Demucs 스템 분리 엔진이 설치되어 있습니다 (Drums/Bass/Other/Vocals 분리 가능)."
            if available
            else "Demucs가 설치되어 있지 않아 실제 스템 분리를 실행할 수 없습니다 (가짜 스템을 생성하지 않습니다. 설치: `uv pip install demucs`)."
        ),
        "statusNoteEn": (
            "Demucs stem separation is installed (Drums/Bass/Other/Vocals)."
            if available
            else "Demucs is not installed on this host (never fabricates fake stems; install via `uv pip install demucs`)."
        ),
    }


def separate_stems_demucs(
    audio_path: Path,
    out_dir: Path,
    model_name: str = "htdemucs",
    timeout_sec: int = 300,
) -> list[dict[str, Any]]:
    """Run real Demucs separation on `audio_path`; raises honestly if Demucs is missing."""
    info = probe_demucs()
    if not info["available"]:
        raise RuntimeError(
            "Demucs is not installed on this machine. Real stem separation cannot run without Demucs."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = (
        [info["cliPath"], "-n", model_name, "-o", str(out_dir), str(audio_path)]
        if info["cliPath"]
        else ["python", "-m", "demucs", "-n", model_name, "-o", str(out_dir), str(audio_path)]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Demucs failed (code {proc.returncode}): {proc.stderr[-300:]}")

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
        raise RuntimeError(f"Demucs completed but no stem WAVs found under {stem_dir}")
    return stems
