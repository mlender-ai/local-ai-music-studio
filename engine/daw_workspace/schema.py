"""Versioned project data model for AI-Native DAW (schema v1.0.0).

All time and gain fields explicitly encode their unit in the field name:
- Beats: quarter-note musical beats (0.0 = Bar 1, Beat 1)
- Sec: wall-clock seconds
- Samples: integer frames at sampleRate
- Db: decibels relative to unity gain (0.0 dB = 1.0 linear)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.4.0"
DEFAULT_PPQ = 480
DEFAULT_SAMPLE_RATE = 48000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class DawModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TimeSignature(DawModel):
    numerator: int = Field(default=4, ge=1, le=16)
    denominator: Literal[2, 4, 8, 16] = 4

    @property
    def beats_per_bar(self) -> float:
        return self.numerator * (4.0 / self.denominator)


class LoopRegion(DawModel):
    enabled: bool = False
    startBeats: float = Field(default=0.0, ge=0.0)
    endBeats: float = Field(default=16.0, gt=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "LoopRegion":
        if self.endBeats <= self.startBeats:
            raise ValueError("loopRegion.endBeats must be greater than startBeats")
        return self


class SectionMarker(DawModel):
    id: str = Field(default_factory=lambda: make_id("sec"))
    name: str = Field(min_length=1, max_length=64)
    startBeats: float = Field(ge=0.0)
    endBeats: float = Field(gt=0.0)
    color: str = "#4e5663"

    @model_validator(mode="after")
    def validate_bounds(self) -> "SectionMarker":
        if self.endBeats <= self.startBeats:
            raise ValueError("Section endBeats must be greater than startBeats")
        return self


class ChordEvent(DawModel):
    """Editable sub-bar Chord Track event (Phase 03.2 · Section 5)."""

    id: str = Field(default_factory=lambda: make_id("chd"))
    symbol: str = Field(min_length=1, max_length=32)
    root: str = Field(default="C", max_length=8)
    quality: str = Field(default="major", max_length=24)
    extension: str | None = Field(default=None, max_length=16)
    bassNote: str | None = Field(default=None, max_length=8)
    startBeat: float = Field(ge=0.0)
    endBeat: float = Field(gt=0.0)
    sourceReferenceId: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    isEstimate: bool = False
    isPassing: bool = False
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    userCorrected: bool = False
    locked: bool = False

    @model_validator(mode="after")
    def validate_bounds(self) -> "ChordEvent":
        if self.endBeat <= self.startBeat:
            raise ValueError("ChordEvent endBeat must be greater than startBeat")
        return self


class MidiNote(DawModel):
    id: str = Field(default_factory=lambda: make_id("note"))
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(default=100, ge=1, le=127)
    startBeat: float = Field(ge=0.0)
    durationBeats: float = Field(gt=0.0, le=512.0)


class Clip(DawModel):
    id: str = Field(default_factory=lambda: make_id("clp"))
    name: str = Field(min_length=1, max_length=120)
    type: Literal["audio", "midi"]
    assetId: str | None = None
    timelineStartBeats: float = Field(ge=0.0)
    durationBeats: float = Field(gt=0.0, le=4096.0)
    sourceOffsetSec: float = Field(default=0.0, ge=0.0)
    sourceDurationSec: float = Field(default=0.0, ge=0.0)
    loop: bool = False
    loopLengthSec: float | None = Field(default=None, gt=0.0)
    loopLengthBeats: float | None = Field(default=None, gt=0.0)
    gainDb: float = Field(default=0.0, ge=-24.0, le=12.0)
    fadeInBeats: float = Field(default=0.0, ge=0.0, le=64.0)
    fadeOutBeats: float = Field(default=0.0, ge=0.0, le=64.0)
    reversed: bool = False
    notes: list[MidiNote] = Field(default_factory=list)


class Track(DawModel):
    id: str = Field(default_factory=lambda: make_id("trk"))
    name: str = Field(min_length=1, max_length=80)
    type: Literal["audio", "stem", "midi"]
    color: str = "#6a997c"
    gainDb: float = Field(default=0.0, ge=-60.0, le=6.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    mute: bool = False
    solo: bool = False
    stemLabel: str | None = None
    stemMeta: dict[str, Any] | None = None
    instrumentRef: str | None = None
    effects: list[dict[str, Any]] = Field(default_factory=list)
    takeLanes: list[dict[str, Any]] = Field(default_factory=list)
    clips: list[Clip] = Field(default_factory=list)


class Asset(DawModel):
    id: str = Field(default_factory=lambda: make_id("ast"))
    name: str = Field(min_length=1, max_length=160)
    kind: Literal["audio", "midi", "reference"]
    relativePath: str = Field(min_length=1)
    source: str = "imported"
    provenance: str = ""
    sha256: str = Field(min_length=8)
    sampleRate: int = Field(default=0, ge=0)
    channels: int = Field(default=0, ge=0)
    durationSec: float = Field(default=0.0, ge=0.0)
    durationSamples: int = Field(default=0, ge=0)
    durationBeats: float | None = Field(default=None, ge=0.0)
    mimeType: str = "audio/wav"


class Project(DawModel):
    id: str = Field(default_factory=lambda: make_id("proj"))
    schemaVersion: str = SCHEMA_VERSION
    revision: int = Field(default=1, ge=1)
    name: str = Field(default="Untitled 01", min_length=1, max_length=120)
    bpm: float = Field(default=128.0, ge=30.0, le=300.0)
    timeSignature: TimeSignature = Field(default_factory=TimeSignature)
    ppq: int = Field(default=DEFAULT_PPQ, ge=96, le=960)
    sampleRate: int = Field(default=DEFAULT_SAMPLE_RATE, ge=22050, le=192000)
    lengthBeats: float = Field(default=64.0, ge=4.0, le=4096.0)
    masterGainDb: float = Field(default=0.0, ge=-60.0, le=6.0)
    loopRegion: LoopRegion = Field(
        default_factory=lambda: LoopRegion(enabled=False, startBeats=0.0, endBeats=16.0)
    )
    sections: list[SectionMarker] = Field(default_factory=list)
    chordTrack: list[ChordEvent] = Field(default_factory=list)
    chordTrackLocked: bool = False
    assets: list[Asset] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    compositionPlans: list[dict[str, Any]] = Field(default_factory=list)
    takes: list[dict[str, Any]] = Field(default_factory=list)
    musicMemory: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    createdAt: str = Field(default_factory=utc_now_iso)
    updatedAt: str = Field(default_factory=utc_now_iso)


class ProjectSummary(DawModel):
    id: str
    name: str
    revision: int = 1
    bpm: float
    timeSignature: TimeSignature
    trackCount: int
    assetCount: int
    lengthBeats: float
    updatedAt: str
    createdAt: str
    hasAutosave: bool = False


class CommandRequest(DawModel):
    type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    expectedRevision: int | None = Field(default=None, ge=1)
