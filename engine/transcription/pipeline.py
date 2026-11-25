"""Unified Sequential Transcription Pipeline, Stem Analysis, Reference Blueprint v2 & Mode A Reconstruct.

Designed for 16 GB Apple Silicon unified memory:
1. Runs DSP v3.0.0 analysis (`analysis.py`)
2. Runs cached Demucs `htdemucs` 4-stem separation on MPS sequentially (releasing GPU/RAM immediately!)
3. Analyzes every separated stem (`drums`, `bass`, `other`, `vocals`) for energy-per-section, pitch range,
   attack transient, timbre centroid, and honest stem-vs-recording classification
4. Runs real Spotify Basic Pitch ONNX on Bass stem (28–320 Hz, monophonic) & Other stem (130–2200 Hz, polyphonic + lead melody)
5. Runs real Multi-Band Drum & Groove transcription on Drums stem
6. Runs sub-bar Chord Track analyzer on Bass + Other harmonic stems
7. Builds Stem-informed Reference Arrangement Map & Reference Blueprint v2 + 10-feature Feature Lock config
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from scipy import signal

from engine.composition.midi_composer import notes_to_midi_bytes
from engine.daw_workspace import analysis, blueprint, commands, proposals, store
from engine.daw_workspace.schema import Clip, MidiNote, SectionMarker, make_id, utc_now_iso
from engine.daw_workspace.session import event_bus
from engine.generation.adapters.stem_separator import probe_demucs, separate_stems_demucs

from .basic_pitch_transcriber import extract_melody_topline, transcribe_audio_basic_pitch
from .chord_tracker import extract_chord_timeline
from .drum_transcriber import transcribe_drum_groove
from .sheetsage_adapter import build_yue2_abc_from_reference
from .sound_profiler import (
    analyze_bass_performance,
    classify_instruments_honestly,
    extract_sound_and_spatial_profile,
)

TRANSCRIPTION_VERSION = "4.1.0"

# Section 8: 10 Canonical Reference Feature Lock definitions
FEATURE_LOCK_SPECS: list[dict[str, Any]] = [
    {"id": "bpm", "labelKo": "BPM (템포)", "labelEn": "BPM (Tempo)", "defaultState": "locked"},
    {"id": "beat_grid", "labelKo": "Beat Grid (박자)", "labelEn": "Beat Grid", "defaultState": "reference"},
    {"id": "chord_progression", "labelKo": "코드 진행", "labelEn": "Chord Progression", "defaultState": "locked"},
    {"id": "drum_rhythm", "labelKo": "드럼 리듬 · 그루브", "labelEn": "Drum Rhythm & Groove", "defaultState": "reference"},
    {"id": "bass_groove", "labelKo": "베이스 그루브", "labelEn": "Bass Groove", "defaultState": "reference"},
    {"id": "melody", "labelKo": "멜로디", "labelEn": "Melody", "defaultState": "free"},
    {"id": "instrumentation", "labelKo": "악기 구성", "labelEn": "Instrumentation", "defaultState": "reference"},
    {"id": "arrangement", "labelKo": "편곡 구조 · 전개", "labelEn": "Arrangement Structure", "defaultState": "reference"},
    {"id": "timbre", "labelKo": "음색 · 질감", "labelEn": "Timbre Character", "defaultState": "free"},
    {"id": "spatial_character", "labelKo": "공간감 · 스테레오", "labelEn": "Spatial Character", "defaultState": "free"},
]

DEFAULT_FEATURE_LOCKS: dict[str, str] = {spec["id"]: spec["defaultState"] for spec in FEATURE_LOCK_SPECS}
ALLOWED_LOCK_STATES = frozenset(("free", "reference", "locked", "unsupported"))


def validate_feature_locks_for_engine(
    feature_locks: dict[str, str],
    engine_id: str = "local-multitrack-composer",
    has_transcribed_drums: bool = False,
    has_transcribed_bass: bool = False,
    has_chord_timeline: bool = False,
) -> dict[str, Any]:
    """Honest pre-generation capability check (Section 8): warn before generating if a locked feature cannot be enforced!"""
    is_midi = engine_id in ("local-multitrack-composer", "midi-composer-v3", "auto", "editable_midi")
    warnings_ko: list[str] = []
    warnings_en: list[str] = []
    effective: dict[str, str] = {}

    for spec in FEATURE_LOCK_SPECS:
        fid = spec["id"]
        req_state = str(feature_locks.get(fid, spec["defaultState"]))
        if req_state not in ALLOWED_LOCK_STATES:
            req_state = "free"

        if is_midi and fid in ("timbre", "spatial_character") and req_state in ("locked", "reference"):
            effective[fid] = "unsupported"
            warnings_ko.append(
                f"'{spec['labelKo']}' 고정/참고는 MIDI 신스 엔진에서 정확한 음색·공간감 복제를 지원하지 않습니다 (비교 지표로만 기록됨)."
            )
            warnings_en.append(
                f"'{spec['labelEn']}' cannot be faithfully matched by MIDI synth voices (tracked for post-comparison only)."
            )
        elif fid == "drum_rhythm" and req_state == "locked" and not has_transcribed_drums:
            effective[fid] = "unsupported"
            warnings_ko.append("드럼 채보 데이터가 없어 드럼 리듬을 완전 고정할 수 없습니다. 정밀 채보를 먼저 실행하세요 (LOCK→REFERENCE 암묵 강등 없음).")
            warnings_en.append("No transcribed drum events available for strict drum rhythm lock; run transcription first (never silently downgraded).")
        elif fid == "bass_groove" and req_state == "locked" and not has_transcribed_bass:
            effective[fid] = "unsupported"
            warnings_ko.append("베이스 채보 데이터가 없어 베이스 그루브를 완전 고정할 수 없습니다. 정밀 채보를 먼저 실행하세요.")
            warnings_en.append("No transcribed bass events available for strict bass groove lock; run transcription first.")
        elif fid == "chord_progression" and req_state == "locked" and not has_chord_timeline:
            effective[fid] = "unsupported"
            warnings_ko.append("확정된 코드 타임라인이 없어 코드 진행을 완전 고정할 수 없습니다. 정밀 채보 또는 코드 트랙을 먼저 설정하세요.")
            warnings_en.append("No chord timeline available for strict chord lock; run transcription or set Chord Track first.")
        elif not is_midi and fid in ("drum_rhythm", "bass_groove") and req_state == "locked":
            effective[fid] = "unsupported"
            warnings_ko.append(
                f"신경망 오디오 엔진({engine_id})은 '{spec['labelKo']}'의 음표 단위 완전 고정을 지원하지 않습니다. "
                "Editable MIDI 또는 Hybrid 모드로 전환하세요."
            )
            warnings_en.append(
                f"Neural audio engine ({engine_id}) cannot guarantee exact note-level lock for '{spec['labelEn']}' "
                "(marked unsupported — switch to Editable MIDI or Hybrid mode instead)."
            )
        else:
            effective[fid] = req_state

    return {
        "engine": engine_id,
        "effectiveLocks": effective,
        "warningsKo": warnings_ko,
        "warningsEn": warnings_en,
        "allLockedSatisfied": len(warnings_en) == 0,
    }


def _analyze_single_stem(
    role: str,
    wav_path: Path,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze a single Demucs stem for RMS energy, attack, spectral centroid, and per-section activity."""
    data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1).astype(np.float64)
    duration_sec = len(mono) / max(1, sr)
    rms = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
    rms_db = round(20.0 * math.log10(max(rms, 1e-9)), 2)
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    crest_db = round(20.0 * math.log10(max(peak, 1e-9) / max(rms, 1e-9)), 2) if rms > 1e-6 else 0.0

    # Spectral centroid (timbre brightness)
    nperseg = min(4096, max(256, len(mono)))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg)
    centroid_hz = round(float((freqs * psd).sum() / (psd.sum() + 1e-18)), 1)

    # Per-section RMS energy & active presence
    sec_activity: list[dict[str, Any]] = []
    for sec in sections:
        i0 = max(0, int(round(float(sec.get("startSec", 0.0)) * sr)))
        i1 = min(len(mono), int(round(float(sec.get("endSec", duration_sec)) * sr)))
        seg = mono[i0:i1]
        s_rms = float(np.sqrt(np.mean(seg * seg))) if len(seg) > 0 else 0.0
        s_db = round(20.0 * math.log10(max(s_rms, 1e-9)), 2)
        sec_activity.append(
            {
                "sectionId": sec.get("id"),
                "label": sec.get("label"),
                "rmsDbfs": s_db,
                "active": s_db > -44.0 and (s_db > rms_db - 18.0 if rms_db > -50.0 else False),
            }
        )

    is_active = rms_db > -46.0
    honest_label = (
        "Other Stem (Guitar / Keys / Synth / Pads — mixed harmonic stem, NOT isolated instrument)"
        if role == "other"
        else f"{role.title()} Stem (Demucs separated — NOT independent studio recording)"
    )
    attack_char = "sharp / percussive" if crest_db >= 14.0 else ("medium" if crest_db >= 9.0 else "sustained / smooth")
    return {
        "role": role,
        "assetKind": "separated_stem",
        "honestLabel": honest_label,
        "active": is_active,
        "rmsDbfs": rms_db,
        "crestFactorDb": crest_db,
        "attackCharacter": attack_char,
        "spectralCentroidHz": centroid_hz,
        "durationSec": round(duration_sec, 3),
        "sampleRate": int(sr),
        "sectionActivity": sec_activity,
    }


