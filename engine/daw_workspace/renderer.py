"""Full Studio 3-Pass Stereo WAV Renderer: Pro Instruments + Insert FX + External Sidechain + Automation + Send/Return & Group Buses + Track Freeze (Phase 05 · GATE 4)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from engine.fx.automation import apply_automated_filter_sweep, find_automation_lane, sample_automation_curve
from engine.fx.chain import process_fx_chain
from engine.fx.freeze import is_track_freeze_valid
from engine.instruments import render_track_instrument

from .schema import Project, Track
from .store import project_dir, resolve_asset_file


def db_to_linear(db: float) -> float:
    if db <= -60.0:
        return 0.0
    return float(10.0 ** (db / 20.0))


def equal_power_pan(pan: float) -> tuple[float, float]:
    """Match Web Audio StereoPannerNode equal-power panning law."""
    p = max(-1.0, min(1.0, float(pan)))
    x = (p + 1.0) * 0.5
    angle = x * (math.pi * 0.5)
    return math.cos(angle), math.sin(angle)


def _load_stereo_audio(path: Path, target_sr: int) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != target_sr and len(data) > 0:
        g = math.gcd(int(sr), int(target_sr))
        up = int(target_sr) // g
        down = int(sr) // g
        left = resample_poly(data[:, 0], up, down)
        right = resample_poly(data[:, 1], up, down)
        data = np.stack([left, right], axis=1).astype(np.float32)
    return data


def _apply_clip_fades(
    buf: np.ndarray,
    sr: int,
    fade_in_sec: float = 0.0,
    fade_out_sec: float = 0.0,
    min_edge_ms: float = 4.0,
) -> np.ndarray:
    n = len(buf)
    if n <= 1:
        return buf
    min_samp = max(1, int(sr * min_edge_ms / 1000.0))
    fi_samp = max(min_samp, int(round(max(0.0, fade_in_sec) * sr)))
    fo_samp = max(min_samp, int(round(max(0.0, fade_out_sec) * sr)))
    if fi_samp + fo_samp > n:
        scale = n / float(fi_samp + fo_samp)
        fi_samp = max(1, int(fi_samp * scale))
        fo_samp = max(1, n - fi_samp)
    out = buf.copy()
    if fi_samp > 0:
        out[:fi_samp] *= np.linspace(0.0, 1.0, fi_samp, dtype=np.float32)[:, None]
    if fo_samp > 0:
        out[-fo_samp:] *= np.linspace(1.0, 0.0, fo_samp, dtype=np.float32)[:, None]
    return out


def active_tracks(tracks: list[Track]) -> list[Track]:
    any_solo = any(t.solo for t in tracks)
    if any_solo:
        return [t for t in tracks if t.solo and not t.mute]
    return [t for t in tracks if not t.mute]


def _render_track_raw_source(
    project: Project,
    trk: Track,
    *,
    start_beats: float,
    render_dur_sec: float,
    total_samples: int,
    sr: int,
    asset_cache: dict[str, np.ndarray],
) -> np.ndarray:
    """Render a track's dry audio / MIDI Pro Instrument clips into a stereo buffer (before Insert FX & fader)."""
    sec_per_beat = 60.0 / project.bpm
    trk_buf = np.zeros((total_samples, 2), dtype=np.float64)

    for clip in trk.clips:
        clip_gain = db_to_linear(clip.gainDb)
        if clip_gain <= 0.0:
            continue
        clip_start_sec = (clip.timelineStartBeats - start_beats) * sec_per_beat
        clip_dur_sec = clip.durationBeats * sec_per_beat
        if clip_start_sec + clip_dur_sec <= 0.0 or clip_start_sec >= render_dur_sec:
            continue

        if clip.type == "audio" and clip.assetId:
            if clip.assetId not in asset_cache:
                _, abs_path = resolve_asset_file(project.id, clip.assetId)
                asset_cache[clip.assetId] = _load_stereo_audio(abs_path, sr)
            src = asset_cache[clip.assetId]
            if len(src) == 0:
                continue

            src_offset_samp = max(0, int(round(clip.sourceOffsetSec * sr)))
            clip_len_samp = max(1, int(round(clip_dur_sec * sr)))
            loop_len_sec = clip.loopLengthSec or max(0.05, (len(src) / sr) - clip.sourceOffsetSec)
            loop_len_samp = max(1, int(round(loop_len_sec * sr)))

            clip_pcm = np.zeros((clip_len_samp, 2), dtype=np.float32)
            if clip.loop:
                pos = 0
                while pos < clip_len_samp:
                    chunk_end_src = min(len(src), src_offset_samp + loop_len_samp)
                    avail = max(0, chunk_end_src - src_offset_samp)
                    if avail == 0:
                        break
                    take = min(avail, clip_len_samp - pos)
                    clip_pcm[pos : pos + take] = src[src_offset_samp : src_offset_samp + take]
                    pos += take
            else:
                avail = max(0, len(src) - src_offset_samp)
                take = min(avail, clip_len_samp)
                if take > 0:
                    clip_pcm[:take] = src[src_offset_samp : src_offset_samp + take]

            if getattr(clip, "reversed", False):
                clip_pcm = clip_pcm[::-1].copy()

            fade_in_sec = max(0.0, float(getattr(clip, "fadeInBeats", 0.0))) * sec_per_beat
            fade_out_sec = max(0.0, float(getattr(clip, "fadeOutBeats", 0.0))) * sec_per_beat
            clip_pcm = _apply_clip_fades(clip_pcm, sr, fade_in_sec=fade_in_sec, fade_out_sec=fade_out_sec) * clip_gain
            dst_start = int(round(clip_start_sec * sr))
            src_slice_start = max(0, -dst_start)
            dst_write_start = max(0, dst_start)
            write_len = min(len(clip_pcm) - src_slice_start, total_samples - dst_write_start)
            if write_len > 0:
                trk_buf[dst_write_start : dst_write_start + write_len] += clip_pcm[
                    src_slice_start : src_slice_start + write_len
                ]

        elif clip.type == "midi":
            loop_len_beats = clip.loopLengthBeats or max(
                4.0,
                max((n.startBeat + n.durationBeats for n in clip.notes), default=4.0),
            )
            reps = int(math.ceil(clip.durationBeats / loop_len_beats)) if clip.loop else 1
            clip_notes_expanded: list[dict[str, Any]] = []
            for rep in range(reps):
                rep_offset_beats = rep * loop_len_beats
                for note in clip.notes:
                    rel_start_beats = rep_offset_beats + note.startBeat
                    if rel_start_beats >= clip.durationBeats:
                        continue
                    clipped_dur_beats = min(note.durationBeats, clip.durationBeats - rel_start_beats)
                    if clipped_dur_beats <= 0.0:
                        continue
                    clip_notes_expanded.append(
                        {
                            "id": note.id,
                            "pitch": note.pitch,
                            "velocity": note.velocity,
                            "startBeat": rel_start_beats,
                            "durationBeats": clipped_dur_beats,
                        }
                    )
            if clip_notes_expanded:
                def _resolve_asset_path(aid: str) -> Path | None:
                    try:
                        _, ap = resolve_asset_file(project.id, aid)
                        return ap
                    except Exception:
                        return None

                inst_cfg = getattr(trk, "instrumentConfig", None) or {}
                clip_pcm = (
                    render_track_instrument(
                        clip_notes_expanded,
                        instrument_ref=trk.instrumentRef,
                        bpm=project.bpm,
                        total_beats=clip.durationBeats,
                        sr=sr,
                        instrument_config=inst_cfg,
                        asset_resolver=_resolve_asset_path,
                    )
                    * clip_gain
                )
                dst_start = int(round(clip_start_sec * sr))
                src_slice_start = max(0, -dst_start)
                dst_write_start = max(0, dst_start)
                write_len = min(len(clip_pcm) - src_slice_start, total_samples - dst_write_start)
                if write_len > 0:
                    trk_buf[dst_write_start : dst_write_start + write_len] += clip_pcm[
                        src_slice_start : src_slice_start + write_len
                    ]

    return trk_buf.astype(np.float32)


