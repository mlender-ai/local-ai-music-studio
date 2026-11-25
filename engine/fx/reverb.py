"""Professional Convolution IR & Algorithmic Spatial Reverb (Phase 05 · GATE 4).

Supports 6 realistic studio space modes (`small_room`, `studio_room`, `chamber`, `plate`, `hall`, `large_ambient`)
using physically modeled Stereo Impulse Responses convolved via Spotify `pedalboard.Convolution`, with real
Decay, Pre-delay, Wet/Dry, Damping, Low-Cut, High-Cut, and Stereo Width!
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

REVERB_MODES: dict[str, dict[str, Any]] = {
    "small_room": {"name": "Small Room", "nameKo": "스몰 룸", "decaySec": 0.55, "preDelayMs": 6.0, "damping": 0.52, "earlyLevel": 0.72, "lowCutHz": 120.0, "highCutHz": 9500.0},
    "studio_room": {"name": "Studio Room", "nameKo": "스튜디오 룸", "decaySec": 1.05, "preDelayMs": 12.0, "damping": 0.45, "earlyLevel": 0.62, "lowCutHz": 110.0, "highCutHz": 10500.0},
    "chamber": {"name": "Acoustic Chamber", "nameKo": "챔버", "decaySec": 1.45, "preDelayMs": 18.0, "damping": 0.42, "earlyLevel": 0.55, "lowCutHz": 130.0, "highCutHz": 8800.0},
    "plate": {"name": "Vintage Plate", "nameKo": "빈티지 플레이트", "decaySec": 1.85, "preDelayMs": 14.0, "damping": 0.28, "earlyLevel": 0.35, "lowCutHz": 180.0, "highCutHz": 12000.0},
    "hall": {"name": "Concert Hall", "nameKo": "콘서트 홀", "decaySec": 2.65, "preDelayMs": 28.0, "damping": 0.38, "earlyLevel": 0.42, "lowCutHz": 100.0, "highCutHz": 9000.0},
    "large_ambient": {"name": "Large Ambient Space", "nameKo": "라지 앰비언트", "decaySec": 4.20, "preDelayMs": 40.0, "damping": 0.30, "earlyLevel": 0.25, "lowCutHz": 90.0, "highCutHz": 11500.0},
}


def _generate_studio_ir(
    room_type: str,
    decay_sec: float,
    pre_delay_ms: float,
    damping: float,
    early_level: float,
    stereo_width: float,
    sr: int,
) -> Path:
    """Synthesize and cache a deterministic stereo Impulse Response WAV (early reflections + damped diffuse tail)."""
    ir_dir = engine_paths.ROOT / "outputs" / "daw" / "cache" / "ir"
    ir_dir.mkdir(parents=True, exist_ok=True)
    key_str = f"{room_type}_{decay_sec:.2f}_{pre_delay_ms:.1f}_{damping:.2f}_{early_level:.2f}_{stereo_width:.2f}_{sr}"
    ir_path = ir_dir / f"rev_{hashlib.sha1(key_str.encode()).hexdigest()[:12]}.wav"
    if ir_path.is_file():
        return ir_path

    dur_sec = max(0.25, min(6.0, decay_sec + pre_delay_ms / 1000.0 + 0.12))
    n = int(round(dur_sec * sr))
    pre_n = int(round(max(0.0, pre_delay_ms) * sr / 1000.0))
    rng = np.random.default_rng(abs(hash(room_type)) % (2 ** 31))

    ir = np.zeros((n, 2), dtype=np.float64)
    # 1. Realistic stereo Early Reflections taps (5..75 ms after pre-delay)
    er_taps_ms = [5.2, 9.8, 14.3, 19.7, 25.1, 31.8, 39.4, 48.2, 57.6, 68.5]
    for idx, t_ms in enumerate(er_taps_ms):
        pos = pre_n + int(round(t_ms * sr / 1000.0))
        if pos < n:
            amp = early_level * (0.78 ** idx) * (1.0 if idx % 2 == 0 else -0.92)
            # Haas stereo decorrelation
            if idx % 2 == 0:
                ir[pos, 0] += amp
                if pos + 11 < n:
                    ir[pos + 11, 1] += amp * (1.0 - 0.45 * stereo_width)
            else:
                ir[pos, 1] += amp
                if pos + 13 < n:
                    ir[pos + 13, 0] += amp * (1.0 - 0.45 * stereo_width)

    # 2. Smoothly rising & exponentially decaying diffuse stereo tail (RT60 = decay_sec -> -60 dB at decay_sec)
    tail_len = max(64, n - pre_n)
    t = np.arange(tail_len, dtype=np.float64) / sr
    # Attack bloom over first 28ms so diffuse tail merges seamlessly after early reflections
    bloom = np.minimum(1.0, t / 0.028)
    tau = max(0.06, decay_sec / 6.907755)  # exp(-6.908) = -60 dB
    env_lo = bloom * np.exp(-t / tau)
    # High frequencies decay faster proportionally to `damping`!
    hi_tau = tau * max(0.18, 1.0 - 0.72 * damping)
    env_hi = bloom * np.exp(-t / hi_tau)

    n_l = rng.standard_normal(tail_len)
    n_r = rng.standard_normal(tail_len)
    # Mix correlated/decorrelated according to stereo_width
    corr = max(0.0, 1.0 - stereo_width)
    raw_l = n_l
    raw_r = corr * n_l + math.sqrt(max(0.0, 1.0 - corr * corr)) * n_r

    # Split noise into warm low-mid & damped high band
    sos_lp = signal.butter(2, min(0.92, 2400.0 / (sr * 0.5)), btype="lowpass", output="sos")
    sos_hp = signal.butter(2, min(0.92, 2400.0 / (sr * 0.5)), btype="highpass", output="sos")
    tail_l = signal.sosfilt(sos_lp, raw_l) * env_lo + signal.sosfilt(sos_hp, raw_l) * env_hi * 0.65
    tail_r = signal.sosfilt(sos_lp, raw_r) * env_lo + signal.sosfilt(sos_hp, raw_r) * env_hi * 0.65

    ir[pre_n : pre_n + tail_len, 0] += tail_l * 0.35
    ir[pre_n : pre_n + tail_len, 1] += tail_r * 0.35

    # L2 energy-normalize IR so wet convolution output matches studio unity level cleanly across all room sizes!
    l2_norm = float(np.sqrt(np.sum(ir[:, 0] ** 2))) + 1e-9
    ir = ir / l2_norm * 0.95
    ir = np.clip(ir, -0.98, 0.98).astype(np.float32)
    sf.write(str(ir_path), ir, sr, subtype="PCM_24")
    return ir_path


def apply_reverb(
    stereo: np.ndarray,
    sr: int,
    params: dict[str, Any],
    *,
    wet_dry: float = 0.28,
) -> np.ndarray:
    """Apply real Convolution Reverb (Pedalboard.Convolution) with Low/High Cut & Stereo Width."""
    if len(stereo) == 0:
        return stereo
    room_type = str(params.get("roomType", "studio_room"))
    preset = REVERB_MODES.get(room_type, REVERB_MODES["studio_room"])
    decay_sec = max(0.2, min(6.0, float(params.get("decaySec", preset["decaySec"]))))
    pre_delay_ms = max(0.0, min(180.0, float(params.get("preDelayMs", preset["preDelayMs"]))))
    damping = max(0.0, min(0.95, float(params.get("damping", preset["damping"]))))
    early_level = max(0.0, min(1.0, float(params.get("earlyLevel", preset["earlyLevel"]))))
    low_cut_hz = max(20.0, min(800.0, float(params.get("lowCutHz", preset["lowCutHz"]))))
    high_cut_hz = max(1200.0, min(18000.0, float(params.get("highCutHz", preset["highCutHz"]))))
    stereo_width = max(0.0, min(1.0, float(params.get("stereoWidth", 0.85))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))

    ir_path = _generate_studio_ir(room_type, decay_sec, pre_delay_ms, damping, early_level, stereo_width, sr)
    inp = stereo.astype(np.float32)

    # Filter send into reverb for clean mud-free low end & silky top end!
    wet_in = inp.copy()
    if pb is not None:
        pre_chain = pb.Pedalboard(
            [
                pb.HighpassFilter(cutoff_frequency_hz=low_cut_hz),
                pb.LowpassFilter(cutoff_frequency_hz=high_cut_hz),
                pb.Convolution(impulse_response_filename=str(ir_path), mix=1.0),
            ]
        )
        wet_sig = pre_chain(wet_in.T, sr).T.astype(np.float32)
    else:
        ir_data, _ = sf.read(str(ir_path), dtype="float32", always_2d=True)
        wl = signal.fftconvolve(wet_in[:, 0], ir_data[:, 0], mode="full")[: len(inp)]
        wr = signal.fftconvolve(wet_in[:, 1], ir_data[:, 1], mode="full")[: len(inp)]
        wet_sig = np.stack([wl, wr], axis=1).astype(np.float32)

    out = (inp * (1.0 - mix) + wet_sig * mix).astype(np.float32)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
