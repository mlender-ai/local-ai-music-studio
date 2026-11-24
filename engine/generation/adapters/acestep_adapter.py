"""ACE-Step Local Adapter probe (Phase 03-D). Honestly reports uninstalled weights."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from engine import paths as engine_paths


def probe_acestep() -> dict[str, Any]:
    env_dir = os.environ.get("ACESTEP_CHECKPOINT_DIR", "").strip()
    ckpt_dir = Path(env_dir).expanduser() if env_dir else (engine_paths.RUNTIME / "models" / "checkpoints")
    has_weights = ckpt_dir.is_dir() and any(
        p.suffix in (".safetensors", ".pt", ".bin", ".ckpt") for p in ckpt_dir.rglob("*") if p.is_file()
    )
    has_pkg = importlib.util.find_spec("acestep") is not None
    available = bool(has_weights and has_pkg)
    return {
        "id": "ace-step-local",
        "name": "ACE-Step Local Diffusion Generator",
        "kind": "neural-audio",
        "available": available,
        "checkpointDir": str(ckpt_dir),
        "weightsDetected": has_weights,
        "packageInstalled": has_pkg,
        "modes": ["full_music"],
        "statusNoteKo": (
            f"ACE-Step 로컬 체크포인트 및 패키지 감지됨 ({ckpt_dir})."
            if available
            else "ACE-Step 모델 체크포인트(`.runtime/models/checkpoints/`) 또는 패키지가 설치되지 않았습니다."
        ),
        "statusNoteEn": (
            f"ACE-Step checkpoints and package detected ({ckpt_dir})."
            if available
            else "ACE-Step checkpoints (`.runtime/models/checkpoints/`) or package are not installed."
        ),
    }
