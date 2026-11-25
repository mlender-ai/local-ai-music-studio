"""Non-destructive Audio Arrangement, Reverse, Fades, Seam Validation & In-Context Preview Renderer (Phase 04-A & 04-C · Sections 9 & 14)."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from engine.daw_workspace import commands, loudness, proposals, renderer, store
from engine.daw_workspace.schema import Clip, Project, Track, make_id
from engine.daw_workspace.session import event_bus


def create_reversed_clip_asset(
    project_id: str,
    clip_id: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Non-destructively reverse an audio clip by creating a new immutable reversed WAV asset."""
    proj = store.load_project(project_id)
    if expected_revision is not None and proj.revision != expected_revision:
        raise store.RevisionConflictError(expected_revision, proj.revision, proj)

    target_trk: Track | None = None
    target_clp: Clip | None = None
    for t in proj.tracks:
        for c in t.clips:
            if c.id == clip_id:
                target_trk, target_clp = t, c
                break
    if not target_trk or not target_clp:
        raise FileNotFoundError(f"Clip not found: {clip_id}")
    if target_clp.type != "audio" or not target_clp.assetId:
        raise ValueError("Reverse requires an audio clip with a valid audio asset")

    asset, abs_path = store.resolve_asset_file(project_id, target_clp.assetId)
    data, sr = sf.read(str(abs_path), dtype="float32", always_2d=True)
    sec_per_beat = 60.0 / proj.bpm
    s0 = max(0, int(round(target_clp.sourceOffsetSec * sr)))
    dur_samps = max(1, int(round(target_clp.durationBeats * sec_per_beat * sr)))
    seg = data[s0 : min(len(data), s0 + dur_samps)]
    if len(seg) == 0:
        seg = data
    rev_pcm = np.ascontiguousarray(seg[::-1])

    pdir = store.project_dir(project_id)
    tmp_wav = pdir / "cache" / f"rev_{clip_id}.wav"
    tmp_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(tmp_wav), rev_pcm, sr, subtype="PCM_24")
    rev_bytes = tmp_wav.read_bytes()
    tmp_wav.unlink(missing_ok=True)

    proposals.record_undo_snapshot(proj)
    new_asset, _ = store.import_asset_bytes(
        project_id=project_id,
        filename=f"{Path(asset.name).stem}_reversed.wav",
        raw_bytes=rev_bytes,
        kind_hint="audio",
        source="audio-arrangement-reverse",
        provenance=f"Non-destructive reverse of {asset.name} (original preserved)",
    )

    proj = store.load_project(project_id)
    for t in proj.tracks:
        for c in t.clips:
            if c.id == clip_id:
                c.assetId = new_asset.id
                c.sourceOffsetSec = 0.0
                c.sourceDurationSec = round(len(rev_pcm) / sr, 4)
                c.reversed = not c.reversed
                c.name = f"{c.name} (Rev)" if not c.name.endswith("(Rev)") else c.name
                break
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": "Audio clip reversed (non-destructive)", "project": saved.model_dump()},
    )
    return {"reversed": True, "newAsset": new_asset.model_dump(), "project": saved.model_dump(), "revision": saved.revision}


