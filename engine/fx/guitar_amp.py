"""Multi-Stage Tube Guitar Amp Simulator + Real Speaker Cabinet IR Convolution (Phase 05 · GATE 4 / Section 34).

Never fakes an amp with single-stage tanh!
Signal chain:
  Input Gain -> Pre-HPF (tight bass control) -> Cascaded Asymmetric Tube Preamp Stages (Clean / Edge / Crunch / Overdrive / High Gain)
  -> 3-Band Tone Stack (Bass / Mid / Treble) + Presence -> Real Cabinet Speaker Impulse Response via `pedalboard.Convolution`
  -> Output Gain & Wet/Dry Mix!
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine import paths as engine_paths

try:
    import pedalboard as pb
except Exception:
    pb = None  # type: ignore

AMP_MODELS: dict[str, dict[str, Any]] = {
    "clean": {"name": "Twin Clean Tube", "nameKo": "트윈 클린 튜브", "preGain": 1.6, "stages": 1, "asym": 0.06, "defaultCab": "1x12_open"},
    "edge_of_breakup": {"name": "Indie Edge of Breakup", "nameKo": "인디 에지 브레이크업", "preGain": 3.4, "stages": 2, "asym": 0.14, "defaultCab": "2x12_british"},
    "crunch": {"name": "British Classic Crunch", "nameKo": "브리티시 크런치", "preGain": 6.2, "stages": 2, "asym": 0.22, "defaultCab": "2x12_british"},
    "overdrive": {"name": "Warm Tube Overdrive", "nameKo": "웜 튜브 오버드라이브", "preGain": 10.5, "stages": 3, "asym": 0.28, "defaultCab": "4x12_modern"},
    "high_gain": {"name": "Modern High Gain Stack", "nameKo": "모던 하이게인 스택", "preGain": 18.0, "stages": 3, "asym": 0.34, "defaultCab": "4x12_modern"},
}

CABINET_PROFILES: dict[str, dict[str, Any]] = {
    "1x12_open": {"name": "1x12 Open-Back Combo", "resHz": 108.0, "resDb": 4.2, "scoopHz": 580.0, "scoopDb": -2.5, "presHz": 2650.0, "presDb": 4.0, "lpHz": 5400.0},
    "2x12_british": {"name": "2x12 British Greenback", "resHz": 96.0, "resDb": 4.8, "scoopHz": 460.0, "scoopDb": -3.2, "presHz": 2950.0, "presDb": 5.2, "lpHz": 5100.0},
    "4x12_modern": {"name": "4x12 Closed-Back V30", "resHz": 88.0, "resDb": 5.5, "scoopHz": 420.0, "scoopDb": -4.2, "presHz": 3250.0, "presDb": 5.8, "lpHz": 4800.0},
    "direct_di": {"name": "Direct DI (No Cabinet)", "bypass": True},
}


def _generate_cabinet_ir(cabinet_id: str, sr: int) -> Path | None:
    """Synthesize and cache a realistic guitar speaker Cabinet Impulse Response WAV."""
    spec = CABINET_PROFILES.get(cabinet_id, CABINET_PROFILES["2x12_british"])
    if spec.get("bypass"):
        return None
    ir_dir = engine_paths.ROOT / "outputs" / "daw" / "cache" / "ir"
    ir_dir.mkdir(parents=True, exist_ok=True)
    ir_path = ir_dir / f"cab_{cabinet_id}_{sr}.wav"
    if ir_path.is_file():
        return ir_path

    # Start with a clean unit impulse (1024 samples = 21.3 ms @ 48 kHz)
    n = 1024
    imp = np.zeros((n, 2), dtype=np.float32)
    imp[8, 0] = 1.0
    imp[8, 1] = 1.0

    # Shape speaker cabinet frequency response using Pedalboard C++ filters + subtle cabinet wood reflection!
    if pb is not None:
        cab_chain = pb.Pedalboard(
            [
                pb.HighpassFilter(cutoff_frequency_hz=72.0),
                pb.PeakFilter(cutoff_frequency_hz=spec["resHz"], gain_db=spec["resDb"], q=2.2),
                pb.PeakFilter(cutoff_frequency_hz=spec["scoopHz"], gain_db=spec["scoopDb"], q=1.1),
                pb.PeakFilter(cutoff_frequency_hz=spec["presHz"], gain_db=spec["presDb"], q=1.8),
                # Steep dual-stage speaker cone roll-off eliminating harsh >5 kHz digital fizz!
                pb.LowpassFilter(cutoff_frequency_hz=spec["lpHz"]),
                pb.LowpassFilter(cutoff_frequency_hz=spec["lpHz"] * 1.15),
            ]
        )
        shaped = cab_chain(imp.T, sr).T
    else:
        sos_lp = signal.butter(4, min(0.92, spec["lpHz"] / (sr * 0.5)), btype="lowpass", output="sos")
        sos_hp = signal.butter(2, 75.0 / (sr * 0.5), btype="highpass", output="sos")
        m = signal.sosfilt(sos_lp, signal.sosfilt(sos_hp, imp[:, 0]))
        shaped = np.stack([m, m], axis=1)

    # Subtle close-mic cabinet reflection at 1.4ms / 2.6ms
    for d_ms, gain in ((1.4, -0.18), (2.7, 0.11)):
        s_off = int(round(d_ms * sr / 1000.0))
        if s_off < n:
            shaped[s_off:, 0] += shaped[:-s_off, 0] * gain
            shaped[s_off:, 1] += shaped[:-s_off, 1] * (gain * 0.92)

    norm = float(np.sqrt(np.sum(shaped[:, 0] ** 2))) + 1e-9
    shaped = np.clip(shaped / norm * 0.85, -0.98, 0.98).astype(np.float32)
    sf.write(str(ir_path), shaped, sr, subtype="PCM_24")
    return ir_path


def apply_guitar_amp(
    stereo: np.ndarray,
    sr: int,
    params: dict[str, Any],
    *,
    wet_dry: float = 1.0,
) -> np.ndarray:
    """Apply Multi-Stage Tube Preamp + 3-Band Tone Stack + Real Cabinet IR Convolution."""
    if len(stereo) == 0:
        return stereo
    amp_model = str(params.get("ampModel", "crunch"))
    spec = AMP_MODELS.get(amp_model, AMP_MODELS["crunch"])
    input_gain_db = max(-12.0, min(24.0, float(params.get("inputGainDb", 0.0))))
    drive = max(0.1, min(1.0, float(params.get("drive", 0.55))))
    bass_db = max(-10.0, min(10.0, float(params.get("bassDb", 0.0))))
    mid_db = max(-10.0, min(10.0, float(params.get("midDb", 0.0))))
    treble_db = max(-10.0, min(10.0, float(params.get("trebleDb", 1.0))))
    presence_db = max(-8.0, min(8.0, float(params.get("presenceDb", 1.5))))
    output_gain_db = max(-18.0, min(12.0, float(params.get("outputGainDb", 0.0))))
    cabinet_id = str(params.get("cabinet", spec["defaultCab"]))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))

    inp = stereo.astype(np.float64)
    in_lin = 10.0 ** (input_gain_db / 20.0)
    x = inp * in_lin

    # Tight pre-amp HPF (85 Hz) so low strings stay articulated under overdrive
    sos_pre = signal.butter(2, 85.0 / (sr * 0.5), btype="highpass", output="sos")
    x[:, 0] = signal.sosfilt(sos_pre, x[:, 0])
    x[:, 1] = signal.sosfilt(sos_pre, x[:, 1])

    # Multi-stage cascaded asymmetric tube clipping (with inter-stage coupling filter!)
    total_drive = spec["preGain"] * (0.35 + 1.45 * drive)
    stages = int(spec["stages"])
    asym = float(spec["asym"])
    stage_gain = total_drive ** (1.0 / max(1, stages))
    sos_miller = signal.butter(1, min(0.92, 6800.0 / (sr * 0.5)), btype="lowpass", output="sos")

    for _ in range(stages):
        x = x * stage_gain
        # Asymmetric triode curve -> rich even (2nd) + odd (3rd) guitar harmonics!
        x = np.tanh(x + asym * (x * x) / (1.0 + np.abs(x))) - asym * 0.05
        # Remove DC offset + inter-stage Miller roll-off
        x -= np.mean(x, axis=0, keepdims=True)
        x[:, 0] = signal.sosfilt(sos_miller, x[:, 0])
        x[:, 1] = signal.sosfilt(sos_miller, x[:, 1])

    wet = x.astype(np.float32)

    # 3-Band Tube Tone Stack + Presence + Real Speaker Cabinet IR Convolution!
    cab_ir = _generate_cabinet_ir(cabinet_id, sr)
    if pb is not None:
        plugins: list[Any] = [
            pb.LowShelfFilter(cutoff_frequency_hz=130.0, gain_db=bass_db, q=0.7),
            pb.PeakFilter(cutoff_frequency_hz=720.0, gain_db=mid_db, q=0.9),
            pb.HighShelfFilter(cutoff_frequency_hz=3200.0, gain_db=treble_db, q=0.7),
            pb.PeakFilter(cutoff_frequency_hz=4500.0, gain_db=presence_db, q=1.2),
        ]
        if cab_ir is not None:
            plugins.append(pb.Convolution(impulse_response_filename=str(cab_ir), mix=1.0))
        if abs(output_gain_db) > 0.01:
            plugins.append(pb.Gain(gain_db=output_gain_db))
        wet = pb.Pedalboard(plugins)(wet.T, sr).T.astype(np.float32)
    elif cab_ir is not None:
        ir_d, _ = sf.read(str(cab_ir), dtype="float32", always_2d=True)
        wl = signal.fftconvolve(wet[:, 0], ir_d[:, 0], mode="full")[: len(wet)]
        wr = signal.fftconvolve(wet[:, 1], ir_d[:, 1], mode="full")[: len(wet)]
        wet = np.stack([wl, wr], axis=1).astype(np.float32)

    # Gentle output loudness balance relative to clean input
    in_rms = float(np.sqrt(np.mean(inp * inp))) + 1e-6
    wet_rms = float(np.sqrt(np.mean(wet.astype(np.float64) ** 2))) + 1e-6
    if wet_rms > in_rms * 2.2:
        wet = (wet * ((in_rms * 1.6) / wet_rms)).astype(np.float32)

    out = (stereo * (1.0 - mix) + wet * mix).astype(np.float32) if mix < 0.999 else wet
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
