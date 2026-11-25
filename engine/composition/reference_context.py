"""Multi-Reference Binding & 5-State Feature Consumption Matrix (Phase 03.1 · Section 5).

Key Phase 03.1 upgrades:
- Supports MULTIPLE references independently (e.g., Ref A -> drums_groove, Ref B -> arrangement_arc,
  Ref C -> bass_movement), tracking exact per-feature source reference ID & name.
- NEVER auto-attaches an unselected reference when `reference_ids == []` (explicit opt-in!).
- Tracks honest 5-state lifecycle for every musical feature:
  `extracted` -> `selected` -> `mapped` -> `consumed` -> `verified`.
  (e.g., if `stereoWidthTarget` was analyzed & selected, but MIDI synth cannot directly target
  an exact stereo-width number, it stays `mapped` and is NEVER falsely marked `consumed`!)
"""

from __future__ import annotations

from typing import Any

from engine.daw_workspace.schema import Project

from .schemas import ReferenceBinding


def build_reference_binding(
    project: Project,
    reference_ids: list[str] | None = None,
    explicit_influences: list[str] | None = None,
    per_reference_influences: dict[str, list[str]] | None = None,
    target_engine: str = "local-multitrack-composer",
) -> ReferenceBinding:
    """Resolve one or more Reference Blueprints into traceable multi-reference features."""
    refs = project.references or []

    # Strictly honor explicit empty selection (`reference_ids=[]` means NO reference!)
    if reference_ids is not None:
        wanted = set(reference_ids)
        selected_refs = [r for r in refs if r.get("id") in wanted and r.get("analysis")]
    else:
        # Only use references if caller omitted reference_ids AND user explicitly left influences enabled
        selected_refs = []

    if not selected_refs:
        return ReferenceBinding(
            referenceIds=[],
            referenceNames=[],
            selectedInfluences=[],
            appliedFeatures={},
            unmappedFeatures=["No reference selected by user (references are never auto-attached without selection)."],
            traceabilityNote="선택된 레퍼런스가 없어 프로젝트 설정과 프롬프트만으로 작곡 계획을 생성했습니다.",
            featureLifecycle=[],
            perReferenceBindings=[],
        )

    applied: dict[str, Any] = {}
    all_selected_influences: list[str] = []
    per_ref_bindings: list[dict[str, Any]] = []
    feature_lifecycle: list[dict[str, Any]] = []
    unmapped: list[str] = [
        "melodic_transcription (DSP reference analysis does not transcribe individual melodies)",
        "exact_audio_timbre_cloning (copyright-safe structural inspiration only)",
        "exact_fx_plugin_parameters (EQ/Comp/Reverb settings are never reverse-engineered)",
    ]

    is_midi_engine = target_engine in ("local-multitrack-composer", "midi-composer-v3", "auto")

    def record_feature(
        feature_key: str,
        value: Any,
        ref_id: str,
        ref_name: str,
        influence_id: str,
        can_consume_in_engine: bool,
        consumption_note: str,
    ) -> None:
        applied[feature_key] = value
        feature_lifecycle.append(
            {
                "feature": feature_key,
                "value": value,
                "sourceReferenceId": ref_id,
                "sourceReferenceName": ref_name,
                "influenceId": influence_id,
                "extracted": True,
                "selected": True,
                "mapped": True,
                "consumed": bool(can_consume_in_engine),
                "verified": False,  # Updated after generation comparison!
                "note": consumption_note,
            }
        )

    for ref in selected_refs:
        rid = str(ref.get("id"))
        rname = str(ref.get("name", "Reference"))
        ana = ref.get("analysis") or {}
        bp = ref.get("blueprint") or {}

        if per_reference_influences and rid in per_reference_influences:
            infs = list(per_reference_influences[rid])
        elif explicit_influences is not None:
            infs = list(explicit_influences)
        else:
            infs = list(ref.get("selectedInfluences") or bp.get("selectedInfluences") or ["drums_groove", "arrangement_arc"])

        for inf in infs:
            if inf not in all_selected_influences:
                all_selected_influences.append(inf)

        rhythm = ana.get("rhythm", {})
        harmony = ana.get("harmony", {})
        sound_m = ana.get("sound", {}).get("measured", {})
        sound_e = ana.get("sound", {}).get("estimated", {})
        arr_sections = ana.get("arrangement", {}).get("sections", [])
        mapped_keys_for_ref: list[str] = []

        if any(k in infs for k in ("drums_groove", "tempo_groove", "mood_energy")):
            bpm = rhythm.get("adoptedTempoBpm") or rhythm.get("estimatedBpm")
            if bpm and "tempoBpm" not in applied:
                record_feature("tempoBpm", round(float(bpm), 1), rid, rname, "drums_groove", True, "Sets project/generation BPM directly.")
                mapped_keys_for_ref.append("tempoBpm")
            if "grooveFeel" not in applied:
                record_feature("grooveFeel", rhythm.get("grooveFeel") or "straight", rid, rname, "drums_groove", True, "Selects drum/bass groove feel.")
                mapped_keys_for_ref.append("grooveFeel")
            if "swingRatio" not in applied:
                record_feature("swingRatio", float(rhythm.get("swingRatio") or 0.5), rid, rname, "drums_groove", True, "Controls offbeat 16th/8th swing timing.")
                mapped_keys_for_ref.append("swingRatio")
            if "transientCharacter" not in applied:
                record_feature(
                    "transientCharacter",
                    sound_e.get("transientCharacter") or "controlled",
                    rid,
                    rname,
                    "drums_groove",
                    not is_midi_engine,
                    "Prompted into neural style text; not directly synthesized by MIDI velocity alone." if is_midi_engine else "Passed to neural audio prompt.",
                )
                mapped_keys_for_ref.append("transientCharacter")

        if any(k in infs for k in ("bass_movement", "harmony_mood", "mood_energy")):
            est_key = harmony.get("estimatedKey")
            if est_key and est_key != "Uncertain" and "key" not in applied:
                record_feature("key", est_key, rid, rname, "bass_movement", True, "Sets composition key & scale.")
                mapped_keys_for_ref.append("key")
            chords = [c for c in (bp.get("harmonicCharacter", {}).get("sampleChords") or []) if c and c not in ("N/C", "uncertain")]
            if chords and "referenceChords" not in applied:
                record_feature("referenceChords", chords[:8], rid, rname, "bass_movement", True, "Feeds chord progression into bass/keys/hook composer.")
                mapped_keys_for_ref.append("referenceChords")

        if "arrangement_arc" in infs and arr_sections and "arrangementArc" not in applied:
            arc = [
                {
                    "label": s.get("label", "Section"),
                    "relativeEnergy": float(s.get("relativeEnergy", 0.6)),
                    "startSec": float(s.get("startSec", 0.0)),
                    "endSec": float(s.get("endSec", 0.0)),
                }
                for s in arr_sections[:8]
            ]
            record_feature("arrangementArc", arc, rid, rname, "arrangement_arc", True, "Shapes planned section count & energy trajectory.")
            mapped_keys_for_ref.append("arrangementArc")

        if any(k in infs for k in ("spatial_depth", "timbre_tone", "sound_space")):
            if "stereoWidthTarget" not in applied:
                record_feature(
                    "stereoWidthTarget",
                    float(sound_m.get("stereoWidth", 0.35)),
                    rid,
                    rname,
                    "spatial_depth",
                    False,  # Honest: neither MIDI composer nor YuE2 takes an exact numeric stereo width control!
                    "Measured & mapped for post-generation comparison only (engine cannot directly target exact stereo width).",
                )
                mapped_keys_for_ref.append("stereoWidthTarget")
            if "targetIntegratedLufs" not in applied:
                record_feature(
                    "targetIntegratedLufs",
                    float(sound_m.get("integratedLufs", sound_m.get("approxLufs", -16.0))),
                    rid,
                    rname,
                    "sound_space",
                    False,
                    "Used as reference target during post-generation comparison & level-matched preview.",
                )
                mapped_keys_for_ref.append("targetIntegratedLufs")

        if "instrumentation" in infs and "estimatedRoleFocus" not in applied:
            est_elems = [
                e.get("name")
                for e in ana.get("instrumentation", {}).get("elements", [])
                if e.get("status") != "unconfirmed"
            ]
            if est_elems:
                record_feature("estimatedRoleFocus", est_elems, rid, rname, "instrumentation", True, "Guides active instrument role selection.")
                mapped_keys_for_ref.append("estimatedRoleFocus")

        per_ref_bindings.append(
            {
                "referenceId": rid,
                "referenceName": rname,
                "selectedInfluences": infs,
                "mappedFeatureKeys": mapped_keys_for_ref,
            }
        )

    ref_names = [b["referenceName"] for b in per_ref_bindings]
    consumed_keys = [f["feature"] for f in feature_lifecycle if f["consumed"]]
    note = (
        f"레퍼런스 {len(per_ref_bindings)}개({', '.join(ref_names)})에서 선택된 요소만 매핑했습니다. "
        f"실제 생성 소비(Consumed): {', '.join(consumed_keys) or '없음'}. 원본 멜로디/오디오 복제는 수행하지 않습니다."
    )

    return ReferenceBinding(
        referenceIds=[b["referenceId"] for b in per_ref_bindings],
        referenceNames=ref_names,
        selectedInfluences=all_selected_influences,
        appliedFeatures=applied,
        unmappedFeatures=unmapped,
        traceabilityNote=note,
        featureLifecycle=feature_lifecycle,
        perReferenceBindings=per_ref_bindings,
    )
