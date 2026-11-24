"""Studio-quality multi-timbre Python synth voices (mirrored in apps/daw/src/audio/instruments.ts).

Supports 6 distinct musical instruments + legacy basic-poly-synth so generated & edited MIDI
sounds like actual Drums, FM Sub Bass, Stereo Synth Hook, Electric Piano, Clean Guitar, and Warm Pad.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "drum-kit-electronic",
        "name": "Electronic Drum Kit",
        "nameKo": "일렉트로닉 드럼 킷",
        "category": "drums",
        "role": "drums",
        "engine": "builtin-dsp-synth",
        "description": "GM-mapped synthesized kick, snare, clap, closed/open hats, crash & toms",
    },
    {
        "id": "bass-fm-sub",
        "name": "FM Sub Bass",
        "nameKo": "FM 서브 베이스",
        "category": "bass",
        "role": "bass",
        "engine": "builtin-dsp-synth",
        "description": "Tight mono sub-fundamental with fast punchy FM transient pluck",
    },
    {
        "id": "synth-fm-hook",
        "name": "Stereo Synth Hook",
        "nameKo": "스테레오 신스 훅",
        "category": "synth",
        "role": "synth_hook",
        "engine": "builtin-dsp-synth",
        "description": "Wide dual-detuned melodic lead/hook synth with dynamic filter envelope",
    },
    {
        "id": "keys-electric-ep",
        "name": "Warm Electric Piano",
        "nameKo": "일렉트릭 피아노 (EP)",
        "category": "keys",
        "role": "keys",
        "engine": "builtin-dsp-synth",
        "description": "Bell tine attack + rich warm harmonic sustain with gentle stereo shimmer",
    },
    {
        "id": "guitar-clean-pluck",
        "name": "Clean Guitar Pluck",
        "nameKo": "클린 기타 플럭",
        "category": "guitar",
        "role": "guitar",
        "engine": "builtin-dsp-synth",
        "description": "Crisp plucked transient with natural woody overtone damping",
    },
    {
        "id": "pad-warm-analog",
        "name": "Warm Analog Pad",
        "nameKo": "웜 아날로그 패드",
        "category": "pad",
        "role": "pad",
        "engine": "builtin-dsp-synth",
        "description": "Slow-attack wide stereo chorus harmonic bed for atmosphere and breakdowns",
    },
    {
        "id": "basic-poly-synth",
        "name": "Basic Poly Synth",
        "nameKo": "기본 폴리 신스",
        "category": "synth",
        "role": "synth",
        "engine": "builtin-dsp-synth",
        "description": "Phase 01 warm band-limited polyphonic synthesizer",
    },
]


def list_instruments() -> list[dict[str, Any]]:
    return [dict(item) for item in INSTRUMENTS]


def _adsr(n_samples: int, dur_samples: int, sr: int, atk_s: float, dec_s: float, sus: float) -> np.ndarray:
    env = np.zeros(n_samples, dtype=np.float32)
    if n_samples == 0:
        return env
    atk_n = min(n_samples, max(1, int(round(atk_s * sr))))
    env[:atk_n] = np.linspace(0.0, 1.0, atk_n, dtype=np.float32)
    off_idx = min(n_samples, max(atk_n, dur_samples))
    body_n = off_idx - atk_n
    if body_n > 0:
        t_body = np.arange(body_n, dtype=np.float32) / float(sr)
        tau = max(0.015, dec_s)
        env[atk_n:off_idx] = sus + (1.0 - sus) * np.exp(-t_body / tau)
    rel_n = n_samples - off_idx
    if rel_n > 0:
        start_v = float(env[off_idx - 1]) if off_idx > 0 else sus
        env[off_idx:] = start_v * np.linspace(1.0, 0.0, rel_n, dtype=np.float32) ** 1.5
    return env


def _synth_drum(pitch: int, velocity: int, sr: int) -> np.ndarray:
    amp = (velocity / 127.0) * 0.62
    rng = np.random.default_rng(seed=pitch * 97 + velocity)

    # Kick (35, 36)
    if pitch in (35, 36):
        n = int(0.32 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        freq = 46.0 + 128.0 * np.exp(-t * 36.0)
        phase = 2.0 * math.pi * np.cumsum(freq) / sr
        body = np.sin(phase) * np.exp(-t * 9.5)
        click = np.sin(2.0 * math.pi * 1650.0 * t) * np.exp(-t * 180.0) * 0.25
        mono = np.tanh((body + click) * 1.35) * amp * 1.15
        return np.stack([mono, mono], axis=1).astype(np.float32)

    # Snare (38, 40)
    if pitch in (38, 40):
        n = int(0.24 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        f_body = 165.0 + 55.0 * np.exp(-t * 45.0)
        body = np.sin(2.0 * math.pi * np.cumsum(f_body) / sr) * np.exp(-t * 22.0) * 0.58
        noise = rng.standard_normal(n)
        sos = signal.butter(2, [950.0, 7500.0], btype="bandpass", fs=sr, output="sos")
        snare_n = signal.sosfilt(sos, noise) * np.exp(-t * 16.0) * 0.72
        mono = np.tanh((body + snare_n) * 1.2) * amp * 0.92
        return np.stack([mono, mono], axis=1).astype(np.float32)

    # Clap (39)
    if pitch == 39:
        n = int(0.26 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        noise_l = rng.standard_normal(n)
        noise_r = rng.standard_normal(n)
        sos = signal.butter(2, [900.0, 4800.0], btype="bandpass", fs=sr, output="sos")
        nl = signal.sosfilt(sos, noise_l)
        nr = signal.sosfilt(sos, noise_r)
        env = np.zeros(n, dtype=np.float64)
        for d_ms in (0.0, 11.0, 22.0):
            s = int(d_ms * sr / 1000.0)
            if s < n:
                env[s:] += np.exp(-(t[: n - s]) * 55.0) * 0.55
        s_tail = int(0.030 * sr)
        if s_tail < n:
            env[s_tail:] += np.exp(-(t[: n - s_tail]) * 14.0) * 0.85
        left = np.tanh(nl * env * 1.1) * amp * 0.82
        right = np.tanh(nr * env * 1.1) * amp * 0.82
        return np.stack([left, right], axis=1).astype(np.float32)

    # Closed Hat (42, 44)
    if pitch in (42, 44):
        n = int(0.075 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        noise = rng.standard_normal(n)
        sos = signal.butter(2, 6200.0, btype="highpass", fs=sr, output="sos")
        hh = signal.sosfilt(sos, noise) * np.exp(-t * 58.0)
        mono = hh * amp * 0.62
        return np.stack([mono * 1.05, mono * 0.95], axis=1).astype(np.float32)

    # Open Hat (46)
    if pitch == 46:
        n = int(0.28 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        noise_l = rng.standard_normal(n)
        noise_r = rng.standard_normal(n)
        sos = signal.butter(2, 5400.0, btype="highpass", fs=sr, output="sos")
        env = np.exp(-t * 11.5)
        left = signal.sosfilt(sos, noise_l) * env * amp * 0.58
        right = signal.sosfilt(sos, noise_r) * env * amp * 0.58
        return np.stack([left, right], axis=1).astype(np.float32)

    # Crash / Ride (49, 51, 52, 55, 57)
    if pitch >= 49:
        n = int(0.95 * sr)
        t = np.arange(n, dtype=np.float64) / sr
        noise_l = rng.standard_normal(n)
        noise_r = rng.standard_normal(n)
        sos = signal.butter(2, 3400.0, btype="highpass", fs=sr, output="sos")
        env = np.exp(-t * 3.8)
        shimmer = 0.15 * np.sin(2.0 * math.pi * 5180.0 * t) * np.exp(-t * 7.0)
        left = (signal.sosfilt(sos, noise_l) * env + shimmer) * amp * 0.52
        right = (signal.sosfilt(sos, noise_r) * env - shimmer) * amp * 0.52
        return np.stack([left, right], axis=1).astype(np.float32)

    # Toms (41, 43, 45, 47, 48, 50)
    base_f = 82.0 + max(0, pitch - 41) * 14.0
    n = int(0.28 * sr)
    t = np.arange(n, dtype=np.float64) / sr
    freq = base_f + (base_f * 0.55) * np.exp(-t * 28.0)
    mono = np.sin(2.0 * math.pi * np.cumsum(freq) / sr) * np.exp(-t * 10.0) * amp * 0.85
    return np.stack([mono, mono], axis=1).astype(np.float32)


def synth_note_for_instrument(
    instrument_ref: str | None,
    pitch: int,
    velocity: int,
    duration_sec: float,
    sr: int,
) -> np.ndarray:
    """Render a stereo float32 voice for the specified instrumentRef."""
    inst = instrument_ref or "basic-poly-synth"
    if inst == "drum-kit-electronic":
        return _synth_drum(pitch, velocity, sr)

    freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    vel_norm = max(0.05, velocity / 127.0)

    if inst == "bass-fm-sub":
        rel = 0.06
        total_sec = max(0.03, duration_sec + rel)
        n = int(round(total_sec * sr))
        t = np.arange(n, dtype=np.float64) / sr
        dur_n = int(round(duration_sec * sr))
        env = _adsr(n, dur_n, sr, atk_s=0.004, dec_s=0.14, sus=0.72)
        mod_idx = 2.6 * np.exp(-t * 16.0) + 0.35
        carrier = np.sin(2.0 * math.pi * freq * t + mod_idx * np.sin(2.0 * math.pi * (freq * 2.0) * t))
        sub = np.sin(2.0 * math.pi * freq * t)
        sig = np.tanh((0.68 * sub + 0.42 * carrier) * 1.15) * env * vel_norm * 0.44
        mono = sig.astype(np.float32)
        return np.stack([mono, mono], axis=1)

    if inst == "synth-fm-hook":
        rel = 0.14
        total_sec = max(0.04, duration_sec + rel)
        n = int(round(total_sec * sr))
        t = np.arange(n, dtype=np.float64) / sr
        dur_n = int(round(duration_sec * sr))
        env = _adsr(n, dur_n, sr, atk_s=0.006, dec_s=0.18, sus=0.58)
        bright_env = np.exp(-t * 7.5)
        # Dual slight-detuned rich harmonic voices for wide stereo hook presence
        f_l = freq * 0.9965
        f_r = freq * 1.0035
        ph_l = 2.0 * math.pi * f_l * t
        ph_r = 2.0 * math.pi * f_r * t
        mod_l = 1.6 * bright_env * np.sin(2.0 * ph_l)
        mod_r = 1.6 * bright_env * np.sin(2.0 * ph_r)
        left = (
            0.55 * np.sin(ph_l + mod_l)
            + 0.28 * np.sin(2.0 * ph_l) * (0.35 + 0.65 * bright_env)
            + 0.14 * np.sin(3.0 * ph_l) * bright_env
        )
        right = (
            0.55 * np.sin(ph_r + mod_r)
            + 0.28 * np.sin(2.0 * ph_r) * (0.35 + 0.65 * bright_env)
            + 0.14 * np.sin(3.0 * ph_r) * bright_env
        )
        amp = vel_norm * 0.28
        return np.stack([left * env * amp, right * env * amp], axis=1).astype(np.float32)

    if inst == "keys-electric-ep":
        rel = 0.22
        total_sec = max(0.05, duration_sec + rel)
        n = int(round(total_sec * sr))
        t = np.arange(n, dtype=np.float64) / sr
        dur_n = int(round(duration_sec * sr))
        env = _adsr(n, dur_n, sr, atk_s=0.004, dec_s=0.45, sus=0.42)
        ph = 2.0 * math.pi * freq * t
        # Rhodes tine attack + warm body + gentle stereo autopan tremolo
        tine = 0.24 * np.sin(7.0 * ph) * np.exp(-t * 24.0) + 0.18 * np.sin(3.0 * ph) * np.exp(-t * 10.0)
        body = 0.72 * np.sin(ph) + 0.22 * np.sin(2.0 * ph) * np.exp(-t * 3.5)
        trem_l = 0.88 + 0.12 * np.sin(2.0 * math.pi * 4.2 * t)
        trem_r = 0.88 - 0.12 * np.sin(2.0 * math.pi * 4.2 * t)
        amp = vel_norm * 0.22
        sig = (body + tine) * env * amp
        return np.stack([sig * trem_l, sig * trem_r], axis=1).astype(np.float32)

    if inst == "guitar-clean-pluck":
        rel = 0.18
        total_sec = max(0.05, duration_sec + rel)
        n = int(round(total_sec * sr))
        t = np.arange(n, dtype=np.float64) / sr
        dur_n = int(round(duration_sec * sr))
        env = _adsr(n, dur_n, sr, atk_s=0.002, dec_s=0.22, sus=0.28)
        ph = 2.0 * math.pi * freq * t
        # Damped string overtones (higher harmonics decay faster like real plucked guitar)
        sig = np.zeros(n, dtype=np.float64)
        for h in range(1, 7):
            if freq * h >= sr * 0.45:
                break
            sig += (1.0 / (h ** 1.15)) * np.sin(h * ph) * np.exp(-t * (2.5 + h * 4.2))
        amp = vel_norm * 0.26
        mono = (sig * env * amp).astype(np.float32)
        return np.stack([mono * 0.96, mono * 1.04], axis=1)

    if inst == "pad-warm-analog":
        rel = 0.38
        total_sec = max(0.08, duration_sec + rel)
        n = int(round(total_sec * sr))
        t = np.arange(n, dtype=np.float64) / sr
        dur_n = int(round(duration_sec * sr))
        env = _adsr(n, dur_n, sr, atk_s=0.14, dec_s=0.5, sus=0.78)
        lfo = 0.002 * np.sin(2.0 * math.pi * 0.65 * t)
        ph_l = 2.0 * math.pi * freq * (0.994 + lfo) * t
        ph_c = 2.0 * math.pi * freq * t
        ph_r = 2.0 * math.pi * freq * (1.006 - lfo) * t
        left = 0.55 * np.sin(ph_l) + 0.30 * np.sin(ph_c) + 0.18 * np.sin(2.0 * ph_l)
        right = 0.55 * np.sin(ph_r) + 0.30 * np.sin(ph_c) + 0.18 * np.sin(2.0 * ph_r)
        amp = vel_norm * 0.16
        return np.stack([left * env * amp, right * env * amp], axis=1).astype(np.float32)

    # Default: basic-poly-synth
    rel = 0.08
    total_sec = max(0.02, duration_sec + rel)
    n = int(round(total_sec * sr))
    if n <= 0:
        return np.zeros((0, 2), dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / float(sr)
    dur_n = int(round(duration_sec * sr))
    env = _adsr(n, dur_n, sr, atk_s=0.008, dec_s=0.22, sus=0.55)
    ph = 2.0 * math.pi * freq * t
    sig = (
        0.62 * np.sin(ph)
        + 0.24 * np.sin(2.0 * ph) * np.exp(-3.5 * t)
        + 0.10 * np.sin(3.0 * ph) * np.exp(-6.0 * t)
    )
    mono = (sig * env * (vel_norm * 0.24)).astype(np.float32)
    return np.stack([mono, mono], axis=1)
