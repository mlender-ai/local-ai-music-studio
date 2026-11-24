"""Sample & Loop Library Intelligence with cached real acoustic metadata (Phase 03-E)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.daw_workspace import analysis, loudness, midi, store
from engine.daw_workspace.waveforms import inspect_audio_file


def _infer_role(rel_path: str) -> str:
    low = rel_path.lower()
    if any(k in low for k in ("drum", "kick", "snare", "hat", "perc", "beat")):
        return "drums"
    if "bass" in low or "sub" in low:
        return "bass"
    if any(k in low for k in ("guitar", "gtr")):
        return "guitar"
    if any(k in low for k in ("key", "piano", "ep", "rhodes", "chord")):
        return "keys"
    if any(k in low for k in ("synth", "hook", "lead", "arp")):
        return "synth_hook"
    if any(k in low for k in ("pad", "tex", "amb", "fx")):
        return "pad"
    if any(k in low for k in ("yue2", "v72", "mix", "full")):
        return "full_mix"
    return "audio"


def _infer_license(category: str) -> str:
    low = category.lower()
    if "yue2" in low or "studio" in low or "demo" in low:
        return "Local Studio Original / Generated Asset"
    return "Local User Library File"


def list_library_catalog(project_bpm: float | None = None) -> list[dict[str, Any]]:
    """Return enriched studio library items with cached BPM, Key, LUFS, role & BPM compatibility."""
    lib_dir = engine_paths.DATA / "daw" / "library"
    if not lib_dir.is_dir():
        return []

    cache_file = lib_dir / ".catalog_cache.json"
    cache: dict[str, Any] = {}
    if cache_file.is_file():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    items: list[dict[str, Any]] = []
    cache_dirty = False
    analysis_cache_dir = lib_dir / ".analysis_cache"

    for f in sorted(lib_dir.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if ext not in store.ALLOWED_AUDIO_EXTS and ext not in store.ALLOWED_MIDI_EXTS:
            continue
        rel = f.relative_to(lib_dir).as_posix()
        stat = f.stat()
        cache_key = f"{rel}:{stat.st_size}:{int(stat.st_mtime)}"
        entry = cache.get(cache_key)

        if not entry:
            category = f.parent.name if f.parent != lib_dir else "studio"
            kind = "midi" if ext in store.ALLOWED_MIDI_EXTS else "audio"
            entry = {
                "id": rel,
                "name": f.name,
                "category": category,
                "kind": kind,
                "role": _infer_role(rel),
                "sizeBytes": stat.st_size,
                "durationSec": 0.0,
                "sampleRate": 0,
                "channels": 0,
                "bpm": None,
                "key": None,
                "integratedLufs": None,
                "isLoop": False,
                "license": _infer_license(category),
            }
            if kind == "midi":
                try:
                    parsed = midi.parse_midi_bytes(f.read_bytes())
                    entry["bpm"] = parsed.get("bpm")
                    entry["durationBeats"] = parsed.get("durationBeats")
                    entry["noteCount"] = len(parsed.get("notes", []))
                    entry["isLoop"] = (parsed.get("durationBeats") or 0) <= 32.0
                except Exception:
                    pass
            else:
                try:
                    meta = inspect_audio_file(f)
                    entry["durationSec"] = round(float(meta["durationSec"]), 3)
                    entry["sampleRate"] = int(meta["sampleRate"])
                    entry["channels"] = int(meta["channels"])
                    entry["isLoop"] = 0.5 <= entry["durationSec"] <= 20.0
                    # Run lightweight cached analysis on short-to-medium files (<= 180s)
                    if entry["durationSec"] <= 180.0:
                        sha = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
                        ana = analysis.analyze_audio_file(f, source_asset_id=rel, sha256=sha, cache_dir=analysis_cache_dir)
                        entry["bpm"] = ana.get("rhythm", {}).get("adoptedTempoBpm") or ana.get("rhythm", {}).get("estimatedBpm")
                        entry["key"] = ana.get("harmony", {}).get("estimatedKey")
                        entry["integratedLufs"] = ana.get("sound", {}).get("measured", {}).get("integratedLufs")
                    else:
                        stereo, sr = analysis._load_audio_bounded(f, max_duration_sec=30.0)
                        entry["integratedLufs"] = loudness.measure_loudness(stereo, sr)["integratedLufs"]
                except Exception:
                    pass

            cache[cache_key] = entry
            cache_dirty = True

        enriched = dict(entry)
        if project_bpm and enriched.get("bpm"):
            rel_info = analysis.resolve_octave_tempo_relation(project_bpm, float(enriched["bpm"]))
            enriched["tempoCompatibility"] = {
                "compatible": rel_info["compatible"],
                "relation": rel_info["relation"],
                "effectiveDeltaBpm": rel_info["effectiveDeltaBpm"],
                "requiresTimeStretch": rel_info["compatible"] is False,
                "note": (
                    "프로젝트 템포와 호환됨"
                    if rel_info["compatible"]
                    else f"프로젝트({project_bpm} BPM)와 템포 차이 있음 (자동 타임스트레치 미적용)"
                ),
            }
        else:
            enriched["tempoCompatibility"] = None
        items.append(enriched)

    if cache_dirty:
        try:
            tmp = cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, cache_file)
        except Exception:
            pass

    return items
