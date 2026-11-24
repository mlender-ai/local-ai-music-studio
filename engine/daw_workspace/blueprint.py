"""Reference Blueprint builder — structured musical design data for future composition."""

from __future__ import annotations

from typing import Any

from .analysis import ANALYSIS_VERSION

DEFAULT_INFLUENCES = [
    {"id": "drums_groove", "labelKo": "드럼 그루브", "labelEn": "Drum Groove", "selected": True},
    {"id": "bass_movement", "labelKo": "베이스 움직임", "labelEn": "Bass Movement", "selected": True},
    {"id": "instrumentation", "labelKo": "악기 구성", "labelEn": "Instrumentation", "selected": True},
    {"id": "melody_density", "labelKo": "멜로디·리듬 밀도", "labelEn": "Melody & Rhythm Density", "selected": False},
    {"id": "arrangement_arc", "labelKo": "구간 전개 & 하이라이트", "labelEn": "Arrangement Arc & Climax", "selected": True},
    {"id": "timbre_tone", "labelKo": "음색·주파수 질감", "labelEn": "Timbre & Tonal Balance", "selected": False},
    {"id": "spatial_depth", "labelKo": "공간감 & 스테레오", "labelEn": "Spatial Depth & Stereo", "selected": False},
    {"id": "mood_energy", "labelKo": "전체 에너지·정서", "labelEn": "Overall Energy & Mood", "selected": True},
]


def build_reference_blueprint(
    analysis: dict[str, Any],
    existing_influences: list[str] | None = None,
) -> dict[str, Any]:
    """Convert raw acoustic ReferenceAnalysis into a structured ReferenceBlueprint."""
    rhythm = analysis.get("rhythm", {})
    harmony = analysis.get("harmony", {})
    arrangement = analysis.get("arrangement", {})
    sound_m = analysis.get("sound", {}).get("measured", {})
    sound_e = analysis.get("sound", {}).get("estimated", {})
    inst = analysis.get("instrumentation", {})

    selected_set = (
        set(existing_influences)
        if existing_influences is not None
        else {item["id"] for item in DEFAULT_INFLUENCES if item["selected"]}
    )

    confident_chords = [
        c["chord"]
        for c in harmony.get("chordProgression", [])[:8]
        if c.get("chord") and c["chord"] != "uncertain"
    ]

    return {
        "sourceAssetId": analysis.get("sourceAssetId"),
        "analysisVersion": analysis.get("analysisVersion", ANALYSIS_VERSION),
        "tempo": {
            "bpm": rhythm.get("estimatedBpm"),
            "candidates": rhythm.get("candidates", []),
            "halfDoubleAmbiguous": rhythm.get("halfDoubleAmbiguous", False),
        },
        "meter": rhythm.get("meterEstimate", "4/4"),
        "harmonicCharacter": {
            "key": harmony.get("estimatedKey", "Uncertain"),
            "modeCandidates": harmony.get("modeCandidates", [])[:3],
            "sampleChords": confident_chords[:8],
            "harmonicShiftCount": len(harmony.get("harmonicChangeTimesSec", [])),
        },
        "rhythmProfile": {
            "onsetDensityPerSec": rhythm.get("onsetDensityPerSec", 0.0),
            "regularity": rhythm.get("regularity", 0.0),
            "accentPattern": rhythm.get("accentPattern", []),
        },
        "grooveProfile": {
            "swingRatio": rhythm.get("swingRatio", 0.5),
            "feel": rhythm.get("grooveFeel", "straight"),
        },
        "instrumentation": {
            "isEstimated": True,
            "elements": inst.get("elements", []),
        },
        "motifCharacteristics": {
            "repetitionScore": harmony.get("motifRepetitionScore", 0.0),
            "description": (
                "Strong repeating harmonic/melodic motif detected"
                if harmony.get("motifRepetitionScore", 0.0) >= 0.72
                else "Moderate or evolving harmonic motif"
            ),
        },
        "arrangementTimeline": arrangement.get("sections", []),
        "energyCurve": arrangement.get("energyCurve", []),
        "timbreProfile": {
            "frequencyBandsPct": sound_m.get("frequencyBandsPct", {}),
            "spectralCentroidHz": sound_m.get("spectralCentroidHz", 0.0),
            "transientCharacter": sound_e.get("transientCharacter", "controlled"),
        },
        "spatialProfile": {
            "stereoWidth": sound_m.get("stereoWidth", 0.0),
            "lrCorrelation": sound_m.get("lrCorrelation", 1.0),
            "reverbCharacter": sound_e.get("reverbCharacter", "balanced room"),
        },
        "productionCharacteristics": {
            "crestFactorDb": sound_m.get("crestFactorDb", 0.0),
            "dynamicRangeDb": sound_m.get("dynamicRangeDb", 0.0),
            "approxLufs": sound_m.get("approxLufs", -24.0),
            "samplePeakDbfs": sound_m.get("samplePeakDbfs", -6.0),
        },
        "confidence": {
            "tempo": rhythm.get("regularity", 0.0),
            "harmony": harmony.get("confidence", 0.0),
            "overall": round(
                0.5 * float(rhythm.get("regularity", 0.0)) + 0.5 * float(harmony.get("confidence", 0.0)),
                3,
            ),
        },
        "selectedInfluences": sorted(selected_set),
        "availableInfluences": DEFAULT_INFLUENCES,
        "guidanceNote": "이 설계도는 원본을 복제하기 위한 데이터가 아니라 새 오리지널 작곡/편곡 시 참고할 음악적 특성 지표입니다.",
    }
