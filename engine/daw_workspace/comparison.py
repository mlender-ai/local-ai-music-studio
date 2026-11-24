"""Phase 02-C: Reference vs Target Audio Comparison (normalized structural & acoustic diff).

Never collapses musical quality into a fake single similarity score; explicitly
separates measured acoustic deltas from actionable production observations.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _quartile_energies(energy_curve: list[dict[str, Any]]) -> list[float]:
    if not energy_curve:
        return [0.0, 0.0, 0.0, 0.0]
    vals = [float(p.get("normEnergy", 0.0)) for p in energy_curve]
    chunks = np.array_split(vals, 4)
    return [round(float(np.mean(c)), 3) if len(c) > 0 else 0.0 for c in chunks]


def compare_analyses(
    ref_name: str,
    ref_analysis: dict[str, Any],
    target_name: str,
    target_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Compare a Reference analysis against a Target (generated/project) analysis."""
    ref_r = ref_analysis.get("rhythm", {})
    tgt_r = target_analysis.get("rhythm", {})
    ref_h = ref_analysis.get("harmony", {})
    tgt_h = target_analysis.get("harmony", {})
    ref_s = ref_analysis.get("sound", {}).get("measured", {})
    tgt_s = target_analysis.get("sound", {}).get("measured", {})

    ref_bands = ref_s.get("frequencyBandsPct", {})
    tgt_bands = tgt_s.get("frequencyBandsPct", {})
    band_deltas = {
        k: round(float(tgt_bands.get(k, 0.0)) - float(ref_bands.get(k, 0.0)), 2)
        for k in ("sub_20_60", "bass_60_200", "low_mid_200_500", "mid_500_2000", "presence_2k_6k", "air_6k_20k")
    }

    ref_bpm = ref_r.get("estimatedBpm")
    tgt_bpm = tgt_r.get("estimatedBpm")
    bpm_delta = round(float(tgt_bpm) - float(ref_bpm), 1) if (ref_bpm and tgt_bpm) else None

    crest_delta = round(float(tgt_s.get("crestFactorDb", 0.0)) - float(ref_s.get("crestFactorDb", 0.0)), 2)
    dyn_delta = round(float(tgt_s.get("dynamicRangeDb", 0.0)) - float(ref_s.get("dynamicRangeDb", 0.0)), 2)
    lufs_delta = round(float(tgt_s.get("approxLufs", 0.0)) - float(ref_s.get("approxLufs", 0.0)), 2)
    width_delta = round(float(tgt_s.get("stereoWidth", 0.0)) - float(ref_s.get("stereoWidth", 0.0)), 3)
    perc_delta = round(float(tgt_s.get("percussiveRatio", 0.0)) - float(ref_s.get("percussiveRatio", 0.0)), 3)
    motif_delta = round(
        float(tgt_h.get("motifRepetitionScore", 0.0)) - float(ref_h.get("motifRepetitionScore", 0.0)), 3
    )

    # Normalized progression quartiles (handles tracks of different lengths fairly)
    ref_q = _quartile_energies(ref_analysis.get("arrangement", {}).get("energyCurve", []))
    tgt_q = _quartile_energies(target_analysis.get("arrangement", {}).get("energyCurve", []))
    quartile_labels = ["0–25% (Opening)", "25–50% (Development)", "50–75% (Middle)", "75–100% (Late / Climax)"]
    progression_comparison = [
        {
            "phase": quartile_labels[i],
            "referenceNormEnergy": ref_q[i],
            "targetNormEnergy": tgt_q[i],
            "delta": round(tgt_q[i] - ref_q[i], 3),
        }
        for i in range(4)
    ]

    # Actionable, strictly measurement-backed observations (never fabricated!)
    observations: list[dict[str, str]] = []

    if band_deltas["low_mid_200_500"] >= 4.0:
        observations.append(
            {
                "category": "frequency",
                "ko": f"대상 음원의 저중역(200–500 Hz) 에너지가 레퍼런스보다 +{band_deltas['low_mid_200_500']}% 높습니다 (먹먹함 원인 후보).",
                "en": f"Target has +{band_deltas['low_mid_200_500']}% more low-mid (200–500 Hz) energy than reference.",
            }
        )
    elif band_deltas["low_mid_200_500"] <= -4.0:
        observations.append(
            {
                "category": "frequency",
                "ko": f"대상 음원의 저중역(200–500 Hz) 에너지가 레퍼런스보다 {band_deltas['low_mid_200_500']}% 낮습니다.",
                "en": f"Target has {band_deltas['low_mid_200_500']}% less low-mid (200–500 Hz) energy than reference.",
            }
        )

    low_delta = round(band_deltas["sub_20_60"] + band_deltas["bass_60_200"], 2)
    if abs(low_delta) >= 5.0:
        observations.append(
            {
                "category": "bass",
                "ko": f"저역(20–200 Hz) 비중이 레퍼런스 대비 {low_delta:+.1f}% 차이납니다.",
                "en": f"Low-end (20–200 Hz) share differs by {low_delta:+.1f}% vs reference.",
            }
        )

    if crest_delta <= -2.0 or perc_delta <= -0.08:
        observations.append(
            {
                "category": "transients",
                "ko": f"레퍼런스보다 드럼·트랜지언트 타격감이 약합니다 (Crest {crest_delta:+.1f} dB, 퍼커시브 비중 {perc_delta:+.2f}).",
                "en": f"Drum/transient punch is lower than reference (Crest {crest_delta:+.1f} dB, percussive ratio {perc_delta:+.2f}).",
            }
        )
    elif crest_delta >= 2.0:
        observations.append(
            {
                "category": "transients",
                "ko": f"대상 음원의 트랜지언트 피크 대비 RMS 차이(Crest Factor)가 레퍼런스보다 +{crest_delta:.1f} dB 큽니다.",
                "en": f"Target Crest Factor is +{crest_delta:.1f} dB higher (more transient/less dense) than reference.",
            }
        )

    if dyn_delta <= -2.0:
        observations.append(
            {
                "category": "dynamics",
                "ko": f"구간별 다이내믹 변화 폭이 레퍼런스보다 {abs(dyn_delta):.1f} dB 작습니다.",
                "en": f"Section-to-section dynamic range is {abs(dyn_delta):.1f} dB narrower than reference.",
            }
        )

    climax_delta = round(tgt_q[3] - ref_q[3], 3)
    if abs(climax_delta) >= 0.12:
        observations.append(
            {
                "category": "arrangement",
                "ko": f"후반부(75–100%) 상대 에너지가 레퍼런스 대비 {climax_delta:+.2f} 차이납니다.",
                "en": f"Late-section (75–100%) relative energy differs by {climax_delta:+.2f} vs reference.",
            }
        )

    if abs(width_delta) >= 0.12:
        observations.append(
            {
                "category": "stereo",
                "ko": f"스테레오 폭이 레퍼런스 대비 {width_delta:+.2f} 차이납니다 ({'더 넓음' if width_delta > 0 else '더 좁음'}).",
                "en": f"Stereo width differs by {width_delta:+.2f} vs reference ({'wider' if width_delta > 0 else 'narrower'}).",
            }
        )

    if bpm_delta is not None and abs(bpm_delta) >= 2.0:
        observations.append(
            {
                "category": "tempo",
                "ko": f"추정 템포 차이: 레퍼런스 {ref_bpm} BPM vs 대상 {tgt_bpm} BPM ({bpm_delta:+.1f} BPM).",
                "en": f"Estimated tempo delta: Reference {ref_bpm} BPM vs Target {tgt_bpm} BPM ({bpm_delta:+.1f} BPM).",
            }
        )

    if not observations:
        observations.append(
            {
                "category": "summary",
                "ko": "측정된 주파수 균형·다이내믹·트랜지언트 지표가 레퍼런스와 대체로 유사한 범위에 있습니다.",
                "en": "Measured frequency balance, dynamics, and transient metrics fall within a similar range to reference.",
            }
        )

    return {
        "referenceName": ref_name,
        "targetName": target_name,
        "referenceDurationSec": ref_analysis.get("durationSec"),
        "targetDurationSec": target_analysis.get("durationSec"),
        "measuredDeltas": {
            "bpmDelta": bpm_delta,
            "referenceKey": ref_h.get("estimatedKey"),
            "targetKey": tgt_h.get("estimatedKey"),
            "frequencyBandsDeltaPct": band_deltas,
            "crestFactorDeltaDb": crest_delta,
            "dynamicRangeDeltaDb": dyn_delta,
            "approxLufsDelta": lufs_delta,
            "stereoWidthDelta": width_delta,
            "percussiveRatioDelta": perc_delta,
            "motifRepetitionDelta": motif_delta,
        },
        "normalizedProgression": progression_comparison,
        "observations": observations,
        "methodologyNote": "길이가 다른 두 음원은 4단계 정규화 전개(0–100%)와 실측 음향 지표로 비교하며, 단일 유사도 점수로 단순화하지 않습니다.",
    }
