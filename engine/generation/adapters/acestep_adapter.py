"""ACE-Step Local Adapter probe backed by Shared Runtime Registry (Phase 03.1)."""

from __future__ import annotations

from typing import Any

from engine.runtime import get_runtime_registry


def probe_acestep() -> dict[str, Any]:
    reg = get_runtime_registry()
    return next(e for e in reg["engines"] if e["id"] == "ace-step-local")
