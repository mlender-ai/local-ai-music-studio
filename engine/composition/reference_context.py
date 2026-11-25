"""Multi-Reference Binding, Reference Feature Lock & 5-State Feature Consumption Matrix (Phase 03.1 + 03.2).

Upgrades in Phase 03.2:
- Reads Reference Blueprint v2 (`chordTimeline`, `drumEvents`, `bassEvents`, `melodyEvents`, `arrangementMap`, `abcScore`)
- Enforces 10-feature Reference Feature Locks (`free | reference | locked | unsupported`)
- Integrates Project's own editable/locked `project.chordTrack` directly into composition constraints
- Tracks honest 5-state lifecycle (`extracted -> selected -> mapped -> consumed -> verified`) for every feature!
"""

from __future__ import annotations

from typing import Any

from engine.daw_workspace.schema import Project
from engine.transcription.pipeline import DEFAULT_FEATURE_LOCKS, validate_feature_locks_for_engine

from .schemas import ReferenceBinding


def _locks_from_legacy_influences(infs: list[str]) -> dict[str, str]:
    locks = {k: "free" for k in DEFAULT_FEATURE_LOCKS}
    if any(k in infs for k in ("drums_groove", "tempo_groove", "mood_energy")):
        locks["bpm"] = "reference"
        locks["drum_rhythm"] = "reference"
    if any(k in infs for k in ("bass_movement", "harmony_mood", "mood_energy")):
        locks["chord_progression"] = "reference"
        locks["bass_groove"] = "reference"
    if "arrangement_arc" in infs:
        locks["arrangement"] = "reference"
    if "instrumentation" in infs:
        locks["instrumentation"] = "reference"
    if "timbre_tone" in infs:
        locks["timbre"] = "reference"
    if any(k in infs for k in ("spatial_depth", "sound_space")):
        locks["spatial_character"] = "reference"
    return locks


