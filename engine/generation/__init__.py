"""Phase 03-D/E/F Generation Engine Adapters and Background Job Manager."""

from .adapters import detect_generation_engines
from .daw_jobs import (
    apply_take,
    generation_jobs,
    get_composition_plan,
    get_take,
    list_takes,
    reject_take,
    resolve_take_preview_audio,
    save_composition_plan,
)

__all__ = [
    "apply_take",
    "detect_generation_engines",
    "generation_jobs",
    "get_composition_plan",
    "get_take",
    "list_takes",
    "reject_take",
    "resolve_take_preview_audio",
    "save_composition_plan",
]
