"""Persistent User Music Taste & Feedback Profile (Phase 05.1 · Section 15).

Stores durable, inspectable, editable, resettable user musical preferences and past feedback locally
under `outputs/daw/taste_profile.json` (gitignored, never hardcoded into personal paths).
Separates Global Taste Profile from Project-specific overrides.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.daw_workspace.schema import utc_now_iso

DEFAULT_TASTE_PROFILE: dict[str, Any] = {
    "schemaVersion": 1,
    "globalPreferences": {
        "defaultInstrumentalOnly": True,
        "defaultFullMusicEngine": "yue2-native",
        "preferredQualities": [
            "sophisticated_rnb_hiphop_neosoul",
            "warm_jazzy_harmony",
            "natural_groove_and_pocket",
            "real_audio_texture_and_space",
            "subtle_musical_sound_design",
        ],
        "avoidQualities": [
            "basic_midi_instrument_sound",
            "monotonous_robotic_drum_groove",
            "unnatural_midi_guitar_riff",
            "soundfont_based_primary_music_production",
            "rule_based_midi_riffs_and_mechanical_ensemble",
            "harmonic_clashes_between_independent_midi_layers",
            "dry_unprocessed_flat_texture",
            "excessive_harsh_distortion_or_muddy_reverb",
        ],
        "preferredGenres": ["rnb_neosoul", "hiphop", "funk", "house", "indie_rock"],
        "preferredInstruments": {},
        "soundDesignNotes": (
            "Phase 05.1 YuE2 Native Audio의 음악적 자연스러움과 Studio Preview의 공간감·음색을 기준으로 삼습니다. "
            "SoundFont/MIDI Performer 기반 음악 제작은 음악성 저하로 불합격 판정되었으므로, 일반 연주 요청도 "
            "YuE2 Native Performance를 기본으로 사용하고 불필요한 과잉 FX를 피합니다."
        ),
    },
    "projectOverrides": {},
    "feedbackHistory": [
        {
            "id": "fb_initial_after_midnight_t02",
            "project": "After Midnight (Take 02)",
            "recordedAt": "2026-11-27T00:00:00Z",
            "verdict": "rejected_quality",
            "tags": [
                "unnatural_midi_guitar_riff",
                "monotonous_drum_groove",
                "basic_midi_instrument_sound",
                "lack_of_sound_design_and_space",
            ],
            "noteKo": "기타 리프·연주가 부자연스럽고 드럼 그루브가 단조로우며 피아노·기타가 기본 MIDI처럼 들림. 이펙터 질감·공간감이 부족함. YuE2 Native Audio 우선 정책으로 전환.",
        },
        {
            "id": "fb_phase051_native_approved",
            "project": "Native Production Validation 001",
            "recordedAt": "2026-11-27T15:00:00Z",
            "verdict": "approved_direction",
            "tags": [
                "yue2_native_musical_naturalness",
                "studio_preview_improved_tone_and_space",
                "realistic_live_performance_texture",
            ],
            "noteKo": "Phase 05.1 YuE2 Native Audio + Studio Preview 결과에 대해 자연스러운 연주감과 개선된 음색·공간감으로 긍정적 평가.",
        },
        {
            "id": "fb_phase052_midi_performer_rejected",
            "project": "Late Night Sessions 001 (Phase 05.2)",
            "recordedAt": "2026-11-28T01:12:00Z",
            "verdict": "rejected_quality",
            "tags": [
                "soundfont_based_music_rejected",
                "awkward_guitar_and_piano_performance",
                "harmonic_clashes",
                "loss_of_yue2_musical_naturalness",
                "rule_based_midi_riffs",
                "mechanical_ensemble",
            ],
            "noteKo": "Phase 05.2 자체 MIDI Performer + SoundFont 기반 레이어 음악은 연주가 어색하고 불협화음이 많으며 YuE2 특유의 자연스러움이 사라짐(청취 불합격). 일반 연주 요청을 Native Performance Mode(YuE2)로 전환하고 SoundFont 자동 추천 차단.",
        },
    ],
    "updatedAt": "2026-11-27T00:00:00Z",
}


def _taste_profile_path() -> Path:
    env_p = os.environ.get("DAW_TASTE_PROFILE_PATH", "").strip()
    if env_p:
        p = Path(env_p).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    d = engine_paths.DATA / "daw"
    d.mkdir(parents=True, exist_ok=True)
    return d / "taste_profile.json"


def _save_raw(profile: dict[str, Any]) -> dict[str, Any]:
    p = _taste_profile_path()
    profile["updatedAt"] = utc_now_iso()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return profile


def get_taste_profile(project_id: str | None = None) -> dict[str, Any]:
    """Load persistent global taste profile (creating initial seeded file if absent) + optional project overlay."""
    p = _taste_profile_path()
    if not p.is_file():
        profile = deepcopy(DEFAULT_TASTE_PROFILE)
        _save_raw(profile)
    else:
        try:
            profile = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            profile = deepcopy(DEFAULT_TASTE_PROFILE)

    result = deepcopy(profile)
    if project_id:
        proj_ov = (profile.get("projectOverrides") or {}).get(project_id) or {}
        effective = deepcopy(profile.get("globalPreferences") or {})
        effective.update(proj_ov)
        result["effectiveForProject"] = effective
        result["projectId"] = project_id
    else:
        result["effectiveForProject"] = deepcopy(profile.get("globalPreferences") or {})
    return result


def update_taste_profile(
    *,
    global_patch: dict[str, Any] | None = None,
    project_id: str | None = None,
    project_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update persistent user taste preferences cleanly (separating global vs per-project overrides)."""
    profile = get_taste_profile()
    profile.pop("effectiveForProject", None)
    profile.pop("projectId", None)

    if global_patch:
        gp = dict(profile.get("globalPreferences") or {})
        gp.update(global_patch)
        profile["globalPreferences"] = gp

    if project_id and project_patch is not None:
        po = dict(profile.get("projectOverrides") or {})
        cur = dict(po.get(project_id) or {})
        cur.update(project_patch)
        po[project_id] = cur
        profile["projectOverrides"] = po

    _save_raw(profile)
    return get_taste_profile(project_id=project_id)


def record_user_feedback(
    *,
    note: str,
    verdict: str = "feedback",
    tags: list[str] | None = None,
    project_name: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Append explicit user listening feedback to taste history without silently rewriting global locks."""
    profile = get_taste_profile()
    profile.pop("effectiveForProject", None)
    profile.pop("projectId", None)
    hist = list(profile.get("feedbackHistory") or [])
    hist.append(
        {
            "id": f"fb_{len(hist) + 1:03d}",
            "project": project_name or project_id or "global",
            "recordedAt": utc_now_iso(),
            "verdict": verdict,
            "tags": list(tags or []),
            "noteKo": note.strip(),
        }
    )
    profile["feedbackHistory"] = hist[-50:]
    _save_raw(profile)
    return get_taste_profile(project_id=project_id)


def reset_taste_profile(project_id: str | None = None) -> dict[str, Any]:
    """Reset project-level override (if project_id given) or entire global taste profile to clean defaults."""
    if project_id:
        profile = get_taste_profile()
        profile.pop("effectiveForProject", None)
        profile.pop("projectId", None)
        po = dict(profile.get("projectOverrides") or {})
        po.pop(project_id, None)
        profile["projectOverrides"] = po
        _save_raw(profile)
        return get_taste_profile(project_id=project_id)

    fresh = deepcopy(DEFAULT_TASTE_PROFILE)
    _save_raw(fresh)
    return get_taste_profile()
