"""Project paths and strict file access boundary."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = (
    Path(os.environ.get("MUSIC_DATA_DIR", str(ROOT / "outputs"))).expanduser().resolve()
)
RUNTIME = ROOT / ".runtime"


def initialize():
    for folder in ["originals", "processed", "exports", "imports"]:
        (DATA / folder).mkdir(parents=True, exist_ok=True)
    (RUNTIME / "logs").mkdir(parents=True, exist_ok=True)


def audio_path(value: str | Path, must_exist=True) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = DATA / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(DATA) or candidate.suffix.lower() != ".wav":
        raise ValueError(
            "Only WAV files inside the configured outputs directory are allowed."
        )
    if must_exist and not candidate.is_file():
        raise ValueError("Audio file does not exist.")
    return candidate