def render_single_track_pre_fader(
    project: Project,
    trk: Track,
    *,
    start_beats: float = 0.0,
    end_beats: float | None = None,
    sidechain_buffers: dict[str, np.ndarray] | None = None,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Render one track's full source + Instrument Automation + Insert FX Chain (used by Track Freeze!)."""
    sr = project.sampleRate
    sec_per_beat = 60.0 / project.bpm
    render_end = end_beats if end_beats is not None else project.lengthBeats
    render_dur_sec = max(0.1, (render_end - start_beats) * sec_per_beat)
    total_samples = int(round(render_dur_sec * sr))
    asset_cache: dict[str, np.ndarray] = {}

    raw = _render_track_raw_source(
        project,
        trk,
        start_beats=start_beats,
        render_dur_sec=render_dur_sec,
        total_samples=total_samples,
        sr=sr,
        asset_cache=asset_cache,
    )
    lanes = list(getattr(trk, "automationLanes", None) or [])
    inst_cut_lane = find_automation_lane(lanes, target_type="instrument", parameter_id="cutoffHz")
    if inst_cut_lane is not None:
        raw = apply_automated_filter_sweep(
            raw,
            inst_cut_lane,
            sr=sr,
            bpm=project.bpm,
            start_beats=start_beats,
            default_cutoff=float((trk.instrumentConfig.get("parameters") or {}).get("cutoffHz", 2200.0)),
            resonance=float((trk.instrumentConfig.get("parameters") or {}).get("resonance", 0.25)),
        )
    processed, meters = process_fx_chain(
        raw,
        list(trk.effects or []),
        sr=sr,
        bpm=project.bpm,
        start_beats=start_beats,
        sidechain_buffers=sidechain_buffers,
        automation_lanes=lanes,
    )
    return processed, sr, meters


def render_project_to_array(
    project: Project,
    start_beats: float = 0.0,
    end_beats: float | None = None,
    return_meters: bool = False,
) -> tuple[np.ndarray, int] | tuple[np.ndarray, int, dict[str, Any]]:
    """3-Pass Studio Audio Graph Renderer:
    Pass 1: Render dry/frozen source per track (providing true external Sidechain key buffers!)
    Pass 2: Insert FX + Automation -> Track Volume/Pan (automated!) -> Pre/Post-Fader Sends -> Group/Master routing
    Pass 3: Process Return & Group Buses (Solo/Mute parity + cycle guard) -> Master FX -> Master Gain!
    """
    sr = project.sampleRate
    sec_per_beat = 60.0 / project.bpm
    render_end_beats = end_beats if end_beats is not None else project.lengthBeats
    render_dur_sec = max(0.1, (render_end_beats - start_beats) * sec_per_beat)
    total_samples = int(round(render_dur_sec * sr))

    asset_cache: dict[str, np.ndarray] = {}
    act_tracks = active_tracks(project.tracks)
    act_ids = {t.id for t in act_tracks}

    # Identify any external sidechain source tracks needed by active tracks (even if sidechain source is muted/ghost kick!)
    needed_sc_ids: set[str] = set()
    for trk in act_tracks:
        for fx in trk.effects or []:
            if fx.get("enabled", True) and not fx.get("bypass", False):
                sc_id = fx.get("sidechainTrackId") or (fx.get("parameters") or {}).get("sidechainTrackId")
                if sc_id and sc_id != trk.id:
                    needed_sc_ids.add(str(sc_id))

    # PASS 1: Render dry sources (or load valid Frozen WAV cache!)
    track_sources: dict[str, np.ndarray] = {}
    track_from_freeze: set[str] = set()
    for trk in project.tracks:
        if trk.id not in act_ids and trk.id not in needed_sc_ids:
            continue
        if start_beats == 0.0 and is_track_freeze_valid(project, trk):
            try:
                aid = str(trk.freezeState["assetId"])  # type: ignore[index]
                _, fpath = resolve_asset_file(project.id, aid)
                fpcm = _load_stereo_audio(fpath, sr)
                buf = np.zeros((total_samples, 2), dtype=np.float32)
                w = min(len(fpcm), total_samples)
                buf[:w] = fpcm[:w]
                track_sources[trk.id] = buf
                track_from_freeze.add(trk.id)
                continue
            except Exception:
                pass
        track_sources[trk.id] = _render_track_raw_source(
            project,
            trk,
            start_beats=start_beats,
            render_dur_sec=render_dur_sec,
            total_samples=total_samples,
            sr=sr,
            asset_cache=asset_cache,
        )

    # Prepare Bus accumulators (Return & Group buses)
    buses = list(getattr(project, "buses", None) or [])
    bus_by_id = {str(b["id"]): b for b in buses if b.get("id")}
    bus_bufs: dict[str, np.ndarray] = {bid: np.zeros((total_samples, 2), dtype=np.float64) for bid in bus_by_id}
    mix = np.zeros((total_samples, 2), dtype=np.float64)
    all_meters: dict[str, Any] = {"tracks": {}, "buses": {}, "master": {}}

    # PASS 2: Track Insert FX + Automation + Sends + Track Fader/Pan -> Group Bus or Master
    for trk in act_tracks:
        src_pcm = track_sources.get(trk.id)
        if src_pcm is None:
            continue
        lanes = list(getattr(trk, "automationLanes", None) or [])

        if trk.id in track_from_freeze:
            pre_fader = src_pcm
            fx_meters: dict[str, Any] = (trk.freezeState or {}).get("fxMeters", {})
        else:
            # Instrument cutoff automation (e.g. synth filter sweep during buildup!)
            inst_cut = find_automation_lane(lanes, target_type="instrument", parameter_id="cutoffHz")
            if inst_cut is not None:
                src_pcm = apply_automated_filter_sweep(
                    src_pcm,
                    inst_cut,
                    sr=sr,
                    bpm=project.bpm,
                    start_beats=start_beats,
                    default_cutoff=float((trk.instrumentConfig.get("parameters") or {}).get("cutoffHz", 2200.0)),
                    resonance=float((trk.instrumentConfig.get("parameters") or {}).get("resonance", 0.25)),
                )
            # Exclude self from sidechain map (prevents feedback loop!)
            sc_map = {k: v for k, v in track_sources.items() if k != trk.id}
            pre_fader, fx_meters = process_fx_chain(
                src_pcm,
                list(trk.effects or []),
                sr=sr,
                bpm=project.bpm,
                start_beats=start_beats,
                sidechain_buffers=sc_map,
                automation_lanes=lanes,
            )

        all_meters["tracks"][trk.id] = fx_meters

        # Track Volume & Pan (with real sample-rate automation curve support!)
        vol_lane = find_automation_lane(lanes, target_type="track", parameter_id="gainDb")
        pan_lane = find_automation_lane(lanes, target_type="track", parameter_id="pan")

        if vol_lane is not None:
            db_curve = sample_automation_curve(
                vol_lane, n_samples=total_samples, sr=sr, bpm=project.bpm, start_beats=start_beats, default_value=trk.gainDb
            )
            gain_curve = np.where(db_curve <= -60.0, 0.0, 10.0 ** (db_curve / 20.0))
        else:
            gain_curve = db_to_linear(trk.gainDb)

        if pan_lane is not None:
            p_curve = np.clip(
                sample_automation_curve(
                    pan_lane, n_samples=total_samples, sr=sr, bpm=project.bpm, start_beats=start_beats, default_value=trk.pan
                ),
                -1.0,
                1.0,
            )
            ang = ((p_curve + 1.0) * 0.5) * (math.pi * 0.5)
            pl_v = np.cos(ang)
            pr_v = np.sin(ang)
        else:
            pl_v, pr_v = equal_power_pan(trk.pan)

        post_fader = np.empty((total_samples, 2), dtype=np.float64)
        post_fader[:, 0] = pre_fader[:, 0] * gain_curve * pl_v
        post_fader[:, 1] = pre_fader[:, 1] * gain_curve * pr_v

        # Pre-Fader & Post-Fader Sends into Return/Group Buses (strictly acyclic — tracks only send to buses!)
        for snd in getattr(trk, "sends", None) or []:
            if not snd.get("enabled", True):
                continue
            bid = str(snd.get("busId", ""))
            if bid not in bus_bufs:
                continue
            snd_lane = find_automation_lane(lanes, target_type="send", target_id=bid, parameter_id="levelDb")
            if snd_lane is not None:
                sdb = sample_automation_curve(
                    snd_lane,
                    n_samples=total_samples,
                    sr=sr,
                    bpm=project.bpm,
                    start_beats=start_beats,
                    default_value=float(snd.get("levelDb", -12.0)),
                )
                s_lin = np.where(sdb <= -60.0, 0.0, 10.0 ** (sdb / 20.0))[:, None]
            else:
                s_lin = db_to_linear(float(snd.get("levelDb", -12.0)))
            tap = pre_fader if snd.get("preFader", False) else post_fader
            bus_bufs[bid] += tap * s_lin

        # Route Track Output to assigned Group Bus or Master
        out_bus = str(getattr(trk, "outputBusId", "master") or "master")
        if out_bus != "master" and out_bus in bus_bufs:
            bus_bufs[out_bus] += post_fader
        else:
            mix += post_fader

    # PASS 3: Process Return & Group Buses (Solo/Mute parity + Bus FX chains) -> Sum into Master!
    any_bus_solo = any(b.get("solo", False) for b in buses)
    for bid, bus in bus_by_id.items():
        if bus.get("mute", False):
            continue
        if any_bus_solo and not bus.get("solo", False):
            continue
        b_in = bus_bufs[bid].astype(np.float32)
        if float(np.max(np.abs(b_in))) < 1e-7:
            continue
        b_proc, b_meters = process_fx_chain(
            b_in,
            list(bus.get("effects") or []),
            sr=sr,
            bpm=project.bpm,
            start_beats=start_beats,
        )
        all_meters["buses"][bid] = b_meters
        b_gain = db_to_linear(float(bus.get("gainDb", 0.0)))
        bl, br = equal_power_pan(float(bus.get("pan", 0.0)))
        mix[:, 0] += b_proc[:, 0] * b_gain * bl
        mix[:, 1] += b_proc[:, 1] * b_gain * br

    # Master Insert FX Chain + Master Fader
    master_fxs = list(getattr(project, "masterEffects", None) or [])
    mix_f32 = mix.astype(np.float32)
    if master_fxs:
        mix_f32, m_meters = process_fx_chain(mix_f32, master_fxs, sr=sr, bpm=project.bpm, start_beats=start_beats)
        all_meters["master"] = m_meters

    master_gain = db_to_linear(project.masterGainDb)
    final_pcm = (mix_f32 * master_gain).astype(np.float32)
    if return_meters:
        return final_pcm, sr, all_meters
    return final_pcm, sr


def export_project_wav(
    project: Project,
    filename: str | None = None,
    start_beats: float = 0.0,
    end_beats: float | None = None,
) -> dict[str, Any]:
    """Render and write a Stereo PCM-24 WAV export into project/exports/."""
    audio, sr = render_project_to_array(project, start_beats=start_beats, end_beats=end_beats)  # type: ignore[misc]
    peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    rms = float(np.sqrt(np.mean(audio * audio))) if len(audio) > 0 else 0.0
    clipped = int(np.sum(np.abs(audio) >= 1.0))

    pdir = project_dir(project.id).resolve()
    exports_dir = pdir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_base = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.name).strip("_") or "export"
    out_name = filename or f"{safe_base}_export.wav"
    if not out_name.lower().endswith(".wav"):
        out_name += ".wav"
    out_path = (exports_dir / out_name).resolve()
    if not out_path.is_relative_to(exports_dir.resolve()):
        raise ValueError("Invalid export path")

    clipped_audio = np.clip(audio, -1.0, 1.0)
    sf.write(str(out_path), clipped_audio, sr, subtype="PCM_24")
    raw_bytes = out_path.read_bytes()

    return {
        "filename": out_name,
        "relativePath": f"exports/{out_name}",
        "sampleRate": sr,
        "channels": 2,
        "durationSec": round(len(audio) / sr, 6),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "peakLinear": round(peak, 6),
        "peakDbfs": round(20.0 * math.log10(peak), 2) if peak > 1e-9 else -120.0,
        "rmsDbfs": round(20.0 * math.log10(rms), 2) if rms > 1e-9 else -120.0,
        "clippedSamples": clipped,
    }