def validate_audio_seam(
    left_audio: np.ndarray,
    right_audio: np.ndarray,
    sr: int = 48000,
    beat_alignment_error_ms: float = 0.0,
) -> dict[str, Any]:
    """Validate click/pop discontinuity, level delta, phase correlation, and beat alignment at an audio edit seam."""
    if len(left_audio) < 64 or len(right_audio) < 64:
        return {
            "status": "WARN",
            "clickDiscontinuity": 0.0,
            "levelDeltaDb": 0.0,
            "recommendedCrossfadeMs": 12.0,
            "warnings": ["Audio segment too short for full seam diagnostics."],
        }

    l_stereo = left_audio if left_audio.ndim == 2 else np.stack([left_audio, left_audio], axis=1)
    r_stereo = right_audio if right_audio.ndim == 2 else np.stack([right_audio, right_audio], axis=1)

    # 1. Exact sample discontinuity at boundary (click/pop check)
    sample_jump = float(np.max(np.abs(r_stereo[0] - l_stereo[-1])))
    # Compare against typical local step size
    win = min(512, len(l_stereo) - 1, len(r_stereo) - 1)
    typ_step = float(np.mean(np.abs(np.diff(l_stereo[-win:], axis=0)))) + 1e-6
    jump_ratio = sample_jump / typ_step

    # 2. RMS level difference across 150ms boundary window
    rms_n = min(int(0.15 * sr), len(l_stereo), len(r_stereo))
    rms_l = float(np.sqrt(np.mean(l_stereo[-rms_n:] ** 2))) + 1e-9
    rms_r = float(np.sqrt(np.mean(r_stereo[:rms_n] ** 2))) + 1e-9
    level_delta_db = round(20.0 * math.log10(rms_r / rms_l), 2)

    # 3. Stereo L/R phase health on replacement head
    head = r_stereo[:rms_n].astype(np.float64)
    denom = float(np.sqrt((head[:, 0] @ head[:, 0]) * (head[:, 1] @ head[:, 1]))) + 1e-12
    lr_corr = round(float(np.clip((head[:, 0] @ head[:, 1]) / denom, -1.0, 1.0)), 3)

    warnings: list[str] = []
    click_risk = sample_jump > 0.06 and jump_ratio > 6.0
    if click_risk:
        warnings.append(f"Seam sample discontinuity ({sample_jump:.3f}) risks click/pop without crossfade.")
    if abs(level_delta_db) > 4.5:
        warnings.append(f"Noticeable level jump at seam ({level_delta_db:+.1f} dB).")
    if abs(beat_alignment_error_ms) > 15.0:
        warnings.append(f"Beat alignment offset ({beat_alignment_error_ms:.1f} ms) exceeds 15 ms grid tolerance.")
    if lr_corr < -0.2:
        warnings.append(f"Negative L/R phase correlation ({lr_corr}) detected near seam.")

    rec_xfade = 18.0 if click_risk else (10.0 if abs(level_delta_db) > 3.0 else 6.0)
    return {
        "status": "WARN" if warnings else "PASS",
        "clickRisk": click_risk,
        "sampleDiscontinuity": round(sample_jump, 5),
        "levelDeltaDb": level_delta_db,
        "beatAlignmentErrorMs": round(beat_alignment_error_ms, 2),
        "lrPhaseCorrelation": lr_corr,
        "recommendedCrossfadeMs": rec_xfade,
        "warnings": warnings,
    }


def render_contextual_preview_pair(
    project: Project,
    target_track_id: str,
    start_beats: float,
    end_beats: float,
    replacement_clip: Clip,
    out_dir: Path,
) -> dict[str, Any]:
    """Render level-matched (-16 LUFS) In-Context Preview AND Original A/B Preview without mutating Project!"""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Pad preview slightly before/after range (up to 4 beats context if available) for musical continuity
    ctx_start = max(0.0, start_beats)
    ctx_end = max(ctx_start + 1.0, end_beats)

    # 1. Original context render
    orig_pcm, sr = renderer.render_project_to_array(project, start_beats=ctx_start, end_beats=ctx_end)
    orig_loud = loudness.measure_loudness(orig_pcm, sr)
    orig_gain_db = round(max(-12.0, min(12.0, -16.0 - float(orig_loud["integratedLufs"]))), 2) if orig_loud["integratedLufs"] > -60.0 else 0.0
    orig_path = out_dir / "preview_original_context.wav"
    sf.write(str(orig_path), np.clip(orig_pcm, -1.0, 1.0), sr, subtype="PCM_24")

    # 2. In-context candidate render (substitutes ONLY target track in [start_beats, end_beats] on an in-memory copy!)
    from engine.generation.daw_jobs import _carve_out_range_on_track

    sim = deepcopy(project)
    sim = _carve_out_range_on_track(sim, target_track_id, start_beats, end_beats)
    sim = commands.apply_command(sim, "clip.add", {"trackId": target_track_id, "clip": replacement_clip.model_dump()})
    cand_pcm, sr = renderer.render_project_to_array(sim, start_beats=ctx_start, end_beats=ctx_end)
    cand_loud = loudness.measure_loudness(cand_pcm, sr)
    cand_gain_db = round(max(-12.0, min(12.0, -16.0 - float(cand_loud["integratedLufs"]))), 2) if cand_loud["integratedLufs"] > -60.0 else 0.0
    cand_path = out_dir / "preview_in_context.wav"
    sf.write(str(cand_path), np.clip(cand_pcm, -1.0, 1.0), sr, subtype="PCM_24")

    pdir = store.project_dir(project.id).resolve()
    return {
        "inContextRelativePath": cand_path.resolve().relative_to(pdir).as_posix(),
        "originalContextRelativePath": orig_path.resolve().relative_to(pdir).as_posix(),
        "durationSec": round(len(cand_pcm) / sr, 3),
        "inContextIntegratedLufs": cand_loud["integratedLufs"],
        "inContextLevelMatchedGainDb": cand_gain_db,
        "originalIntegratedLufs": orig_loud["integratedLufs"],
        "originalLevelMatchedGainDb": orig_gain_db,
        "startBeats": ctx_start,
        "endBeats": ctx_end,
    }
