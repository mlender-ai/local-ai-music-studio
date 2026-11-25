"""Phase 03-A Foundation QA: ITU-R BS.1770-4 Loudness, Half/Double-Time BPM, Harmony & Unconfirmed Instruments."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from engine import paths as engine_paths
from engine.daw_workspace import analysis, comparison, loudness


def test_bs1770_4_calibration_1khz_stereo_sine():
    """EBU Tech 3341 / ITU-R BS.1770-4 calibration: 1 kHz stereo sine at -23 dBFS peak measures -23.0 ± 0.15 LUFS."""
    sr = 48000
    t = np.arange(sr * 3, dtype=np.float64) / sr
    # 0 dBFS peak stereo 1 kHz sine -> K-weighting (+0.65 dB at 1 kHz) - 0.691 = -0.04 LUFS
    sine_0 = np.sin(2.0 * math.pi * 1000.0 * t).astype(np.float32)
    stereo_0 = np.stack([sine_0, sine_0], axis=1)

    res0 = loudness.measure_loudness(stereo_0, sr)
    assert res0["standard"] == "ITU-R BS.1770-4"
    assert -0.2 <= res0["integratedLufs"] <= 0.1, f"Unexpected 0 dBFS stereo sine LUFS: {res0['integratedLufs']}"
    assert -0.15 <= res0["truePeakDbtp"] <= 0.15
    assert -0.15 <= res0["samplePeakDbfs"] <= 0.05

    # EBU Tech 3341 reference: -23.0 dBFS peak stereo 1 kHz sine => -23.04 LUFS (within ±0.15 LU of -23.0)
    amp_m23 = 10.0 ** (-23.0 / 20.0)
    res_m23 = loudness.measure_loudness((stereo_0 * amp_m23).astype(np.float32), sr)
    assert -23.2 <= res_m23["integratedLufs"] <= -22.85

    # Half amplitude (-6.02 dB) must drop Integrated LUFS by exactly 6.02 ± 0.1 dB
    res_half = loudness.measure_loudness((stereo_0 * 0.5).astype(np.float32), sr)
    delta = res0["integratedLufs"] - res_half["integratedLufs"]
    assert 5.9 <= delta <= 6.15


def test_true_peak_4x_catches_intersample_peak():
    """4x oversampled True Peak must exceed sample peak on Nyquist/4 worst-case inter-sample waveform."""
    sr = 48000
    # Alternating +0.9, +0.9, -0.9, -0.9 at Fs/4 produces ~+2.1 dB inter-sample overshoot!
    pattern = np.array([0.9, 0.9, -0.9, -0.9], dtype=np.float32)
    wave = np.tile(pattern, sr // 4)
    stereo = np.stack([wave, wave], axis=1)

    res = loudness.measure_loudness(stereo, sr)
    assert res["truePeakDbtp"] > res["samplePeakDbfs"] + 1.0


def test_half_time_double_time_tempo_comparison_compatible():
    """127.9 BPM vs 64.0 BPM must be reported as octave-compatible half/double-time, NOT -63.9 BPM error."""
    rel = analysis.resolve_octave_tempo_relation(127.9, 64.0)
    assert rel["compatible"] is True
    assert rel["relation"] == "half_time"
    assert abs(rel["effectiveDeltaBpm"]) <= 0.3

    rel_double = analysis.resolve_octave_tempo_relation(64.0, 128.0)
    assert rel_double["compatible"] is True
    assert rel_double["relation"] == "double_time"
    assert abs(rel_double["effectiveDeltaBpm"]) <= 0.1

    fake_ref = {
        "durationSec": 60.0,
        "rhythm": {"adoptedTempoBpm": 127.9, "estimatedBpm": 127.9},
        "harmony": {"estimatedKey": "F minor", "harmonicRepetitionScore": 0.7},
        "arrangement": {"energyCurve": [{"timeSec": 0.0, "normEnergy": 0.5}]},
        "sound": {"measured": {"integratedLufs": -16.5, "truePeakDbtp": -1.5, "crestFactorDb": 12.0, "dynamicRangeDb": 6.0, "stereoWidth": 0.35, "percussiveRatio": 0.4, "frequencyBandsPct": {}}},
    }
    fake_tgt = {
        "durationSec": 30.0,
        "rhythm": {"adoptedTempoBpm": 64.0, "estimatedBpm": 64.0},
        "harmony": {"estimatedKey": "F minor", "harmonicRepetitionScore": 0.65},
        "arrangement": {"energyCurve": [{"timeSec": 0.0, "normEnergy": 0.5}]},
        "sound": {"measured": {"integratedLufs": -16.2, "truePeakDbtp": -1.2, "crestFactorDb": 12.0, "dynamicRangeDb": 6.0, "stereoWidth": 0.35, "percussiveRatio": 0.4, "frequencyBandsPct": {}}},
    }
    comp = comparison.compare_analyses("Ref", fake_ref, "Target", fake_tgt)
    assert comp["measuredDeltas"]["tempoCompatible"] is True
    assert comp["measuredDeltas"]["tempoRelation"] == "half_time"
    assert abs(comp["measuredDeltas"]["bpmDelta"]) <= 0.3


def test_analysis_v3_separates_melodic_untranscribed_and_unconfirmed_instruments(tmp_path):
    """Synthesized F-minor 128 BPM test signal validates v3.0.0 schema honesty & bass-weighted key."""
    sr = 48000
    dur = 8.0
    t = np.arange(int(sr * dur), dtype=np.float64) / sr
    # Pure low bass F2 (87.31 Hz) + C3 (130.81 Hz) + Ab3 (207.65 Hz) with 128 BPM pulse
    beat_hz = 128.0 / 60.0
    pulse = np.exp(-8.0 * ((t * beat_hz) % 1.0))
    sig = (
        0.35 * np.sin(2 * math.pi * 87.31 * t)
        + 0.20 * np.sin(2 * math.pi * 130.81 * t)
        + 0.18 * np.sin(2 * math.pi * 207.65 * t)
    ) * (0.4 + 0.6 * pulse)
    stereo = np.stack([sig, sig], axis=1).astype(np.float32)
    wav_path = tmp_path / "fminor_128.wav"
    sf.write(str(wav_path), stereo, sr, subtype="PCM_24")

    res = analysis.analyze_audio_file(
        wav_path,
        source_asset_id="ast_test",
        sha256="deadbeef1234",
        cache_dir=tmp_path / "cache",
        project_bpm=128.0,
    )
    assert res["analysisVersion"] in ("3.0.0", "3.1.0")
    assert res["harmony"]["melodicMotifStatus"] == "not_transcribed_in_dsp_mode"
    assert res["harmony"]["instrumentPhraseStatus"] == "not_transcribed_in_dsp_mode"
    assert res["sound"]["measured"]["loudnessStandard"] == "ITU-R BS.1770-4"
    assert "truePeakDbtp" in res["sound"]["measured"]
    assert "integratedLufs" in res["sound"]["measured"]
    # Upper harmonic / synth should be unconfirmed since signal is < 250 Hz
    upper = next(e for e in res["instrumentation"]["elements"] if "Upper Harmonic" in e["name"])
    assert upper["status"] == "unconfirmed"
    assert res["harmony"]["estimatedKey"].startswith("F")


def test_real_v72_magnetic_afterhours_analysis_v3_if_present(tmp_path):
    """When real V7.2 Magnetic Afterhours demo audio exists, verify BS.1770-4 LUFS and ~128 BPM."""
    candidates = [
        engine_paths.ROOT / "outputs" / "daw" / "projects" / "demo_v72_magnetic_afterhours" / "assets" / "audio",
        engine_paths.ROOT / "outputs" / "daw" / "library" / "yue2",
    ]
    wav_file: Path | None = None
    for folder in candidates:
        if folder.is_dir():
            matches = sorted(folder.glob("*magnetic*afterhours*.wav"))
            if matches:
                wav_file = matches[0]
                break
    if not wav_file:
        return  # Skip cleanly in CI/minimal checkout without demo renders

    res = analysis.analyze_audio_file(
        wav_file,
        source_asset_id="v72_check",
        sha256="v72_test_sha",
        cache_dir=tmp_path / "cache",
        project_bpm=128.0,
    )
    assert 125.0 <= (res["rhythm"]["adoptedTempoBpm"] or 0) <= 131.0
    # Known mastered delivery loudness of V7.2 Magnetic Afterhours is ~ -16.7 LUFS / -1.6 dBTP
    assert -19.5 <= res["sound"]["measured"]["integratedLufs"] <= -13.5
    assert -3.5 <= res["sound"]["measured"]["truePeakDbtp"] <= 0.2
