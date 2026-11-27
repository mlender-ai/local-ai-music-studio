"""Permanent Production Quality Policy & Engine Routing Single Source of Truth (Phase 05.1 · Sections 6, 7, 14).

Enforced identically across DAW UI, REST API, MCP Tools, Claude Code, Codex, and Antigravity:
- Default full-music generation engine is `yue2-native`.
- Silent MIDI fallback is strictly forbidden (`allowSilentMidiFallback: false`).
- Preview-tier lightweight synths are blocked from automatic selection in production (`allowPreviewInstrumentsInProduction: false`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.runtime import get_runtime_registry

POLICY_DIR = engine_paths.ROOT / "config" / "production"


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return dict(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)


DEFAULT_POLICY_FALLBACK: dict[str, Any] = {
    "schemaVersion": 1,
    "policyId": "ai-native-daw-permanent-production-policy",
    "defaultFullMusicEngine": "yue2-native",
    "allowSilentMidiFallback": False,
    "allowPreviewInstrumentsInProduction": False,
    "preserveNativeAudio": True,
    "instrumentalByDefault": True,
    "autoSoundDesign": True,
    "requireActualAudioRender": True,
    "requireEngineProvenance": True,
    "preserveOriginalTake": True,
    "requireUserApprovalForPaidServices": True,
    "shortValidationDurationSec": {"min": 15, "default": 22, "max": 30},
}


def load_production_policy() -> dict[str, Any]:
    data = _read_json(POLICY_DIR / "default_policy.json", DEFAULT_POLICY_FALLBACK)
    merged = dict(DEFAULT_POLICY_FALLBACK)
    merged.update(data)
    return merged


def load_engine_routing() -> dict[str, Any]:
    return _read_json(POLICY_DIR / "engine_routing.json", {"schemaVersion": 1, "routes": {}})


def load_instrument_quality_policy() -> dict[str, Any]:
    return _read_json(
        POLICY_DIR / "instrument_quality.json",
        {"schemaVersion": 1, "tiers": {}, "instrumentTiers": {}, "userApprovedInstruments": []},
    )


def get_full_production_policy_snapshot() -> dict[str, Any]:
    """Return full persistent policy, routing rules, instrument quality tiers, and runtime readiness."""
    policy = load_production_policy()
    routing = load_engine_routing()
    inst_quality = load_instrument_quality_policy()
    runtime = get_runtime_registry()
    yue2 = next((e for e in runtime.get("engines", []) if e.get("id") == "yue2-native"), None)
    return {
        "policy": policy,
        "engineRouting": routing,
        "instrumentQuality": inst_quality,
        "yue2Status": {
            "available": bool(yue2 and yue2.get("available")),
            "verified": bool(yue2 and yue2.get("verified")),
            "state": yue2.get("state") if yue2 else "uninstalled",
            "runtimeStatus": yue2.get("runtimeStatus") if yue2 else "NOT_INSTALLED",
        },
    }


def validate_instrument_selection(
    instrument_ref: str,
    *,
    production_mode: bool = True,
    allow_preview: bool = False,
    explicit_user_request: bool = False,
) -> dict[str, Any]:
    """Validate whether an instrument may be selected under Permanent Production Policy."""
    policy = load_production_policy()
    qpol = load_instrument_quality_policy()
    tiers_map: dict[str, str] = dict(qpol.get("instrumentTiers") or {})
    approved: set[str] = set(qpol.get("userApprovedInstruments") or [])

    if instrument_ref in approved:
        tier = "USER_APPROVED"
    else:
        tier = str(tiers_map.get(instrument_ref, "PRODUCTION_CANDIDATE"))

    if tier == "PREVIEW" and production_mode and not (
        allow_preview or explicit_user_request or bool(policy.get("allowPreviewInstrumentsInProduction", False))
    ):
        return {
            "allowed": False,
            "instrumentRef": instrument_ref,
            "qualityTier": tier,
            "reasonKo": (
                f"'{instrument_ref}'는 PREVIEW(초경량 미리듣기) 등급 악기입니다. "
                "영구 프로덕션 품질 정책에 따라 자동 선택이 차단되었습니다. "
                "프로덕션 후보 악기(SF3 / Pro Synth / Drum Rack / Sampler)를 사용하거나, 사용자가 명시적으로 Preview 사용을 허용해야 합니다."
            ),
            "reasonEn": (
                f"'{instrument_ref}' is a PREVIEW-tier lightweight voice blocked from automatic production selection "
                "by Permanent Production Policy. Use a PRODUCTION_CANDIDATE/USER_APPROVED instrument or pass explicit allowPreviewInstruments=true."
            ),
        }

    return {
        "allowed": True,
        "instrumentRef": instrument_ref,
        "qualityTier": tier,
        "overrideUsed": bool(tier == "PREVIEW" and (allow_preview or explicit_user_request)),
        "reasonKo": f"'{instrument_ref}' ({tier}) 선택 허용됨.",
        "reasonEn": f"'{instrument_ref}' ({tier}) allowed.",
    }


def resolve_production_route(
    *,
    mode: str = "full_music",
    engine_choice: str = "auto",
    production_mode: str | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    instruction: str = "",
) -> dict[str, Any]:
    """Single source of truth for Music Production Engine Routing (Section 6 & 14).

    Guarantees:
    - Full Music requests default to `yue2-native` (`neural_audio`).
    - When `yue2-native` is unavailable or unready, returns `policyAction="block_engine_unavailable"`
      and NEVER silently falls back to `local-multitrack-composer`.
    - Explicit MIDI / Note Editing (`editable_midi`, `loop_midi`, `instrument_session`, `local-multitrack-composer`,
      `midi-composer-v3`) explicitly routes to MIDI engine with Pro Instrument enforcement.
    - Strict event-level locks (`drum_rhythm=locked` or `bass_groove=locked` or `reconstruct`) warn honestly
      when paired with `yue2-native` because YuE2 cannot hard-guarantee note-level drum/bass locks.
    """
    policy = load_production_policy()
    routing = load_engine_routing()
    runtime = get_runtime_registry()
    yue2 = next((e for e in runtime.get("engines", []) if e.get("id") == "yue2-native"), None) or {
        "available": False,
        "state": "uninstalled",
        "runtimeStatus": "NOT_INSTALLED",
        "missingItems": ["yue-synth", "YuE2-3B-Q8_0.gguf", "YuE2-Vae-F32.gguf"],
        "statusNoteKo": "YuE2 런타임이 준비되지 않았습니다.",
        "statusNoteEn": "YuE2 native runtime is not available.",
    }
    acestep = next((e for e in runtime.get("engines", []) if e.get("id") == "ace-step-local"), None) or {
        "available": False,
        "state": "uninstalled",
        "missingItems": [],
    }

    default_engine = str(policy.get("defaultFullMusicEngine", "yue2-native"))
    allow_silent_fallback = bool(policy.get("allowSilentMidiFallback", False))
    low_inst = instruction.lower()
    locks = dict(feature_locks or {})

    # Normalize aliases
    normalized_engine = (engine_choice or "auto").strip()
    if normalized_engine == "local-midi-composer":
        normalized_engine = "local-multitrack-composer"

    explicit_midi_requested = (
        normalized_engine in ("local-multitrack-composer", "midi-composer-v3", "editable_midi")
        or production_mode == "editable_midi"
        or mode in ("loop_midi", "instrument_session")
        or any(
            k in low_inst
            for k in (
                "midi로만",
                "미디로만",
                "편집 가능 midi",
                "editable midi",
                "midi note",
                "노트 편집",
                "피아노 롤",
                "piano roll",
            )
        )
    )

    explicit_acestep_requested = normalized_engine == "ace-step-local"
    explicit_hybrid_requested = production_mode == "hybrid" or normalized_engine == "hybrid"

    warnings_ko: list[str] = []
    warnings_en: list[str] = []
    has_strict_event_lock = (
        reference_mode == "reconstruct"
        or locks.get("drum_rhythm") == "locked"
        or locks.get("bass_groove") == "locked"
    )

    # 1. Explicit ACE-Step request
    if explicit_acestep_requested:
        if acestep.get("available"):
            return {
                "policyAction": "execute_acestep",
                "engineUnavailable": False,
                "requestedEngine": normalized_engine,
                "routedEngine": "ace-step-local",
                "productionMode": "neural_audio",
                "silentFallbackBlocked": False,
                "reasonKo": "사용자 명시 요청으로 ACE-Step 로컬 확산 엔진을 사용합니다.",
                "reasonEn": "Using explicitly requested ACE-Step local diffusion engine.",
                "alternatives": [],
                "warningsKo": warnings_ko,
                "warningsEn": warnings_en,
                "policyApplied": policy,
            }
        return {
            "policyAction": "block_engine_unavailable",
            "engineUnavailable": True,
            "requestedEngine": "ace-step-local",
            "routedEngine": None,
            "productionMode": "neural_audio",
            "state": acestep.get("state", "uninstalled"),
            "missingItems": acestep.get("missingItems", []),
            "silentFallbackBlocked": True,
            "suggestedAlternative": "yue2-native" if yue2.get("available") else "local-multitrack-composer",
            "messageKo": f"{acestep.get('statusNoteKo', 'ACE-Step 미설치.')} 미설치 상태에서 MIDI로 자동 대체하지 않습니다.",
            "messageEn": f"{acestep.get('statusNoteEn', 'ACE-Step unavailable.')} Refusing silent MIDI fallback.",
            "alternatives": routing.get("routes", {}).get("full_music", {}).get("alternatives", []),
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # 2. Explicit Editable MIDI / Loop / Instrument Session request
    if explicit_midi_requested and normalized_engine not in ("yue2-native", "neural_audio"):
        midi_engine = "midi-composer-v3" if mode in ("loop_midi", "instrument_session") else "local-multitrack-composer"
        return {
            "policyAction": "execute_midi",
            "engineUnavailable": False,
            "requestedEngine": normalized_engine,
            "routedEngine": midi_engine,
            "productionMode": "editable_midi",
            "silentFallbackBlocked": False,
            "reasonKo": (
                "편집 가능한 MIDI / 단일 악기 세션 모드 요청에 따라 프로덕션 등급 가상악기(SF3 / Pro Synth / Drum Rack) 기반 MIDI 엔진을 사용합니다."
            ),
            "reasonEn": (
                "Routing to Editable MIDI engine with Production-tier instruments (SF3 / Pro Synth / Drum Rack)."
            ),
            "alternatives": [],
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # 3. Hybrid mode
    if explicit_hybrid_requested:
        return {
            "policyAction": "execute_hybrid",
            "engineUnavailable": False,
            "requestedEngine": normalized_engine,
            "routedEngine": "yue2-native" if yue2.get("available") else "local-multitrack-composer",
            "productionMode": "hybrid",
            "silentFallbackBlocked": False,
            "reasonKo": "하이브리드 제작 모드: 원본 네이티브 오디오를 보존하면서 프로덕션 가상악기·스템 레이어를 결합합니다.",
            "reasonEn": "Hybrid production mode: preserve native audio untouched while layering production virtual instruments or stems.",
            "alternatives": [],
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # 4. Exact Event/Groove Lock Routing (engine_routing.json -> compatible_controlled when engine_choice == "auto")
    if has_strict_event_lock and normalized_engine == "auto":
        warnings_ko.append(
            "드럼 리듬·베이스 그루브 완전 고정(LOCK) 또는 재구성(reconstruct) 요청은 YuE2 Native Audio 단독으로 이벤트 단위 고정을 보장할 수 없어 "
            "호환 제어 경로(Editable MIDI + Pro Virtual Instruments)로 라우팅했습니다."
        )
        warnings_en.append(
            "Strict drum/bass LOCK or reconstruct requested with engine='auto': routed to compatible controlled MIDI path "
            "because YuE2 Native Audio cannot hard-guarantee exact note-level event locks."
        )
        return {
            "policyAction": "execute_midi",
            "engineUnavailable": False,
            "requestedEngine": normalized_engine,
            "routedEngine": "local-multitrack-composer",
            "productionMode": "editable_midi",
            "silentFallbackBlocked": False,
            "reasonKo": warnings_ko[-1],
            "reasonEn": warnings_en[-1],
            "alternatives": [],
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # 5. Full Music Generation -> YuE2 First Policy!
    if has_strict_event_lock:
        warnings_ko.append(
            "정확한 드럼 타점·베이스 음표 완전 고정(LOCK)은 YuE2 Native Audio가 100% 보장하지 못합니다. "
            "완전한 이벤트 고정이 필요하면 Hybrid 또는 Editable MIDI 모드로 전환하세요."
        )
        warnings_en.append(
            "YuE2 Native Audio cannot hard-guarantee exact note-level drum/bass LOCK constraints; "
            "switch to Hybrid or Editable MIDI for strict event-level locking."
        )

    if yue2.get("available"):
        return {
            "policyAction": "execute_yue2",
            "engineUnavailable": False,
            "requestedEngine": normalized_engine,
            "routedEngine": default_engine,
            "productionMode": "neural_audio",
            "silentFallbackBlocked": False,
            "reasonKo": (
                f"영구 프로덕션 품질 정책(YuE2 First)에 따라 기본 풀 음악 생성 엔진으로 '{default_engine}' "
                f"({yue2.get('runtimeStatus', yue2.get('state'))})를 선택했습니다."
            ),
            "reasonEn": (
                f"Permanent Production Policy (YuE2 First) routed full music generation to '{default_engine}' "
                f"({yue2.get('runtimeStatus', yue2.get('state'))})."
            ),
            "alternatives": routing.get("routes", {}).get("full_music", {}).get("alternatives", []),
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # YuE2 is NOT available! Strictly obey allowSilentMidiFallback=false!
    if not allow_silent_fallback:
        alts = routing.get("routes", {}).get("full_music", {}).get("alternatives", [])
        return {
            "policyAction": "block_engine_unavailable",
            "engineUnavailable": True,
            "requestedEngine": default_engine if normalized_engine == "auto" else normalized_engine,
            "routedEngine": None,
            "productionMode": "neural_audio",
            "state": yue2.get("state", "uninstalled"),
            "runtimeStatus": yue2.get("runtimeStatus", "NOT_INSTALLED"),
            "missingItems": yue2.get("missingItems", []),
            "silentFallbackBlocked": True,
            "suggestedAlternative": "editable_midi",
            "alternatives": alts,
            "messageKo": (
                f"기본 음악 생성 엔진 YuE2 Native Audio를 사용할 수 없습니다 ({yue2.get('state', 'uninstalled')}). "
                f"{yue2.get('statusNoteKo', '')} "
                "영구 프로덕션 품질 정책(allowSilentMidiFallback=false)에 따라 저품질 MIDI로 몰래 대체하지 않고 대기합니다. "
                "YuE2 런타임을 복구하거나, 원하시면 '편집 가능 MIDI + 프로 가상악기' 또는 '하이브리드' 모드를 명시적으로 선택해 주세요."
            ),
            "messageEn": (
                f"Default full-music engine YuE2 Native Audio is unavailable ({yue2.get('state', 'uninstalled')}). "
                "Permanent Production Policy (allowSilentMidiFallback=false) forbids silent MIDI fallback. "
                "Restore YuE2 runtime or explicitly choose Editable MIDI + Pro Instruments or Hybrid mode."
            ),
            "warningsKo": warnings_ko,
            "warningsEn": warnings_en,
            "policyApplied": policy,
        }

    # Only reachable if user explicitly edited default_policy.json to allowSilentMidiFallback=true
    return {
        "policyAction": "execute_midi",
        "engineUnavailable": False,
        "requestedEngine": normalized_engine,
        "routedEngine": "local-multitrack-composer",
        "productionMode": "editable_midi",
        "silentFallbackBlocked": False,
        "reasonKo": "사용자 정책 오버라이드에 따라 로컬 MIDI 엔진으로 폴백했습니다.",
        "reasonEn": "Fallback to local MIDI engine permitted by explicit policy override.",
        "alternatives": [],
        "warningsKo": warnings_ko,
        "warningsEn": warnings_en,
        "policyApplied": policy,
    }
