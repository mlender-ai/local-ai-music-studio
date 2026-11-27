"""5-Gate Honest Music Production Quality Gate (Phase 05.1 · Section 16).

Verdict values are strictly one of: `PASS`, `WARNING`, `FAIL`, `UNVERIFIED`.
Automated verification NEVER claims subjective musical excellence — human listening verdict
always remains `UNVERIFIED` until the user listens and approves!
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw_workspace import loudness

from .instrument_resolver import get_instrument_quality_tier
from .policy import load_production_policy

GateStatus = str  # "PASS" | "WARNING" | "FAIL" | "UNVERIFIED"


def _worst_status(statuses: list[GateStatus]) -> GateStatus:
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if "UNVERIFIED" in statuses:
        return "UNVERIFIED"
    return "PASS"


def evaluate_five_gate_quality(
    *,
    requested_engine: str,
    actual_engine: str,
    production_mode: str = "neural_audio",
    expected_duration_sec: float | None = None,
    expected_bpm: float | None = None,
    estimated_bpm: float | None = None,
    audio_path: Path | None = None,
    audio_pcm: np.ndarray | None = None,
    sample_rate: int | None = None,
    vocal_screening: dict[str, Any] | None = None,
    instrumental_only: bool = True,
    instruments_used: list[str] | None = None,
    allow_preview_override: bool = False,
    native_audio_preserved: bool = True,
    playback_verified: bool | None = None,
    preview_status: str | None = None,
    silent_fallback_occurred: bool = False,
) -> dict[str, Any]:
    """Run all 5 Phase 05.1 Quality Gates honestly and return structured gate verdicts + metrics."""
    policy = load_production_policy()

    # --- Gate A: Engine Integrity ---
    gate_a_issues: list[str] = []
    gate_a_status: GateStatus = "PASS"
    if silent_fallback_occurred:
        gate_a_status = "FAIL"
        gate_a_issues.append("Silent MIDI fallback occurred while YuE2/neural engine was expected.")
    elif requested_engine in ("yue2-native", "neural_audio") and actual_engine != "yue2-native":
        gate_a_status = "FAIL"
        gate_a_issues.append(f"Requested '{requested_engine}' but actual engine was '{actual_engine}'.")
    elif production_mode == "neural_audio" and actual_engine != "yue2-native":
        gate_a_status = "FAIL"
        gate_a_issues.append(f"Production mode 'neural_audio' requires YuE2 Native Audio, got '{actual_engine}'.")

    gate_a = {
        "name": "Gate A · Engine Integrity",
        "status": gate_a_status,
        "requestedEngine": requested_engine,
        "actualEngine": actual_engine,
        "silentFallbackOccurred": silent_fallback_occurred,
        "issues": gate_a_issues,
    }

    # --- Gate B: Production Policy Compliance ---
    gate_b_issues: list[str] = []
    gate_b_status: GateStatus = "PASS"
    preview_used: list[str] = []
    for inst_id in instruments_used or []:
        t_info = get_instrument_quality_tier(inst_id)
        if t_info["qualityTier"] == "PREVIEW":
            preview_used.append(inst_id)
    if preview_used and not (allow_preview_override or bool(policy.get("allowPreviewInstrumentsInProduction", False))):
        gate_b_status = "FAIL"
        gate_b_issues.append(f"PREVIEW instruments used in production without explicit override: {', '.join(preview_used)}")
    if not native_audio_preserved:
        gate_b_status = "FAIL"
        gate_b_issues.append("Native audio preservation policy violated (original native audio was overwritten/degraded).")

    gate_b = {
        "name": "Gate B · Production Policy",
        "status": gate_b_status,
        "previewInstrumentsDetected": preview_used,
        "nativeAudioPreserved": native_audio_preserved,
        "allowPreviewOverride": allow_preview_override,
        "issues": gate_b_issues,
    }

    # --- Gate C: Audio Integrity ---
    gate_c_issues: list[str] = []
    gate_c_warnings: list[str] = []
    gate_c_metrics: dict[str, Any] = {}
    pcm: np.ndarray | None = audio_pcm
    sr: int = int(sample_rate or 48000)

    if pcm is None and audio_path is not None and audio_path.is_file():
        pcm, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)

    if pcm is None or len(pcm) == 0:
        gate_c_status: GateStatus = "FAIL"
        gate_c_issues.append("Audio file or PCM buffer is missing or empty.")
    else:
        if pcm.ndim == 1:
            pcm = np.stack([pcm, pcm], axis=1)
        finite = bool(np.isfinite(pcm).all())
        dur_sec = round(len(pcm) / max(1, sr), 3)
        peak_lin = float(np.max(np.abs(pcm)))
        rms_lin = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
        loud = loudness.measure_loudness(pcm, sr)
        clipped_samples = int(np.sum(np.abs(pcm) >= 0.9999))
        # Measure fraction of 250ms blocks that are essentially silent (-60 dBFS)
        blk = max(1, sr // 4)
        n_blk = max(1, len(pcm) // blk)
        silent_blks = 0
        for i in range(n_blk):
            seg = pcm[i * blk : (i + 1) * blk]
            if float(np.sqrt(np.mean(seg.astype(np.float64) ** 2))) < 1e-3:
                silent_blks += 1
        silence_ratio = round(silent_blks / n_blk, 3)

        gate_c_metrics = {
            "sampleRate": sr,
            "channels": int(pcm.shape[1]),
            "durationSec": dur_sec,
            "finitePcm": finite,
            "peakLinear": round(peak_lin, 4),
            "rmsDbfs": round(20.0 * math.log10(max(rms_lin, 1e-9)), 2),
            "integratedLufs": loud["integratedLufs"],
            "truePeakDbtp": loud["truePeakDbtp"],
            "loudnessRangeLu": loud["loudnessRangeLu"],
            "crestFactorDb": loud["crestFactorDb"],
            "clippedSamples": clipped_samples,
            "silenceRatio": silence_ratio,
        }

        if not finite:
            gate_c_issues.append("Audio contains NaN/Inf samples.")
        if peak_lin < 1e-4 or silence_ratio > 0.75:
            gate_c_issues.append(f"Audio is silent or mostly silent (silenceRatio={silence_ratio}).")
        if expected_duration_sec is not None and abs(dur_sec - expected_duration_sec) > max(4.0, expected_duration_sec * 0.35):
            gate_c_warnings.append(f"Duration {dur_sec}s differs noticeably from target {expected_duration_sec:.1f}s.")
        if loud["truePeakDbtp"] > 0.0:
            gate_c_warnings.append(
                f"True Peak ({loud['truePeakDbtp']} dBTP) exceeds 0 dBTP; apply headroom trim or safety limiter before 24-bit PCM export."
            )
        elif clipped_samples > 16:
            gate_c_warnings.append(f"Detected {clipped_samples} full-scale samples (>= 0.9999).")

        if instrumental_only and vocal_screening:
            v_st = str(vocal_screening.get("status", "UNCERTAIN")).upper()
            if v_st == "REJECT":
                gate_c_issues.append("Vocal leakage screening REJECTED output in instrumental-only mode.")
            elif v_st == "UNCERTAIN":
                gate_c_warnings.append("Vocal screening is UNCERTAIN — manual listening verification required.")

        gate_c_status = "FAIL" if gate_c_issues else ("WARNING" if gate_c_warnings else "PASS")

    gate_c = {
        "name": "Gate C · Audio Integrity",
        "status": gate_c_status,
        "metrics": gate_c_metrics,
        "vocalScreeningStatus": (vocal_screening or {}).get("status"),
        "issues": gate_c_issues,
        "warnings": gate_c_warnings,
    }

    # --- Gate D: Musical Risk Detection (Objective DSP risks only; NEVER claims good music!) ---
    gate_d_warnings: list[str] = []
    gate_d_metrics: dict[str, Any] = {}
    gate_d_status: GateStatus = "UNVERIFIED"
    if pcm is not None and len(pcm) >= max(256, sr // 2) and gate_c_status != "FAIL":
        mono = pcm.mean(axis=1).astype(np.float64)
        nperseg = min(8192, max(256, len(mono)))
        freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg)
        tot = float(psd.sum()) + 1e-18
        low_mid_pct = round(float(psd[(freqs >= 200) & (freqs < 500)].sum() / tot) * 100.0, 2)
        high_pct = round(float(psd[(freqs >= 2000) & (freqs < 16000)].sum() / tot) * 100.0, 2)
        centroid_hz = round(float((freqs * psd).sum() / tot), 1)
        left, right = pcm[:, 0].astype(np.float64), pcm[:, 1].astype(np.float64)
        mid_e = float(np.mean((0.5 * (left + right)) ** 2))
        side_e = float(np.mean((0.5 * (left - right)) ** 2))
        stereo_width = round(float(np.clip(math.sqrt(side_e / (mid_e + 1e-12)), 0.0, 1.5)), 3)

        gate_d_metrics = {
            "lowMid200to500Pct": low_mid_pct,
            "high2kTo16kPct": high_pct,
            "spectralCentroidHz": centroid_hz,
            "stereoWidth": stereo_width,
            "expectedBpm": expected_bpm,
            "estimatedBpm": estimated_bpm,
        }
        if low_mid_pct >= 38.0:
            gate_d_warnings.append(f"High low-mid density ({low_mid_pct}% in 200–500 Hz) — may sound muddy.")
        if centroid_hz < 550.0:
            gate_d_warnings.append(f"Very dark spectral centroid ({centroid_hz} Hz) — check top-end clarity.")
        if stereo_width < 0.05:
            gate_d_warnings.append(f"Nearly mono stereo width ({stereo_width}) — limited spatial spread.")
        if expected_bpm and estimated_bpm:
            # Allow half-time / double-time octave equivalence
            diffs = [abs(estimated_bpm - expected_bpm), abs(estimated_bpm * 2 - expected_bpm), abs(estimated_bpm * 0.5 - expected_bpm)]
            if min(diffs) > 8.0:
                gate_d_warnings.append(f"Measured tempo ({estimated_bpm:.1f} BPM) deviates from target ({expected_bpm:.1f} BPM).")
        gate_d_status = "WARNING" if gate_d_warnings else "PASS"

    gate_d = {
        "name": "Gate D · Musical Risk Detection",
        "status": gate_d_status,
        "metrics": gate_d_metrics,
        "warnings": gate_d_warnings,
        "subjectiveMusicality": "UNVERIFIED",
        "honestyNoteKo": "자동 검사는 명백한 음향·리듬 리스크만 탐지하며, 음악적 완성도·감성·그루브는 사용자 직접 청취 전까지 UNVERIFIED입니다.",
    }

    # --- Gate E: Playback & Preview Parity Verification ---
    if playback_verified is True:
        gate_e_status: GateStatus = "PASS"
        gate_e_note = f"DAW playback verified (previewStatus={preview_status or 'Original Audio'})."
    elif playback_verified is False:
        gate_e_status = "FAIL"
        gate_e_note = "Playback or Studio Preview verification failed."
    else:
        gate_e_status = "UNVERIFIED"
        gate_e_note = "Playback in browser/audio output not yet verified."

    gate_e = {
        "name": "Gate E · Playback Verification",
        "status": gate_e_status,
        "previewStatus": preview_status or ("Original Audio" if actual_engine == "yue2-native" else "Realtime Preview"),
        "note": gate_e_note,
    }

    overall = _worst_status([gate_a["status"], gate_b["status"], gate_c["status"], gate_d["status"], gate_e["status"]])
    return {
        "schemaVersion": 1,
        "overallStatus": overall,
        "humanListeningRequired": True,
        "subjectiveMusicality": "UNVERIFIED",
        "gates": {
            "gateA": gate_a,
            "gateB": gate_b,
            "gateC": gate_c,
            "gateD": gate_d,
            "gateE": gate_e,
        },
        "summaryKo": (
            f"5단계 Quality Gate 결과: {overall} "
            f"(A:{gate_a['status']} / B:{gate_b['status']} / C:{gate_c['status']} / D:{gate_d['status']} / E:{gate_e['status']}) · "
            "최종 음악성 판단: UNVERIFIED (사용자 청취 필요)"
        ),
        "summaryEn": (
            f"5-Gate Quality Gate: {overall} "
            f"(A:{gate_a['status']} / B:{gate_b['status']} / C:{gate_c['status']} / D:{gate_d['status']} / E:{gate_e['status']}) · "
            "Subjective musicality: UNVERIFIED (human listening required)"
        ),
    }
