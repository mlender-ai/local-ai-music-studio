"""Unified Professional Instrument Registry v2 & Track Instrument Renderer (Phase 05 · GATE 3).

Cleanly registers and dispatches:
- `pro_soundfont` (FluidSynth + MuseScore_General.sf3 MIT multi-sampled studio instruments)
- `pro_synth` (Subtractive / FM / Supersaw Unison + Pedalboard Moog LadderFilter)
- `pro_sampler` (Single/Multi-zone Sampler + Transient Slicer)
- `pro_drum_rack` (Per-pad Drum Rack + Round-Robin + TRUE Hi-Hat Choke Groups)
- `lightweight_preview` (Phase 03 built-in 6-voice synth preserved cleanly for instant browser preview & backward compat!)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from .articulation import apply_articulation
from .drum_rack import DRUM_RACK_KITS, render_drum_rack_sequence
from .pro_synth import PRO_SYNTH_PRESETS, render_pro_synth_sequence
from .sampler import render_sampler_sequence
from .soundfont_engine import SOUNDFONT_INSTRUMENTS, probe_fluidsynth_engine, render_soundfont_sequence
from .synth_engine import INSTRUMENTS as LEGACY_VOICES, synth_note_for_instrument

PRO_SYNTH_PARAMS_SPEC = [
    {"id": "cutoffHz", "label": "Cutoff", "labelKo": "컷오프", "min": 120.0, "max": 16000.0, "default": 2200.0, "unit": "Hz", "scale": "log"},
    {"id": "resonance", "label": "Resonance", "labelKo": "레조넌스", "min": 0.0, "max": 0.90, "default": 0.25, "unit": ""},
    {"id": "drive", "label": "Drive", "labelKo": "드라이브", "min": 1.0, "max": 6.0, "default": 1.4, "unit": "x"},
    {"id": "attackSec", "label": "Attack", "labelKo": "어택", "min": 0.002, "max": 1.2, "default": 0.005, "unit": "s"},
    {"id": "decaySec", "label": "Decay", "labelKo": "디케이", "min": 0.03, "max": 2.0, "default": 0.22, "unit": "s"},
    {"id": "sustain", "label": "Sustain", "labelKo": "서스테인", "min": 0.0, "max": 1.0, "default": 0.45, "unit": ""},
    {"id": "releaseSec", "label": "Release", "labelKo": "릴리즈", "min": 0.03, "max": 2.5, "default": 0.20, "unit": "s"},
    {"id": "detuneCents", "label": "Detune", "labelKo": "디튠", "min": 0.0, "max": 45.0, "default": 11.0, "unit": "ct"},
    {"id": "fmAmount", "label": "FM Depth", "labelKo": "FM 강도", "min": 0.0, "max": 6.0, "default": 0.2, "unit": ""},
    {"id": "stereoSpread", "label": "Width", "labelKo": "스테레오 폭", "min": 0.0, "max": 1.0, "default": 0.65, "unit": ""},
]

SOUNDFONT_PARAMS_SPEC = [
    {"id": "cutoffHz", "label": "Tone", "labelKo": "톤(밝기)", "min": 600.0, "max": 18000.0, "default": 10000.0, "unit": "Hz", "scale": "log"},
    {"id": "gain", "label": "Gain", "labelKo": "출력 게인", "min": 0.2, "max": 1.5, "default": 0.72, "unit": ""},
    {"id": "releaseTailSec", "label": "Release Tail", "labelKo": "잔향 테일", "min": 0.2, "max": 3.0, "default": 1.25, "unit": "s"},
    {"id": "transpose", "label": "Transpose", "labelKo": "트랜스포즈", "min": -24, "max": 24, "default": 0, "unit": "st"},
]

DRUM_RACK_PARAMS_SPEC = [
    {"id": "kitToneCutoffHz", "label": "Kit Tone", "labelKo": "킷 톤", "min": 1200.0, "max": 18000.0, "default": 15000.0, "unit": "Hz", "scale": "log"},
    {"id": "punchDrive", "label": "Punch Drive", "labelKo": "펀치 드라이브", "min": 1.0, "max": 3.0, "default": 1.25, "unit": "x"},
]

SAMPLER_PARAMS_SPEC = [
    {"id": "pitchSemitones", "label": "Pitch", "labelKo": "피치", "min": -24.0, "max": 24.0, "default": 0.0, "unit": "st"},
    {"id": "fineTuneCents", "label": "Fine Tune", "labelKo": "미세 조율", "min": -50.0, "max": 50.0, "default": 0.0, "unit": "ct"},
    {"id": "filterCutoffHz", "label": "Filter", "labelKo": "필터", "min": 250.0, "max": 18000.0, "default": 18000.0, "unit": "Hz", "scale": "log"},
    {"id": "attackSec", "label": "Attack", "labelKo": "어택", "min": 0.001, "max": 1.0, "default": 0.003, "unit": "s"},
    {"id": "releaseSec", "label": "Release", "labelKo": "릴리즈", "min": 0.01, "max": 2.0, "default": 0.08, "unit": "s"},
]


def get_instrument_catalog() -> list[dict[str, Any]]:
    """Return full Instrument Registry v2 combining Pro SoundFonts, Pro Synths, Drum Rack, Sampler & Lightweight Previews."""
    fs_probe = probe_fluidsynth_engine()
    fs_avail = bool(fs_probe["available"])
    catalog: list[dict[str, Any]] = []

    # 1. Professional Drum Rack (P0)
    catalog.append(
        {
            "id": "pro-drum-rack",
            "instrumentId": "pro-drum-rack",
            "name": "Studio Drum Rack (Choke & Round-Robin)",
            "instrumentName": "Studio Drum Rack (Choke & Round-Robin)",
            "nameKo": "스튜디오 드럼 랙 (초크·라운드 로빈)",
            "category": "drums",
            "role": "drums",
            "engineType": "pro_drum_rack",
            "engine": "pro-drum-rack",
            "pluginFormat": "builtin+sf3",
            "pluginIdentifier": "daw.pro_drum_rack.v1",
            "pluginVersion": "1.0.0",
            "presetList": [{"id": k, "name": v["name"], "nameKo": v["nameKo"]} for k, v in DRUM_RACK_KITS.items()],
            "supportedParameters": DRUM_RACK_PARAMS_SPEC,
            "supportedArticulations": ["natural", "flam_accents"],
            "sampleLibrary": fs_probe.get("soundfontName") or "builtin",
            "license": "LGPL-2.1 / MIT",
            "runtimeAvailability": "ready",
            "realtimeSupport": "frozen_cache_or_webaudio",
            "offlineRenderSupport": True,
            "latencySamples": 0,
            "cpuEstimate": "low",
            "memoryEstimate": "45 MB",
            "verificationStatus": "verified",
            "description": "Per-pad SF3/custom sample drum rack with true Open/Closed Hi-Hat choke groups & Round-Robin variation.",
        }
    )

    # 2. Professional Hybrid Analog & FM Synthesizers (P0)
    for sid, name_en, name_ko, desc in [
        (
            "pro-synth-analog",
            "Analog Unison & Ladder Synth",
            "아날로그 유니슨 · 래더 신스",
            "Band-limited Saw/Square/Supersaw (up to 7-voice unison) + Moog-style Pedalboard LadderFilter",
        ),
        (
            "pro-synth-fm",
            "Modern FM & Bell Synthesizer",
            "모던 FM · 벨 신시사이저",
            "Expressive FM operator modulation + unison stereo spread + resonant filter envelope",
        ),
    ]:
        presets = PRO_SYNTH_PRESETS[sid]
        catalog.append(
            {
                "id": sid,
                "instrumentId": sid,
                "name": name_en,
                "instrumentName": name_en,
                "nameKo": name_ko,
                "category": "synth",
                "role": "synth_hook",
                "engineType": "pro_synth",
                "engine": sid,
                "pluginFormat": "builtin+pedalboard",
                "pluginIdentifier": f"daw.{sid}.v1",
                "pluginVersion": "1.0.0",
                "presetList": [{"id": k, "name": v["name"], "nameKo": v["nameKo"]} for k, v in presets.items()],
                "supportedParameters": PRO_SYNTH_PARAMS_SPEC,
                "supportedArticulations": ["natural", "legato"],
                "sampleLibrary": None,
                "license": "MIT + GPL-3.0 (Pedalboard LadderFilter)",
                "runtimeAvailability": "ready",
                "realtimeSupport": "frozen_cache_or_webaudio",
                "offlineRenderSupport": True,
                "latencySamples": 0,
                "cpuEstimate": "medium",
                "memoryEstimate": "12 MB",
                "verificationStatus": "verified",
                "description": desc,
            }
        )

    # 3. Professional Audio Sampler & Transient Slicer (P0)
    catalog.append(
        {
            "id": "pro-sampler",
            "instrumentId": "pro-sampler",
            "name": "Studio Sampler & Loop Slicer",
            "instrumentName": "Studio Sampler & Loop Slicer",
            "nameKo": "스튜디오 샘플러 · 루프 슬라이서",
            "category": "sampler",
            "role": "sampler",
            "engineType": "pro_sampler",
            "engine": "pro-sampler",
            "pluginFormat": "builtin",
            "pluginIdentifier": "daw.pro_sampler.v1",
            "pluginVersion": "1.0.0",
            "presetList": [
                {"id": "one-shot", "name": "One-Shot Sample", "nameKo": "원샷 샘플"},
                {"id": "sustain-chromatic", "name": "Chromatic Sustain", "nameKo": "크로매틱 서스테인"},
                {"id": "transient-slice", "name": "Transient Slice Kit", "nameKo": "트랜지언트 슬라이스"},
            ],
            "supportedParameters": SAMPLER_PARAMS_SPEC,
            "supportedArticulations": ["natural"],
            "sampleLibrary": "user_project_assets",
            "license": "MIT",
            "runtimeAvailability": "ready",
            "realtimeSupport": "frozen_cache_or_webaudio",
            "offlineRenderSupport": True,
            "latencySamples": 0,
            "cpuEstimate": "low",
            "memoryEstimate": "24 MB",
            "verificationStatus": "verified",
            "description": "Multi-zone / chromatic / transient-sliced WAV sampler with ADSR, reverse, loop & filter.",
        }
    )

    # 4. Multi-Sampled FluidSynth SF3 Studio Instruments (P0 & P1)
    for sf_id, spec in SOUNDFONT_INSTRUMENTS.items():
        artics = (
            ["natural", "strum_down", "strum_up", "palm_mute"]
            if spec["category"] == "guitar"
            else (
                ["natural", "picked", "legato", "slide"]
                if spec["category"] == "bass"
                else (["natural", "warm_roll"] if spec["category"] == "keys" else ["natural"])
            )
        )
        catalog.append(
            {
                "id": sf_id,
                "instrumentId": sf_id,
                "name": spec["name"],
                "instrumentName": spec["name"],
                "nameKo": spec["nameKo"],
                "category": spec["category"],
                "role": spec["category"],
                "engineType": "pro_soundfont",
                "engine": "fluidsynth-sf3",
                "pluginFormat": "SF3/SF2",
                "pluginIdentifier": f"fluidsynth:bank{spec['bank']}:prog{spec['program']}",
                "pluginVersion": "2.6.3",
                "presetList": [{"id": p["id"], "name": p["name"], "nameKo": p["name"]} for p in spec["presets"]],
                "supportedParameters": SOUNDFONT_PARAMS_SPEC,
                "supportedArticulations": artics,
                "sampleLibrary": fs_probe.get("soundfontName") or "MuseScore_General.sf3 (missing)",
                "license": "LGPL-2.1 (FluidSynth) + MIT (MuseScore_General.sf3)",
                "runtimeAvailability": "ready" if fs_avail else "unavailable",
                "realtimeSupport": "frozen_cache_or_webaudio",
                "offlineRenderSupport": fs_avail,
                "latencySamples": 0,
                "cpuEstimate": "low",
                "memoryEstimate": "42 MB",
                "verificationStatus": "verified" if fs_avail else "uninstalled",
                "description": f"Multi-sampled FluidSynth studio instrument ({spec['name']}, MIT SoundFont).",
            }
        )

    # 5. Preserve Phase 03 lightweight preview synth voices cleanly (explicitly labeled `lightweight_preview`)
    for lv in LEGACY_VOICES:
        catalog.append(
            {
                **lv,
                "instrumentId": lv["id"],
                "instrumentName": lv["name"],
                "engineType": "lightweight_preview",
                "pluginFormat": "builtin-lightweight",
                "pluginIdentifier": f"daw.preview.{lv['id']}",
                "pluginVersion": "1.0.0",
                "presetList": [{"id": "default", "name": lv["name"], "nameKo": lv["nameKo"]}],
                "supportedParameters": [],
                "supportedArticulations": ["natural"],
                "sampleLibrary": None,
                "license": "MIT",
                "runtimeAvailability": "ready",
                "realtimeSupport": "webaudio_native",
                "offlineRenderSupport": True,
                "latencySamples": 0,
                "cpuEstimate": "very_low",
                "memoryEstimate": "2 MB",
                "verificationStatus": "verified",
            }
        )

    # Attach Permanent Production Quality Tier metadata (Phase 05.1 · Section 7) to every instrument
    from engine.production.instrument_resolver import get_instrument_quality_tier

    for entry in catalog:
        tier_meta = get_instrument_quality_tier(
            str(entry["id"]),
            runtime_available=(entry.get("runtimeAvailability") == "ready"),
        )
        entry["qualityTier"] = tier_meta["qualityTier"]
        entry["autoSelectInProduction"] = tier_meta["autoSelectInProduction"]
        entry["qualityTierNoteKo"] = tier_meta["descriptionKo"]
        entry["qualityTierNoteEn"] = tier_meta["descriptionEn"]

    return catalog


def list_instruments() -> list[dict[str, Any]]:
    """Backward-compatible helper returning the full Instrument Registry v2."""
    return get_instrument_catalog()


def render_track_instrument(
    notes: list[dict[str, Any]],
    *,
    instrument_ref: str | None,
    bpm: float = 120.0,
    total_beats: float = 16.0,
    sr: int = 48000,
    instrument_config: dict[str, Any] | None = None,
    asset_resolver: Callable[[str], Path | None] | None = None,
) -> np.ndarray:
    """Unified studio instrument renderer routing to SoundFont SF3, Pro Synth, Drum Rack, Sampler, or Lightweight Preview."""
    inst_id = (instrument_ref or "basic-poly-synth").strip()
    cfg = dict(instrument_config or {})
    preset_id = cfg.get("preset") or cfg.get("presetId")
    params = dict(cfg.get("parameters") or cfg.get("params") or {})
    articulation = str(cfg.get("articulation") or "natural")

    # Determine category for musical articulation
    if inst_id in SOUNDFONT_INSTRUMENTS:
        cat = SOUNDFONT_INSTRUMENTS[inst_id]["category"]
    elif inst_id == "pro-drum-rack" or "drum" in inst_id:
        cat = "drums"
    elif "bass" in inst_id:
        cat = "bass"
    elif "guitar" in inst_id:
        cat = "guitar"
    elif "keys" in inst_id or "piano" in inst_id or "ep" in inst_id:
        cat = "keys"
    else:
        cat = "synth"

    shaped_notes = apply_articulation(notes, category=cat, articulation=articulation, bpm=bpm)

    # 1. FluidSynth Multi-Sampled SF3/SF2
    if inst_id in SOUNDFONT_INSTRUMENTS:
        if probe_fluidsynth_engine()["available"]:
            return render_soundfont_sequence(
                shaped_notes,
                instrument_id=inst_id,
                bpm=bpm,
                total_beats=total_beats,
                sr=sr,
                preset_id=str(preset_id) if preset_id else None,
                params=params,
            )
        # Honest fallback ONLY if FluidSynth unavailable on another host
        fallback_map = {
            "drums": "drum-kit-electronic",
            "bass": "bass-fm-sub",
            "guitar": "guitar-clean-pluck",
            "keys": "keys-electric-ep",
            "pad": "pad-warm-analog",
        }
        inst_id = fallback_map.get(cat, "basic-poly-synth")

    # 2. Professional Hybrid Analog / FM Synth
    if inst_id in PRO_SYNTH_PRESETS:
        return render_pro_synth_sequence(
            shaped_notes,
            instrument_id=inst_id,
            preset_id=str(preset_id) if preset_id else None,
            params=params,
            bpm=bpm,
            total_beats=total_beats,
            sr=sr,
        )

    # 3. Professional Drum Rack (with Choke Groups & Round-Robin!)
    if inst_id == "pro-drum-rack":
        kit_id = str(preset_id or cfg.get("kitPreset") or "house-909")
        rack_cfg = dict(cfg.get("drumRackConfig") or params)
        return render_drum_rack_sequence(
            shaped_notes,
            kit_preset=kit_id,
            drum_rack_config=rack_cfg,
            bpm=bpm,
            total_beats=total_beats,
            sr=sr,
        )

    # 4. Professional Sampler
    if inst_id == "pro-sampler":
        samp_cfg = dict(cfg.get("samplerConfig") or params)
        if not samp_cfg.get("samplePath") and samp_cfg.get("audioAssetId") and asset_resolver:
            resolved = asset_resolver(str(samp_cfg["audioAssetId"]))
            if resolved:
                samp_cfg["samplePath"] = str(resolved)
        return render_sampler_sequence(
            shaped_notes,
            sampler_config=samp_cfg,
            bpm=bpm,
            total_beats=total_beats,
            sr=sr,
        )

    # 5. Phase 03 Lightweight Preview Voices
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    total_samples = max(int(sr * 0.5), int(round((total_beats * sec_per_beat + 0.5) * sr)))
    buf = np.zeros((total_samples, 2), dtype=np.float64)
    for n in shaped_notes:
        st_sec = float(n.get("startBeat", 0.0)) * sec_per_beat
        dur_sec = float(n.get("durationBeats", 0.25)) * sec_per_beat
        voice = synth_note_for_instrument(inst_id, int(n.get("pitch", 60)), int(n.get("velocity", 96)), dur_sec, sr)
        dst = int(round(st_sec * sr))
        if dst >= total_samples or len(voice) == 0:
            continue
        s0 = max(0, -dst)
        d0 = max(0, dst)
        w = min(len(voice) - s0, total_samples - d0)
        if w > 0:
            buf[d0 : d0 + w] += voice[s0 : s0 + w]
    return buf.astype(np.float32)


def render_instrument_preview(
    instrument_ref: str,
    *,
    preset_id: str | None = None,
    params: dict[str, Any] | None = None,
    sr: int = 48000,
) -> np.ndarray:
    """Render a crisp 2-second musical audition phrase tailored to the instrument's category (for Browser/Rack preview)."""
    bpm = 120.0
    cat = "synth"
    if instrument_ref in SOUNDFONT_INSTRUMENTS:
        cat = SOUNDFONT_INSTRUMENTS[instrument_ref]["category"]
    elif instrument_ref == "pro-drum-rack" or "drum" in instrument_ref:
        cat = "drums"
    elif "bass" in instrument_ref:
        cat = "bass"
    elif "guitar" in instrument_ref:
        cat = "guitar"
    elif "keys" in instrument_ref or "piano" in instrument_ref or "ep" in instrument_ref:
        cat = "keys"
    elif "pad" in instrument_ref or "strings" in instrument_ref:
        cat = "pad"

    if cat == "drums":
        notes = [
            {"pitch": 36, "velocity": 116, "startBeat": 0.0, "durationBeats": 0.3},
            {"pitch": 42, "velocity": 82, "startBeat": 0.5, "durationBeats": 0.18},
            {"pitch": 38, "velocity": 108, "startBeat": 1.0, "durationBeats": 0.25},
            {"pitch": 46, "velocity": 90, "startBeat": 1.5, "durationBeats": 0.35},
            {"pitch": 36, "velocity": 112, "startBeat": 2.0, "durationBeats": 0.3},
            {"pitch": 42, "velocity": 84, "startBeat": 2.5, "durationBeats": 0.18},
            {"pitch": 38, "velocity": 110, "startBeat": 3.0, "durationBeats": 0.25},
            {"pitch": 36, "velocity": 100, "startBeat": 3.5, "durationBeats": 0.25},
        ]
    elif cat == "bass":
        notes = [
            {"pitch": 41, "velocity": 110, "startBeat": 0.0, "durationBeats": 0.85},
            {"pitch": 41, "velocity": 96, "startBeat": 1.0, "durationBeats": 0.45},
            {"pitch": 48, "velocity": 104, "startBeat": 1.5, "durationBeats": 0.45},
            {"pitch": 44, "velocity": 108, "startBeat": 2.0, "durationBeats": 0.85},
            {"pitch": 43, "velocity": 102, "startBeat": 3.0, "durationBeats": 0.85},
        ]
    elif cat in ("keys", "guitar", "pad"):
        # Fm9 -> Dbmaj7 studio audition voicing
        notes = [
            {"pitch": 53, "velocity": 88, "startBeat": 0.0, "durationBeats": 1.8},
            {"pitch": 56, "velocity": 84, "startBeat": 0.0, "durationBeats": 1.8},
            {"pitch": 60, "velocity": 86, "startBeat": 0.0, "durationBeats": 1.8},
            {"pitch": 63, "velocity": 90, "startBeat": 0.0, "durationBeats": 1.8},
            {"pitch": 67, "velocity": 92, "startBeat": 0.0, "durationBeats": 1.8},
            {"pitch": 49, "velocity": 88, "startBeat": 2.0, "durationBeats": 1.8},
            {"pitch": 56, "velocity": 84, "startBeat": 2.0, "durationBeats": 1.8},
            {"pitch": 60, "velocity": 88, "startBeat": 2.0, "durationBeats": 1.8},
            {"pitch": 65, "velocity": 92, "startBeat": 2.0, "durationBeats": 1.8},
        ]
    else:
        # Expressive synth hook motif in F minor
        notes = [
            {"pitch": 65, "velocity": 106, "startBeat": 0.0, "durationBeats": 0.55},
            {"pitch": 68, "velocity": 98, "startBeat": 0.75, "durationBeats": 0.50},
            {"pitch": 72, "velocity": 110, "startBeat": 1.5, "durationBeats": 0.60},
            {"pitch": 70, "velocity": 96, "startBeat": 2.25, "durationBeats": 0.45},
            {"pitch": 68, "velocity": 100, "startBeat": 2.75, "durationBeats": 0.45},
            {"pitch": 65, "velocity": 108, "startBeat": 3.25, "durationBeats": 0.70},
        ]

    pcm = render_track_instrument(
        notes,
        instrument_ref=instrument_ref,
        bpm=bpm,
        total_beats=4.0,
        sr=sr,
        instrument_config={"preset": preset_id, "parameters": params or {}},
    )
    peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
    if peak > 0.90:
        pcm = (pcm / peak * 0.88).astype(np.float32)
    return pcm
