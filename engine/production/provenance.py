"""Canonical Generation Provenance Builder (Phase 05.1 · Section 14.3)."""

from __future__ import annotations

from typing import Any

from engine.daw_workspace.schema import utc_now_iso


def build_generation_provenance(
    *,
    requested_engine: str,
    routed_engine: str,
    actual_engine: str,
    production_mode: str,
    mode: str,
    policy_snapshot: dict[str, Any] | None = None,
    model_version: str | None = None,
    seed: int | None = None,
    plan_id: str | None = None,
    reference_ids: list[str] | None = None,
    abc_score_source: str | None = None,
    cot_mode: str | None = None,
    cfg_scale: float | None = None,
    semantic_temperature: float | None = None,
    runtime_log_path: str | None = None,
    semantic_tokens_path: str | None = None,
    instrument_resolutions: list[dict[str, Any]] | None = None,
    silent_fallback_occurred: bool = False,
) -> dict[str, Any]:
    """Build structured, auditable Generation Provenance attached to Plans, Takes, and Reports."""
    return {
        "schemaVersion": 1,
        "recordedAt": utc_now_iso(),
        "requestedEngine": requested_engine,
        "routedEngine": routed_engine,
        "actualEngine": actual_engine,
        "productionMode": production_mode,
        "compositionMode": mode,
        "modelVersion": model_version,
        "seed": seed,
        "planId": plan_id,
        "referenceIds": list(reference_ids or []),
        "silentFallbackOccurred": bool(silent_fallback_occurred),
        "yue2Workflow": (
            {
                "abcScoreSource": abc_score_source,
                "cot": cot_mode,
                "cfgScale": cfg_scale,
                "semanticTemperature": semantic_temperature,
                "runtimeLogPath": runtime_log_path,
                "semanticTokensPath": semantic_tokens_path,
            }
            if actual_engine == "yue2-native"
            else None
        ),
        "instrumentResolutions": list(instrument_resolutions or []),
        "policyEnforced": {
            "defaultFullMusicEngine": (policy_snapshot or {}).get("defaultFullMusicEngine", "yue2-native"),
            "allowSilentMidiFallback": bool((policy_snapshot or {}).get("allowSilentMidiFallback", False)),
            "allowPreviewInstrumentsInProduction": bool(
                (policy_snapshot or {}).get("allowPreviewInstrumentsInProduction", False)
            ),
            "instrumentalByDefault": bool((policy_snapshot or {}).get("instrumentalByDefault", True)),
            "preserveNativeAudio": bool((policy_snapshot or {}).get("preserveNativeAudio", True)),
        },
    }
