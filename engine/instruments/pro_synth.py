"""Professional Hybrid Subtractive / FM / Supersaw Synthesizer (Phase 05 · GATE 3).

Provides studio-grade analog/FM synthesis with:
- Band-limited additive/PolyBLEP Oscillators: saw, square, triangle, sine, supersaw
- True Multi-Voice Unison (1–7 voices) with stereo pan spread & cent detuning
- FM Synthesis operator (fmAmount, fmRatio) + Sub Oscillator + White Noise
- Resonant Moog-style 24 dB/oct Ladder Filter (`pedalboard.LadderFilter`) + Filter Envelope
- Full Amp ADSR, LFO (Pitch vibrato & Filter modulation), Glide/Portamento, Velocity sensitivity
- Named Studio Preset Banks for Analog & FM instruments
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

try:
    import pedalboard as pb
except Exception:
    pb = None  # type: ignore


PRO_SYNTH_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "pro-synth-analog": {
        "warm-analog-pluck": {
            "name": "Warm Analog Pluck",
            "nameKo": "웜 아날로그 플럭",
            "waveform": "saw",
            "unisonVoices": 3,
            "detuneCents": 11.0,
            "stereoSpread": 0.65,
            "subLevel": 0.25,
            "fmAmount": 0.15,
            "fmRatio": 2.0,
            "noiseLevel": 0.02,
            "cutoffHz": 1850.0,
            "resonance": 0.28,
            "drive": 1.4,
            "filterEnvAmount": 2800.0,
            "attackSec": 0.004,
            "decaySec": 0.22,
            "sustain": 0.32,
            "releaseSec": 0.18,
            "lfoRateHz": 0.8,
            "lfoDepthPitch": 0.001,
            "glideSec": 0.0,
        },
        "deep-house-chord": {
            "name": "Deep House Chord Stab",
            "nameKo": "딥하우스 코드 스탭",
            "waveform": "saw",
            "unisonVoices": 5,
            "detuneCents": 14.0,
            "stereoSpread": 0.82,
            "subLevel": 0.20,
            "fmAmount": 0.0,
            "fmRatio": 1.0,
            "noiseLevel": 0.015,
            "cutoffHz": 1200.0,
            "resonance": 0.35,
            "drive": 1.7,
            "filterEnvAmount": 2400.0,
            "attackSec": 0.008,
            "decaySec": 0.26,
            "sustain": 0.38,
            "releaseSec": 0.25,
            "lfoRateHz": 0.4,
            "lfoDepthPitch": 0.0015,
            "glideSec": 0.0,
        },
        "wide-analog-pad": {
            "name": "Wide Analog Pad",
            "nameKo": "와이드 아날로그 패드",
            "waveform": "supersaw",
            "unisonVoices": 7,
            "detuneCents": 22.0,
            "stereoSpread": 0.95,
            "subLevel": 0.18,
            "fmAmount": 0.0,
            "fmRatio": 1.0,
            "noiseLevel": 0.01,
            "cutoffHz": 1650.0,
            "resonance": 0.18,
            "drive": 1.2,
            "filterEnvAmount": 900.0,
            "attackSec": 0.28,
            "decaySec": 0.65,
            "sustain": 0.82,
            "releaseSec": 0.60,
            "lfoRateHz": 0.45,
            "lfoDepthPitch": 0.0025,
            "glideSec": 0.0,
        },
        "acid-saw-bass": {
            "name": "Acid Saw Bass",
            "nameKo": "애시드 소우 베이스",
            "waveform": "saw",
            "unisonVoices": 1,
            "detuneCents": 0.0,
            "stereoSpread": 0.05,
            "subLevel": 0.45,
            "fmAmount": 0.1,
            "fmRatio": 1.0,
            "noiseLevel": 0.0,
            "cutoffHz": 680.0,
            "resonance": 0.62,
            "drive": 2.4,
            "filterEnvAmount": 2600.0,
            "attackSec": 0.003,
            "decaySec": 0.18,
            "sustain": 0.48,
            "releaseSec": 0.08,
            "lfoRateHz": 0.0,
            "lfoDepthPitch": 0.0,
            "glideSec": 0.04,
        },
        "sub-808-glide": {
            "name": "Sub 808 Analog Bass",
            "nameKo": "서브 808 아날로그 베이스",
            "waveform": "triangle",
            "unisonVoices": 1,
            "detuneCents": 0.0,
            "stereoSpread": 0.0,
            "subLevel": 0.85,
            "fmAmount": 0.35,
            "fmRatio": 1.0,
            "noiseLevel": 0.0,
            "cutoffHz": 420.0,
            "resonance": 0.15,
            "drive": 1.8,
            "filterEnvAmount": 350.0,
            "attackSec": 0.004,
            "decaySec": 0.32,
            "sustain": 0.72,
            "releaseSec": 0.12,
            "lfoRateHz": 0.0,
            "lfoDepthPitch": 0.0,
            "glideSec": 0.06,
        },
        "supersaw-anthem": {
            "name": "Supersaw Lead Anthem",
            "nameKo": "슈퍼소우 리드 앤섬",
            "waveform": "supersaw",
            "unisonVoices": 7,
            "detuneCents": 26.0,
            "stereoSpread": 0.92,
            "subLevel": 0.22,
            "fmAmount": 0.05,
            "fmRatio": 2.0,
            "noiseLevel": 0.02,
            "cutoffHz": 5800.0,
            "resonance": 0.22,
            "drive": 1.6,
            "filterEnvAmount": 2400.0,
            "attackSec": 0.008,
            "decaySec": 0.24,
            "sustain": 0.75,
            "releaseSec": 0.24,
            "lfoRateHz": 5.2,
            "lfoDepthPitch": 0.002,
            "glideSec": 0.03,
        },
    },
    "pro-synth-fm": {
        "modern-house-hook": {
            "name": "Modern House FM Hook",
            "nameKo": "모던 하우스 FM 훅",
            "waveform": "sine",
            "unisonVoices": 3,
            "detuneCents": 9.0,
            "stereoSpread": 0.72,
            "subLevel": 0.15,
            "fmAmount": 2.4,
            "fmRatio": 2.0,
            "noiseLevel": 0.01,
            "cutoffHz": 4800.0,
            "resonance": 0.20,
            "drive": 1.3,
            "filterEnvAmount": 2200.0,
            "attackSec": 0.003,
            "decaySec": 0.18,
            "sustain": 0.42,
            "releaseSec": 0.16,
            "lfoRateHz": 1.5,
            "lfoDepthPitch": 0.001,
            "glideSec": 0.0,
        },
        "glass-fm-bell": {
            "name": "Glass FM Bell",
            "nameKo": "글래스 FM 벨",
            "waveform": "sine",
            "unisonVoices": 3,
            "detuneCents": 6.0,
            "stereoSpread": 0.78,
            "subLevel": 0.0,
            "fmAmount": 3.8,
            "fmRatio": 3.5,
            "noiseLevel": 0.0,
            "cutoffHz": 9500.0,
            "resonance": 0.12,
            "drive": 1.0,
            "filterEnvAmount": 1800.0,
            "attackSec": 0.002,
            "decaySec": 0.55,
            "sustain": 0.18,
            "releaseSec": 0.50,
            "lfoRateHz": 3.5,
            "lfoDepthPitch": 0.0015,
            "glideSec": 0.0,
        },
        "fm-sub-punch": {
            "name": "FM Sub Punch Bass",
            "nameKo": "FM 서브 펀치 베이스",
            "waveform": "sine",
            "unisonVoices": 1,
            "detuneCents": 0.0,
            "stereoSpread": 0.0,
            "subLevel": 0.72,
            "fmAmount": 2.8,
            "fmRatio": 2.0,
            "noiseLevel": 0.0,
            "cutoffHz": 1400.0,
            "resonance": 0.18,
            "drive": 1.6,
            "filterEnvAmount": 1200.0,
            "attackSec": 0.003,
            "decaySec": 0.15,
            "sustain": 0.65,
            "releaseSec": 0.07,
            "lfoRateHz": 0.0,
            "lfoDepthPitch": 0.0,
            "glideSec": 0.02,
        },
        "metallic-fm-lead": {
            "name": "Metallic FM Lead",
            "nameKo": "메탈릭 FM 리드",
            "waveform": "triangle",
            "unisonVoices": 3,
            "detuneCents": 13.0,
            "stereoSpread": 0.75,
            "subLevel": 0.1,
            "fmAmount": 4.2,
            "fmRatio": 3.0,
            "noiseLevel": 0.015,
            "cutoffHz": 6200.0,
            "resonance": 0.30,
            "drive": 1.8,
            "filterEnvAmount": 2500.0,
            "attackSec": 0.004,
            "decaySec": 0.22,
            "sustain": 0.55,
            "releaseSec": 0.20,
            "lfoRateHz": 5.5,
            "lfoDepthPitch": 0.003,
            "glideSec": 0.025,
        },
    },
}


def _bandlimited_osc(phase: np.ndarray, waveform: str, freq_hz: float, sr: int) -> np.ndarray:
    """Generate clean alias-reduced oscillator waveform from instantaneous phase array."""
    if waveform == "sine":
        return np.sin(phase)
    max_h = max(1, min(18, int((sr * 0.42) / max(20.0, freq_hz))))
    if waveform == "triangle":
        out = np.zeros_like(phase)
        for k in range(min(max_h, 9)):
            h = 2 * k + 1
            sign = -1.0 if (k % 2 == 1) else 1.0
            out += sign * (1.0 / (h * h)) * np.sin(h * phase)
        return out * (8.0 / (math.pi * math.pi))
    if waveform == "square":
        out = np.zeros_like(phase)
        for k in range(min(max_h, 11)):
            h = 2 * k + 1
            out += (1.0 / h) * np.sin(h * phase)
        return out * (4.0 / math.pi)
    # saw / supersaw
    out = np.zeros_like(phase)
    for h in range(1, min(max_h + 1, 15)):
        out += ((-1.0) ** (h + 1)) * (1.0 / h) * np.sin(h * phase)
    return out * (2.0 / math.pi)


def _adsr_env(n: int, dur_n: int, sr: int, atk: float, dec: float, sus: float, rel: float) -> np.ndarray:
    env = np.zeros(n, dtype=np.float64)
    if n <= 0:
        return env
    atk_n = min(n, max(1, int(round(max(0.001, atk) * sr))))
    env[:atk_n] = np.linspace(0.0, 1.0, atk_n)
    off_i = min(n, max(atk_n, dur_n))
    body_n = off_i - atk_n
    if body_n > 0:
        tb = np.arange(body_n, dtype=np.float64) / sr
        env[atk_n:off_i] = sus + (1.0 - sus) * np.exp(-tb / max(0.01, dec))
    rel_n = n - off_i
    if rel_n > 0:
        sv = float(env[off_i - 1]) if off_i > 0 else sus
        tr = np.arange(rel_n, dtype=np.float64) / sr
        env[off_i:] = sv * np.exp(-tr / max(0.015, rel * 0.45)) * np.linspace(1.0, 0.0, rel_n)
    return env


def resolve_pro_synth_params(
    instrument_id: str,
    preset_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bank = PRO_SYNTH_PRESETS.get(instrument_id, PRO_SYNTH_PRESETS["pro-synth-analog"])
    default_key = next(iter(bank))
    base = dict(bank.get(preset_id or "", bank[default_key]))
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                base[k] = v
    return base


def render_pro_synth_sequence(
    notes: list[dict[str, Any]],
    *,
    instrument_id: str = "pro-synth-analog",
    preset_id: str | None = None,
    params: dict[str, Any] | None = None,
    bpm: float = 120.0,
    total_beats: float = 16.0,
    sr: int = 48000,
) -> np.ndarray:
    """Render full MIDI clip through our Professional Subtractive/FM/Unison Synth + Pedalboard LadderFilter."""
    cfg = resolve_pro_synth_params(instrument_id, preset_id, params)
    sec_per_beat = 60.0 / max(30.0, float(bpm))
    rel_sec = max(0.03, float(cfg.get("releaseSec", 0.2)))
    total_samples = max(int(sr * 0.5), int(round((total_beats * sec_per_beat + rel_sec + 0.35) * sr)))
    if not notes:
        return np.zeros((total_samples, 2), dtype=np.float32)

    waveform = str(cfg.get("waveform", "saw"))
    unison = max(1, min(7, int(cfg.get("unisonVoices", 3))))
    detune_cents = max(0.0, min(60.0, float(cfg.get("detuneCents", 12.0))))
    spread = max(0.0, min(1.0, float(cfg.get("stereoSpread", 0.65))))
    sub_lvl = max(0.0, min(1.0, float(cfg.get("subLevel", 0.2))))
    fm_amt = max(0.0, min(8.0, float(cfg.get("fmAmount", 0.0))))
    fm_ratio = max(0.25, min(12.0, float(cfg.get("fmRatio", 2.0))))
    noise_lvl = max(0.0, min(0.5, float(cfg.get("noiseLevel", 0.01))))
    atk_s = max(0.001, float(cfg.get("attackSec", 0.005)))
    dec_s = max(0.015, float(cfg.get("decaySec", 0.22)))
    sus_v = max(0.0, min(1.0, float(cfg.get("sustain", 0.45))))
    cutoff_hz = max(80.0, min(18000.0, float(cfg.get("cutoffHz", 2400.0))))
    reso = max(0.0, min(0.92, float(cfg.get("resonance", 0.25))))
    drive = max(1.0, min(8.0, float(cfg.get("drive", 1.3))))
    filt_env_amt = float(cfg.get("filterEnvAmount", 1800.0))
    lfo_rate = max(0.0, float(cfg.get("lfoRateHz", 0.8)))
    lfo_pitch = max(0.0, float(cfg.get("lfoDepthPitch", 0.001)))
    glide_s = max(0.0, float(cfg.get("glideSec", 0.0)))
    vel_sens = max(0.0, min(1.0, float(cfg.get("velocitySensitivity", 0.85))))

    buf = np.zeros((total_samples, 2), dtype=np.float64)
    rng = np.random.default_rng(2026)

    sorted_notes = sorted(notes, key=lambda n: float(n.get("startBeat", 0.0)))
    prev_freq: float | None = None

    for n in sorted_notes:
        st_sec = max(0.0, float(n.get("startBeat", 0.0)) * sec_per_beat)
        dur_sec = max(0.03, float(n.get("durationBeats", 0.25)) * sec_per_beat)
        pitch = max(12, min(115, int(n.get("pitch", 60))))
        vel = max(1, min(127, int(n.get("velocity", 96))))
        freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))

        n_samp = int(round((dur_sec + rel_sec) * sr))
        dur_n = int(round(dur_sec * sr))
        dst = int(round(st_sec * sr))
        if dst >= total_samples or n_samp <= 0:
            continue

        t = np.arange(n_samp, dtype=np.float64) / sr
        # Pitch contour with optional glide/portamento + LFO vibrato
        if glide_s > 0.002 and prev_freq is not None:
            f_inst = freq + (prev_freq - freq) * np.exp(-t / glide_s)
        else:
            f_inst = np.full(n_samp, freq, dtype=np.float64)
        prev_freq = freq

        if lfo_rate > 0.0 and lfo_pitch > 0.0:
            f_inst = f_inst * (1.0 + lfo_pitch * np.sin(2.0 * math.pi * lfo_rate * t))

        amp_env = _adsr_env(n_samp, dur_n, sr, atk_s, dec_s, sus_v, rel_sec)
        vel_gain = (1.0 - vel_sens) + vel_sens * (vel / 127.0)

        left = np.zeros(n_samp, dtype=np.float64)
        right = np.zeros(n_samp, dtype=np.float64)

        # Unison voice spread
        if unison == 1:
            offsets = [0.0]
            pans = [0.0]
        else:
            offsets = np.linspace(-detune_cents, detune_cents, unison).tolist()
            pans = np.linspace(-spread, spread, unison).tolist()

        voice_scale = 1.0 / math.sqrt(unison)
        fm_env = np.exp(-t / max(0.04, dec_s * 0.9))

        for u_idx, (c_off, pan_v) in enumerate(zip(offsets, pans)):
            ratio = 2.0 ** (c_off / 1200.0)
            ph = 2.0 * math.pi * np.cumsum(f_inst * ratio) / sr + (u_idx * 0.73)
            if fm_amt > 0.01:
                mod = fm_amt * (0.25 + 0.75 * fm_env) * np.sin(ph * fm_ratio)
                osc = _bandlimited_osc(ph + mod, waveform, freq * ratio, sr)
            else:
                osc = _bandlimited_osc(ph, waveform, freq * ratio, sr)
            pl = math.cos((pan_v + 1.0) * math.pi * 0.25)
            pr = math.sin((pan_v + 1.0) * math.pi * 0.25)
            left += osc * pl * voice_scale
            right += osc * pr * voice_scale

        if sub_lvl > 0.005:
            sub_ph = 2.0 * math.pi * np.cumsum(f_inst * 0.5) / sr
            sub_sig = np.sin(sub_ph) * sub_lvl
            left += sub_sig * 0.707
            right += sub_sig * 0.707

        if noise_lvl > 0.001:
            n_sig = rng.standard_normal(n_samp) * noise_lvl * np.exp(-t * 14.0)
            left += n_sig
            right += n_sig

        # Per-note dynamic brightness envelope shaping (approximates filter env before master LadderFilter!)
        if filt_env_amt > 50.0:
            peak_cut = min(sr * 0.44, max(160.0, cutoff_hz + filt_env_amt * vel_gain))
            # Blend bright attack into darker sustained body smoothly
            sos_dark = signal.butter(2, min(0.95, max(0.008, cutoff_hz / (sr * 0.5))), btype="lowpass", output="sos")
            sos_bright = signal.butter(2, min(0.95, max(0.01, peak_cut / (sr * 0.5))), btype="lowpass", output="sos")
            f_env = np.exp(-t / max(0.03, dec_s))
            left = signal.sosfilt(sos_bright, left) * f_env + signal.sosfilt(sos_dark, left) * (1.0 - f_env)
            right = signal.sosfilt(sos_bright, right) * f_env + signal.sosfilt(sos_dark, right) * (1.0 - f_env)

        gain = vel_gain * 0.26
        left *= amp_env * gain
        right *= amp_env * gain

        w = min(n_samp, total_samples - dst)
        buf[dst : dst + w, 0] += left[:w]
        buf[dst : dst + w, 1] += right[:w]

    out = buf.astype(np.float32)

    # Apply real Spotify Pedalboard Moog-style resonant LadderFilter!
    if pb is not None:
        try:
            board = pb.Pedalboard(
                [
                    pb.LadderFilter(
                        mode=pb.LadderFilter.Mode.LPF24,
                        cutoff_hz=float(min(18000.0, max(100.0, cutoff_hz + filt_env_amt * 0.35))),
                        resonance=float(min(0.95, max(0.0, reso))),
                        drive=float(min(8.0, max(1.0, drive))),
                    )
                ]
            )
            # pedalboard expects (channels, samples)
            proc = board(out.T, sr)
            out = proc.T.astype(np.float32)
        except Exception:
            pass

    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
