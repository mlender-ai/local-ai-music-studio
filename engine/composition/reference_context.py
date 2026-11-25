"""Multi-Reference Independent Feature Binding, Conflict Detection & 5-State Feature Consumption Matrix (Phase 03.2.1).

Upgrades in Phase 03.2.1:
- Reads Reference Blueprint v3 (`drumPerformance`, `bassPerformance`, `chordTimeline`, `soundProfiles`, `spatialProfile`, `variationMap`)
- Supports **Multi-Reference Independent Feature Binding** via `feature_source_map` (e.g., Ref A -> BPM + Drums, Ref B -> Chords, Ref C -> Sound Profile, Ref D -> Arrangement)
- Performs explicit pre-generation **Conflict Detection** across multiple bound references (BPM mismatch, meter mismatch, key/chord clash)
- Preserves FULL bar-by-bar `drumPerformance` & `bassPerformance` (NEVER truncating locked performances to 2 bars!)
- Supports granular `bass_lock_mode` (`rhythm_and_duration | rhythm_only | pitch_only | full`)
- Strict Lock Honesty: NEVER silently downgrades unsupported `locked` features to `reference`!
"""

from __future__ import annotations

from typing import Any

from engine.daw_workspace.analysis import resolve_octave_tempo_relation
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


def detect_multi_reference_conflicts(
    selected_refs: list[dict[str, Any]],
    feature_source_map: dict[str, str],
    project: Project,
    use_project_chord_track: bool = False,
) -> list[dict[str, Any]]:
    """Detect real musical conflicts across bound references (BPM, Meter, Key/Chord Track) before generation."""
    conflicts: list[dict[str, Any]] = []
    if len(selected_refs) < 2 and not (selected_refs and project.chordTrack and (project.chordTrackLocked or use_project_chord_track)):
        return conflicts

    ref_by_id = {str(r.get("id")): r for r in selected_refs}

    def _ref_bpm(r: dict[str, Any]) -> float | None:
        bp = r.get("blueprint") or {}
        ana = r.get("analysis") or {}
        v = bp.get("tempoMap", {}).get("bpm") or ana.get("rhythm", {}).get("adoptedTempoBpm") or ana.get("rhythm", {}).get("estimatedBpm")
        return float(v) if v else None

    def _ref_meter(r: dict[str, Any]) -> str:
        bp = r.get("blueprint") or {}
        ana = r.get("analysis") or {}
        return str(bp.get("tempoMap", {}).get("meter") or ana.get("rhythm", {}).get("meterEstimate") or "4/4")

    def _ref_key(r: dict[str, Any]) -> str | None:
        bp = r.get("blueprint") or {}
        ana = r.get("analysis") or {}
        k = bp.get("harmonicCharacter", {}).get("key") or ana.get("harmony", {}).get("estimatedKey")
        return str(k) if k and k != "Uncertain" else None

    # 1. Check BPM compatibility between BPM source & Drum/Chord/Arrangement sources
    bpm_src_id = feature_source_map.get("bpm") or (str(selected_refs[0].get("id")) if selected_refs else None)
    bpm_ref = ref_by_id.get(bpm_src_id) if bpm_src_id else None
    base_bpm = _ref_bpm(bpm_ref) if bpm_ref else None
    if base_bpm:
        for r in selected_refs:
            rid = str(r.get("id"))
            if rid == bpm_src_id:
                continue
            other_bpm = _ref_bpm(r)
            if other_bpm:
                rel = resolve_octave_tempo_relation(base_bpm, other_bpm)
                if rel["compatible"] is False and abs(other_bpm - base_bpm) > 4.0:
                    conflicts.append(
                        {
                            "type": "bpm_mismatch",
                            "severity": "warning",
                            "referenceIds": [bpm_src_id, rid],
                            "messageKo": (
                                f"템포 충돌 감지: '{bpm_ref.get('name')}'({base_bpm:.1f} BPM)와 "
                                f"'{r.get('name')}'({other_bpm:.1f} BPM)의 템포가 다릅니다. "
                                f"'{bpm_ref.get('name')}'의 BPM({base_bpm:.1f})을 기준으로 시간 정렬합니다."
                            ),
                            "messageEn": (
                                f"Tempo mismatch: '{bpm_ref.get('name')}' ({base_bpm:.1f} BPM) vs "
                                f"'{r.get('name')}' ({other_bpm:.1f} BPM). Adopting {base_bpm:.1f} BPM as timeline grid."
                            ),
                        }
                    )

    # 2. Check Meter mismatch across bound references
    meters = {(str(r.get("id")), str(r.get("name")), _ref_meter(r)) for r in selected_refs}
    unique_meters = {m[2] for m in meters}
    if len(unique_meters) > 1:
        conflicts.append(
            {
                "type": "meter_mismatch",
                "severity": "warning",
                "referenceIds": [str(r.get("id")) for r in selected_refs],
                "messageKo": f"박자(Meter) 불일치 감지: {', '.join(sorted(unique_meters))}. 프로젝트 박자({project.timeSignature.numerator}/{project.timeSignature.denominator})를 기준으로 정규화합니다.",
                "messageEn": f"Meter mismatch across references ({', '.join(sorted(unique_meters))}). Normalizing to project meter.",
            }
        )

    # 3. Check Bass Pitch vs Chord Source conflict (when bass_groove comes from Ref A and chords from Ref B or Project Chord Track)
    chord_src_id = feature_source_map.get("chord_progression")
    bass_src_id = feature_source_map.get("bass_groove")
    if chord_src_id and bass_src_id and chord_src_id != bass_src_id:
        cr = ref_by_id.get(chord_src_id)
        br = ref_by_id.get(bass_src_id)
        if cr and br:
            ck, bk = _ref_key(cr), _ref_key(br)
            if ck and bk and ck != bk:
                conflicts.append(
                    {
                        "type": "harmony_bass_key_clash",
                        "severity": "info",
                        "referenceIds": [chord_src_id, bass_src_id],
                        "messageKo": (
                            f"코드 소스('{cr.get('name')}', {ck})와 베이스 그루브 소스('{br.get('name')}', {bk})의 조성이 다릅니다. "
                            "베이스 리듬·음가·쉼표는 유지하고 코드 트랙에 맞춰 음정을 재매핑합니다."
                        ),
                        "messageEn": (
                            f"Chord source ('{cr.get('name')}', {ck}) and Bass source ('{br.get('name')}', {bk}) differ in key. "
                            "Preserving bass rhythm/durations while re-harmonizing pitches to active Chord Track."
                        ),
                    }
                )

    return conflicts


