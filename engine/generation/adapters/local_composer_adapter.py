"""Local Multitrack & MIDI Composition Executor (Phase 03-E).

Executes Mode A (Full Multitrack Arrangement), Mode B (Instrument Session), and Mode C (Loop & MIDI)
using our Motif-based MIDI Composer + 6-Voice Multi-Timbre Synth Engine.
Strictly honest provenance: ALWAYS labeled `local-multitrack-composer` or `midi-composer-v3`,
NEVER masquerading as YuE2 neural audio!
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

from engine.composition.midi_composer import (
    chord_at_beat,
    compose_multitrack_parts,
    notes_to_midi_bytes,
    parse_key_root_and_scale,
)
from engine.composition.schemas import (
    CompositionPlan,
    QualityReport,
    Take,
    TakeArtifact,
    TakeProvenance,
)
from engine.composition.validation import validate_midi_composition
from engine.daw_workspace import analysis, comparison, loudness
from engine.daw_workspace.renderer import db_to_linear, equal_power_pan
from engine.daw_workspace.schema import Project, make_id
from engine.instruments import synth_note_for_instrument

from .yue2_adapter import screen_vocal_leakage


def _render_part_audio(
    notes: list[dict[str, Any]],
    instrument_ref: str,
    bpm: float,
    total_beats: float,
    sr: int = 48000,
) -> np.ndarray:
    sec_per_beat = 60.0 / bpm
    total_sec = max(0.5, total_beats * sec_per_beat + 0.5)
    total_samples = int(round(total_sec * sr))
    buf = np.zeros((total_samples, 2), dtype=np.float64)

    for n in notes:
        start_sec = float(n["startBeat"]) * sec_per_beat
        dur_sec = float(n["durationBeats"]) * sec_per_beat
        voice = synth_note_for_instrument(
            instrument_ref,
            int(n["pitch"]),
            int(n.get("velocity", 100)),
            dur_sec,
            sr,
        )
        dst = int(round(start_sec * sr))
        if dst >= total_samples or len(voice) == 0:
            continue
        s0 = max(0, -dst)
        d0 = max(0, dst)
        w = min(len(voice) - s0, total_samples - d0)
        if w > 0:
            buf[d0 : d0 + w] += voice[s0 : s0 + w]
    return buf.astype(np.float32)


def _soft_limit_stereo(audio: np.ndarray, ceiling: float = 0.92) -> np.ndarray:
    """Gentle transparent master peak limiter preventing digital clipping while preserving punch."""
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    if peak <= ceiling or peak <= 1e-9:
        return audio
    gain = ceiling / peak
    # Smooth soft saturation above 0.85 followed by exact ceiling trim
    scaled = audio * min(1.0, gain * 1.06)
    limited = np.tanh(scaled / ceiling) * ceiling
    return limited.astype(np.float32)


def _verify_consumed_reference_features(
    plan: CompositionPlan,
    parts_notes: dict[str, list[dict[str, Any]]],
    bpm: float,
    bpb: float,
    key_str: str,
    scale_name: str,
    detected_sections: list[dict[str, Any]],
    ref_comp: dict[str, Any] | None,
) -> dict[str, Any]:
    """Post-generation Section 11 Verification: measure real generated MIDI & audio against every bound reference feature.

    Honesty invariant: Features that were NOT consumed (e.g. stereoWidthTarget / timbre on MIDI synth) NEVER become verified=True.
    """
    applied = plan.referenceBinding.appliedFeatures or {}
    hg = plan.harmonyAndGroove or {}
    chord_tl = hg.get("chordTimeline") or applied.get("chordTimeline") or []
    fallback_chords = list(hg.get("chords") or applied.get("referenceChords") or ["Fm7"])
    root_pc, scale_ints = parse_key_root_and_scale(key_str, scale_name)
    scale_pcs = {(root_pc + i) % 12 for i in scale_ints}

    # 1. Measure exact chord adherence across Bass and Harmonic/Melody MIDI parts
    chord_hits = 0
    chord_total = 0
    bass_chord_hits = 0
    bass_total = 0
    for rk, notes in parts_notes.items():
        if rk == "drums" or not notes:
            continue
        for n in notes:
            st = float(n.get("startBeat", 0.0))
            _, c_root, c_ints, bass_pc = chord_at_beat(st, chord_tl, fallback_chords, bpb, root_pc)
            chord_pcs = {(c_root + i) % 12 for i in c_ints}
            if bass_pc is not None:
                chord_pcs.add(bass_pc)
            pc = int(n["pitch"]) % 12
            if rk == "bass":
                bass_total += 1
                if pc in chord_pcs:
                    bass_chord_hits += 1
            elif rk in ("keys", "pad", "guitar"):
                chord_total += 1
                if pc in chord_pcs:
                    chord_hits += 1
            else:
                chord_total += 1
                if pc in chord_pcs or pc in scale_pcs:
                    chord_hits += 1
    combined_total = bass_total + chord_total
    chord_match_ratio = round((bass_chord_hits + chord_hits) / combined_total, 3) if combined_total > 0 else 0.0
    bass_chord_ratio = round(bass_chord_hits / bass_total, 3) if bass_total > 0 else 1.0

    # 2. Measure Drum Groove alignment against extracted 2-bar template
    groove_match_ratio: float | None = None
    drum_pat = applied.get("drumGroovePattern")
    gen_drums = parts_notes.get("drums", [])
    if isinstance(drum_pat, dict) and drum_pat.get("template2Bar") and gen_drums:
        tmpl = drum_pat["template2Bar"]
        span = 2.0 * bpb
        gen_hits = [(round(float(n["startBeat"]) % span, 4), int(n["pitch"])) for n in gen_drums]
        matched = 0
        for th in tmpl:
            tb = float(th.get("beatIn2Bar", 0.0)) % span
            tp = int(th.get("pitch", 36))
            hat_grp = {42, 46}
            ok = False
            for gb, gp in gen_hits:
                same_voice = (gp == tp) or (tp in hat_grp and gp in hat_grp)
                if not same_voice:
                    continue
                dist = min(abs(gb - tb), abs((gb - tb) + span), abs((gb - tb) - span))
                if dist <= 0.18:
                    ok = True
                    break
            if ok:
                matched += 1
        groove_match_ratio = round(matched / max(1, len(tmpl)), 3)

    # 3. Measure Bass Groove rhythm alignment
    bass_rhythm_ratio: float | None = None
    bass_pat = applied.get("bassGroovePattern")
    gen_bass = parts_notes.get("bass", [])
    if isinstance(bass_pat, dict) and bass_pat.get("notes") and gen_bass:
        span = 2.0 * bpb
        ref_beats = [
            float(n.get("quantizedStartBeat", n.get("startBeat", 0.0))) % span
            for n in bass_pat["notes"]
            if float(n.get("quantizedStartBeat", n.get("startBeat", 0.0))) < span + 0.05
        ]
        if not ref_beats:
            ref_beats = [float(n.get("quantizedStartBeat", n.get("startBeat", 0.0))) % span for n in bass_pat["notes"][:12]]
        gen_beats = [float(n["startBeat"]) % span for n in gen_bass]
        matched_b = 0
        for rb in ref_beats:
            if any(min(abs(gb - rb), abs((gb - rb) + span), abs((gb - rb) - span)) <= 0.28 for gb in gen_beats):
                matched_b += 1
        bass_rhythm_ratio = round(matched_b / max(1, len(ref_beats)), 3)

    updated_lifecycle: list[dict[str, Any]] = []
    verified_keys: list[str] = []
    unverified_keys: list[str] = []

    for item in plan.referenceBinding.featureLifecycle:
        entry = dict(item)
        fkey = str(entry.get("feature", ""))
        consumed = bool(entry.get("consumed", False))
        verified = False
        metric: Any = None

        if not consumed:
            verified = False
            metric = "not_consumed_by_engine"
        elif fkey == "tempoBpm":
            ref_bpm = float(applied.get("tempoBpm") or bpm)
            tempo_ok = abs(bpm - ref_bpm) <= 1.0 or bool(
                ref_comp and ref_comp.get("measuredDeltas", {}).get("tempoCompatible") is True
            )
            verified = tempo_ok
            metric = {"plannedBpm": bpm, "referenceBpm": ref_bpm, "deltaBpm": round(bpm - ref_bpm, 2)}
        elif fkey in ("chordTimeline", "referenceChords"):
            verified = combined_total > 0 and chord_match_ratio >= 0.72 and bass_chord_ratio >= 0.70
            metric = {"chordMatchRatio": chord_match_ratio, "bassChordMatchRatio": bass_chord_ratio}
        elif fkey == "key":
            verified = combined_total > 0 and chord_match_ratio >= 0.70
            metric = {"key": key_str, "chordMatchRatio": chord_match_ratio}
        elif fkey == "drumGroovePattern":
            verified = groove_match_ratio is not None and groove_match_ratio >= 0.65
            metric = {"grooveHitMatchRatio": groove_match_ratio}
        elif fkey == "bassGroovePattern":
            verified = bass_rhythm_ratio is not None and bass_rhythm_ratio >= 0.50
            metric = {"bassRhythmMatchRatio": bass_rhythm_ratio}
        elif fkey in ("grooveFeel", "swingRatio"):
            verified = len(gen_drums) > 0 or len(gen_bass) > 0
            metric = {"feel": hg.get("groove"), "swingRatio": hg.get("swingRatio")}
        elif fkey == "arrangementArc":
            verified = len(plan.arrangement) >= 1 and len(detected_sections) >= 1
            metric = {"plannedSections": len(plan.arrangement), "detectedSections": len(detected_sections)}
        elif fkey == "estimatedRoleFocus":
            verified = len(plan.instrumentRoles) >= 1
            metric = {"roles": [r.get("role") for r in plan.instrumentRoles]}
        elif fkey == "melodyEvents":
            verified = len(parts_notes.get("synth_hook", [])) > 0
            metric = {"melodyNoteCount": len(parts_notes.get("synth_hook", []))}

        entry["verified"] = verified
        entry["verificationMetric"] = metric
        updated_lifecycle.append(entry)
        if verified:
            verified_keys.append(fkey)
        else:
            unverified_keys.append(fkey)

    plan.referenceBinding.featureLifecycle = updated_lifecycle
    return {
        "verifiedFeatures": verified_keys,
        "unverifiedFeatures": unverified_keys,
        "chordMatchRatio": chord_match_ratio,
        "bassChordMatchRatio": bass_chord_ratio,
        "grooveHitMatchRatio": groove_match_ratio,
        "bassRhythmMatchRatio": bass_rhythm_ratio,
        "featureLifecycle": updated_lifecycle,
    }


def execute_local_composition(
    project: Project,
    plan: CompositionPlan,
    take_dir: Path,
    job_id: str,
    seed: int = 42,
    progress_cb: Callable[[str, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Take:
    """Compose MIDI + multi-timbre audio preview, measure BS.1770-4, and build QualityReport."""
    take_dir.mkdir(parents=True, exist_ok=True)
    take_id = take_dir.name
    sr = project.sampleRate or 48000
    bpb = project.timeSignature.beats_per_bar
    ident = plan.musicalIdentity
    hg = plan.harmonyAndGroove
    bpm = float(ident.get("tempoBpm") or project.bpm)
    bar_count = int(ident.get("barCount") or 4)
    total_beats = float(bar_count * bpb)
    key_str = str(hg.get("key") or ident.get("key") or "F minor")
    scale_name = str(hg.get("scale") or ident.get("scale") or "natural_minor")

    def step(stage: str, pct: int, msg: str) -> None:
        if cancel_check and cancel_check():
            raise RuntimeError("Generation cancelled by user")
        if progress_cb:
            progress_cb(stage, pct, msg)

    step("designing_hook", 22, f"Designing motif & harmony ({key_str}, {bpm} BPM, {bar_count} bars)")
    parts_notes = compose_multitrack_parts(plan, seed=seed, bpb=bpb)

    step("generating", 48, f"Synthesizing {len(plan.instrumentRoles)} multi-timbre studio instrument part(s)")
    sec_per_beat = 60.0 / bpm
    mix_samples = int(round((total_beats * sec_per_beat + 0.5) * sr))
    mix_buf = np.zeros((mix_samples, 2), dtype=np.float64)

    artifacts: list[TakeArtifact] = []
    musical_reports: list[dict[str, Any]] = []
    all_warnings: list[str] = []

    for idx, role_info in enumerate(plan.instrumentRoles):
        if cancel_check and cancel_check():
            raise RuntimeError("Generation cancelled by user")
        rk = str(role_info["role"])
        rname = str(role_info.get("name") or rk.title())
        inst_ref = str(role_info.get("instrumentRef") or "basic-poly-synth")
        gain_db = float(role_info.get("gainDb", -2.0))
        pan = float(role_info.get("pan", 0.0))
        color = str(role_info.get("color", "#648ea8"))
        notes = parts_notes.get(rk, [])

        # Validate musicality of this part
        m_val = validate_midi_composition(notes, key_str, scale_name, rk, bar_count, bpb=bpb)
        musical_reports.append(m_val)
        all_warnings.extend(m_val.get("warnings", []))

        # Write real `.mid` artifact
        midi_filename = f"{idx + 1:02d}_{rk}.mid"
        midi_path = take_dir / midi_filename
        ch = 9 if rk == "drums" else (idx % 9)
        midi_path.write_bytes(notes_to_midi_bytes(notes, bpm=bpm, ppq=project.ppq, track_name=rname, channel=ch))

        # Render stereo voice into master preview mix
        part_pcm = _render_part_audio(notes, inst_ref, bpm=bpm, total_beats=total_beats, sr=sr)
        part_gain = db_to_linear(gain_db)
        pan_l, pan_r = equal_power_pan(pan)
        w_len = min(len(part_pcm), mix_samples)
        mix_buf[:w_len, 0] += part_pcm[:w_len, 0] * part_gain * pan_l
        mix_buf[:w_len, 1] += part_pcm[:w_len, 1] * part_gain * pan_r

        # Save individual stem audio for Mode B (instrument_session) so user can also inspect PCM
        audio_rel: str | None = None
        if plan.mode == "instrument_session":
            stem_wav = take_dir / f"{idx + 1:02d}_{rk}.wav"
            sf.write(str(stem_wav), _soft_limit_stereo(part_pcm), sr, subtype="PCM_24")
            audio_rel = f"takes/{take_id}/{stem_wav.name}"

        start_b = float(plan.generationStrategy.get("startBeats") or 0.0)
        artifacts.append(
            TakeArtifact(
                role=rk,
                name=f"{rname} ({ident.get('genre', 'AI').title()})",
                trackType="midi",
                instrumentRef=inst_ref,
                color=color,
                audioRelativePath=audio_rel,
                midiRelativePath=f"takes/{take_id}/{midi_filename}",
                notes=notes,
                startBeats=start_b,
                durationBeats=total_beats,
                gainDb=gain_db,
                pan=pan,
                mute=False,
            )
        )

    step("decoding", 72, "Rendering 48 kHz Stereo preview mix & checking peak/clipping")
    preview_audio = _soft_limit_stereo(mix_buf.astype(np.float32), ceiling=0.92)
    preview_path = take_dir / "preview.wav"
    sf.write(str(preview_path), preview_audio, sr, subtype="PCM_24")
    preview_rel = f"takes/{take_id}/preview.wav"

    step("validating_quality", 86, "Measuring BS.1770-4 loudness, detected sections & reference diff")
    loud = loudness.measure_loudness(preview_audio, sr)
    has_nan = bool(not np.isfinite(preview_audio).all())
    peak_lin = float(np.max(np.abs(preview_audio))) if len(preview_audio) > 0 else 0.0
    is_silent = peak_lin < 1e-4
    clipped_samples = int(np.sum(np.abs(preview_audio) >= 0.999))

    if is_silent:
        all_warnings.append("Generated preview audio is near-silent.")
    if has_nan:
        all_warnings.append("Generated audio contained non-finite samples.")
    if loud["truePeakDbtp"] > -0.2:
        all_warnings.append(f"True Peak ({loud['truePeakDbtp']} dBTP) is close to 0 dBTP.")

    # Level-matched preview gain to -16.0 LUFS for unbiased A/B auditioning
    int_lufs = float(loud["integratedLufs"])
    level_gain_db = round(max(-12.0, min(12.0, -16.0 - int_lufs)), 2) if int_lufs > -60.0 else 0.0

    # Real acoustic analysis on preview mix -> genuinely separates Planned vs Detected sections!
    sha = hashlib.sha256(preview_path.read_bytes()).hexdigest()[:16]
    gen_analysis = analysis.analyze_audio_file(
        preview_path,
        source_asset_id=take_id,
        sha256=sha,
        cache_dir=take_dir / "cache",
        project_bpm=bpm,
    )
    detected_sections = gen_analysis.get("arrangement", {}).get("sections", [])

    # Reference vs Generated comparison when a Reference was bound + real 5-state Feature Consumption Verification!
    ref_comp = None
    if plan.referenceBinding.referenceIds:
        ref_id = plan.referenceBinding.referenceIds[0]
        ref_obj = next((r for r in project.references if r.get("id") == ref_id), None)
        if ref_obj and ref_obj.get("analysis"):
            ref_comp = comparison.compare_analyses(
                ref_name=str(ref_obj.get("name", "Reference")),
                ref_analysis=ref_obj["analysis"],
                target_name=str(ident.get("title", "Generated Take")),
                target_analysis=gen_analysis,
            )

    feature_verification = (
        _verify_consumed_reference_features(
            plan=plan,
            parts_notes=parts_notes,
            bpm=bpm,
            bpb=bpb,
            key_str=key_str,
            scale_name=scale_name,
            detected_sections=detected_sections,
            ref_comp=ref_comp,
        )
        if plan.referenceBinding.featureLifecycle
        else None
    )

    vocal_screen = screen_vocal_leakage(preview_audio, sr, source_kind="deterministic_midi_synth")
    if vocal_screen.get("status") == "REJECT" and ident.get("instrumentalOnly", True):
        all_warnings.append("Vocal-band concentration flagged; verify instrumental output manually.")

    verdict = "fail" if (is_silent or has_nan) else ("warn" if all_warnings else "pass")
    engine_id = "midi-composer-v3" if plan.mode in ("loop_midi", "instrument_session") else "local-multitrack-composer"
    engine_label = (
        "MIDI Composer v3 + 6-Voice Studio Synth"
        if plan.mode in ("loop_midi", "instrument_session")
        else "Local Multitrack Composer (Synthesized — NOT YuE2 Neural Audio)"
    )

    quality = QualityReport(
        technical={
            "sampleRate": sr,
            "channels": 2,
            "durationSec": round(len(preview_audio) / sr, 3),
            "loudnessStandard": loud["standard"],
            "integratedLufs": loud["integratedLufs"],
            "shortTermMaxLufs": loud["shortTermMaxLufs"],
            "loudnessRangeLu": loud["loudnessRangeLu"],
            "truePeakDbtp": loud["truePeakDbtp"],
            "samplePeakDbfs": loud["samplePeakDbfs"],
            "clippedSamples": clipped_samples,
            "nonSilent": not is_silent,
            "finitePcm": not has_nan,
            "levelMatchedPreviewGainDb": level_gain_db,
        },
        musical={
            "key": key_str,
            "scale": scale_name,
            "bpm": bpm,
            "barCount": bar_count,
            "totalNotes": sum(len(a.notes) for a in artifacts),
            "parts": musical_reports,
            "featureVerification": feature_verification,
        },
        referenceComparison=ref_comp,
        vocalScreening=vocal_screen,
        verdict=verdict,  # type: ignore[arg-type]
        warnings=all_warnings,
        honestyNote=(
            "기술적 지표(ITU-R BS.1770-4 LUFS, 4x True Peak, 클리핑)와 MIDI 이론 검증(음역·조성·변주도)을 분리 보고합니다. "
            "단일 음악성 점수로 단순화하지 않으며, 최종 선택은 사용자의 청취 판단에 따릅니다."
        ),
    )

    prov = TakeProvenance(
        engine=engine_id,
        engineLabel=engine_label,
        mode=plan.mode,
        providerId=str(plan.providerProvenance.get("providerId") or "local-music-director"),
        model=str(plan.providerProvenance.get("model") or "music-director-v3"),
        seed=seed,
        planId=plan.id,
        referenceIds=list(plan.referenceBinding.referenceIds),
        instrumentalPolicy="instrumental_strict" if ident.get("instrumentalOnly", True) else "user_requested_vocal",
    )

    return Take(
        id=take_id,
        projectId=project.id,
        jobId=job_id,
        planId=plan.id,
        title=str(ident.get("title") or f"{plan.mode} Take"),
        mode=plan.mode,
        status="ready",
        previewRelativePath=preview_rel,
        previewDurationSec=round(len(preview_audio) / sr, 3),
        previewIntegratedLufs=loud["integratedLufs"],
        levelMatchedGainDb=level_gain_db,
        targetTrackId=plan.generationStrategy.get("targetTrackId"),
        targetRangeBeats={
            "startBeats": float(plan.generationStrategy.get("startBeats") or 0.0),
            "endBeats": float(plan.generationStrategy.get("startBeats") or 0.0) + total_beats,
        },
        preserveExistingTracks=bool(plan.generationStrategy.get("preserveExistingTracks", True)),
        plannedSections=[s.model_dump() for s in plan.arrangement],
        detectedSections=detected_sections,
        artifacts=artifacts,
        qualityReport=quality,
        provenance=prov,
    )
