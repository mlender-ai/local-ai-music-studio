"""Professional FX Registry & Ordered Insert Chain Processor (Phase 05 · GATE 4).

Supports all 13 studio FX types:
  parametric_eq, compressor, sidechain_compressor, limiter, noise_gate, transient_shaper,
  reverb, delay, chorus, phaser, flanger, tremolo, saturation, guitar_amp, filter, distortion, bitcrush, pitch_shift
Every slot supports `enabled`, `bypass`, `wetDry`, `preset`, `parameters`, `sidechainTrackId`, and real automation!
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from .automation import apply_automated_filter_sweep, find_automation_lane, sample_automation_curve
from .delay_mod import (
    SUBDIVISION_BEATS,
    apply_chorus,
    apply_creative_fx,
    apply_delay,
    apply_flanger,
    apply_phaser,
    apply_saturation,
    apply_tremolo,
)
from .dynamics import (
    apply_compressor,
    apply_limiter,
    apply_noise_gate,
    apply_sidechain_compressor,
    apply_transient_shaper,
)
from .eq import DEFAULT_EQ_BANDS, apply_parametric_eq
from .guitar_amp import AMP_MODELS, CABINET_PROFILES, apply_guitar_amp
from .reverb import REVERB_MODES, apply_reverb

FX_CATALOG: list[dict[str, Any]] = [
    {
        "type": "parametric_eq",
        "name": "Parametric EQ",
        "nameKo": "파라메트릭 EQ",
        "category": "eq",
        "engine": "pedalboard-cpp",
        "description": "6-band HPF / Low Shelf / Dual Peak / High Shelf / LPF with analytical frequency curve",
        "defaultParams": {"bands": DEFAULT_EQ_BANDS, "outputGainDb": 0.0},
        "presets": [
            {"id": "flat", "name": "Flat Studio EQ", "nameKo": "플랫"},
            {
                "id": "low_mid_clean",
                "name": "Low-Mid Clean (Cut 320Hz)",
                "nameKo": "로우미드 정리 (320Hz 컷)",
                "params": {
                    "bands": [
                        {"id": "hpf", "type": "highpass", "freqHz": 85.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                        {"id": "low", "type": "low_shelf", "freqHz": 110.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                        {"id": "low_mid", "type": "peak", "freqHz": 320.0, "gainDb": -3.5, "q": 1.2, "enabled": True},
                        {"id": "high_mid", "type": "peak", "freqHz": 2800.0, "gainDb": 1.8, "q": 1.0, "enabled": True},
                        {"id": "high", "type": "high_shelf", "freqHz": 8500.0, "gainDb": 1.2, "q": 0.707, "enabled": True},
                        {"id": "lpf", "type": "lowpass", "freqHz": 18000.0, "gainDb": 0.0, "q": 0.707, "enabled": False},
                    ]
                },
            },
            {
                "id": "bass_focus",
                "name": "Bass Focus (Sub Clean)",
                "nameKo": "베이스 포커스",
                "params": {
                    "bands": [
                        {"id": "hpf", "type": "highpass", "freqHz": 32.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                        {"id": "low", "type": "low_shelf", "freqHz": 85.0, "gainDb": 2.2, "q": 0.8, "enabled": True},
                        {"id": "low_mid", "type": "peak", "freqHz": 260.0, "gainDb": -2.5, "q": 1.1, "enabled": True},
                        {"id": "high_mid", "type": "peak", "freqHz": 1200.0, "gainDb": 1.5, "q": 1.0, "enabled": True},
                        {"id": "high", "type": "high_shelf", "freqHz": 6000.0, "gainDb": -2.0, "q": 0.707, "enabled": True},
                        {"id": "lpf", "type": "lowpass", "freqHz": 9500.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                    ]
                },
            },
        ],
    },
    {
        "type": "compressor",
        "name": "Studio Compressor",
        "nameKo": "스튜디오 컴프레서",
        "category": "dynamics",
        "engine": "pedalboard-cpp",
        "description": "Precision dynamics compressor with Threshold, Ratio, Attack, Release, Makeup, Parallel Mix & real GR meter",
        "defaultParams": {"thresholdDb": -16.0, "ratio": 3.5, "attackMs": 12.0, "releaseMs": 120.0, "makeupGainDb": 1.5},
        "presets": [
            {"id": "gentle_glue", "name": "Gentle Bus Glue", "nameKo": "버스 글루", "params": {"thresholdDb": -14.0, "ratio": 2.5, "attackMs": 20.0, "releaseMs": 150.0, "makeupGainDb": 1.0}},
            {"id": "drum_punch", "name": "Drum Punch", "nameKo": "드럼 펀치", "params": {"thresholdDb": -18.0, "ratio": 4.5, "attackMs": 25.0, "releaseMs": 90.0, "makeupGainDb": 2.5}},
            {"id": "bass_tight", "name": "Tight Bass Control", "nameKo": "타이트 베이스", "params": {"thresholdDb": -16.0, "ratio": 5.0, "attackMs": 8.0, "releaseMs": 110.0, "makeupGainDb": 2.0}},
        ],
    },
    {
        "type": "sidechain_compressor",
        "name": "External Sidechain Comp",
        "nameKo": "외부 사이드체인 컴프레서",
        "category": "dynamics",
        "engine": "builtin-sidechain",
        "description": "True external-track sidechain ducking triggered by actual Kick/Drum audio envelope (never fake LFO!)",
        "defaultParams": {"thresholdDb": -22.0, "ratio": 6.0, "attackMs": 4.0, "releaseMs": 115.0, "kneeDb": 3.0},
        "presets": [
            {"id": "house_pump", "name": "House Kick Ducking", "nameKo": "하우스 킥 덕킹", "params": {"thresholdDb": -24.0, "ratio": 7.0, "attackMs": 3.0, "releaseMs": 125.0}},
            {"id": "subtle_pocket", "name": "Subtle Low-End Pocket", "nameKo": "저역 정리 포켓", "params": {"thresholdDb": -18.0, "ratio": 3.5, "attackMs": 5.0, "releaseMs": 90.0}},
        ],
    },
    {
        "type": "reverb",
        "name": "Studio Space Reverb",
        "nameKo": "스튜디오 리버브 (Convolution IR)",
        "category": "space",
        "engine": "pedalboard-convolution",
        "description": "6-mode Convolution IR Reverb (Small Room, Studio Room, Chamber, Plate, Hall, Large Ambient)",
        "defaultParams": {"roomType": "studio_room", "decaySec": 1.1, "preDelayMs": 14.0, "damping": 0.42, "lowCutHz": 120.0, "highCutHz": 10000.0, "stereoWidth": 0.85, "wetDry": 0.26},
        "presets": [{"id": k, "name": v["name"], "nameKo": v["nameKo"], "params": {"roomType": k, "decaySec": v["decaySec"], "preDelayMs": v["preDelayMs"], "damping": v["damping"]}} for k, v in REVERB_MODES.items()],
    },
    {
        "type": "delay",
        "name": "Tempo-Synced Stereo Delay",
        "nameKo": "템포 동기화 딜레이",
        "category": "delay",
        "engine": "builtin-feedback-dsp",
        "description": "BPM-locked Stereo & Ping-Pong delay (1/4, 1/8, 1/8 dotted, 1/16, triplets) with feedback loop filter",
        "defaultParams": {"tempoSync": True, "subdivision": "1/8 dotted", "delayMs": 375.0, "feedback": 0.36, "pingPong": True, "lowCutHz": 180.0, "highCutHz": 5200.0, "wetDry": 0.24},
        "presets": [
            {"id": "dotted_eighth", "name": "1/8 Dotted Ping-Pong", "nameKo": "점8분 핑퐁", "params": {"tempoSync": True, "subdivision": "1/8 dotted", "feedback": 0.38, "pingPong": True, "wetDry": 0.26}},
            {"id": "slapback", "name": "Vintage Slapback (115ms)", "nameKo": "슬랩백", "params": {"tempoSync": False, "delayMs": 115.0, "feedback": 0.16, "pingPong": False, "wetDry": 0.22}},
            {"id": "dub_quarter", "name": "1/4 Dub Echo", "nameKo": "4분 덥 에코", "params": {"tempoSync": True, "subdivision": "1/4", "feedback": 0.52, "pingPong": True, "highCutHz": 3400.0, "wetDry": 0.30}},
        ],
    },
    {
        "type": "guitar_amp",
        "name": "Tube Guitar Amp & Cab IR",
        "nameKo": "튜브 기타 앰프 · 캐비닛 IR",
        "category": "amp",
        "engine": "pedalboard-convolution",
        "description": "Multi-stage asymmetric tube preamp + 3-band tone stack + real Cabinet IR (1x12, 2x12, 4x12)",
        "defaultParams": {"ampModel": "crunch", "inputGainDb": 0.0, "drive": 0.55, "bassDb": 0.5, "midDb": 0.0, "trebleDb": 1.2, "presenceDb": 1.5, "outputGainDb": 0.0, "cabinet": "2x12_british"},
        "presets": [{"id": k, "name": v["name"], "nameKo": v["nameKo"], "params": {"ampModel": k, "cabinet": v["defaultCab"]}} for k, v in AMP_MODELS.items()],
        "cabinets": [{"id": k, "name": v["name"]} for k, v in CABINET_PROFILES.items()],
    },
    {
        "type": "saturation",
        "name": "Analog Tape Saturation",
        "nameKo": "아날로그 테이프 새츄레이션",
        "category": "drive",
        "engine": "builtin-analog-shaper",
        "description": "Asymmetric even/odd harmonic warmth & gentle soft-clip glue",
        "defaultParams": {"driveDb": 7.5, "toneHz": 9500.0, "wetDry": 0.65},
        "presets": [
            {"id": "warm_tape", "name": "Warm Tape Glue", "nameKo": "웜 테이프", "params": {"driveDb": 6.0, "toneHz": 8500.0, "wetDry": 0.60}},
            {"id": "vintage_grit", "name": "Vintage Grit", "nameKo": "빈티지 그릿", "params": {"driveDb": 14.0, "toneHz": 6200.0, "wetDry": 0.72}},
        ],
    },
    {
        "type": "chorus",
        "name": "Stereo Ensemble Chorus",
        "nameKo": "스테레오 코러스",
        "category": "modulation",
        "engine": "pedalboard-cpp",
        "description": "Lush stereo chorus widening keys, guitars & analog synth pads",
        "defaultParams": {"rateHz": 0.85, "depth": 0.35, "centreDelayMs": 7.5, "feedback": 0.15, "wetDry": 0.35},
        "presets": [{"id": "juno_wide", "name": "Juno Wide Chorus", "nameKo": "주노 와이드", "params": {"rateHz": 0.65, "depth": 0.48, "centreDelayMs": 8.0, "wetDry": 0.42}}],
    },
    {
        "type": "phaser",
        "name": "Analog Phaser",
        "nameKo": "아날로그 페이저",
        "category": "modulation",
        "engine": "pedalboard-cpp",
        "description": "Sweeping all-pass phase shifter for Rhodes EP, guitars & pads",
        "defaultParams": {"rateHz": 0.55, "depth": 0.55, "centreFrequencyHz": 950.0, "feedback": 0.35, "wetDry": 0.42},
        "presets": [],
    },
    {
        "type": "flanger",
        "name": "Jet Stereo Flanger",
        "nameKo": "스테레오 플랜저",
        "category": "modulation",
        "engine": "pedalboard-cpp",
        "description": "Short modulated comb delay for metallic sweep textures",
        "defaultParams": {"rateHz": 0.35, "depth": 0.55, "feedback": 0.45, "wetDry": 0.38},
        "presets": [],
    },
    {
        "type": "tremolo",
        "name": "Stereo Auto-Pan Tremolo",
        "nameKo": "스테레오 트레몰로",
        "category": "modulation",
        "engine": "builtin-dsp",
        "description": "Vintage Rhodes / Guitar optical amplitude tremolo with stereo phase",
        "defaultParams": {"rateHz": 4.5, "depth": 0.50, "stereoPhaseDeg": 90.0},
        "presets": [],
    },
    {
        "type": "limiter",
        "name": "Master True-Peak Limiter",
        "nameKo": "마스터 리미터",
        "category": "dynamics",
        "engine": "pedalboard-cpp",
        "description": "Transparent brickwall ceiling protection (-0.8 dBTP default)",
        "defaultParams": {"thresholdDb": -1.5, "releaseMs": 80.0, "ceilingDb": -0.8},
        "presets": [{"id": "master_safe", "name": "Transparent -1.0 dBTP", "nameKo": "마스터 안전 (-1 dB)", "params": {"thresholdDb": -2.0, "releaseMs": 90.0, "ceilingDb": -1.0}}],
    },
    {
        "type": "noise_gate",
        "name": "Noise Gate / Expander",
        "nameKo": "노이즈 게이트",
        "category": "dynamics",
        "engine": "pedalboard-cpp",
        "description": "Tightens room bleed or shapes punchy drum decays",
        "defaultParams": {"thresholdDb": -42.0, "ratio": 6.0, "attackMs": 2.0, "releaseMs": 85.0},
        "presets": [],
    },
    {
        "type": "transient_shaper",
        "name": "Transient Shaper",
        "nameKo": "트랜지언트 셰이퍼",
        "category": "dynamics",
        "engine": "builtin-dsp",
        "description": "Independent Attack punch & Sustain length shaping for drums & plucks",
        "defaultParams": {"attackGainDb": 3.0, "sustainGainDb": -1.5},
        "presets": [{"id": "snappy_drums", "name": "Snappy Tight Drums", "nameKo": "스내피 드럼", "params": {"attackGainDb": 4.5, "sustainGainDb": -3.0}}],
    },
    {
        "type": "filter",
        "name": "Resonant Ladder Filter",
        "nameKo": "레조넌트 래더 필터",
        "category": "creative",
        "engine": "pedalboard-cpp",
        "description": "Moog-style 24dB/oct LPF/HPF/BPF filter with smooth automation support for buildups",
        "defaultParams": {"mode": "lpf24", "cutoffHz": 1800.0, "resonance": 0.35, "drive": 1.3},
        "presets": [{"id": "buildup_lp", "name": "Buildup Low-Pass", "nameKo": "빌드업 로우패스", "params": {"mode": "lpf24", "cutoffHz": 600.0, "resonance": 0.45, "drive": 1.4}}],
    },
    {
        "type": "bitcrush",
        "name": "Lo-Fi Bitcrusher",
        "nameKo": "로파이 비트크러셔",
        "category": "creative",
        "engine": "pedalboard-cpp",
        "description": "Vintage 8/12-bit sampler grit for Boom-Bap & Lo-Fi",
        "defaultParams": {"bitDepth": 10.0, "wetDry": 0.55},
        "presets": [],
    },
    {
        "type": "distortion",
        "name": "Overdrive Distortion",
        "nameKo": "디스토션",
        "category": "drive",
        "engine": "pedalboard-cpp",
        "description": "Aggressive Pedalboard distortion stage",
        "defaultParams": {"driveDb": 16.0, "wetDry": 0.65},
        "presets": [],
    },
    {
        "type": "pitch_shift",
        "name": "Creative Pitch Shifter",
        "nameKo": "피치 시프터",
        "category": "creative",
        "engine": "pedalboard-cpp",
        "description": "Octave / Fifth harmonic texture shifter",
        "defaultParams": {"semitones": 12.0, "wetDry": 0.30},
        "presets": [],
    },
]

FX_BY_TYPE: dict[str, dict[str, Any]] = {f["type"]: f for f in FX_CATALOG}


def list_fx_catalog() -> list[dict[str, Any]]:
    return deepcopy(FX_CATALOG)


def default_fx_slot(fx_type: str, slot_id: str, preset_id: str | None = None, params_override: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = FX_BY_TYPE.get(fx_type)
    if not spec:
        raise ValueError(f"Unsupported FX type: {fx_type}")
    params = deepcopy(spec["defaultParams"])
    if preset_id:
        pr = next((p for p in spec.get("presets", []) if p["id"] == preset_id), None)
        if pr and pr.get("params"):
            params.update(deepcopy(pr["params"]))
    if params_override:
        params.update(deepcopy(params_override))
    return {
        "id": slot_id,
        "type": fx_type,
        "name": spec["name"],
        "nameKo": spec["nameKo"],
        "enabled": True,
        "bypass": False,
        "wetDry": float(params.get("wetDry", 1.0)),
        "preset": preset_id,
        "parameters": params,
        "sidechainTrackId": None,
    }


def process_fx_chain(
    stereo: np.ndarray,
    effects: list[dict[str, Any]],
    *,
    sr: int = 48000,
    bpm: float = 120.0,
    start_beats: float = 0.0,
    sidechain_buffers: dict[str, np.ndarray] | None = None,
    automation_lanes: list[dict[str, Any]] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Run an ordered FX Insert chain on stereo float32 PCM, returning (audio, metering_by_slot_id)."""
    if len(stereo) == 0 or not effects:
        return stereo.astype(np.float32), {}

    audio = stereo.astype(np.float32, copy=True)
    meters: dict[str, Any] = {}
    lanes = automation_lanes or []

    for slot in effects:
        if not slot.get("enabled", True) or slot.get("bypass", False):
            continue
        fx_id = str(slot.get("id", ""))
        fx_type = str(slot.get("type", ""))
        params = dict(slot.get("parameters") or slot.get("params") or {})
        wet = float(slot.get("wetDry", params.get("wetDry", 1.0)))

        # Check for real FX parameter automation lanes!
        wet_lane = find_automation_lane(lanes, target_type="fx", target_id=fx_id, parameter_id="wetDry")
        cut_lane = find_automation_lane(lanes, target_type="fx", target_id=fx_id, parameter_id="cutoffHz")

        if fx_type == "filter" and cut_lane is not None:
            audio = apply_automated_filter_sweep(
                audio,
                cut_lane,
                sr=sr,
                bpm=bpm,
                start_beats=start_beats,
                default_cutoff=float(params.get("cutoffHz", 1600.0)),
                resonance=float(params.get("resonance", 0.35)),
                mode=str(params.get("mode", "lpf24")),
            )
            continue

        # If wetDry is automated (e.g. "후반 기타 솔로에서만 딜레이를 늘려줘"), process 100% wet then blend with exact time-varying curve!
        eff_wet = 1.0 if wet_lane is not None else wet
        dry_before = audio.copy() if wet_lane is not None else None

        if fx_type == "parametric_eq":
            audio = apply_parametric_eq(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "compressor":
            audio, m = apply_compressor(audio, sr, params, wet_dry=eff_wet)
            meters[fx_id] = m
        elif fx_type == "sidechain_compressor":
            sc_tid = slot.get("sidechainTrackId") or params.get("sidechainTrackId")
            sc_buf = (sidechain_buffers or {}).get(str(sc_tid)) if sc_tid else None
            audio, m = apply_sidechain_compressor(audio, sc_buf, sr, params, wet_dry=eff_wet)
            meters[fx_id] = m
        elif fx_type == "limiter":
            audio, m = apply_limiter(audio, sr, params)
            meters[fx_id] = m
        elif fx_type == "noise_gate":
            audio = apply_noise_gate(audio, sr, params)
        elif fx_type == "transient_shaper":
            audio = apply_transient_shaper(audio, sr, params)
        elif fx_type == "reverb":
            p_rev = {**params, "wetDry": eff_wet} if wet_lane is not None else params
            audio = apply_reverb(audio, sr, p_rev, wet_dry=eff_wet)
        elif fx_type == "delay":
            p_del = {**params, "wetDry": eff_wet} if wet_lane is not None else params
            audio = apply_delay(audio, sr, p_del, bpm=bpm, wet_dry=eff_wet)
        elif fx_type == "chorus":
            audio = apply_chorus(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "phaser":
            audio = apply_phaser(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "flanger":
            audio = apply_flanger(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "tremolo":
            audio = apply_tremolo(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "saturation":
            audio = apply_saturation(audio, sr, params, wet_dry=eff_wet)
        elif fx_type == "guitar_amp":
            audio = apply_guitar_amp(audio, sr, params, wet_dry=eff_wet)
        elif fx_type in ("distortion", "bitcrush", "pitch_shift", "filter"):
            audio = apply_creative_fx(fx_type, audio, sr, params, wet_dry=eff_wet)

        if wet_lane is not None and dry_before is not None:
            curve = np.clip(
                sample_automation_curve(wet_lane, n_samples=len(audio), sr=sr, bpm=bpm, start_beats=start_beats, default_value=wet),
                0.0,
                1.0,
            ).astype(np.float32)
            audio = (dry_before * (1.0 - curve[:, None]) + audio * curve[:, None]).astype(np.float32)

    return np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0), meters
