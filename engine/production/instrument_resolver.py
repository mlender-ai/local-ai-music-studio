"""Production Instrument Resolver & Quality Tier Classification (Phase 05.1 · Section 7).

Queries Instrument Registry + Quality Policy + User Taste Profile so production tasks NEVER
auto-select legacy Phase 03 PREVIEW voices (`drum-kit-electronic`, `bass-fm-sub`, `keys-electric-ep`,
`guitar-clean-pluck`, `synth-fm-hook`, `pad-warm-analog`, `basic-poly-synth`).
"""

from __future__ import annotations

from typing import Any

from engine.instruments.soundfont_engine import probe_fluidsynth_engine

from .policy import load_instrument_quality_policy, load_production_policy

PREVIEW_INSTRUMENT_IDS = frozenset(
    (
        "drum-kit-electronic",
        "bass-fm-sub",
        "keys-electric-ep",
        "guitar-clean-pluck",
        "synth-fm-hook",
        "pad-warm-analog",
        "basic-poly-synth",
    )
)


def get_instrument_quality_tier(
    instrument_ref: str,
    *,
    runtime_available: bool = True,
) -> dict[str, Any]:
    """Return canonical Instrument Quality Tier (`PREVIEW | PRODUCTION_CANDIDATE | USER_APPROVED | UNAVAILABLE`)."""
    qpol = load_instrument_quality_policy()
    tiers_map: dict[str, str] = dict(qpol.get("instrumentTiers") or {})
    approved: set[str] = set(qpol.get("userApprovedInstruments") or [])

    if not runtime_available:
        tier = "UNAVAILABLE"
    elif instrument_ref in approved:
        tier = "USER_APPROVED"
    elif instrument_ref in tiers_map:
        tier = str(tiers_map[instrument_ref])
    elif instrument_ref in PREVIEW_INSTRUMENT_IDS:
        tier = "PREVIEW"
    else:
        tier = "PRODUCTION_CANDIDATE"

    tier_spec = (qpol.get("tiers") or {}).get(tier) or {}
    return {
        "instrumentRef": instrument_ref,
        "qualityTier": tier,
        "autoSelectInProduction": bool(tier_spec.get("autoSelectInProduction", tier in ("PRODUCTION_CANDIDATE", "USER_APPROVED"))),
        "descriptionKo": str(tier_spec.get("descriptionKo") or ""),
        "descriptionEn": str(tier_spec.get("descriptionEn") or ""),
    }


