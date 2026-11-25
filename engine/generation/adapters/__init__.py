"""Phase 03.1 Generation Engine Adapters backed by Shared Runtime Registry."""

from __future__ import annotations

from typing import Any

from engine.runtime import get_runtime_registry

from .acestep_adapter import probe_acestep
from .local_composer_adapter import execute_local_composition
from .stem_separator import probe_demucs, separate_stems_demucs
from .yue2_adapter import (
    build_yue2_request_from_plan,
    check_resting_voice,
    probe_yue2,
    run_yue2_generation,
    screen_vocal_leakage,
)


def detect_generation_engines() -> list[dict[str, Any]]:
    """Return honest 6-state runtime availability from the Shared Runtime Registry."""
    return list(get_runtime_registry()["engines"])


__all__ = [
    "build_yue2_request_from_plan",
    "check_resting_voice",
    "detect_generation_engines",
    "execute_local_composition",
    "probe_acestep",
    "probe_demucs",
    "probe_yue2",
    "run_yue2_generation",
    "screen_vocal_leakage",
    "separate_stems_demucs",
]
