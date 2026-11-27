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
            "dry_unprocessed_flat_texture",
            "excessive_harsh_distortion_or_muddy_reverb",
        ],
        "preferredGenres": ["rnb_neosoul", "hiphop", "house", "indie_rock"],
        "preferredInstruments": {},
        "soundDesignNotes": (
            "자연스러운 공간감과 따뜻한 질감을 선호하며, 과장된 FX나 기본 MIDI 느낌의 촌스러운 톤을 피합니다. "
            "이미 잘 믹스된 네이티브 오디오에는 필요한 최소한의 정리(먹먹한 로우미드 컷, 자연스러운 공간/헤드룸 정리)만 적용합니다."
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
        }
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
