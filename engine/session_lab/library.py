"""Persistent Studio Session Library & Performance Feedback System (Phase 05.2 · Part G · Sections 33–36).

Stores reusable musical performance assets (loops, riffs, comping, solos, transitions, bridges)
and Performance Recipes locally under `outputs/daw/session_library.json` (overrideable via
`DAW_SESSION_LIBRARY_PATH` for isolated tests). Never fabricates missing MIDI or stem links.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.daw_workspace.schema import make_id, utc_now_iso
from engine.production.taste_profile import record_user_feedback

_lib_lock = threading.Lock()

SESSION_ASSET_CATEGORIES: tuple[str, ...] = (
    "drum_groove",
    "drum_fill",
    "percussion_loop",
    "percussion_break",
    "bass_groove",
    "bass_riff",
    "piano_comping",
    "piano_melody",
    "piano_solo",
    "guitar_funk_riff",
    "guitar_clean_phrase",
    "guitar_solo",
    "synth_hook",
    "synth_pad",
    "melody_motif",
    "bridge_idea",
    "transition_idea",
    "full_session_groove",
)

USER_RATINGS = ("good", "average", "poor", "unused")


def _library_path() -> Path:
    env_p = os.environ.get("DAW_SESSION_LIBRARY_PATH", "").strip()
    if env_p:
        p = Path(env_p).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    d = engine_paths.DATA / "daw"
    d.mkdir(parents=True, exist_ok=True)
    return d / "session_library.json"


def _load_db() -> dict[str, Any]:
    p = _library_path()
    if not p.is_file():
        return {"schemaVersion": 1, "assets": [], "recipes": [], "updatedAt": utc_now_iso()}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("assets", [])
        data.setdefault("recipes", [])
        return data
    except Exception:
        return {"schemaVersion": 1, "assets": [], "recipes": [], "updatedAt": utc_now_iso()}


def _save_db(db: dict[str, Any]) -> dict[str, Any]:
    p = _library_path()
    db["updatedAt"] = utc_now_iso()
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return db


def save_session_asset(
    *,
    name: str,
    category: str,
    instrument: str,
    performance_type: str,
    bpm: float,
    key: str = "D minor",
    time_signature: str = "4/4",
    bars: int = 8,
    chord_progression: list[str] | None = None,
    groove_feel: str = "neo_soul_pocket",
    source_engine: str = "pro-instrument-performance",
    generation_strategy: str = "strategy_c_pro_instrument",
    audio_path: str | None = None,
    midi_notes: list[dict[str, Any]] | None = None,
    instrument_ref: str | None = None,
    instrument_preset: str | None = None,
    fx_chain: list[dict[str, Any]] | None = None,
    quality_gate_summary: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    project_id: str | None = None,
    track_id: str | None = None,
    notes_text: str = "",
    recipe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a verified musical session asset (and optional Performance Recipe) to the Studio Session Library."""
    cat = category if category in SESSION_ASSET_CATEGORIES else "full_session_groove"
    asset_id = make_id("slib")
    now = utc_now_iso()
    asset: dict[str, Any] = {
        "id": asset_id,
        "name": name.strip() or f"{instrument} {performance_type}",
        "category": cat,
        "instrument": instrument,
        "performanceType": performance_type,
        "bpm": float(bpm),
        "timeSignature": time_signature,
        "key": key,
        "chordProgression": list(chord_progression or []),
        "bars": int(bars),
        "grooveFeel": groove_feel,
        "sourceEngine": source_engine,
        "generationStrategy": generation_strategy,
        "audioPath": audio_path,
        "hasMidi": bool(midi_notes),
        "midiNoteCount": len(midi_notes) if midi_notes else 0,
        "midiNotes": list(midi_notes) if midi_notes else None,
        "instrumentRef": instrument_ref,
        "instrumentPreset": instrument_preset,
        "fxChain": list(fx_chain or []),
        "qualityGateSummary": quality_gate_summary,
        "userRating": "unused",
        "feedbackHistory": [],
        "tags": sorted({t.strip().lower() for t in (tags or []) if t.strip()}),
        "projectId": project_id,
        "trackId": track_id,
        "notes": notes_text,
        "createdAt": now,
        "updatedAt": now,
    }

    with _lib_lock:
        db = _load_db()
        db["assets"].append(asset)
        saved_recipe = None
        if recipe:
            saved_recipe = {
                "id": make_id("rcp"),
                "assetId": asset_id,
                "name": recipe.get("name") or f"Recipe: {asset['name']}",
                "instrument": instrument,
                "performanceType": performance_type,
                "generationStrategy": generation_strategy,
                "instrumentRef": instrument_ref,
                "instrumentPreset": instrument_preset,
                "fxChain": list(fx_chain or []),
                "grooveProfile": recipe.get("grooveProfile") or {},
                "promptTemplate": recipe.get("promptTemplate") or "",
                "createdAt": now,
            }
            db["recipes"].append(saved_recipe)
        _save_db(db)

    return {"asset": asset, "recipe": saved_recipe, "libraryPath": str(_library_path())}


