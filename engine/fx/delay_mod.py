"""Tempo-Synced Delay (Stereo & Ping-Pong), Modulation (Chorus/Phaser/Flanger/Tremolo) & Creative FX (Phase 05 · GATE 4)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

try:
    import pedalboard as pb
except Exception:
    pb = None  # type: ignore

SUBDIVISION_BEATS: dict[str, float] = {
    "1/16": 0.25,
    "1/8 triplet": 1.0 / 3.0,
    "1/8": 0.5,
    "1/8 dotted": 0.75,
    "1/4 triplet": 2.0 / 3.0,
    "1/4": 1.0,
    "1/2": 2.0,
}


def compute_delay_ms(params: dict[str, Any], bpm: float) -> float:
    """Resolve exact delay time in milliseconds from tempo-synced subdivision OR manual delayMs."""
    if params.get("tempoSync", True) and params.get("subdivision") in SUBDIVISION_BEATS:
        sec_per_beat = 60.0 / max(30.0, float(bpm))
        return round(SUBDIVISION_BEATS[str(params["subdivision"])] * sec_per_beat * 1000.0, 2)
    return max(10.0, min(2000.0, float(params.get("delayMs", 375.0))))


def apply_delay(
    stereo: np.ndarray,
    sr: int,
    params: dict[str, Any],
    *,
    bpm: float = 120.0,
    wet_dry: float = 0.25,
) -> np.ndarray:
    """Apply real Stereo or Ping-Pong Delay with Feedback Loop Low/High Cut filters."""
    if len(stereo) == 0:
        return stereo
    delay_ms = compute_delay_ms(params, bpm)
    feedback = max(0.0, min(0.88, float(params.get("feedback", 0.38))))
    ping_pong = bool(params.get("pingPong", True))
    low_cut_hz = max(40.0, min(1500.0, float(params.get("lowCutHz", 180.0))))
    high_cut_hz = max(1200.0, min(16000.0, float(params.get("highCutHz", 5500.0))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))

    inp = stereo.astype(np.float64)
    n = len(inp)
    d_samp = max(16, int(round(delay_ms * sr / 1000.0)))

    # Band-limit input entering the delay line (classic tape/dub feedback tone!)
    sos_hp = signal.butter(2, min(0.92, low_cut_hz / (sr * 0.5)), btype="highpass", output="sos")
    sos_lp = signal.butter(2, min(0.92, high_cut_hz / (sr * 0.5)), btype="lowpass", output="sos")
    filt_l = signal.sosfilt(sos_lp, signal.sosfilt(sos_hp, inp[:, 0]))
    filt_r = signal.sosfilt(sos_lp, signal.sosfilt(sos_hp, inp[:, 1]))

    # Iterative multi-tap feedback accumulation (exact, zero-drift, ping-pong stereo cross-feed!)
    wet_l = np.zeros(n, dtype=np.float64)
    wet_r = np.zeros(n, dtype=np.float64)
    tap_l = filt_l.copy()
    tap_r = filt_r.copy()
    gain = 1.0
    max_taps = min(24, max(1, int(math.ceil(n / max(1, d_samp)))))

    for tap_idx in range(1, max_taps + 1):
        shift = tap_idx * d_samp
        if shift >= n or gain < 1e-4:
            break
        if ping_pong:
            if tap_idx == 1:
                src_l = 0.5 * (tap_l + tap_r)
                src_r = np.zeros_like(src_l)
            elif tap_idx % 2 == 0:
                src_l = np.zeros_like(tap_l)
                src_r = 0.5 * (tap_l + tap_r)
            else:
                src_l = 0.5 * (tap_l + tap_r)
                src_r = np.zeros_like(tap_r)
        else:
            src_l, src_r = tap_l, tap_r

        avail = n - shift
        wet_l[shift:] += src_l[:avail] * gain
        wet_r[shift:] += src_r[:avail] * gain
        gain *= feedback
        # Subtle progressive high-frequency darkening on subsequent repeats
        tap_l = signal.sosfilt(sos_lp, tap_l)
        tap_r = signal.sosfilt(sos_lp, tap_r)

    wet = np.stack([wet_l, wet_r], axis=1)
    out = inp * (1.0 - mix) + wet * mix
    return np.nan_to_num(out.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def apply_chorus(stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 0.35) -> np.ndarray:
    if len(stereo) == 0:
        return stereo
    rate = max(0.05, min(10.0, float(params.get("rateHz", 0.9))))
    depth = max(0.0, min(1.0, float(params.get("depth", 0.35))))
    delay_ms = max(2.0, min(25.0, float(params.get("centreDelayMs", 7.0))))
    fb = max(-0.8, min(0.8, float(params.get("feedback", 0.15))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))
    inp = stereo.astype(np.float32)
    if pb is not None:
        return pb.Pedalboard([pb.Chorus(rate_hz=rate, depth=depth, centre_delay_ms=delay_ms, feedback=fb, mix=mix)])(inp.T, sr).T.astype(np.float32)
    return inp


def apply_phaser(stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 0.45) -> np.ndarray:
    if len(stereo) == 0:
        return stereo
    rate = max(0.05, min(10.0, float(params.get("rateHz", 0.6))))
    depth = max(0.0, min(1.0, float(params.get("depth", 0.55))))
    centre_hz = max(150.0, min(4000.0, float(params.get("centreFrequencyHz", 950.0))))
    fb = max(-0.85, min(0.85, float(params.get("feedback", 0.35))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))
    inp = stereo.astype(np.float32)
    if pb is not None:
        return pb.Pedalboard([pb.Phaser(rate_hz=rate, depth=depth, centre_frequency_hz=centre_hz, feedback=fb, mix=mix)])(inp.T, sr).T.astype(np.float32)
    return inp


def apply_flanger(stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 0.40) -> np.ndarray:
    """Short-delay modulated stereo Flanger (1–6 ms comb sweep)."""
    if len(stereo) == 0:
        return stereo
    rate = max(0.05, min(8.0, float(params.get("rateHz", 0.4))))
    depth = max(0.0, min(1.0, float(params.get("depth", 0.6))))
    fb = max(-0.7, min(0.7, float(params.get("feedback", 0.45))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))
    inp = stereo.astype(np.float32)
    if pb is not None:
        return pb.Pedalboard([pb.Chorus(rate_hz=rate, depth=depth, centre_delay_ms=2.2, feedback=fb, mix=mix)])(inp.T, sr).T.astype(np.float32)
    return inp


def apply_tremolo(stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 1.0) -> np.ndarray:
    if len(stereo) == 0:
        return stereo
    rate = max(0.2, min(18.0, float(params.get("rateHz", 4.5))))
    depth = max(0.0, min(1.0, float(params.get("depth", 0.55))))
    phase_deg = float(params.get("stereoPhaseDeg", 90.0))
    t = np.arange(len(stereo), dtype=np.float64) / sr
    mod_l = 1.0 - depth * 0.5 * (1.0 + np.sin(2.0 * math.pi * rate * t))
    mod_r = 1.0 - depth * 0.5 * (1.0 + np.sin(2.0 * math.pi * rate * t + math.radians(phase_deg)))
    wet = np.stack([stereo[:, 0] * mod_l, stereo[:, 1] * mod_r], axis=1).astype(np.float32)
    mix = max(0.0, min(1.0, float(wet_dry)))
    return (stereo * (1.0 - mix) + wet * mix).astype(np.float32)


def apply_saturation(stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 0.65) -> np.ndarray:
    """Warm analog tape / tube harmonic saturator with asymmetric even/odd overtones & warmth filter."""
    if len(stereo) == 0:
        return stereo
    drive_db = max(0.0, min(30.0, float(params.get("driveDb", 8.0))))
    tone_hz = max(1200.0, min(18000.0, float(params.get("toneHz", 9500.0))))
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))
    gain = float(10.0 ** (drive_db / 20.0))
    inp = stereo.astype(np.float64)
    # Asymmetric soft-clip adds 2nd & 3rd harmonics like real analog tape/tube!
    x = inp * gain
    sat = np.tanh(x + 0.14 * x * x) - 0.14 * np.tanh(0.0)
    # Level-compensate loudness cleanly
    comp = 1.0 / max(1.0, math.sqrt(gain) * 0.85)
    wet = (sat * comp).astype(np.float32)
    if tone_hz < 16000.0:
        sos = signal.butter(2, min(0.95, tone_hz / (sr * 0.5)), btype="lowpass", output="sos")
        wet[:, 0] = signal.sosfilt(sos, wet[:, 0]).astype(np.float32)
        wet[:, 1] = signal.sosfilt(sos, wet[:, 1]).astype(np.float32)
    return (stereo * (1.0 - mix) + wet * mix).astype(np.float32)


def apply_creative_fx(fx_type: str, stereo: np.ndarray, sr: int, params: dict[str, Any], *, wet_dry: float = 1.0) -> np.ndarray:
    """Creative Pedalboard FX: distortion, bitcrush, pitch_shift, ladder_filter."""
    if len(stereo) == 0:
        return stereo
    inp = stereo.astype(np.float32)
    mix = max(0.0, min(1.0, float(params.get("wetDry", wet_dry))))
    if pb is None:
        return inp

    if fx_type == "distortion":
        drive = max(0.0, min(40.0, float(params.get("driveDb", 16.0))))
        wet = pb.Pedalboard([pb.Distortion(drive_db=drive)])(inp.T, sr).T.astype(np.float32)
    elif fx_type == "bitcrush":
        bits = max(3.0, min(16.0, float(params.get("bitDepth", 8.0))))
        wet = pb.Pedalboard([pb.Bitcrush(bit_depth=bits)])(inp.T, sr).T.astype(np.float32)
    elif fx_type == "pitch_shift":
        semi = max(-12.0, min(12.0, float(params.get("semitones", 0.0))))
        wet = pb.Pedalboard([pb.PitchShift(semitones=semi)])(inp.T, sr).T.astype(np.float32)
    elif fx_type == "filter":
        cut = max(80.0, min(18000.0, float(params.get("cutoffHz", 1600.0))))
        res = max(0.0, min(0.95, float(params.get("resonance", 0.35))))
        drv = max(1.0, min(6.0, float(params.get("drive", 1.2))))
        mode_str = str(params.get("mode", "lpf24")).lower()
        lmode = pb.LadderFilter.Mode.HPF24 if "hp" in mode_str else (pb.LadderFilter.Mode.BPF24 if "bp" in mode_str else pb.LadderFilter.Mode.LPF24)
        wet = pb.Pedalboard([pb.LadderFilter(mode=lmode, cutoff_hz=cut, resonance=res, drive=drv)])(inp.T, sr).T.astype(np.float32)
    else:
        return inp

    return (inp * (1.0 - mix) + wet * mix).astype(np.float32) if mix < 0.999 else wet