def build_reference_binding(
    project: Project,
    reference_ids: list[str] | None = None,
    explicit_influences: list[str] | None = None,
    per_reference_influences: dict[str, list[str]] | None = None,
    feature_locks: dict[str, str] | None = None,
    target_engine: str = "local-multitrack-composer",
    reference_mode: str = "reference_compose",  # "reconstruct" | "reference_compose" | "reinterpret"
    use_project_chord_track: bool = False,
) -> ReferenceBinding:
    """Resolve one or more Reference Blueprints (v1 or v2) + Feature Locks into verifiable generation conditions."""
    refs = project.references or []

    if reference_ids is not None:
        wanted = set(reference_ids)
        selected_refs = [r for r in refs if r.get("id") in wanted and (r.get("analysis") or r.get("blueprint"))]
    else:
        selected_refs = []

    applied: dict[str, Any] = {}
    all_selected_influences: list[str] = []
    per_ref_bindings: list[dict[str, Any]] = []
    feature_lifecycle: list[dict[str, Any]] = []
    unmapped: list[str] = [
        "exact_audio_timbre_cloning (copyright-safe structural inspiration only; original audio never copied)",
        "exact_fx_plugin_parameters (EQ/Comp/Reverb plugin settings are never reverse-engineered)",
    ]

    is_midi_engine = target_engine in ("local-multitrack-composer", "midi-composer-v3", "auto", "editable_midi")

    def record_feature(
        feature_key: str,
        value: Any,
        ref_id: str,
        ref_name: str,
        influence_id: str,
        lock_state: str,
        can_consume_in_engine: bool,
        consumption_note: str,
    ) -> None:
        applied[feature_key] = value
        feature_lifecycle.append(
            {
                "feature": feature_key,
                "value": value if not isinstance(value, list) or len(value) <= 12 else f"[{len(value)} items]",
                "sourceReferenceId": ref_id,
                "sourceReferenceName": ref_name,
                "influenceId": influence_id,
                "lockState": lock_state,
                "extracted": True,
                "selected": lock_state in ("reference", "locked"),
                "mapped": True,
                "consumed": bool(can_consume_in_engine),
                "verified": False,  # Updated post-generation by real output verification!
                "note": consumption_note,
            }
        )

    # First honor Project's own locked Chord Track if present and requested/locked!
    if project.chordTrack and (project.chordTrackLocked or use_project_chord_track):
        ct_dicts = [c.model_dump() for c in project.chordTrack]
        syms = [c["symbol"] for c in ct_dicts if c.get("symbol") and c["symbol"] != "N/C"]
        if ct_dicts:
            record_feature(
                "chordTimeline",
                ct_dicts,
                "project_chord_track",
                f"{project.name} Chord Track",
                "chord_progression",
                "locked" if project.chordTrackLocked else "reference",
                True,
                "Project Chord Track directly controls harmony at every beat position.",
            )
            if syms:
                applied["referenceChords"] = syms[:16]

    if not selected_refs and not applied:
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

    merged_locks: dict[str, str] = dict(DEFAULT_FEATURE_LOCKS)
    has_transcribed_drums = False
    has_transcribed_bass = False
    has_chord_timeline = "chordTimeline" in applied

    for ref in selected_refs:
        rid = str(ref.get("id"))
        rname = str(ref.get("name", "Reference"))
        ana = ref.get("analysis") or {}
        bp = ref.get("blueprint") or {}
        tr = ref.get("transcription") or {}

        if per_reference_influences and rid in per_reference_influences:
            infs = list(per_reference_influences[rid])
        elif explicit_influences is not None:
            infs = list(explicit_influences)
        else:
            infs = list(ref.get("selectedInfluences") or bp.get("selectedInfluences") or ["drums_groove", "arrangement_arc"])

        for inf in infs:
            if inf not in all_selected_influences:
                all_selected_influences.append(inf)

        # Combine reference's saved Blueprint v2 locks + explicit caller overrides + legacy influence flags
        ref_locks = dict(ref.get("featureLocks") or bp.get("featureLocks") or _locks_from_legacy_influences(infs))
        if explicit_influences is not None and not feature_locks:
            ref_locks = _locks_from_legacy_influences(infs)
        if feature_locks:
            for lk, lv in feature_locks.items():
                ref_locks[lk] = lv
        merged_locks.update(ref_locks)

        rhythm = ana.get("rhythm", {})
        harmony = ana.get("harmony", {})
        sound_m = ana.get("sound", {}).get("measured", {})
        sound_e = ana.get("sound", {}).get("estimated", {})
        arr_sections = bp.get("arrangementMap") or ana.get("arrangement", {}).get("sections", [])
        mapped_keys_for_ref: list[str] = []

        # 1. BPM & Beat Grid
        if ref_locks.get("bpm") in ("locked", "reference") or any(k in infs for k in ("drums_groove", "tempo_groove", "mood_energy")):
            bpm = bp.get("tempoMap", {}).get("bpm") or rhythm.get("adoptedTempoBpm") or rhythm.get("estimatedBpm")
            if bpm and "tempoBpm" not in applied:
                record_feature(
                    "tempoBpm",
                    round(float(bpm), 1),
                    rid,
                    rname,
                    "bpm",
                    ref_locks.get("bpm", "reference"),
                    True,
                    "Sets composition & generation BPM directly.",
                )
                mapped_keys_for_ref.append("tempoBpm")

        # 2. Sub-bar Chord Timeline (Phase 03.2 real Chord Track!)
        chord_tl = bp.get("chordTimeline") or tr.get("chordTimeline") or []
        if chord_tl:
            has_chord_timeline = True
        if (
            ref_locks.get("chord_progression") in ("locked", "reference")
            or any(k in infs for k in ("bass_movement", "harmony_mood", "mood_energy"))
        ):
            est_key = harmony.get("estimatedKey")
            if est_key and est_key != "Uncertain" and "key" not in applied:
                record_feature(
                    "key",
                    est_key,
                    rid,
                    rname,
                    "chord_progression",
                    ref_locks.get("chord_progression", "reference"),
                    True,
                    "Sets composition key & scale.",
                )
                mapped_keys_for_ref.append("key")
            if chord_tl and "chordTimeline" not in applied:
                record_feature(
                    "chordTimeline",
                    chord_tl,
                    rid,
                    rname,
                    "chord_progression",
                    ref_locks.get("chord_progression", "locked"),
                    True,
                    "Exact beat-aligned Chord Timeline consumed directly by Bass/Keys/Hook/ABC generators.",
                )
                mapped_keys_for_ref.append("chordTimeline")
            chords = [c.get("symbol") for c in chord_tl if c.get("symbol") and c["symbol"] != "N/C"] or [
                c for c in (bp.get("harmonicCharacter", {}).get("sampleChords") or []) if c and c not in ("N/C", "uncertain")
            ]
            if chords and "referenceChords" not in applied:
                record_feature(
                    "referenceChords",
                    chords[:16],
                    rid,
                    rname,
                    "chord_progression",
                    ref_locks.get("chord_progression", "reference"),
                    True,
                    "Chord progression symbols fed into composer & ABC generator.",
                )
                mapped_keys_for_ref.append("referenceChords")

        # 3. Real Drum Rhythm & Microtiming Groove Transfer (TEST C!)
        drum_ev = bp.get("drumEvents") or tr.get("drums") or {}
        drum_template = drum_ev.get("patternTemplate2Bar") or drum_ev.get("quantizedNotes") or drum_ev.get("quantizedMidiNotes") or []
        if drum_template:
            has_transcribed_drums = True
        if ref_locks.get("drum_rhythm") in ("locked", "reference") or "drums_groove" in infs:
            groove_prof = bp.get("grooveProfile") or {}
            if "grooveFeel" not in applied:
                record_feature(
                    "grooveFeel",
                    groove_prof.get("feel") or rhythm.get("grooveFeel") or "straight",
                    rid,
                    rname,
                    "drum_rhythm",
                    ref_locks.get("drum_rhythm", "reference"),
                    True,
                    "Selects drum & bass groove feel.",
                )
                mapped_keys_for_ref.append("grooveFeel")
            if "swingRatio" not in applied:
                record_feature(
                    "swingRatio",
                    float(groove_prof.get("swingRatio") or rhythm.get("swingRatio") or 0.5),
                    rid,
                    rname,
                    "drum_rhythm",
                    ref_locks.get("drum_rhythm", "reference"),
                    True,
                    "Controls offbeat timing ratio measured from reference audio.",
                )
                mapped_keys_for_ref.append("swingRatio")
            if drum_template and "drumGroovePattern" not in applied:
                record_feature(
                    "drumGroovePattern",
                    {
                        "lockMode": ref_locks.get("drum_rhythm", "reference"),
                        "sourceKind": drum_ev.get("sourceKind", "transcribed"),
                        "template2Bar": (drum_ev.get("patternTemplate2Bar") or [])[:120],
                        "accentGrid16": groove_prof.get("accentGrid16", []),
                        "meanMicrotimingMs": groove_prof.get("meanMicrotimingMs", 0.0),
                        "fillBars": drum_ev.get("fillBars", []),
                    },
                    rid,
                    rname,
                    "drum_rhythm",
                    ref_locks.get("drum_rhythm", "reference"),
                    is_midi_engine,
                    "Extracted Kick/Snare/Hat/Accent groove pattern directly drives MIDI Drum generation."
                    if is_midi_engine
                    else "Mapped as groove guide; neural audio cannot lock exact hit timestamps.",
                )
                mapped_keys_for_ref.append("drumGroovePattern")
            if "transientCharacter" not in applied:
                record_feature(
                    "transientCharacter",
                    sound_e.get("transientCharacter") or "controlled",
                    rid,
                    rname,
                    "drum_rhythm",
                    ref_locks.get("drum_rhythm", "reference"),
                    not is_midi_engine,
                    "Prompted into neural style text; not directly synthesized by MIDI velocity alone."
                    if is_midi_engine
                    else "Passed to neural audio prompt.",
                )
                mapped_keys_for_ref.append("transientCharacter")

        # 4. Real Bass Groove Pattern (Basic Pitch transcribed!)
        bass_ev = bp.get("bassEvents") or tr.get("bass") or {}
        bass_notes = bass_ev.get("notes") or []
        if bass_notes:
            has_transcribed_bass = True
        if (ref_locks.get("bass_groove") in ("locked", "reference") or "bass_movement" in infs) and bass_notes and "bassGroovePattern" not in applied:
            record_feature(
                "bassGroovePattern",
                {
                    "lockMode": ref_locks.get("bass_groove", "reference"),
                    "notes": bass_notes[:120],
                    "pitchMin": bass_ev.get("pitchMin"),
                    "pitchMax": bass_ev.get("pitchMax"),
                },
                rid,
                rname,
                "bass_groove",
                ref_locks.get("bass_groove", "reference"),
                is_midi_engine,
                "Extracted Basic Pitch bass rhythm & articulation mapped onto active Chord Track roots."
                if is_midi_engine
                else "Mapped for neural prompt guidance.",
            )
            mapped_keys_for_ref.append("bassGroovePattern")

        # 5. Melody Lock (ONLY used when user explicitly locks melody / reconstruct mode; default Reference Compose keeps melody FREE!)
        mel_ev = bp.get("melodyEvents") or tr.get("melody") or {}
        if ref_locks.get("melody") == "locked" and reference_mode == "reconstruct" and mel_ev.get("notes") and "melodyEvents" not in applied:
            record_feature(
                "melodyEvents",
                mel_ev["notes"][:160],
                rid,
                rname,
                "melody",
                "locked",
                True,
                "Authorized Reconstruct mode: preserves transcribed melody events.",
            )
            mapped_keys_for_ref.append("melodyEvents")

        # 6. Arrangement Structure Map
        if (ref_locks.get("arrangement") in ("locked", "reference") or "arrangement_arc" in infs) and arr_sections and "arrangementArc" not in applied:
            arc = [
                {
                    "label": s.get("label", "Section"),
                    "relativeEnergy": float(s.get("relativeEnergy", 0.6)),
                    "startSec": float(s.get("startSec", 0.0)),
                    "endSec": float(s.get("endSec", 0.0)),
                    "activeStems": s.get("activeStems", []),
                }
                for s in arr_sections[:8]
            ]
            record_feature(
                "arrangementArc",
                arc,
                rid,
                rname,
                "arrangement",
                ref_locks.get("arrangement", "reference"),
                True,
                "Shapes planned sections, energy arc & active instrument layers.",
            )
            mapped_keys_for_ref.append("arrangementArc")

        # 7. Instrumentation
        if (ref_locks.get("instrumentation") in ("locked", "reference") or "instrumentation" in infs) and "estimatedRoleFocus" not in applied:
            est_elems = [
                e.get("name") or e.get("role")
                for e in (bp.get("instrumentEstimates") or ana.get("instrumentation", {}).get("elements", []))
                if e.get("status") not in ("unconfirmed", "silent_in_stem")
            ]
            if est_elems:
                record_feature(
                    "estimatedRoleFocus",
                    est_elems,
                    rid,
                    rname,
                    "instrumentation",
                    ref_locks.get("instrumentation", "reference"),
                    True,
                    "Guides active ensemble instrument roles.",
                )
                mapped_keys_for_ref.append("estimatedRoleFocus")

        # 8. Timbre & Spatial Character (HONEST: MIDI cannot clone exact stereo width/timbre -> consumed=False!)
        if ref_locks.get("spatial_character") in ("locked", "reference") or any(k in infs for k in ("spatial_depth", "sound_space")):
            if "stereoWidthTarget" not in applied:
                record_feature(
                    "stereoWidthTarget",
                    float(sound_m.get("stereoWidth", 0.35)),
                    rid,
                    rname,
                    "spatial_character",
                    ref_locks.get("spatial_character", "reference"),
                    False,
                    "Measured & mapped for post-generation comparison only (MIDI synth cannot target exact stereo width).",
                )
                mapped_keys_for_ref.append("stereoWidthTarget")
        if ref_locks.get("timbre") in ("locked", "reference") or "timbre_tone" in infs:
            if "spectralCentroidTargetHz" not in applied:
                record_feature(
                    "spectralCentroidTargetHz",
                    float(sound_m.get("spectralCentroidHz", 1400.0)),
                    rid,
                    rname,
                    "timbre",
                    ref_locks.get("timbre", "reference"),
                    not is_midi_engine,
                    "Tracked for comparison; MIDI synth voices do not clone source timbre."
                    if is_midi_engine
                    else "Mapped into neural timbre style description.",
                )
                mapped_keys_for_ref.append("spectralCentroidTargetHz")
            if "targetIntegratedLufs" not in applied:
                record_feature(
                    "targetIntegratedLufs",
                    float(sound_m.get("integratedLufs", sound_m.get("approxLufs", -16.0))),
                    rid,
                    rname,
                    "timbre",
                    "reference",
                    False,
                    "Reference target for level-matched audition & comparison.",
                )
                mapped_keys_for_ref.append("targetIntegratedLufs")

        # 9. Official YuE2 ABC Score from Blueprint v2
        if bp.get("abcScore") and "abcScore" not in applied:
            applied["abcScore"] = bp["abcScore"]

        per_ref_bindings.append(
            {
                "referenceId": rid,
                "referenceName": rname,
                "selectedInfluences": infs,
                "featureLocks": ref_locks,
                "mappedFeatureKeys": mapped_keys_for_ref,
            }
        )

    lock_report = validate_feature_locks_for_engine(
        merged_locks,
        engine_id=target_engine,
        has_transcribed_drums=has_transcribed_drums,
        has_transcribed_bass=has_transcribed_bass,
        has_chord_timeline=has_chord_timeline,
    )
    applied["featureLocks"] = lock_report["effectiveLocks"]
    applied["featureLockReport"] = lock_report
    applied["referenceMode"] = reference_mode

    ref_names = [b["referenceName"] for b in per_ref_bindings]
    consumed_keys = [f["feature"] for f in feature_lifecycle if f["consumed"]]
    note = (
        f"[{reference_mode}] 레퍼런스 {len(per_ref_bindings)}개({', '.join(ref_names) or 'Chord Track'}) 반영. "
        f"실제 생성 소비(Consumed): {', '.join(consumed_keys) or '없음'}."
    )
    if lock_report["warningsKo"]:
        note += " 한계 안내: " + " ".join(lock_report["warningsKo"][:2])

    return ReferenceBinding(
        referenceIds=[b["referenceId"] for b in per_ref_bindings],
        referenceNames=ref_names,
        selectedInfluences=all_selected_influences,
        appliedFeatures=applied,
        unmappedFeatures=unmapped + lock_report["warningsEn"],
        traceabilityNote=note,
        featureLifecycle=feature_lifecycle,
        perReferenceBindings=per_ref_bindings,
    )