def search_session_assets(
    *,
    query: str | None = None,
    category: str | None = None,
    instrument: str | None = None,
    performance_type: str | None = None,
    key: str | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    min_rating: str | None = None,
    include_midi: bool = False,
) -> dict[str, Any]:
    """Search reusable Studio Session Library assets & Performance Recipes."""
    with _lib_lock:
        db = _load_db()

    items: list[dict[str, Any]] = []
    q = (query or "").strip().lower()
    for a in db.get("assets", []):
        if category and a.get("category") != category:
            continue
        if instrument and str(a.get("instrument", "")).lower() != instrument.lower():
            continue
        if performance_type and str(a.get("performanceType", "")).lower() != performance_type.lower():
            continue
        if key and key.lower() not in str(a.get("key", "")).lower():
            continue
        if bpm_min is not None and float(a.get("bpm", 0.0)) < float(bpm_min):
            continue
        if bpm_max is not None and float(a.get("bpm", 999.0)) > float(bpm_max):
            continue
        if min_rating and a.get("userRating") != min_rating:
            continue
        if q:
            hay = " ".join(
                [
                    str(a.get("name", "")),
                    str(a.get("category", "")),
                    str(a.get("instrument", "")),
                    str(a.get("performanceType", "")),
                    str(a.get("grooveFeel", "")),
                    str(a.get("notes", "")),
                    " ".join(a.get("tags") or []),
                ]
            ).lower()
            if q not in hay:
                continue
        entry = dict(a)
        if not include_midi:
            entry.pop("midiNotes", None)
        items.append(entry)

    return {
        "totalCount": len(db.get("assets", [])),
        "matchedCount": len(items),
        "categories": list(SESSION_ASSET_CATEGORIES),
        "assets": items,
        "recipes": list(db.get("recipes", [])),
        "libraryPath": str(_library_path()),
    }


def submit_performance_feedback(
    asset_id: str,
    *,
    rating: str,
    comment: str = "",
    detail_tags: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Record explicit user rating & detailed performance feedback on a Session Asset and sync into Taste Profile (Section 35)."""
    if rating not in USER_RATINGS:
        raise ValueError(f"Unsupported rating '{rating}'. Allowed: {USER_RATINGS}")

    now = utc_now_iso()
    with _lib_lock:
        db = _load_db()
        target = next((a for a in db.get("assets", []) if a.get("id") == asset_id), None)
        if target is None:
            raise FileNotFoundError(f"Session Library asset not found: {asset_id}")
        target["userRating"] = rating
        target["updatedAt"] = now
        fb = {
            "id": make_id("sfb"),
            "rating": rating,
            "tags": list(detail_tags or []),
            "comment": comment.strip(),
            "recordedAt": now,
        }
        target.setdefault("feedbackHistory", []).append(fb)
        _save_db(db)

    # Link meaningful feedback directly into persistent Taste Profile!
    taste = record_user_feedback(
        note=f"[Session Library: {target['name']} ({target['instrument']}/{target['performanceType']})] rating={rating}. {comment}".strip(),
        verdict=f"session_asset_{rating}",
        tags=[f"{target['instrument']}_{target['performanceType']}", *(detail_tags or [])],
        project_name=target.get("name"),
        project_id=project_id or target.get("projectId"),
    )
    return {
        "assetId": asset_id,
        "rating": rating,
        "feedback": fb,
        "tasteProfileUpdated": True,
        "tasteFeedbackCount": len(taste.get("feedbackHistory") or []),
    }
