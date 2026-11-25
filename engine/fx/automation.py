"""Automation Curve Evaluator & Block-Level Automated DSP Processor (Phase 05 · GATE 4 / Section 38).

Supports linear and step interpolation across timeline beats for:
- Track Volume (`targetType="track"`, `parameterId="gainDb"`)
- Track Pan (`targetType="track"`, `parameterId="pan"`)
- Send Level (`targetType="send"`, `targetId=busId`, `parameterId="levelDb"`)
- FX Parameter Automation (`targetType="fx"`, `targetId=fxSlotId`, `parameterId="cutoffHz" | "wetDry" | "feedback" | "drive" | ...`)
- Instrument Parameter Automation (`targetType="instrument"`, `parameterId="cutoffHz"`) -> dynamically shapes rendered synth tone!
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal


def evaluate_automation_at_beat(lane: dict[str, Any], beat: float, default_value: float) -> float:
    """Evaluate an automation lane's value at `beat` using linear or step interpolation."""
    if not lane or not lane.get("enabled", True):
        return default_value
    pts = sorted(lane.get("points") or [], key=lambda p: float(p.get("beat", 0.0)))
    if not pts:
        return default_value
    if beat <= float(pts[0].get("beat", 0.0)):
        return float(pts[0].get("value", default_value))
    if beat >= float(pts[-1].get("beat", 0.0)):
        return float(pts[-1].get("value", default_value))

    for i in range(len(pts) - 1):
        b0 = float(pts[i].get("beat", 0.0))
        b1 = float(pts[i + 1].get("beat", 0.0))
        if b0 <= beat <= b1:
            v0 = float(pts[i].get("value", default_value))
            v1 = float(pts[i + 1].get("value", default_value))
            interp = str(pts[i].get("interpolation", "linear"))
            if interp == "step" or abs(b1 - b0) < 1e-6:
                return v0
            t = (beat - b0) / (b1 - b0)
            return v0 + (v1 - v0) * t
    return float(pts[-1].get("value", default_value))


def find_automation_lane(
    lanes: list[dict[str, Any]],
    *,
    target_type: str,
    parameter_id: str,
    target_id: str | None = None,
) -> dict[str, Any] | None:
    for ln in lanes or []:
        if not ln.get("enabled", True):
            continue
        if ln.get("targetType") == target_type and ln.get("parameterId") == parameter_id:
            if target_id is None or ln.get("targetId") == target_id:
                if ln.get("points"):
                    return ln
    return None


def sample_automation_curve(
    lane: dict[str, Any],
    *,
    n_samples: int,
    sr: int,
    bpm: float,
    start_beats: float,
    default_value: float,
    ctrl_step: int = 256,
) -> np.ndarray:
    """Generate a smooth full-sample-rate parameter trajectory from an automation lane."""
    if n_samples <= 0:
        return np.zeros(0, dtype=np.float64)
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    n_ctrl = max(2, int(math.ceil(n_samples / ctrl_step)) + 1)
    ctrl_idx = np.linspace(0, n_samples - 1, n_ctrl)
    ctrl_vals = np.array(
        [
            evaluate_automation_at_beat(lane, start_beats + (idx / sr) / sec_per_beat, default_value)
            for idx in ctrl_idx
        ],
        dtype=np.float64,
    )
    return np.interp(np.arange(n_samples, dtype=np.float64), ctrl_idx, ctrl_vals)


def apply_automated_filter_sweep(
    stereo: np.ndarray,
    lane: dict[str, Any],
    *,
    sr: int,
    bpm: float,
    start_beats: float,
    default_cutoff: float = 2000.0,
    resonance: float = 0.25,
    mode: str = "lpf",
) -> np.ndarray:
    """Apply smooth overlap-add time-varying resonant filter sweep driven by an automation lane (e.g. buildup filter open!)."""
    n = len(stereo)
    if n == 0:
        return stereo
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    block = 2048
    hop = 1024
    win = np.hanning(block).astype(np.float64)
    out = np.zeros((n, 2), dtype=np.float64)
    weight = np.zeros(n, dtype=np.float64)
    btype = "highpass" if "hp" in mode.lower() else "lowpass"

    pos = 0
    while pos < n:
        end = min(n, pos + block)
        seg = stereo[pos:end].astype(np.float64)
        actual_len = len(seg)
        if actual_len < block:
            seg = np.pad(seg, ((0, block - actual_len), (0, 0)))
        mid_beat = start_beats + ((pos + actual_len * 0.5) / sr) / sec_per_beat
        cut = max(90.0, min(sr * 0.45, evaluate_automation_at_beat(lane, mid_beat, default_cutoff)))
        sos = signal.butter(4, cut / (sr * 0.5), btype=btype, output="sos")
        fl = signal.sosfilt(sos, seg[:, 0])
        fr = signal.sosfilt(sos, seg[:, 1])
        # Subtle resonant emphasis near cutoff when resonance > 0.2
        if resonance > 0.25 and cut < sr * 0.4:
            bw = max(60.0, cut * (0.65 - 0.45 * min(0.9, resonance)))
            lo = max(40.0, cut - bw * 0.5) / (sr * 0.5)
            hi = min(0.95, (cut + bw * 0.5) / (sr * 0.5))
            if lo < hi:
                sos_bp = signal.butter(1, [lo, hi], btype="bandpass", output="sos")
                boost = (resonance - 0.2) * 0.85
                fl += signal.sosfilt(sos_bp, seg[:, 0]) * boost
                fr += signal.sosfilt(sos_bp, seg[:, 1]) * boost

        out[pos:end, 0] += fl[:actual_len] * win[:actual_len]
        out[pos:end, 1] += fr[:actual_len] * win[:actual_len]
        weight[pos:end] += win[:actual_len]
        pos += hop

    weight = np.maximum(weight, 1e-6)
    out[:, 0] /= weight
    out[:, 1] /= weight
    return out.astype(np.float32)
