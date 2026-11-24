"""Traceable Reference Blueprint -> Composition Plan binding (Phase 03-C).

Maps ONLY explicitly selected influences from analyzed References into concrete
musical generation constraints, and honestly lists everything NOT mapped.
"""

from __future__ import annotations

from typing import Any

from engine.daw_workspace.schema import Project

from .schemas import ReferenceBinding


def build_reference_binding(
    project: Project,
    reference_ids: list[str] | None = None,
    explicit_influences: list[str] | None = None,
) -> ReferenceBinding:
    """Resolve Reference Blueprints into appliedFeatures vs unmappedFeatures."""
    refs = project.references or []
    if reference_ids:
        selected_refs = [r for r in refs if r.get("id") in set(reference_ids)]
    else:
        # Use any reference that has completed analysis
        analyzed = [r for r in refs if r.get("analysis") and r.get("blueprint")]
        selected_refs = analyzed[:1] if analyzed else []

    if not selected_refs:
        return ReferenceBinding(
            referenceIds=[],
            referenceNames=[],
            selectedInfluences=[],
            appliedFeatures={},
            unmappedFeatures=["No analyzed reference attached or selected."],
            traceabilityNote="레퍼런스 없이 프로젝트 설정과 프롬프트만으로 작곡 계획을 생성했습니다.",
        )

    primary = selected_refs[0]
    ana = primary.get("analysis") or {}
    bp = primary.get("blueprint") or {}
    influences = (
        list(explicit_influences)
        if explicit_influences is not None
        else list(primary.get("selectedInfluences") or bp.get("selectedInfluences") or ["tempo_groove", "arrangement_arc"])
    )

    applied: dict[str, Any] = {}
    unmapped: list[str] = [
        "melodic_transcription (DSP reference analysis does not transcribe individual melodies)",
        "exact_audio_timbre_cloning (copyright-safe structural inspiration only)",
        "exact_fx_plugin_parameters (EQ/Comp/Reverb settings are never reverse-engineered)",
    ]

    rhythm = ana.get("rhythm", {})
    harmony = ana.get("harmony", {})
    sound_m = ana.get("sound", {}).get("measured", {})
    sound_e = ana.get("sound", {}).get("estimated", {})
    arr_sections = ana.get("arrangement", {}).get("sections", [])

    if any(k in influences for k in ("drums_groove", "tempo_groove", "mood_energy")):
        bpm = rhythm.get("adoptedTempoBpm") or rhythm.get("estimatedBpm")
        if bpm:
            applied["tempoBpm"] = round(float(bpm), 1)
        applied["grooveFeel"] = rhythm.get("grooveFeel") or "straight"
        applied["swingRatio"] = float(rhythm.get("swingRatio") or 0.5)
        applied["percussiveRatioTarget"] = float(sound_m.get("percussiveRatio") or 0.4)
        applied["transientCharacter"] = sound_e.get("transientCharacter") or "controlled"
    else:
        unmapped.append("drums_groove (not selected by user)")

    if any(k in influences for k in ("bass_movement", "harmony_mood", "mood_energy")):
        est_key = harmony.get("estimatedKey")
        if est_key and est_key != "Uncertain":
            applied["key"] = est_key
        chords = bp.get("harmonicCharacter", {}).get("sampleChords") or []
        if chords:
            applied["referenceChords"] = chords[:8]
        bands = sound_m.get("frequencyBandsPct") or {}
        applied["lowEndSharePct"] = round(float(bands.get("sub_20_60", 0.0)) + float(bands.get("bass_60_200", 0.0)), 1)
    else:
        unmapped.append("bass_movement / harmony (not selected by user)")

    if "arrangement_arc" in influences and arr_sections:
        applied["arrangementArc"] = [
            {
                "label": s.get("label", "Section"),
                "relativeEnergy": float(s.get("relativeEnergy", 0.6)),
                "startSec": float(s.get("startSec", 0.0)),
                "endSec": float(s.get("endSec", 0.0)),
            }
            for s in arr_sections[:8]
        ]
    else:
        unmapped.append("arrangement_arc (not selected or no detected sections)")

    if any(k in influences for k in ("spatial_depth", "timbre_tone", "sound_space")):
        applied["targetIntegratedLufs"] = float(sound_m.get("integratedLufs", sound_m.get("approxLufs", -16.0)))
        applied["stereoWidthTarget"] = float(sound_m.get("stereoWidth", 0.35))
        applied["reverbCharacter"] = sound_e.get("reverbCharacter", "balanced room")
    else:
        unmapped.append("spatial_depth / timbre_tone (not selected by user)")

    if "instrumentation" in influences:
        est_elems = [
            e.get("name")
            for e in ana.get("instrumentation", {}).get("elements", [])
            if e.get("status") != "unconfirmed"
        ]
        if est_elems:
            applied["estimatedRoleFocus"] = est_elems
    else:
        unmapped.append("instrumentation (not selected by user)")

    ref_names = [str(r.get("name", "Reference")) for r in selected_refs]
    note = (
        f"레퍼런스 '{ref_names[0]}'의 선택된 요소({', '.join(influences) or '없음'})만 생성 파라미터로 반영했습니다. "
        f"원본 오디오/멜로디 복제는 수행하지 않습니다."
    )

    return ReferenceBinding(
        referenceIds=[str(r.get("id")) for r in selected_refs if r.get("id")],
        referenceNames=ref_names,
        selectedInfluences=influences,
        appliedFeatures=applied,
        unmappedFeatures=unmapped,
        traceabilityNote=note,
    )
