"""Compact Producer Context builder and Provider type definitions (Phase 03-B)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from engine.daw_workspace.schema import Project


@dataclass
class ProviderInfo:
    id: str
    name: str
    kind: str  # "builtin-director" | "mcp-bridge" | "local-llm" | "cli-agent" | "external-api"
    available: bool
    connected: bool
    costModel: str  # "free-local" | "external-session" | "user-configured"
    requiresApproval: bool = False
    models: list[str] = field(default_factory=list)
    activeModel: str | None = None
    capabilities: list[str] = field(default_factory=list)
    statusNoteKo: str = ""
    statusNoteEn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProducerContext:
    project: dict[str, Any]
    tracks: list[dict[str, Any]]
    selection: dict[str, Any]
    activeReference: dict[str, Any] | None
    references: list[dict[str, Any]]
    capabilities: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_producer_context(
    project: Project,
    selection: dict[str, Any] | None = None,
    active_reference_id: str | None = None,
    capabilities_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, bounded JSON snapshot of DAW state for any AI Producer or MCP client."""
    bpb = project.timeSignature.beats_per_bar
    sel = dict(selection or {})
    tr = sel.get("timeRangeBeats") or {}
    bar_range = None
    if isinstance(tr, dict) and tr.get("startBeats") is not None and tr.get("endBeats") is not None:
        start_b = float(tr["startBeats"])
        end_b = float(tr["endBeats"])
        bar_range = {
            "startBar": int(start_b // bpb) + 1,
            "endBar": max(int(start_b // bpb) + 1, int(max(start_b, end_b - 0.001) // bpb) + 1),
            "startBeats": start_b,
            "endBeats": end_b,
        }

    tracks_summary = []
    for t in project.tracks:
        midi_note_count = sum(len(c.notes) for c in t.clips if c.type == "midi")
        tracks_summary.append(
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "instrumentRef": t.instrumentRef,
                "gainDb": t.gainDb,
                "pan": t.pan,
                "mute": t.mute,
                "solo": t.solo,
                "clipCount": len(t.clips),
                "midiNoteCount": midi_note_count,
                "clips": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": c.type,
                        "startBar": round(c.timelineStartBeats / bpb, 2) + 1.0,
                        "bars": round(c.durationBeats / bpb, 2),
                    }
                    for c in t.clips[:12]
                ],
            }
        )

    refs_compact = []
    active_ref_ctx = None
    for ref in project.references:
        ana = ref.get("analysis") or {}
        bp = ref.get("blueprint") or {}
        compact = {
            "id": ref.get("id"),
            "name": ref.get("name"),
            "audioAvailable": bool(ref.get("audioAvailable")),
            "analysisStatus": ref.get("analysisStatus"),
            "estimatedBpm": ana.get("rhythm", {}).get("adoptedTempoBpm") or ana.get("rhythm", {}).get("estimatedBpm"),
            "estimatedKey": ana.get("harmony", {}).get("estimatedKey"),
            "integratedLufs": ana.get("sound", {}).get("measured", {}).get("integratedLufs"),
            "selectedInfluences": list(ref.get("selectedInfluences") or []),
            "sectionCount": len(ana.get("arrangement", {}).get("sections", [])),
        }
        refs_compact.append(compact)
        if active_reference_id and ref.get("id") == active_reference_id:
            active_ref_ctx = {
                **compact,
                "grooveFeel": ana.get("rhythm", {}).get("grooveFeel"),
                "swingRatio": ana.get("rhythm", {}).get("swingRatio"),
                "sampleChords": bp.get("harmonicCharacter", {}).get("sampleChords", [])[:8],
                "sections": [
                    {
                        "label": s.get("label"),
                        "startBar": s.get("startBar"),
                        "endBar": s.get("endBar"),
                        "relativeEnergy": s.get("relativeEnergy"),
                    }
                    for s in ana.get("arrangement", {}).get("sections", [])[:8]
                ],
            }

    if active_ref_ctx is None and refs_compact:
        first_ref = project.references[0]
        if first_ref.get("analysis"):
            ana = first_ref["analysis"]
            bp = first_ref.get("blueprint") or {}
            active_ref_ctx = {
                **refs_compact[0],
                "grooveFeel": ana.get("rhythm", {}).get("grooveFeel"),
                "swingRatio": ana.get("rhythm", {}).get("swingRatio"),
                "sampleChords": bp.get("harmonicCharacter", {}).get("sampleChords", [])[:8],
                "sections": [
                    {
                        "label": s.get("label"),
                        "startBar": s.get("startBar"),
                        "endBar": s.get("endBar"),
                        "relativeEnergy": s.get("relativeEnergy"),
                    }
                    for s in ana.get("arrangement", {}).get("sections", [])[:8]
                ],
            }

    ctx = ProducerContext(
        project={
            "id": project.id,
            "name": project.name,
            "revision": project.revision,
            "bpm": project.bpm,
            "timeSignature": f"{project.timeSignature.numerator}/{project.timeSignature.denominator}",
            "lengthBars": round(project.lengthBeats / bpb, 1),
            "lengthBeats": project.lengthBeats,
            "sections": [
                {
                    "id": s.id,
                    "name": s.name,
                    "startBar": round(s.startBeats / bpb, 1) + 1.0,
                    "endBar": round(s.endBeats / bpb, 1) + 1.0,
                }
                for s in project.sections[:12]
            ],
        },
        tracks=tracks_summary,
        selection={
            "selectedTrackId": sel.get("selectedTrackId"),
            "selectedClipIds": list(sel.get("selectedClipIds") or []),
            "barRange": bar_range,
        },
        activeReference=active_ref_ctx,
        references=refs_compact,
        capabilities=capabilities_summary or {},
    )
    return ctx.to_dict()