def _enrich_arrangement_map_with_stems(
    sections: list[dict[str, Any]],
    stem_analyses: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach real per-stem entry/exit activity onto every Arrangement Map section (Section 6)."""
    enriched: list[dict[str, Any]] = []
    prev_active: set[str] = set()
    for idx, sec in enumerate(sections):
        active_stems: list[str] = []
        for role, st in stem_analyses.items():
            for sa in st.get("sectionActivity", []):
                if sa.get("sectionId") == sec.get("id") and sa.get("active"):
                    active_stems.append(role)
        cur_set = set(active_stems)
        entered = sorted(cur_set - prev_active) if idx > 0 else sorted(cur_set)
        exited = sorted(prev_active - cur_set) if idx > 0 else []
        prev_active = cur_set

        # Refine Breakdown detection honestly when drums drop out mid-song!
        label = str(sec.get("label", f"Section {chr(65 + idx)}"))
        est_role = bool(sec.get("isEstimatedRole", False))
        if idx > 0 and idx < len(sections) - 1 and stem_analyses.get("drums", {}).get("active") and "drums" not in cur_set and cur_set:
            label = "Breakdown"
            est_role = True

        enriched.append(
            {
                **sec,
                "label": label,
                "isEstimatedRole": est_role,
                "activeStems": sorted(active_stems),
                "enteredStems": entered,
                "exitedStems": exited,
            }
        )
    return enriched


def build_reference_blueprint_v2(
    *,
    ref_id: str,
    sha256: str,
    dsp_analysis: dict[str, Any],
    transcription: dict[str, Any],
    existing_influences: list[str] | None = None,
    existing_locks: dict[str, str] | None = None,
    user_corrections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Reference Blueprint v2 (Section 7) strictly separating measured, estimated & user-corrected values."""
    base_bp = blueprint.build_reference_blueprint(dsp_analysis, existing_influences=existing_influences)
    rhythm = dsp_analysis.get("rhythm", {})
    harmony = dsp_analysis.get("harmony", {})
    sound_m = dsp_analysis.get("sound", {}).get("measured", {})
    sound_e = dsp_analysis.get("sound", {}).get("estimated", {})

    drums_tr = transcription.get("drums") or {}
    bass_tr = transcription.get("bass") or {}
    bass_perf = transcription.get("bassPerformance") or {}
    melody_tr = transcription.get("melody") or {}
    other_tr = transcription.get("other") or {}
    chords = list(transcription.get("chordTimeline") or [])
    stems = transcription.get("stems") or {}
    arr_map = list(transcription.get("arrangementMap") or dsp_analysis.get("arrangement", {}).get("sections", []))
    abc_info = transcription.get("abcScore") or {}
    sound_profiles = transcription.get("soundProfiles") or {}
    inst_classes = transcription.get("instrumentClassifications") or []
    analysis_cov = transcription.get("analysisCoverage") or dsp_analysis.get("analysisCoverage") or {}
    drum_var_map = drums_tr.get("variationMap") or {}
    full_quant_drums = list(drums_tr.get("quantizedMidiNotes") or [])
    full_raw_drums = list(drums_tr.get("rawMidiNotes") or [])
    full_bass_notes = list(bass_perf.get("notes") or bass_tr.get("notes") or [])

    locks = dict(DEFAULT_FEATURE_LOCKS)
    if existing_locks:
        for k, v in existing_locks.items():
            if k in locks and v in ALLOWED_LOCK_STATES:
                locks[k] = v

    # Apply any user-corrected chords cleanly over estimates
    corr = dict(user_corrections or {})
    if isinstance(corr.get("chords"), list) and corr["chords"]:
        chords = corr["chords"]

    sample_chord_syms = [c["symbol"] for c in chords if c.get("symbol") and c["symbol"] != "N/C"]
    bpm_val = rhythm.get("adoptedTempoBpm") or rhythm.get("estimatedBpm")

    # Honest instrument estimates grounded in real separated stems + Basic Pitch note counts!
    inst_estimates: list[dict[str, Any]] = []
    if stems:
        for role in ("drums", "bass", "other", "vocals"):
            st = stems.get(role)
            if not st:
                continue
            note_cnt = (
                len(drums_tr.get("quantizedMidiNotes", []))
                if role == "drums"
                else (
                    int(bass_tr.get("noteCount", 0))
                    if role == "bass"
                    else (int(other_tr.get("noteCount", 0)) if role == "other" else 0)
                )
            )
            inst_estimates.append(
                {
                    "role": role,
                    "name": st["honestLabel"],
                    "active": st["active"],
                    "status": "stem_confirmed" if st["active"] else "silent_in_stem",
                    "rmsDbfs": st["rmsDbfs"],
                    "transcribedNoteCount": note_cnt,
                    "spectralCentroidHz": st["spectralCentroidHz"],
                    "attackCharacter": st["attackCharacter"],
                    "caveat": (
                        "Other 스템은 기타·건반·신스가 혼합되어 있어 개별 악기를 임의로 단정하지 않습니다."
                        if role == "other"
                        else None
                    ),
                }
            )
    else:
        inst_estimates = list(dsp_analysis.get("instrumentation", {}).get("elements", []))

    master_sp = (sound_profiles.get("master") or {}).get("spatialProfile") or {}
    return {
        **base_bp,
        "blueprintVersion": "3.0.0",
        "referenceId": ref_id,
        "sourceAudioHash": sha256,
        "analysisCoverage": analysis_cov,
        "analysisModels": transcription.get("modelsUsed", []),
        "tempoMap": {
            "bpm": bpm_val,
            "measuredPulseBpm": rhythm.get("measuredPulseBpm"),
            "halfDoubleAmbiguous": rhythm.get("halfDoubleAmbiguous", False),
            "meter": rhythm.get("meterEstimate", "4/4"),
            "beatOffsetSec": (rhythm.get("beatGridSec") or [0.0])[0] if rhythm.get("beatGridSec") else 0.0,
            "tempoVariationBpmStd": rhythm.get("tempoVariationBpmStd", 0.0),
            "tempoStability": rhythm.get("tempoStability", "steady"),
            "dawFixedBpmApproximationNote": rhythm.get("dawFixedBpmApproximationNote", ""),
        },
        "beatGrid": {
            "beatGridSec": rhythm.get("beatGridSec", []),
            "downbeatsSec": rhythm.get("downbeatsSec", []),
            "actualBeatGrid": rhythm.get("actualBeatGrid", []),
            "fixedBpmGrid": rhythm.get("fixedBpmGrid", []),
        },
        "chordTimeline": chords,
        "harmonicCharacter": {
            **base_bp.get("harmonicCharacter", {}),
            "key": harmony.get("estimatedKey", "Uncertain"),
            "sampleChords": sample_chord_syms[:16] or base_bp.get("harmonicCharacter", {}).get("sampleChords", []),
            "chordEventCount": len(chords),
            "hasSubBarChanges": any((float(c.get("endBeat", 4.0)) - float(c.get("startBeat", 0.0))) < 3.9 for c in chords),
            "hasPassingChords": any(bool(c.get("isPassing")) for c in chords),
        },
        "melodyEvents": {
            "transcribed": bool(melody_tr.get("noteCount", 0) > 0),
            "noteCount": int(melody_tr.get("noteCount", 0)),
            "pitchMin": melody_tr.get("pitchMin"),
            "pitchMax": melody_tr.get("pitchMax"),
            "meanConfidence": melody_tr.get("meanConfidence", 0.0),
            "notes": list(melody_tr.get("notes", [])),
        },
        "drumEvents": {
            "transcribed": bool(drums_tr.get("hasDrums")),
            "sourceKind": drums_tr.get("sourceKind", "untranscribed"),
            "analysisCoverage": drums_tr.get("analysisCoverage", analysis_cov),
            "totalBars": drums_tr.get("totalBars", drum_var_map.get("totalBars", 0)),
            "hitCounts": drums_tr.get("hitCounts", {}),
            "noteCount": len(full_quant_drums),
            "fillBars": drums_tr.get("fillBars", []),
            "breakdownBars": drums_tr.get("breakdownBars", []),
            "cymbalReentryBars": drums_tr.get("cymbalReentryBars", []),
            "patternRepetitionBars": drums_tr.get("patternRepetitionBars", 1),
            "variationMap": drum_var_map,
            "patternTemplate1Bar": drums_tr.get("patternTemplate1Bar", []),
            "patternTemplate2Bar": drums_tr.get("patternTemplate2Bar", []),
            # Full bar-by-bar performance (NO 2-bar or 600-hit truncation!)
            "quantizedNotes": full_quant_drums,
            "rawNotes": full_raw_drums,
        },
        "drumPerformance": {
            "totalBars": drums_tr.get("totalBars", drum_var_map.get("totalBars", 0)),
            "analysisCoverage": drums_tr.get("analysisCoverage", analysis_cov),
            "variationMap": drum_var_map,
            "rawPerformance": full_raw_drums,
            "quantizedPerformance": full_quant_drums,
            "hitCounts": drums_tr.get("hitCounts", {}),
        },
        "bassEvents": {
            "transcribed": bool(len(full_bass_notes) > 0),
            "noteCount": len(full_bass_notes),
            "pitchMin": bass_perf.get("pitchMin", bass_tr.get("pitchMin")),
            "pitchMax": bass_perf.get("pitchMax", bass_tr.get("pitchMax")),
            "meanConfidence": bass_tr.get("meanConfidence", 0.0),
            "syncopationScore": bass_perf.get("syncopationScore", 0.0),
            "kickInteractionScore": bass_perf.get("kickInteractionScore"),
            "octaveJumpCount": bass_perf.get("octaveJumpCount", 0),
            "slideCandidateCount": bass_perf.get("slideCandidateCount", 0),
            "variationMap": bass_perf.get("variationMap", []),
            "notes": full_bass_notes,
        },
        "bassPerformance": bass_perf,
        "instrumentEstimates": inst_estimates,
        "instrumentClassifications": inst_classes,
        "stemReferences": transcription.get("stemReferences", []),
        "arrangementMap": arr_map,
        "arrangementTimeline": arr_map,
        "grooveProfile": {
            "swingRatio": drums_tr.get("swingRatio", rhythm.get("swingRatio", 0.5)),
            "feel": drums_tr.get("grooveFeel", rhythm.get("grooveFeel", "straight")),
            "syncopationScore": drums_tr.get("syncopationScore", 0.0),
            "meanMicrotimingMs": drums_tr.get("meanMicrotimingMs", 0.0),
            "microtimingStdMs": drums_tr.get("microtimingStdMs", 0.0),
            "accentGrid16": drums_tr.get("accentGrid16", []),
        },
        "timbreProfile": {
            "frequencyBandsPct": sound_m.get("frequencyBandsPct", {}),
            "spectralCentroidHz": sound_m.get("spectralCentroidHz", 0.0),
            "transientCharacter": sound_e.get("transientCharacter", "controlled"),
            "integratedLufs": sound_m.get("integratedLufs"),
            "truePeakDbtp": sound_m.get("truePeakDbtp"),
        },
        "soundProfiles": sound_profiles,
        "spatialProfile": {
            "stereoWidth": sound_m.get("stereoWidth", 0.0),
            "lrCorrelation": sound_m.get("lrCorrelation", 1.0),
            "reverbCharacter": sound_e.get("reverbCharacter", "balanced room"),
            **master_sp,
        },
        "abcScore": abc_info,
        "featureLocks": locks,
        "featureLockSpecs": FEATURE_LOCK_SPECS,
        "confidence": {
            "tempo": rhythm.get("confidence", rhythm.get("regularity", 0.0)),
            "harmony": harmony.get("confidence", 0.0),
            "chords": round(float(np.mean([c.get("confidence", 0.0) for c in chords])), 3) if chords else 0.0,
            "bassTranscription": bass_tr.get("meanConfidence", 0.0),
            "melodyTranscription": melody_tr.get("meanConfidence", 0.0),
            "overall": round(
                float(
                    np.mean(
                        [
                            float(rhythm.get("confidence", 0.0)),
                            float(harmony.get("confidence", 0.0)),
                            float(bass_tr.get("meanConfidence", 0.5) if bass_tr.get("noteCount") else 0.4),
                        ]
                    )
                ),
                3,
            ),
        },
        "userCorrections": corr,
        "provenanceSeparation": {
            "measured": [
                "analysisCoverage",
                "tempoMap.measuredPulseBpm",
                "beatGrid.actualBeatGrid",
                "timbreProfile.frequencyBandsPct",
                "timbreProfile.integratedLufs",
                "soundProfiles",
                "spatialProfile",
                "stemReferences.rmsDbfs",
            ],
            "estimated": [
                "chordTimeline (unless userCorrected)",
                "melodyEvents",
                "drumPerformance",
                "bassPerformance",
                "arrangementMap",
                "instrumentClassifications",
            ],
            "userCorrected": list(corr.keys()),
        },
    }


def transcribe_reference_audio(
    audio_path: Path,
    *,
    ref_id: str,
    sha256: str,
    project_dir: Path,
    project_bpm: float | None = None,
    use_demucs: bool = True,
    demucs_model: str = "htdemucs",
    progress_cb: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run sequential DSP + Demucs MPS + Basic Pitch ONNX + Drum/Chord Transcription with content-addressed cache."""
    cache_dir = project_dir / "cache" / "transcription"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem_tag = f"demucs_{demucs_model}" if use_demucs else "dsp_bp"
    cache_file = cache_dir / f"{sha256}_{TRANSCRIPTION_VERSION}_{stem_tag}.json"

    def check_cancel() -> None:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Transcription cancelled by user")

    if progress_cb:
        progress_cb(8, "dsp_acoustic_analysis")
    dsp = analysis.analyze_audio_file(
        audio_path=audio_path,
        source_asset_id=ref_id,
        sha256=sha256,
        cache_dir=project_dir / "cache" / "analysis",
        cancel_event=cancel_event,
        project_bpm=project_bpm,
    )
    check_cancel()

    if cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            cached["fromCache"] = True
            if progress_cb:
                progress_cb(100, "cached")
            return dsp, cached
        except Exception:
            pass

    rhythm = dsp.get("rhythm", {})
    harmony = dsp.get("harmony", {})
    bpm = float(rhythm.get("adoptedTempoBpm") or rhythm.get("estimatedBpm") or project_bpm or 120.0)
    beat_offset = float((rhythm.get("beatGridSec") or [0.0])[0]) if rhythm.get("beatGridSec") else 0.0
    bpb = 3.0 if rhythm.get("meterEstimate") == "3/4" else 4.0
    key_str = str(harmony.get("estimatedKey") or "F minor")
    base_sections = list(dsp.get("arrangement", {}).get("sections", []))

    models_used: list[dict[str, str]] = [
        {"id": "dsp-acoustic-v3", "role": "BPM / Beat Grid / BS.1770-4 / Spectral / Stereo", "license": "MIT"}
    ]

    # Step 2: Optional Demucs 4-stem separation (cached per audio sha256!)
    stem_paths: dict[str, Path] = {}
    stem_refs: list[dict[str, Any]] = []
    stem_analyses: dict[str, dict[str, Any]] = {}
    demucs_info = probe_demucs()
    if use_demucs and demucs_info.get("available"):
        if progress_cb:
            progress_cb(25, "demucs_stem_separation")
        stems_root = project_dir / "cache" / "stems" / sha256[:16]
        try:
            sep_list = separate_stems_demucs(
                audio_path=audio_path,
                out_dir=stems_root,
                model_name=demucs_model,
                cancel_event=cancel_event,
                use_cache=True,
            )
            models_used.append({"id": f"demucs-{demucs_model}", "role": "4-Stem Separation (Apple Silicon MPS)", "license": "MIT"})
            for s in sep_list:
                role = str(s["role"])
                wp = Path(s["wavPath"])
                stem_paths[role] = wp
                st_ana = _analyze_single_stem(role, wp, base_sections)
                stem_analyses[role] = st_ana
                rel_p = wp.resolve().relative_to(project_dir.resolve()).as_posix()
                stem_refs.append(
                    {
                        "role": role,
                        "name": s["name"],
                        "relativePath": rel_p,
                        "assetKind": "separated_stem",
                        "active": st_ana["active"],
                        "rmsDbfs": st_ana["rmsDbfs"],
                        "spectralCentroidHz": st_ana["spectralCentroidHz"],
                        "attackCharacter": st_ana["attackCharacter"],
                    }
                )
        except Exception as exc:
            models_used.append({"id": f"demucs-{demucs_model}", "role": f"Skipped/Failed: {exc}", "license": "MIT"})
    check_cancel()

    # Step 3: Drum & Groove Transcription (on Drums stem when available, else HPSS percussive)
    if progress_cb:
        progress_cb(50, "drum_groove_transcription")
    drums_wav = stem_paths.get("drums") or audio_path
    drums_src = "demucs_drums_stem" if "drums" in stem_paths else "hpss_percussive_fallback"
    drum_result = transcribe_drum_groove(
        drums_wav,
        bpm=bpm,
        beat_offset_sec=beat_offset,
        bpb=bpb,
        source_kind=drums_src,
    )
    models_used.append({"id": "multiband-drum-groove-v1", "role": f"Drum & Microtiming ({drums_src})", "license": "MIT"})
    check_cancel()

    # Step 4: Real Basic Pitch ONNX Transcription on Bass Stem + Other/Melody Stem!
    if progress_cb:
        progress_cb(68, "basic_pitch_bass_and_melody")
    bass_wav = stem_paths.get("bass") or audio_path
    other_wav = stem_paths.get("other") or audio_path

    # Only run Bass Basic Pitch if bass stem is active (or full mix fallback)
    bass_active = stem_analyses.get("bass", {}).get("active", True)
    if bass_active:
        bass_result = transcribe_audio_basic_pitch(
            bass_wav,
            bpm=bpm,
            beat_offset_sec=beat_offset,
            onset_threshold=0.45,
            frame_threshold=0.30,
            minimum_note_length_ms=80.0,
            minimum_frequency_hz=28.0,
            maximum_frequency_hz=310.0,
            monophonic=True,
        )
    else:
        bass_result = {"model": "spotify-basic-pitch-onnx", "noteCount": 0, "pitchMin": None, "pitchMax": None, "meanConfidence": 0.0, "notes": []}

    other_active = stem_analyses.get("other", {}).get("active", True)
    if other_active:
        other_result = transcribe_audio_basic_pitch(
            other_wav,
            bpm=bpm,
            beat_offset_sec=beat_offset,
            onset_threshold=0.48,
            frame_threshold=0.32,
            minimum_note_length_ms=90.0,
            minimum_frequency_hz=130.0,
            maximum_frequency_hz=2200.0,
            monophonic=False,
        )
    else:
        other_result = {"model": "spotify-basic-pitch-onnx", "noteCount": 0, "pitchMin": None, "pitchMax": None, "meanConfidence": 0.0, "notes": []}

    melody_notes = extract_melody_topline(other_result.get("notes", []), min_pitch=55)
    melody_pitches = [n["pitch"] for n in melody_notes]
    melody_result = {
        "model": "spotify-basic-pitch-onnx-topline",
        "sourceStem": "other" if "other" in stem_paths else "full_mix",
        "noteCount": len(melody_notes),
        "pitchMin": min(melody_pitches) if melody_pitches else None,
        "pitchMax": max(melody_pitches) if melody_pitches else None,
        "meanConfidence": round(float(np.mean([n["confidence"] for n in melody_notes])), 3) if melody_notes else 0.0,
        "notes": melody_notes,
    }
    models_used.append({"id": "basic-pitch-onnx", "role": "Polyphonic Bass & Melody MIDI Transcription", "license": "Apache-2.0"})
    check_cancel()

    # Step 5: Sub-bar 15-Quality Chord Track from Bass + Other harmonic stems
    if progress_cb:
        progress_cb(82, "chord_track_extraction")
    chord_timeline = extract_chord_timeline(
        audio_path,
        bpm=bpm,
        beat_offset_sec=beat_offset,
        key_hint=key_str,
        source_reference_id=ref_id,
        bass_stem_path=stem_paths.get("bass"),
        other_stem_path=stem_paths.get("other"),
        slice_beats=1.0,
    )
    models_used.append({"id": "harmonic-viterbi-chords-v2", "role": "15-Quality Sub-bar Chord, Passing Chord & Inversion Track", "license": "MIT"})

    # Step 6: Full-Length Bass Performance, Sound/Spatial Profiles & Honest Instrument Classification
    if progress_cb:
        progress_cb(90, "sound_spatial_and_performance_profiles")
    bass_perf = analyze_bass_performance(
        bass_result.get("notes", []),
        drum_notes=drum_result.get("quantizedMidiNotes", []),
        bpb=bpb,
        duration_sec=float(dsp.get("durationSec", 0.0)),
        bpm=bpm,
        coverage=dsp.get("analysisCoverage"),
    )
    sound_profiles: dict[str, Any] = {
        "master": extract_sound_and_spatial_profile(audio_path, role="master", bpm=bpm),
    }
    for srole, spath in stem_paths.items():
        if stem_analyses.get(srole, {}).get("active"):
            sound_profiles[srole] = extract_sound_and_spatial_profile(spath, role=srole, bpm=bpm)

    inst_classifications = classify_instruments_honestly(
        stem_analyses=stem_analyses,
        drum_result=drum_result,
        bass_result=bass_result,
        melody_result=melody_result,
        other_result=other_result,
        dsp_elements=list(dsp.get("instrumentation", {}).get("elements", [])),
    )

    # Step 7: Enrich Arrangement Map with real per-stem entry/exit activity + build YuE2 ABC score!
    if progress_cb:
        progress_cb(95, "arrangement_map_and_abc")
    arr_map = _enrich_arrangement_map_with_stems(base_sections, stem_analyses)
    total_bars = max(4, min(64, int(math.ceil(dsp.get("durationSec", 16.0) / ((60.0 / bpm) * bpb)))))
    abc_score = build_yue2_abc_from_reference(
        chord_timeline=chord_timeline,
        melody_notes=melody_notes,
        sections=arr_map,
        key_str=key_str,
        bpm=bpm,
        bpb=bpb,
        total_bars=total_bars,
        production_mode="reference_compose",
    )

    transcription = {
        "transcriptionVersion": TRANSCRIPTION_VERSION,
        "transcribedAt": utc_now_iso(),
        "fromCache": False,
        "sourceSha256": sha256,
        "analysisCoverage": dsp.get("analysisCoverage"),
        "bpm": bpm,
        "key": key_str,
        "modelsUsed": models_used,
        "stems": stem_analyses,
        "stemReferences": stem_refs,
        "chordTimeline": chord_timeline,
        "drums": drum_result,
        "bass": bass_result,
        "bassPerformance": bass_perf,
        "other": other_result,
        "melody": melody_result,
        "soundProfiles": sound_profiles,
        "instrumentClassifications": inst_classifications,
        "arrangementMap": arr_map,
        "abcScore": abc_score,
        "limitationsKo": [
            "Other 스템은 기타·건반·신스·패드가 혼합된 Mixed Harmonic Content이며 단일 스튜디오 악기로 단정하지 않습니다.",
            "사운드·공간감 프로필은 음향 실측 기반 시작점 추정이며, 원본 믹스의 정확한 EQ/컴프레서/리버브 플러그인 파라미터를 역산하지 않습니다.",
            "SheetSage2(CC BY-NC 4.0) 및 YourMT3+는 미설치 상태로, Demucs + Basic Pitch ONNX + Full-Length Multi-Band Drum + 15-Quality Viterbi Chord 경로로 실행되었습니다.",
        ],
    }

    if not use_demucs or len(stem_refs) > 0:
        tmp = cache_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(transcription, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache_file)

    if progress_cb:
        progress_cb(100, "completed")
    return dsp, transcription


def reconstruct_reference_to_project(
    project_id: str,
    ref_id: str,
    *,
    import_chords: bool = True,
    import_drums_midi: bool = True,
    import_bass_midi: bool = True,
    import_melody_midi: bool = True,
    import_stems: bool = False,
    import_sections: bool = True,
    use_quantized_drums: bool = True,
    apply_bpm: bool = True,
) -> dict[str, Any]:
    """MODE A (Reconstruct) & Selective Reference Asset Import into an editable DAW project (1-click Undoable)."""
    proj = store.load_project(project_id)
    ref = next((r for r in proj.references if r.get("id") == ref_id), None)
    if not ref:
        raise FileNotFoundError(f"Reference not found: {ref_id}")
    bp = ref.get("blueprint") or {}
    tr = ref.get("transcription") or {}
    if not tr and not bp.get("chordTimeline"):
        raise ValueError("먼저 레퍼런스 정밀 채보를 실행해 주세요 (Run Transcription first).")

    proposals.record_undo_snapshot(proj)
    pdir = store.project_dir(project_id)
    updated = proj
    created_tracks: list[str] = []
    imported_items: list[str] = []
    limitations: list[str] = list(tr.get("limitationsKo") or [])
    bpb = updated.timeSignature.beats_per_bar

    ref_bpm = float(bp.get("tempoMap", {}).get("bpm") or tr.get("bpm") or updated.bpm)
    if apply_bpm and 30.0 <= ref_bpm <= 300.0:
        updated = commands.apply_command(updated, "project.setTempo", {"bpm": round(ref_bpm, 1)})
        imported_items.append(f"BPM ({round(ref_bpm, 1)})")

    # 1. Chord Track
    chords = bp.get("chordTimeline") or tr.get("chordTimeline") or []
    if import_chords and chords:
        updated = commands.apply_command(updated, "chord.setTrack", {"chords": chords, "locked": False})
        imported_items.append(f"Chord Track ({len(chords)} chords)")

    # 2. Arrangement Section Markers
    arr_map = bp.get("arrangementMap") or tr.get("arrangementMap") or []
    if import_sections and arr_map:
        sec_colors = ["#49505e", "#446256", "#554d6b", "#6d5645", "#4c626d", "#5e4959"]
        updated.sections = []
        for idx, sec in enumerate(arr_map):
            sb = max(0.0, (float(sec.get("startBar", 1.0)) - 1.0) * bpb)
            eb = max(sb + bpb, (float(sec.get("endBar", 5.0)) - 1.0) * bpb)
            updated.sections.append(
                SectionMarker(
                    id=make_id("sec"),
                    name=str(sec.get("label", f"Section {idx + 1}"))[:64],
                    startBeats=round(sb, 2),
                    endBeats=round(eb, 2),
                    color=sec_colors[idx % len(sec_colors)],
                )
            )
        imported_items.append(f"Arrangement Markers ({len(updated.sections)})")

    def _add_midi_track(name: str, inst_ref: str, color: str, raw_notes: list[dict[str, Any]], quantized: bool) -> None:
        if not raw_notes:
            return
        nonlocal updated
        midi_notes = [
            MidiNote(
                id=make_id("note"),
                pitch=max(0, min(127, int(n["pitch"]))),
                velocity=max(1, min(127, int(n.get("velocity", 92)))),
                startBeat=round(max(0.0, float(n["quantizedStartBeat"] if quantized and "quantizedStartBeat" in n else n["startBeat"])), 4),
                durationBeats=round(max(0.0625, float(n["quantizedDurationBeats"] if quantized and "quantizedDurationBeats" in n else n["durationBeats"])), 4),
            )
            for n in raw_notes
        ]
        max_end = max((n.startBeat + n.durationBeats for n in midi_notes), default=16.0)
        dur_beats = max(bpb, float(math.ceil(max_end / bpb) * bpb))
        tid = make_id("trk")
        updated = commands.apply_command(
            updated,
            "track.add",
            {"id": tid, "name": name, "type": "midi", "instrumentRef": inst_ref, "color": color},
        )
        updated = commands.apply_command(
            updated,
            "clip.add",
            {
                "trackId": tid,
                "clip": Clip(
                    id=make_id("clp"),
                    name=f"{name} (Transcribed)",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=dur_beats,
                    notes=midi_notes,
                ).model_dump(),
            },
        )
        if dur_beats > updated.lengthBeats:
            updated = commands.apply_command(updated, "project.setLength", {"lengthBeats": dur_beats})
        created_tracks.append(tid)
        imported_items.append(f"{name} ({len(midi_notes)} notes)")

    # 3. Drum MIDI
    if import_drums_midi:
        d_info = tr.get("drums") or bp.get("drumEvents") or {}
        d_notes = d_info.get("quantizedMidiNotes" if use_quantized_drums else "rawMidiNotes") or d_info.get("quantizedNotes") or []
        if d_notes:
            _add_midi_track(f"{ref['name'][:18]} Drums", "drum-kit-electronic", "#6a997c", d_notes, quantized=False)
        else:
            limitations.append("드럼 트랙에서 유의미한 타격 패턴이 감지되지 않아 드럼 MIDI를 생성하지 않았습니다.")

    # 4. Bass MIDI
    if import_bass_midi:
        b_notes = (tr.get("bass") or bp.get("bassEvents") or {}).get("notes") or []
        if b_notes:
            _add_midi_track(f"{ref['name'][:18]} Bass", "bass-fm-sub", "#867ca8", b_notes, quantized=True)
        else:
            limitations.append("베이스 스템에서 유의미한 음표가 감지되지 않았습니다.")

    # 5. Melody MIDI
    if import_melody_midi:
        m_notes = (tr.get("melody") or bp.get("melodyEvents") or {}).get("notes") or []
        if m_notes:
            _add_midi_track(f"{ref['name'][:18]} Melody", "synth-fm-hook", "#648ea8", m_notes, quantized=True)
        else:
            limitations.append("멜로디 상성부 음표가 충분히 감지되지 않았습니다.")

    # Save MIDI/chord/section mutations before importing audio stems via store.import_asset_bytes
    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)

    # 6. Optional Demucs Separated Audio Stems (marked clearly as `type="stem"` with `stemMeta` provenance!)
    if import_stems:
        stem_refs = tr.get("stemReferences") or bp.get("stemReferences") or []
        for sr_item in stem_refs:
            if not sr_item.get("active"):
                continue
            rel = sr_item.get("relativePath")
            if not rel:
                continue
            abs_wav = (pdir / rel).resolve()
            if not abs_wav.is_relative_to(pdir.resolve()) or not abs_wav.is_file():
                continue
            raw_bytes = abs_wav.read_bytes()
            asset, _ = store.import_asset_bytes(
                project_id=project_id,
                filename=f"{ref['name'][:20]}_{sr_item['role']}_stem.wav",
                raw_bytes=raw_bytes,
                kind_hint="audio",
                source="demucs-reference-reconstruct",
                provenance=f"Separated {sr_item['role']} stem from reference '{ref['name']}' (NOT independent recording)",
            )
            cur = store.load_project(project_id)
            tid = make_id("trk")
            dur_beats = max(bpb, round((asset.durationSec / (60.0 / cur.bpm)), 2))
            cur = commands.apply_command(
                cur,
                "track.add",
                {
                    "id": tid,
                    "name": f"{sr_item['name']}",
                    "type": "stem",
                    "stemLabel": sr_item["role"],
                    "stemMeta": {
                        "sourceReferenceId": ref_id,
                        "separationModel": "htdemucs",
                        "assetKind": "separated_stem",
                    },
                },
            )
            cur = commands.apply_command(
                cur,
                "clip.add",
                {
                    "trackId": tid,
                    "clip": Clip(
                        id=make_id("clp"),
                        name=sr_item["name"],
                        type="audio",
                        assetId=asset.id,
                        timelineStartBeats=0.0,
                        durationBeats=dur_beats,
                        sourceDurationSec=asset.durationSec,
                    ).model_dump(),
                },
            )
            saved = store.save_project(cur, clear_autosave=False, expected_revision=cur.revision)
            created_tracks.append(tid)
            imported_items.append(sr_item["name"])

    event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"레퍼런스 재구성 완료: {', '.join(imported_items[:4])}",
            "project": saved.model_dump(),
        },
    )
    return {
        "reconstructed": True,
        "referenceId": ref_id,
        "importedItems": imported_items,
        "createdTrackIds": created_tracks,
        "limitations": limitations,
        "honestNoteKo": "재구성 결과는 자동 채보 및 스템 분리 기반 편집 자산이며 원본 스튜디오 마스터의 완벽한 복원이 아닙니다. 참고용 원본 오디오는 Export에서 제외됩니다.",
        "project": saved.model_dump(),
        "revision": saved.revision,
    }