def resolve_production_instrument(
    role: str,
    *,
    genre: str = "rnb_neosoul",
    instruction: str = "",
    allow_preview: bool = False,
    explicit_instrument_ref: str | None = None,
    taste_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the highest-tier available instrument for a musical role without ever auto-picking PREVIEW voices."""
    policy = load_production_policy()
    qpol = load_instrument_quality_policy()
    fs_avail = bool(probe_fluidsynth_engine().get("available"))
    role_notes = (qpol.get("roleRealismNotes") or {}).get(role) or {}
    low_inst = instruction.lower()

    # If caller explicitly named an instrument, validate against policy!
    if explicit_instrument_ref:
        is_sf = explicit_instrument_ref.startswith("sf-")
        avail = fs_avail if is_sf else True
        tier_info = get_instrument_quality_tier(explicit_instrument_ref, runtime_available=avail)
        if tier_info["qualityTier"] == "PREVIEW" and not (
            allow_preview or bool(policy.get("allowPreviewInstrumentsInProduction", False))
        ):
            raise ValueError(
                f"Instrument '{explicit_instrument_ref}' is PREVIEW tier and blocked in production mode. "
                "Choose a PRODUCTION_CANDIDATE/USER_APPROVED instrument or explicitly set allowPreviewInstruments=true."
            )
        if tier_info["qualityTier"] == "UNAVAILABLE":
            raise ValueError(f"Requested instrument '{explicit_instrument_ref}' is UNAVAILABLE in current runtime.")
        return {
            "role": role,
            "instrumentRef": explicit_instrument_ref,
            "preset": None,
            "qualityTier": tier_info["qualityTier"],
            "autoSelectInProduction": tier_info["autoSelectInProduction"],
            "rationaleKo": f"명시 요청 악기 '{explicit_instrument_ref}' ({tier_info['qualityTier']}) 선택.",
            "rationaleEn": f"Selected explicitly requested instrument '{explicit_instrument_ref}' ({tier_info['qualityTier']}).",
            "limitationNoteKo": role_notes.get("limitationKo"),
            "limitationNoteEn": role_notes.get("limitationEn"),
            "alternatives": [],
        }

    # Check Taste Profile preferred instruments for this role if any
    preferred_by_role = ((taste_profile or {}).get("preferredInstruments") or {})
    candidates: list[dict[str, Any]] = []
    if role in preferred_by_role and preferred_by_role[role]:
        candidates.append({"instrumentRef": str(preferred_by_role[role]), "defaultPreset": None})

    role_priorities = list((qpol.get("roleProductionPriority") or {}).get(role) or [])
    candidates.extend(role_priorities)

    # Smart genre/prompt-sensitive tweaks (still strictly PRODUCTION_CANDIDATE or USER_APPROVED!)
    if role == "keys" and any(k in low_inst for k in ("그랜드", "grand", "어쿠스틱 피아노", "acoustic piano")):
        candidates.insert(0, {"instrumentRef": "sf-piano-grand", "defaultPreset": "concert_grand"})
    elif role == "keys" and any(k in low_inst for k in ("오르간", "organ", "b3")):
        candidates.insert(0, {"instrumentRef": "sf-organ-vintage", "defaultPreset": "drawbar"})
    elif role == "guitar" and any(k in low_inst for k in ("펑크", "funk", "뮤트", "mute")):
        candidates.insert(0, {"instrumentRef": "sf-guitar-clean", "defaultPreset": "muted_funk"})
    elif role == "guitar" and any(k in low_inst for k in ("어쿠스틱 기타", "acoustic guitar", "나일론", "nylon")):
        candidates.insert(0, {"instrumentRef": "sf-guitar-clean", "defaultPreset": "acoustic_nylon"})
    elif role == "guitar" and any(k in low_inst for k in ("클린", "clean", "스트랫", "strat")):
        candidates.insert(0, {"instrumentRef": "sf-guitar-clean", "defaultPreset": "clean_strat"})
    elif role == "bass" and any(k in low_inst for k in ("업라이트", "upright", "콘트라베이스", "재즈 베이스", "acoustic bass")):
        candidates.insert(0, {"instrumentRef": "sf-bass-electric", "defaultPreset": "upright"})
    elif role == "bass" and any(k in low_inst for k in ("서브", "sub", "신스 베이스", "synth bass", "808", "하우스", "house")):
        candidates.insert(0, {"instrumentRef": "pro-synth-analog", "defaultPreset": "deep-sub-bass"})

    alternatives: list[str] = []
    selected: dict[str, Any] | None = None

    for cand in candidates:
        cid = str(cand["instrumentRef"])
        is_sf = cid.startswith("sf-")
        avail = fs_avail if is_sf else True
        tier_info = get_instrument_quality_tier(cid, runtime_available=avail)
        if not avail or tier_info["qualityTier"] in ("UNAVAILABLE", "PREVIEW"):
            continue
        preset = (cand.get("genrePresets") or {}).get(genre) or cand.get("defaultPreset")
        if selected is None:
            selected = {
                "role": role,
                "instrumentRef": cid,
                "preset": preset,
                "qualityTier": tier_info["qualityTier"],
                "autoSelectInProduction": True,
                "rationaleKo": (
                    f"역할 '{role}'(장르: {genre})에 대해 PREVIEW 악기를 배제하고 "
                    f"{tier_info['qualityTier']} 등급 '{cid}'" + (f" (프리셋: {preset})" if preset else "") + "을 선택했습니다."
                ),
                "rationaleEn": (
                    f"Resolved role '{role}' ({genre}) to {tier_info['qualityTier']} '{cid}'"
                    + (f" (preset: {preset})" if preset else "")
                    + ", blocking PREVIEW voices."
                ),
                "limitationNoteKo": role_notes.get("limitationKo"),
                "limitationNoteEn": role_notes.get("limitationEn"),
            }
        elif cid not in alternatives:
            alternatives.append(cid)

    if selected is not None:
        selected["alternatives"] = alternatives
        return selected

    # No FluidSynth / SF3 and role wasn't synth/drum-rack -> choose pro-synth-analog (never PREVIEW unless allowed)
    fallback_pro = "pro-drum-rack" if role == "drums" else "pro-synth-analog"
    tier_info = get_instrument_quality_tier(fallback_pro, runtime_available=True)
    return {
        "role": role,
        "instrumentRef": fallback_pro,
        "preset": "boombap-vintage" if fallback_pro == "pro-drum-rack" else "warm-analog-pluck",
        "qualityTier": tier_info["qualityTier"],
        "autoSelectInProduction": True,
        "rationaleKo": (
            f"역할 '{role}'의 SoundFont(SF3) 런타임이 없어 PREVIEW 대신 {tier_info['qualityTier']} '{fallback_pro}'를 선택했습니다."
        ),
        "rationaleEn": f"SoundFont unavailable for role '{role}'; selected {tier_info['qualityTier']} '{fallback_pro}' instead of PREVIEW.",
        "limitationNoteKo": role_notes.get("limitationKo")
        or "FluidSynth SF3 미사용 환경에서는 실제 멀티샘플 악기 질감이 제한됩니다.",
        "limitationNoteEn": role_notes.get("limitationEn")
        or "Without FluidSynth SF3, realistic multi-sampled acoustic realism is limited.",
        "alternatives": [],
    }
