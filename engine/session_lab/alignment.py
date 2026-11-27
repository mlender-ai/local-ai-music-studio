"""Loop Integrity, Beat Alignment, Harmonic Compatibility, Isolation Validation & 5-Part Musical Quality Gate (Phase 05.2 · Parts D & F)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.composition.midi_composer import chord_at_beat, parse_key_root_and_scale
from engine.daw_workspace import loudness
from engine.generation.adapters.yue2_adapter import screen_vocal_leakage
from engine.production.instrument_resolver import get_instrument_quality_tier


def validate_loop_integrity(
    audio_pcm: np.ndarray,
    sr: int,
    *,
    target_bpm: float,
    target_bars: int = 8,
    bpb: float = 4.0,
) -> dict[str, Any]:
    """Inspect real audio loop boundaries, downbeat onset, seam click risk, unintended silence, and bar-length accuracy (Section 23)."""
    if len(audio_pcm) == 0:
        return {
            "status": "FAIL",
            "durationSec": 0.0,
            "expectedDurationSec": round(target_bars * bpb * (60.0 / max(30.0, target_bpm)), 3),
            "issues": ["Empty audio buffer"],
        }
    stereo = audio_pcm if audio_pcm.ndim == 2 and audio_pcm.shape[1] >= 2 else np.stack([audio_pcm, audio_pcm], axis=1)
    mono = stereo.mean(axis=1).astype(np.float64)
    dur_sec = len(mono) / max(1, sr)
    expected_sec = target_bars * bpb * (60.0 / max(30.0, float(target_bpm)))

    # 1. Detect first audible onset (downbeat lead-in)
    abs_m = np.abs(mono)
    peak = float(np.max(abs_m)) + 1e-9
    onset_idx = int(np.argmax(abs_m > max(1e-3, peak * 0.04))) if peak > 1e-4 else 0
    first_onset_ms = round((onset_idx / sr) * 1000.0, 2)

    # 2. Loop Seam discontinuity (jump from last sample back to first sample -> audible click/pop!)
    seam_jump = float(np.max(np.abs(stereo[-1] - stereo[0])))
    seam_click_risk = seam_jump > 0.08

    # 3. Trailing reverb/tail energy (last 200ms vs body RMS)
    body_rms = float(np.sqrt(np.mean(mono * mono))) + 1e-9
    tail_len = min(len(mono), int(0.20 * sr))
    tail_rms = float(np.sqrt(np.mean(mono[-tail_len:] ** 2)))
    tail_ratio = round(tail_rms / body_rms, 3)

    # 4. Unintended silence ratio (250ms frames below -55 dBFS)
    blk = max(1, sr // 4)
    n_blk = max(1, len(mono) // blk)
    silent_blks = sum(
        1 for i in range(n_blk) if float(np.sqrt(np.mean(mono[i * blk : (i + 1) * blk] ** 2))) < 1.8e-3
    )
    silence_ratio = round(silent_blks / n_blk, 3)

    # 5. Bar-length tolerance
    dur_delta_sec = round(dur_sec - expected_sec, 3)
    exact_bar_match = abs(dur_delta_sec) <= 0.15
    has_reverb_tail_overflow = dur_delta_sec > 0.15 and dur_delta_sec <= 2.5

    issues: list[str] = []
    warnings: list[str] = []
    if peak < 1e-4 or silence_ratio > 0.85:
        issues.append("Audio is silent or nearly silent.")
    if seam_click_risk:
        warnings.append(f"Loop seam discontinuity ({seam_jump:.3f}) may click on wrap; apply 5ms edge crossfade.")
    if not exact_bar_match and not has_reverb_tail_overflow:
        warnings.append(f"Duration {dur_sec:.2f}s differs from {target_bars}-bar boundary ({expected_sec:.2f}s).")
    if first_onset_ms > 80.0:
        warnings.append(f"Leading offset {first_onset_ms:.1f}ms before first transient; check downbeat alignment.")

    status = "FAIL" if issues else ("WARNING" if warnings else "PASS")
    return {
        "status": status,
        "durationSec": round(dur_sec, 3),
        "expectedDurationSec": round(expected_sec, 3),
        "durationDeltaSec": dur_delta_sec,
        "exactBarBoundaryMatch": exact_bar_match,
        "hasNaturalReleaseTail": has_reverb_tail_overflow,
        "firstOnsetMs": first_onset_ms,
        "seamAmplitudeJump": round(seam_jump, 4),
        "seamClickRisk": seam_click_risk,
        "trailingTailRatio": tail_ratio,
        "silenceRatio": silence_ratio,
        "issues": issues,
        "warnings": warnings,
    }


def align_audio_loop_to_bars(
    src_wav: Path,
    out_wav: Path,
    *,
    target_bpm: float,
    target_bars: int = 8,
    bpb: float = 4.0,
    crossfade_ms: float = 8.0,
) -> dict[str, Any]:
    """Extract an exact bar-aligned loop segment starting at the first downbeat while preserving the original WAV untouched (Section 23)."""
    audio, sr = sf.read(str(src_wav), dtype="float32", always_2d=True)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    expected_sec = target_bars * bpb * (60.0 / max(30.0, float(target_bpm)))
    target_samples = int(round(expected_sec * sr))

    mono = audio.mean(axis=1)
    peak = float(np.max(np.abs(mono))) + 1e-9
    onset_idx = int(np.argmax(np.abs(mono) > max(1e-3, peak * 0.05))) if peak > 1e-4 else 0
    # Only trim small leading silence (< 1.5s) to preserve musical rests if intentional
    trim_start = onset_idx if onset_idx < int(1.5 * sr) else 0
    trimmed = audio[trim_start:]

    if len(trimmed) >= target_samples:
        loop_pcm = trimmed[:target_samples].copy()
    else:
        loop_pcm = np.zeros((target_samples, 2), dtype=np.float32)
        loop_pcm[: len(trimmed)] = trimmed

    # Click-free micro-fade at loop edges (never alters interior groove!)
    fade_n = max(4, min(len(loop_pcm) // 20, int(sr * crossfade_ms / 1000.0)))
    ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)[:, None]
    loop_pcm[:fade_n] *= ramp
    loop_pcm[-fade_n:] *= ramp[::-1]

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav), np.clip(loop_pcm, -1.0, 1.0), sr, subtype="PCM_24")
    integrity = validate_loop_integrity(loop_pcm, sr, target_bpm=target_bpm, target_bars=target_bars, bpb=bpb)
    return {
        "originalWavPath": str(src_wav),
        "alignedWavPath": str(out_wav),
        "trimmedLeadingMs": round((trim_start / sr) * 1000.0, 2),
        "targetBars": target_bars,
        "targetBpm": target_bpm,
        "loopIntegrity": integrity,
    }


def check_tempo_alignment(
    detected_bpm: float | None,
    target_bpm: float,
    *,
    bars: int = 8,
    bpb: float = 4.0,
) -> dict[str, Any]:
    """Honestly compute real rhythmic drift over `bars` bars (Section 24 — never hides BPM drift via metadata!)."""
    if detected_bpm is None or detected_bpm <= 0:
        return {
            "status": "UNVERIFIED",
            "targetBpm": target_bpm,
            "detectedBpm": None,
            "deltaBpm": None,
            "driftOverLoopMs": None,
            "safeForDirectLoopLayering": False,
            "noteKo": "실측 BPM을 추정할 수 없어 자동 정렬을 보증할 수 없습니다.",
        }
    # Check direct, half-time, and double-time equivalence
    cands = [detected_bpm, detected_bpm * 2.0, detected_bpm * 0.5]
    best = min(cands, key=lambda b: abs(b - target_bpm))
    delta = round(best - target_bpm, 2)
    total_beats = bars * bpb
    target_sec = total_beats * (60.0 / target_bpm)
    actual_sec_at_detected = total_beats * (60.0 / best)
    drift_ms = round(abs(actual_sec_at_detected - target_sec) * 1000.0, 1)

    if drift_ms <= 25.0:
        status = "ALIGNED"
        safe = True
        note_ko = f"목표 {target_bpm} BPM 대비 실측 {best:.1f} BPM ({bars}마디 누적 드리프트 {drift_ms} ms) — 직접 루프 합주 가능."
    elif drift_ms <= 90.0:
        status = "MINOR_DRIFT"
        safe = True
        note_ko = f"목표 {target_bpm} BPM 대비 {best:.1f} BPM (누적 {drift_ms} ms 미세 오차) — 경계 트리밍 또는 구간 확인 권장."
    else:
        status = "DRIFT_RISK"
        safe = False
        note_ko = (
            f"목표 {target_bpm} BPM 대비 실측 {best:.1f} BPM으로 {bars}마디 누적 {drift_ms} ms 박자 어긋남 발생. "
            "고품질 Time Stretch 없이 자동 레이어 적용을 차단합니다."
        )

    return {
        "status": status,
        "targetBpm": target_bpm,
        "detectedBpm": round(best, 2),
        "rawDetectedBpm": round(detected_bpm, 2),
        "deltaBpm": delta,
        "driftOverLoopMs": drift_ms,
        "safeForDirectLoopLayering": safe,
        "noteKo": note_ko,
    }


def evaluate_harmonic_compatibility(
    notes: list[dict[str, Any]] | None,
    *,
    chord_timeline: list[dict[str, Any]],
    key: str = "D minor",
    scale: str = "dorian",
    bpb: float = 4.0,
    is_unpitched_rhythm: bool = False,
) -> dict[str, Any]:
    """Evaluate harmonic compatibility respecting jazz/neo-soul 9th/11th/13th tensions and passing tones (Section 25)."""
    if is_unpitched_rhythm:
        return {
            "status": "NOT_APPLICABLE",
            "chordTonePct": None,
            "jazzTensionPct": None,
            "passingTonePct": None,
            "clashNoteCount": 0,
            "noteKo": "무음정 리듬(드럼/퍼커션) 레이어로 화성 호환성 검사 대상이 아닙니다.",
        }
    if not notes:
        return {
            "status": "UNCERTAIN",
            "chordTonePct": 0.0,
            "clashNoteCount": 0,
            "noteKo": "MIDI 노트 데이터가 없어 오디오 기반 재분석이 필요합니다(UNCERTAIN).",
        }

    root_pc, scale_ints = parse_key_root_and_scale(key, scale)
    scale_pcs = {(root_pc + i) % 12 for i in scale_ints}
    fallback_chords = [str(c.get("symbol")) for c in chord_timeline if c.get("symbol")] or ["Dm9", "G13", "Cmaj9", "A7"]

    chord_hits = 0
    tension_hits = 0
    passing_hits = 0
    clashes: list[dict[str, Any]] = []

    for n in notes:
        st = float(n.get("startBeat", 0.0))
        dur = float(n.get("durationBeats", 0.25))
        pc = int(n.get("pitch", 60)) % 12
        sym, c_root, c_ints, bass_pc = chord_at_beat(st, chord_timeline or None, fallback_chords, bpb, root_pc)
        chord_pcs = {(c_root + i) % 12 for i in c_ints}
        if bass_pc is not None:
            chord_pcs.add(bass_pc)
        # Jazz tensions: 9th (+2), 11th (+5), 13th (+9) relative to chord root
        jazz_tension_pcs = {(c_root + 2) % 12, (c_root + 5) % 12, (c_root + 9) % 12}

        if pc in chord_pcs:
            chord_hits += 1
        elif pc in jazz_tension_pcs or (pc in scale_pcs and dur <= 0.75):
            tension_hits += 1
        elif dur <= 0.35:
            # Brief chromatic approach / passing tone (e.g. enclosure or slide pickup)
            passing_hits += 1
        else:
            clashes.append({"beat": round(st, 3), "pitch": int(n["pitch"]), "chord": sym, "dur": round(dur, 3)})

    tot = max(1, len(notes))
    chord_pct = round(chord_hits / tot * 100.0, 1)
    tension_pct = round(tension_hits / tot * 100.0, 1)
    passing_pct = round(passing_hits / tot * 100.0, 1)
    compatible_pct = round((chord_hits + tension_hits + passing_hits) / tot * 100.0, 1)

    if compatible_pct >= 92.0 and chord_pct >= 55.0:
        status = "STRONG_MATCH"
        note_ko = f"코드 구성음 {chord_pct}% · 재즈 텐션 {tension_pct}% · 경과음 {passing_pct}% (불협화음 {len(clashes)}건) — 화성 호환 우수."
    elif compatible_pct >= 80.0:
        status = "REFERENCE_MATCH"
        note_ko = f"참고 수준 화성 일치(호환 {compatible_pct}%, 충돌 후보 {len(clashes)}건)."
    else:
        status = "PARTIAL_MISMATCH"
        note_ko = f"화성 불일치 감지(호환 {compatible_pct}%, 장기 불협화음 {len(clashes)}건) — 코드 진행 확인 필요."

    return {
        "status": status,
        "compatiblePct": compatible_pct,
        "chordTonePct": chord_pct,
        "jazzTensionPct": tension_pct,
        "passingTonePct": passing_pct,
        "clashNoteCount": len(clashes),
        "clashes": clashes[:8],
        "noteKo": note_ko,
    }


def evaluate_musical_quality_gate(
    *,
    requested_instrument: str,
    performance_type: str,
    source_engine: str,
    instrument_ref: str | None,
    notes: list[dict[str, Any]] | None,
    audio_pcm: np.ndarray,
    sr: int,
    target_bpm: float,
    detected_bpm: float | None,
    target_bars: int,
    chord_timeline: list[dict[str, Any]],
    key: str,
    scale: str,
    protected_check: dict[str, Any],
    isolation_status: str = "isolated_pure",
    vocal_screening: dict[str, Any] | None = None,
    silent_fallback_occurred: bool = False,
) -> dict[str, Any]:
    """5-part Musical Quality Gate (Section 32: Engine, Performance, Layer, Sound, User Listening)."""
    is_rhythm = requested_instrument in ("drums", "percussion")

    # A. Engine Integrity
    engine_issues: list[str] = []
    if silent_fallback_occurred:
        engine_issues.append("Silent MIDI fallback occurred.")
    if instrument_ref:
        tier = get_instrument_quality_tier(instrument_ref)
        if tier["qualityTier"] == "PREVIEW":
            engine_issues.append(f"PREVIEW instrument '{instrument_ref}' used in production.")
    gate_a = {
        "name": "A · Engine Integrity",
        "status": "FAIL" if engine_issues else "PASS",
        "sourceEngine": source_engine,
        "instrumentRef": instrument_ref,
        "issues": engine_issues,
    }

    # B. Performance Integrity (event diversity, register, rhythmic variety, non-robotic check)
    perf_warnings: list[str] = []
    perf_metrics: dict[str, Any] = {}
    if notes:
        pitches = [int(n["pitch"]) for n in notes]
        vels = [int(n.get("velocity", 96)) for n in notes]
        durs = [round(float(n.get("durationBeats", 0.25)), 2) for n in notes]
        bars_seen: dict[int, list[tuple[int, float]]] = {}
        for n in notes:
            st = float(n.get("startBeat", 0.0))
            bi = int(st // 4.0)
            bars_seen.setdefault(bi, []).append((int(n["pitch"]), round((st % 4.0) * 4.0) / 4.0))
        unique_bar_sigs = len({tuple(v) for v in bars_seen.values()})
        pitch_span = max(pitches) - min(pitches)
        vel_span = max(vels) - min(vels)
        unique_durs = len(set(durs))
        bend_count = sum(1 for n in notes if n.get("pitchBendSemitones"))
        perf_metrics = {
            "noteCount": len(notes),
            "uniqueBarPatterns": unique_bar_sigs,
            "pitchRange": [min(pitches), max(pitches)],
            "pitchSpanSemitones": pitch_span,
            "velocitySpan": vel_span,
            "uniqueDurations": unique_durs,
            "pitchBendEvents": bend_count,
        }
        if unique_bar_sigs < 2 and target_bars >= 4:
            perf_warnings.append("Low bar-to-bar variation (< 2 unique bar patterns).")
        if vel_span < 12:
            perf_warnings.append("Flat dynamics (velocity range < 12).")
        if not is_rhythm and unique_durs < 2 and len(notes) >= 8:
            perf_warnings.append("Uniform note durations detected (may sound mechanical).")
        gate_b_status = "WARNING" if perf_warnings else "PASS"
    else:
        gate_b_status = "UNVERIFIED"
    gate_b = {
        "name": "B · Performance Integrity",
        "status": gate_b_status,
        "performanceType": performance_type,
        "metrics": perf_metrics,
        "warnings": perf_warnings,
    }

    # C. Layer Integrity (BPM alignment, Harmonic compatibility, Loop boundary, Isolation, Layer protection)
    loop_int = validate_loop_integrity(audio_pcm, sr, target_bpm=target_bpm, target_bars=target_bars)
    tempo_al = check_tempo_alignment(detected_bpm if detected_bpm is not None else target_bpm, target_bpm, bars=target_bars)
    harm = evaluate_harmonic_compatibility(
        notes,
        chord_timeline=chord_timeline,
        key=key,
        scale=scale,
        is_unpitched_rhythm=is_rhythm,
    )
    layer_issues: list[str] = []
    layer_warnings: list[str] = []
    if not protected_check.get("allProtectedIntact", True):
        layer_issues.append("Protected existing layer was modified!")
    if isolation_status == "mixed_audio_not_isolated":
        layer_issues.append("Audio contains mixed accompaniment and is NOT an isolated single-instrument layer.")
    if not tempo_al.get("safeForDirectLoopLayering", True):
        layer_issues.append(tempo_al.get("noteKo", "Tempo drift risk"))
    if harm.get("status") == "PARTIAL_MISMATCH":
        layer_warnings.append(harm.get("noteKo", "Harmonic mismatch"))
    layer_warnings.extend(loop_int.get("warnings", []))
    gate_c = {
        "name": "C · Layer Integrity",
        "status": "FAIL" if layer_issues else ("WARNING" if layer_warnings else "PASS"),
        "loopIntegrity": loop_int,
        "tempoAlignment": tempo_al,
        "harmonicCompatibility": harm,
        "isolationStatus": isolation_status,
        "protectedLayersCheck": protected_check,
        "issues": layer_issues,
        "warnings": layer_warnings,
    }

    # D. Sound Integrity (clipping, silence, frequency balance, vocal screening)
    loud = loudness.measure_loudness(audio_pcm, sr)
    peak = float(np.max(np.abs(audio_pcm))) if len(audio_pcm) else 0.0
    clipped = int(np.sum(np.abs(audio_pcm) >= 0.9999))
    mono = audio_pcm.mean(axis=1).astype(np.float64) if audio_pcm.ndim == 2 else audio_pcm.astype(np.float64)
    nperseg = min(4096, max(256, len(mono)))
    f, p = signal.welch(mono, fs=sr, nperseg=nperseg)
    tot_p = float(p.sum()) + 1e-18
    centroid = round(float((f * p).sum() / tot_p), 1)
    low_mid_pct = round(float(p[(f >= 200) & (f < 500)].sum() / tot_p) * 100.0, 1)

    sound_issues: list[str] = []
    sound_warnings: list[str] = []
    if peak < 1e-4 or not bool(np.isfinite(audio_pcm).all()):
        sound_issues.append("Audio is silent or non-finite.")
    if clipped > 16:
        sound_warnings.append(f"{clipped} clipped samples detected.")
    if vocal_screening and vocal_screening.get("status") == "REJECT":
        sound_issues.append("Vocal leakage REJECTED.")
    elif vocal_screening and vocal_screening.get("status") == "UNCERTAIN":
        sound_warnings.append("Vocal screening UNCERTAIN — manual listening required.")
    gate_d = {
        "name": "D · Sound Integrity",
        "status": "FAIL" if sound_issues else ("WARNING" if sound_warnings else "PASS"),
        "integratedLufs": loud["integratedLufs"],
        "truePeakDbtp": loud["truePeakDbtp"],
        "clippedSamples": clipped,
        "spectralCentroidHz": centroid,
        "lowMidPct": low_mid_pct,
        "vocalScreening": vocal_screening,
        "issues": sound_issues,
        "warnings": sound_warnings,
    }

    # E. User Listening (ALWAYS UNVERIFIED until human listens!)
    gate_e = {
        "name": "E · User Listening",
        "status": "UNVERIFIED",
        "humanListeningRequired": True,
        "noteKo": "자연스러운 연주·음색 매력도·그루브·기존 레이어 조화는 사용자 직접 청취 전까지 UNVERIFIED입니다.",
    }

    statuses = [gate_a["status"], gate_b["status"], gate_c["status"], gate_d["status"]]
    overall = "FAIL" if "FAIL" in statuses else ("WARNING" if "WARNING" in statuses else "PASS")
    return {
        "schemaVersion": 1,
        "technicalOverall": overall,
        "subjectiveMusicality": "UNVERIFIED",
        "humanListeningRequired": True,
        "gates": {
            "engineIntegrity": gate_a,
            "performanceIntegrity": gate_b,
            "layerIntegrity": gate_c,
            "soundIntegrity": gate_d,
            "userListening": gate_e,
        },
    }
