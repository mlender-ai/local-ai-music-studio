"""Pydantic contracts for Phase 03 Composition Plans, Reference Binding, Takes & Quality Reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.daw_workspace.schema import make_id, utc_now_iso


class CompModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ReferenceBinding(CompModel):
    referenceIds: list[str] = Field(default_factory=list)
    referenceNames: list[str] = Field(default_factory=list)
    selectedInfluences: list[str] = Field(default_factory=list)
    appliedFeatures: dict[str, Any] = Field(default_factory=dict)
    unmappedFeatures: list[str] = Field(default_factory=list)
    traceabilityNote: str = ""
    featureLifecycle: list[dict[str, Any]] = Field(default_factory=list)
    perReferenceBindings: list[dict[str, Any]] = Field(default_factory=list)


class PlannedSection(CompModel):
    name: str
    startBar: int
    endBar: int
    bars: int
    energy: float = Field(ge=0.0, le=1.0)
    activeRoles: list[str] = Field(default_factory=list)
    transitionNote: str = ""
    source: Literal["planned", "detected", "confirmed"] = "planned"


class CompositionPlan(CompModel):
    id: str = Field(default_factory=lambda: make_id("plan"))
    projectId: str
    createdAt: str = Field(default_factory=utc_now_iso)
    instruction: str
    mode: Literal["full_music", "instrument_session", "loop_midi"] = "full_music"
    musicalIdentity: dict[str, Any] = Field(default_factory=dict)
    signatureMotif: dict[str, Any] = Field(default_factory=dict)
    harmonyAndGroove: dict[str, Any] = Field(default_factory=dict)
    instrumentRoles: list[dict[str, Any]] = Field(default_factory=list)
    arrangement: list[PlannedSection] = Field(default_factory=list)
    variations: list[str] = Field(default_factory=list)
    climax: dict[str, Any] = Field(default_factory=dict)
    generationStrategy: dict[str, Any] = Field(default_factory=dict)
    referenceBinding: ReferenceBinding = Field(default_factory=ReferenceBinding)
    providerProvenance: dict[str, Any] = Field(default_factory=dict)
    summaryKo: str = ""
    summaryEn: str = ""


class QualityReport(CompModel):
    technical: dict[str, Any] = Field(default_factory=dict)
    musical: dict[str, Any] = Field(default_factory=dict)
    referenceComparison: dict[str, Any] | None = None
    vocalScreening: dict[str, Any] | None = None
    verdict: Literal["pass", "warn", "fail"] = "pass"
    warnings: list[str] = Field(default_factory=list)
    honestyNote: str = ""


class TakeProvenance(CompModel):
    engine: str
    engineLabel: str
    mode: Literal["full_music", "instrument_session", "loop_midi", "stem_separation", "midi_variation", "audio_arrangement"]
    providerId: str
    model: str
    seed: int
    planId: str | None = None
    referenceIds: list[str] = Field(default_factory=list)
    instrumentalPolicy: str = "instrumental_strict"
    generatedAt: str = Field(default_factory=utc_now_iso)


class TakeArtifact(CompModel):
    role: str
    name: str
    trackType: Literal["audio", "stem", "midi"]
    instrumentRef: str | None = None
    color: str = "#648ea8"
    audioRelativePath: str | None = None
    midiRelativePath: str | None = None
    notes: list[dict[str, Any]] = Field(default_factory=list)
    startBeats: float = 0.0
    durationBeats: float = 16.0
    gainDb: float = 0.0
    pan: float = 0.0
    mute: bool = False


class Take(CompModel):
    id: str = Field(default_factory=lambda: make_id("take"))
    projectId: str
    jobId: str
    planId: str | None = None
    title: str
    mode: Literal["full_music", "instrument_session", "loop_midi", "stem_separation", "midi_variation", "audio_arrangement"]
    status: Literal["ready", "applied", "rejected", "kept"] = "ready"
    baseRevision: int | None = None
    baseTrackFingerprints: dict[str, str] = Field(default_factory=dict)
    sourceTrackId: str | None = None
    parentSourceAssetId: str | None = None
    separationModel: str | None = None
    separationJobId: str | None = None
    previewRelativePath: str | None = None
    previewDurationSec: float = 0.0
    previewIntegratedLufs: float | None = None
    levelMatchedGainDb: float = 0.0  # gain to hit -16.0 LUFS during A/B audition
    targetTrackId: str | None = None
    targetRangeBeats: dict[str, float] | None = None
    preserveExistingTracks: bool = True
    plannedSections: list[dict[str, Any]] = Field(default_factory=list)
    detectedSections: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[TakeArtifact] = Field(default_factory=list)
    qualityReport: QualityReport = Field(default_factory=QualityReport)
    provenance: TakeProvenance
    createdAt: str = Field(default_factory=utc_now_iso)
    appliedAt: str | None = None
