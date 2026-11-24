"""Phase 05 REAPER Bridge availability probe (no concurrent playback in Phase 01)."""

from __future__ import annotations

import os
from pathlib import Path

from engine.paths import RUNTIME


def detect_reaper() -> dict[str, object]:
    for candidate in (
        RUNTIME / "REAPER.app",
        Path("/Applications/REAPER.app"),
        Path.home() / "Applications/REAPER.app",
    ):
        binary = candidate / "Contents/MacOS/REAPER"
        if binary.is_file() and os.access(binary, os.X_OK):
            return {
                "available": True,
                "mode": "offline-host-adapter-reserved",
                "note": "REAPER detected; host rendering is reserved for Phase 05 to avoid double playback.",
            }
    return {
        "available": False,
        "mode": "web-audio-phase-01",
        "note": "REAPER.app not installed; Phase 01 uses Web Audio realtime preview + offline WAV render.",
    }