def build_reference_binding(
    project: Project,
    reference_ids: list[str] | None = None,
    explicit_influences: list[str] | None = None,
    per_reference_influences: dict[str, list[str]] | None = None,
    feature_locks: dict[str, str] | None = None,
    feature_source_map: dict[str, str] | None = None,
    bass_lock_mode: str = "rhythm_and_duration",  # "full" | "rhythm_only" | "pitch_only" | "rhythm_and_duration"
    target_engine: str = "local-multitrack-composer",
    reference_mode: str = "reference_compose",  # "reconstruct" | "reference_compose" | "reinterpret"
    use_project_chord_track: bool = False,
) -> ReferenceBinding:
    """Resolve one or more Reference Blueprints (v1/v2/v3) + Feature Locks + Multi-Reference Source Map."""
    refs = project.references or []
    src_map = dict(feature_source_map or {})

    # Include any reference IDs explicitly named in feature_source_map!
    wanted_ids: list[str] = list(reference_ids or [])
    for rid in src_map.values():
        if rid and rid != "project_chord_track" and rid not in wanted_ids:
            wanted_ids.append(rid)

    if wanted_ids:
        wanted_set = set(wanted_ids)
        selected_refs = [r for r in refs if r.get("id") in wanted_set and (r.get("analysis") or r.get("blueprint"))]
    else:
        selected_refs = []

    applied: dict[str, Any] = {}
    all_selected_influences: list[str] = []
    per_ref_bindings: list[dict[str, Any]] = []
    feature_lifecycle: list[dict[str, Any]] = []
    resolved_source_map: dict[str, str] = {}
    unmapped: list[str] = [
        "exact_audio_timbre_cloning (copyright-safe structural inspiration only; original audio never copied)",
        "exact_fx_plugin_parameters (EQ/Comp/Reverb plugin settings are never reverse-engineered)",
    ]

    is_midi_engine = target_engine in ("local-multitrack-composer", "midi-composer-v3", "auto", "editable_midi", "hybrid")

    def _ref_allowed_for(feature_id: str, rid: str) -> bool:
        """If feature_source_map assigns feature_id to a specific reference, ONLY that reference supplies it!"""
        assigned = src_map.get(feature_id)
        if not assigned:
            return True
        return assigned == rid

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
        resolved_source_map[influence_id] = ref_id
        feature_lifecycle.append(
            {
                "feature": feature_key,
                "value": value if not isinstance(value, (list, dict)) else (
                    f"[{len(value)} items]" if isinstance(value, list) else f"{{{len(value)} keys}}"
                ),
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
    if project.chordTrack and (project.chordTrackLocked or use_project_chord_track) and src_map.get("chord_progression") in (None, "project_chord_track"):
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
                applied["referenceChords"] = syms[:32]

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
            featureSourceMap={},
            conflicts=[],
        )

    conflicts = detect_multi_reference_conflicts(
        selected_refs, src_map, project, use_project_chord_track=use_project_chord_track
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

        ref_locks = dict(ref.get("featureLocks") or bp.get("featureLocks") or _locks_from_legacy_influences(infs))
        if explicit_influences is not None and not feature_locks:
            ref_locks = _locks_from_legacy_influences(infs)
        if feature_locks:
            for lk, lv in feature_locks.items():
                ref_locks[lk] = lv
        # If feature_source_map explicitly assigns a feature to this ref and its lock was "free", promote to "reference"
        for fk, fsrc in src_map.items():
            if fsrc == rid and ref_locks.get(fk, "free") == "free":
                ref_locks[fk] = "reference"
        merged_locks.update(ref_locks)

        rhythm = ana.get("rhythm", {})
        harmony = ana.get("harmony", {})
        sound_m = ana.get("sound", {}).get("measured", {})
        sound_e = ana.get("sound", {}).get("estimated", {})
        arr_sections = bp.get("arrangementMap") or ana.get("arrangement", {}).get("sections", [])
        mapped_keys_for_ref: list[str] = []

        # 1. BPM & Beat Grid
        if _ref_allowed_for("bpm", rid) and (
            ref_locks.get("bpm") in ("locked", "reference") or any(k in infs for k in ("drums_groove", "tempo_groove", "mood_energy"))
        ):
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

        # 2. Sub-bar 15-Quality Chord Timeline
        chord_tl = bp.get("chordTimeline") or tr.get("chordTimeline") or []
        if chord_tl and _ref_allowed_for("chord_progression", rid):
            has_chord_timeline = True
        if _ref_allowed_for("chord_progression", rid) and (
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
                    "Exact beat-aligned 15-quality Chord Timeline consumed directly by Bass/Keys/Hook/ABC generators.",
                )
                mapped_keys_for_ref.append("chordTimeline")
            chords = [c.get("symbol") for c in chord_tl if c.get("symbol") and c["symbol"] != "N/C"] or [
                c for c in (bp.get("harmonicCharacter", {}).get("sampleChords") or []) if c and c not in ("N/C", "uncertain")
            ]
            if chords and "referenceChords" not in applied:
                record_feature(
                    "referenceChords",
                    chords[:32],
                    rid,
                    rname,
                    "chord_progression",
                    ref_locks.get("chord_progression", "reference"),
                    True,
                    "Chord progression symbols fed into composer & ABC generator.",
                )
                mapped_keys_for_ref.append("referenceChords")

        # 3. FULL-LENGTH Bar-by-Bar Drum Performance & Groove Transfer (NO 2-bar collapse in LOCKED mode!)
        drum_perf = bp.get("drumPerformance") or {}
        drum_ev = bp.get("drumEvents") or tr.get("drums") or {}
        full_quant_drums = list(
            drum_perf.get("quantizedPerformance")
            or drum_ev.get("quantizedNotes")
            or drum_ev.get("quantizedMidiNotes")
            or []
        )
        full_raw_drums = list(
            drum_perf.get("rawPerformance")
            or drum_ev.get("rawNotes")
            or drum_ev.get("rawMidiNotes")
            or []
        )
        drum_var_map = drum_perf.get("variationMap") or drum_ev.get("variationMap") or {}
        drum_template = drum_ev.get("patternTemplate2Bar") or full_quant_drums
        if (full_quant_drums or drum_template) and _ref_allowed_for("drum_rhythm", rid):
            has_transcribed_drums = True
        if _ref_allowed_for("drum_rhythm", rid) and (
            ref_locks.get("drum_rhythm") in ("locked", "reference") or "drums_groove" in infs
        ):
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
            if (full_quant_drums or drum_template) and "drumGroovePattern" not in applied:
                d_lock = ref_locks.get("drum_rhythm", "reference")
                record_feature(
                    "drumGroovePattern",
                    {
                        "lockMode": d_lock,
                        "sourceKind": drum_ev.get("sourceKind", "transcribed"),
                        "totalBars": int(drum_perf.get("totalBars") or drum_ev.get("totalBars") or drum_var_map.get("totalBars") or 0),
                        "fullPerformanceNotes": full_quant_drums,
                        "rawPerformanceNotes": full_raw_drums,
                        "variationMap": drum_var_map,
                        "template2Bar": (drum_ev.get("patternTemplate2Bar") or [])[:160],
                        "accentGrid16": groove_prof.get("accentGrid16", []),
                        "meanMicrotimingMs": groove_prof.get("meanMicrotimingMs", 0.0),
                        "fillBars": drum_ev.get("fillBars", []),
                        "breakdownBars": drum_ev.get("breakdownBars", []),
                    },
                    rid,
                    rname,
                    "drum_rhythm",
                    d_lock,
                    is_midi_engine,
                    (
                        "Full bar-by-bar transcribed Drum Performance (all bars, fills, breakdowns & microtiming) drives MIDI Drums."
                        if d_lock == "locked" and is_midi_engine
                        else (
                            "Transcribed Drum groove & variation guide drives MIDI Drums."
                            if is_midi_engine
                            else "Neural audio engine cannot lock exact drum hit timestamps (unsupported for strict lock)."
                        )
                    ),
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
                    "Tracked for sound design & comparison."
                    if is_midi_engine
                    else "Passed to neural audio prompt.",
                )
                mapped_keys_for_ref.append("transientCharacter")

        # 4. FULL-LENGTH Bass Performance & Granular Bass Lock Modes (full | rhythm_only | pitch_only | rhythm_and_duration)
        bass_perf = bp.get("bassPerformance") or tr.get("bassPerformance") or {}
        bass_ev = bp.get("bassEvents") or tr.get("bass") or {}
        bass_notes = list(bass_perf.get("notes") or bass_ev.get("notes") or [])
        if bass_notes and _ref_allowed_for("bass_groove", rid):
            has_transcribed_bass = True
        if _ref_allowed_for("bass_groove", rid) and (
            ref_locks.get("bass_groove") in ("locked", "reference") or "bass_movement" in infs
        ) and bass_notes and "bassGroovePattern" not in applied:
            b_lock = ref_locks.get("bass_groove", "reference")
            record_feature(
                "bassGroovePattern",
                {
                    "lockMode": b_lock,
                    "bassLockMode": bass_lock_mode,
                    "totalBars": int(bass_perf.get("totalBars") or 0),
                    "notes": bass_notes,
                    "pitchMin": bass_perf.get("pitchMin", bass_ev.get("pitchMin")),
                    "pitchMax": bass_perf.get("pitchMax", bass_ev.get("pitchMax")),
                    "kickInteractionScore": bass_perf.get("kickInteractionScore"),
                },
                rid,
                rname,
                "bass_groove",
                b_lock,
                is_midi_engine,
                f"Full bar-by-bar Bass performance ({len(bass_notes)} notes, mode={bass_lock_mode}) mapped onto active Chord Track."
                if is_midi_engine
                else "Neural audio cannot guarantee exact note-level bass lock.",
            )
            mapped_keys_for_ref.append("bassGroovePattern")

        # 5. Melody Lock (ONLY when user explicitly locks melody / reconstruct mode; default keeps melody FREE!)
        mel_ev = bp.get("melodyEvents") or tr.get("melody") or {}
        if _ref_allowed_for("melody", rid) and ref_locks.get("melody") == "locked" and reference_mode == "reconstruct" and mel_ev.get("notes") and "melodyEvents" not in applied:
            record_feature(
                "melodyEvents",
                mel_ev["notes"],
                rid,
                rname,
                "melody",
                "locked",
                True,
                "Authorized Reconstruct mode: preserves transcribed melody events.",
            )
            mapped_keys_for_ref.append("melodyEvents")

        # 6. Arrangement Structure Map
        if _ref_allowed_for("arrangement", rid) and (
            ref_locks.get("arrangement") in ("locked", "reference") or "arrangement_arc" in infs
        ) and arr_sections and "arrangementArc" not in applied:
            arc = [
                {
                    "label": s.get("label", "Section"),
                    "relativeEnergy": float(s.get("relativeEnergy", 0.6)),
                    "startSec": float(s.get("startSec", 0.0)),
                    "endSec": float(s.get("endSec", 0.0)),
                    "activeStems": s.get("activeStems", []),
                }
                for s in arr_sections[:12]
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
        if _ref_allowed_for("instrumentation", rid) and (
            ref_locks.get("instrumentation") in ("locked", "reference") or "instrumentation" in infs
        ) and "estimatedRoleFocus" not in applied:
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

        # 8. Sound & Spatial Character Profiles (Blueprint v3 — honest starting-point guidance, never exact cloning!)
        master_prof = (bp.get("soundProfiles") or {}).get("master") or {}
        if _ref_allowed_for("spatial_character", rid) and (
            ref_locks.get("spatial_character") in ("locked", "reference") or any(k in infs for k in ("spatial_depth", "sound_space"))
        ):
            if "stereoWidthTarget" not in applied:
                record_feature(
                    "stereoWidthTarget",
                    float(sound_m.get("stereoWidth", 0.35)),
                    rid,
                    rname,
                    "spatial_character",
                    ref_locks.get("spatial_character", "reference"),
                    False,
                    "Measured & mapped for sound design guidance & post-generation comparison (MIDI voices alone do not clone stereo width).",
                )
                mapped_keys_for_ref.append("stereoWidthTarget")
            if master_prof.get("spatialProfile") and "referenceSpatialProfile" not in applied:
                applied["referenceSpatialProfile"] = master_prof["spatialProfile"]
        if _ref_allowed_for("timbre", rid) and (
            ref_locks.get("timbre") in ("locked", "reference") or "timbre_tone" in infs
        ):
            if "spectralCentroidTargetHz" not in applied:
                record_feature(
                    "spectralCentroidTargetHz",
                    float(sound_m.get("spectralCentroidHz", 1400.0)),
                    rid,
                    rname,
                    "timbre",
                    ref_locks.get("timbre", "reference"),
                    not is_midi_engine,
                    "Tracked for sound design guidance & comparison; MIDI voices do not clone exact source timbre."
                    if is_midi_engine
                    else "Mapped into neural timbre style description.",
                )
                mapped_keys_for_ref.append("spectralCentroidTargetHz")
            if master_prof.get("soundProfile") and "referenceSoundProfile" not in applied:
                applied["referenceSoundProfile"] = master_prof["soundProfile"]
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

        # 9. Official YuE2 ABC Score from Blueprint v3
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
    if conflicts:
        note += f" 충돌 감지 {len(conflicts)}건: {conflicts[0]['messageKo']}"
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
        featureSourceMap=resolved_source_map,
        conflicts=conflicts,
    )
