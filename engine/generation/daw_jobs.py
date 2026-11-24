"""Background single-worker Generation Job Manager, Take Store & Transactional Timeline Import (Phase 03-F).

Safe for Apple Silicon 16 GiB RAM: strictly max_workers=1 so heavy generations never compete.
Every Take Apply is a single Revision-checked Undoable transaction that preserves existing tracks
unless explicitly targeted by the user.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import soundfile as sf

from engine.composition import create_composition_plan
from engine.composition.schemas import CompositionPlan, QualityReport, Take, TakeArtifact, TakeProvenance
from engine.daw_workspace import commands, loudness, proposals, store
from engine.daw_workspace.schema import Clip, MidiNote, Project, SectionMarker, Track, make_id, utc_now_iso
from engine.daw_workspace.session import event_bus

from .adapters import (
    execute_local_composition,
    probe_demucs,
    probe_yue2,
    run_yue2_generation,
    separate_stems_demucs,
)


class GenerationJobManager:
    """Single-worker background job queue with cancellation, logs, retry & SSE updates."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daw-gen")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_flags: dict[str, threading.Event] = {}

    def _emit_job(self, job: dict[str, Any]) -> None:
        event_bus.publish(
            "generation.job.updated",
            {"projectId": job["projectId"], "job": dict(job)},
        )

    def _update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[job_id]
            job.update(fields)
            job["updatedAt"] = utc_now_iso()
            snap = dict(job)
        self._emit_job(snap)
        return snap

    def _append_log(self, job_id: str, stage: str, progress: int, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["stage"] = stage
            job["progress"] = progress
            job["logs"].append({"at": utc_now_iso(), "stage": stage, "message": message})
            job["logs"] = job["logs"][-40:]
            job["updatedAt"] = utc_now_iso()
            snap = dict(job)
        self._emit_job(snap)

    def list_jobs(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = [dict(j) for j in self._jobs.values()]
        if project_id:
            items = [j for j in items if j.get("projectId") == project_id]
        items.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        return items

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise FileNotFoundError(f"Generation job not found: {job_id}")
            return dict(self._jobs[job_id])

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise FileNotFoundError(f"Generation job not found: {job_id}")
            ev = self._cancel_flags.get(job_id)
            if ev:
                ev.set()
            job = self._jobs[job_id]
            if job["status"] not in ("ready_for_preview", "applied", "failed", "cancelled"):
                job["status"] = "cancelled"
                job["stage"] = "cancelled"
                job["logs"].append({"at": utc_now_iso(), "stage": "cancelled", "message": "Cancelled by user"})
                job["updatedAt"] = utc_now_iso()
            snap = dict(job)
        self._emit_job(snap)
        return snap

    def start_composition_job(
        self,
        project_id: str,
        plan: CompositionPlan,
        engine_choice: str = "auto",
        seed: int | None = None,
        sync: bool = False,
    ) -> dict[str, Any]:
        """Queue (or run synchronously in tests) a real composition generation job."""
        # Persist plan onto project first
        save_composition_plan(project_id, plan)

        job_id = make_id("gjob")
        take_id = make_id("take")
        actual_seed = int(seed if seed is not None else (int(time.time() * 1000) % 100000))
        cancel_ev = threading.Event()

        job_record: dict[str, Any] = {
            "jobId": job_id,
            "projectId": project_id,
            "planId": plan.id,
            "takeId": take_id,
            "mode": plan.mode,
            "engineRequested": engine_choice,
            "seed": actual_seed,
            "status": "planning",
            "stage": "planning",
            "progress": 5,
            "error": None,
            "logs": [{"at": utc_now_iso(), "stage": "planning", "message": f"Queued {plan.mode} job ({plan.musicalIdentity.get('title', '')})"}],
            "createdAt": utc_now_iso(),
            "updatedAt": utc_now_iso(),
        }

        with self._lock:
            self._jobs[job_id] = job_record
            self._cancel_flags[job_id] = cancel_ev
        self._emit_job(job_record)

        def runner() -> dict[str, Any]:
            try:
                proj = store.load_project(project_id)
                if cancel_ev.is_set():
                    raise RuntimeError("Generation cancelled by user")

                if plan.referenceBinding.referenceIds:
                    self._update(job_id, status="analyzing_reference", stage="analyzing_reference", progress=12)
                    self._append_log(
                        job_id,
                        "analyzing_reference",
                        15,
                        f"Applying Reference Blueprint ({', '.join(plan.referenceBinding.selectedInfluences)})",
                    )

                pdir = store.project_dir(project_id)
                take_dir = pdir / "takes" / take_id

                # Honest routing: use YuE2 ONLY if explicitly requested AND truly installed!
                if engine_choice == "yue2-native":
                    yue_info = probe_yue2()
                    if not yue_info["available"]:
                        raise RuntimeError(yue_info["statusNoteEn"])
                    self._update(job_id, status="generating", stage="generating", progress=35)
                    self._append_log(job_id, "generating", 40, "Running native YuE2 synthesis binary")
                    out_wav = take_dir / "preview.wav"
                    yue_res = run_yue2_generation(plan, out_wav, seed=actual_seed)
                    audio, sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
                    loud = loudness.measure_loudness(audio, sr)
                    lvl_gain = round(max(-12.0, min(12.0, -16.0 - float(loud["integratedLufs"]))), 2)
                    vocal_sc = yue_res["vocalScreening"]
                    warn_list = ["Vocal leakage suspected; review before approving as instrumental."] if vocal_sc.get("suspectedVocal") else []
                    take = Take(
                        id=take_id,
                        projectId=project_id,
                        jobId=job_id,
                        planId=plan.id,
                        title=f"{plan.musicalIdentity.get('title', 'YuE2')} (YuE2 Native)",
                        mode="full_music",
                        status="ready",
                        previewRelativePath=f"takes/{take_id}/preview.wav",
                        previewDurationSec=yue_res["durationSec"],
                        previewIntegratedLufs=loud["integratedLufs"],
                        levelMatchedGainDb=lvl_gain,
                        plannedSections=[s.model_dump() for s in plan.arrangement],
                        artifacts=[
                            TakeArtifact(
                                role="full_mix",
                                name=f"{plan.musicalIdentity.get('title', 'YuE2 Mix')}",
                                trackType="audio",
                                color="#6a997c",
                                audioRelativePath=f"takes/{take_id}/preview.wav",
                                startBeats=0.0,
                                durationBeats=round((yue_res["durationSec"] / (60.0 / proj.bpm)), 2),
                            )
                        ],
                        qualityReport=QualityReport(
                            technical={
                                "sampleRate": sr,
                                "channels": 2,
                                "durationSec": yue_res["durationSec"],
                                "loudnessStandard": loud["standard"],
                                "integratedLufs": loud["integratedLufs"],
                                "truePeakDbtp": loud["truePeakDbtp"],
                            },
                            vocalScreening=vocal_sc,
                            verdict="warn" if warn_list else "pass",
                            warnings=warn_list,
                        ),
                        provenance=TakeProvenance(
                            engine="yue2-native",
                            engineLabel="YuE2 Native Audio Generator",
                            mode="full_music",
                            providerId=str(plan.providerProvenance.get("providerId") or "local-music-director"),
                            model="yue-synth",
                            seed=actual_seed,
                            planId=plan.id,
                            referenceIds=list(plan.referenceBinding.referenceIds),
                        ),
                    )
                else:
                    # Honest built-in multi-timbre composer (Mode A/B/C)
                    def cb(stage: str, pct: int, msg: str) -> None:
                        self._update(job_id, status=stage, stage=stage, progress=pct)
                        self._append_log(job_id, stage, pct, msg)

                    take = execute_local_composition(
                        project=proj,
                        plan=plan,
                        take_dir=take_dir,
                        job_id=job_id,
                        seed=actual_seed,
                        progress_cb=cb,
                        cancel_check=cancel_ev.is_set,
                    )

                persist_take(project_id, take)
                self._update(
                    job_id,
                    status="ready_for_preview",
                    stage="ready_for_preview",
                    progress=100,
                    takeId=take.id,
                )
                self._append_log(job_id, "ready_for_preview", 100, f"Take ready for preview ({take.title})")
                event_bus.publish("take.created", {"projectId": project_id, "take": take.model_dump()})
                return take.model_dump()
            except Exception as exc:
                msg = str(exc)
                is_cancel = cancel_ev.is_set() or "cancelled" in msg.lower()
                self._update(
                    job_id,
                    status="cancelled" if is_cancel else "failed",
                    stage="cancelled" if is_cancel else "failed",
                    error=None if is_cancel else msg,
                )
                self._append_log(job_id, "cancelled" if is_cancel else "failed", 0, msg)
                if sync:
                    raise
                return {"error": msg}

        if sync:
            take_dict = runner()
            return {"job": self.get_job(job_id), "take": take_dict}

        self._executor.submit(runner)
        return {"job": self.get_job(job_id)}

    def start_stem_separation_job(
        self,
        project_id: str,
        asset_id: str,
        model_name: str = "htdemucs",
        sync: bool = False,
    ) -> dict[str, Any]:
        """Run real Demucs stem separation if installed; fail honestly otherwise."""
        demucs_info = probe_demucs()
        if not demucs_info["available"]:
            return {
                "available": False,
                "error": demucs_info["statusNoteEn"],
                "messageKo": demucs_info["statusNoteKo"],
                "messageEn": demucs_info["statusNoteEn"],
            }

        asset, abs_path = store.resolve_asset_file(project_id, asset_id)
        if asset.kind == "midi":
            raise ValueError("Stem separation requires an audio asset, not MIDI")

        job_id = make_id("gjob")
        take_id = make_id("take")
        cancel_ev = threading.Event()
        job_record: dict[str, Any] = {
            "jobId": job_id,
            "projectId": project_id,
            "planId": None,
            "takeId": take_id,
            "mode": "stem_separation",
            "engineRequested": "demucs-htdemucs",
            "status": "generating",
            "stage": "separating_stems",
            "progress": 10,
            "error": None,
            "logs": [{"at": utc_now_iso(), "stage": "separating_stems", "message": f"Separating stems for {asset.name}"}],
            "createdAt": utc_now_iso(),
            "updatedAt": utc_now_iso(),
        }
        with self._lock:
            self._jobs[job_id] = job_record
            self._cancel_flags[job_id] = cancel_ev
        self._emit_job(job_record)

        def runner() -> dict[str, Any]:
            try:
                proj = store.load_project(project_id)
                pdir = store.project_dir(project_id)
                take_dir = pdir / "takes" / take_id
                stems = separate_stems_demucs(abs_path, take_dir, model_name=model_name)
                dur_beats = round((asset.durationSec or 16.0) / (60.0 / proj.bpm), 2)
                artifacts: list[TakeArtifact] = []
                for st in stems:
                    rel = st["wavPath"].relative_to(pdir).as_posix()
                    artifacts.append(
                        TakeArtifact(
                            role=st["role"],
                            name=st["name"],
                            trackType="stem",
                            color=st["color"],
                            audioRelativePath=rel,
                            startBeats=0.0,
                            durationBeats=dur_beats,
                        )
                    )
                take = Take(
                    id=take_id,
                    projectId=project_id,
                    jobId=job_id,
                    title=f"Stems: {asset.name}",
                    mode="stem_separation",
                    status="ready",
                    previewRelativePath=artifacts[0].audioRelativePath if artifacts else None,
                    previewDurationSec=asset.durationSec,
                    artifacts=artifacts,
                    provenance=TakeProvenance(
                        engine="demucs-htdemucs",
                        engineLabel="Demucs Stem Separator",
                        mode="stem_separation",
                        providerId="local-dsp",
                        model=model_name,
                        seed=0,
                    ),
                )
                persist_take(project_id, take)
                self._update(job_id, status="ready_for_preview", stage="ready_for_preview", progress=100)
                event_bus.publish("take.created", {"projectId": project_id, "take": take.model_dump()})
                return take.model_dump()
            except Exception as exc:
                self._update(job_id, status="failed", stage="failed", error=str(exc))
                if sync:
                    raise
                return {"error": str(exc)}

        if sync:
            t_dict = runner()
            return {"available": True, "job": self.get_job(job_id), "take": t_dict}
        self._executor.submit(runner)
        return {"available": True, "job": self.get_job(job_id)}


generation_jobs = GenerationJobManager()


def save_composition_plan(project_id: str, plan: CompositionPlan) -> tuple[dict[str, Any], int]:
    proj = store.load_project(project_id)
    plan_dict = plan.model_dump()
    existing = [p for p in proj.compositionPlans if p.get("id") != plan.id]
    existing.append(plan_dict)
    proj.compositionPlans = existing[-20:]
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return plan_dict, saved.revision


def get_composition_plan(project_id: str, plan_id: str | None = None) -> dict[str, Any] | None:
    proj = store.load_project(project_id)
    if not proj.compositionPlans:
        return None
    if plan_id:
        return next((p for p in proj.compositionPlans if p.get("id") == plan_id), None)
    return proj.compositionPlans[-1]


def persist_take(project_id: str, take: Take) -> tuple[dict[str, Any], int]:
    proj = store.load_project(project_id)
    take_dict = take.model_dump()
    existing = [t for t in proj.takes if t.get("id") != take.id]
    existing.append(take_dict)
    proj.takes = existing[-25:]
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return take_dict, saved.revision


def list_takes(project_id: str) -> list[dict[str, Any]]:
    proj = store.load_project(project_id)
    return list(reversed(proj.takes))


def get_take(project_id: str, take_id: str) -> dict[str, Any]:
    proj = store.load_project(project_id)
    found = next((t for t in proj.takes if t.get("id") == take_id), None)
    if not found:
        raise FileNotFoundError(f"Take not found: {take_id}")
    return found


def resolve_take_preview_audio(project_id: str, take_id: str) -> tuple[dict[str, Any], Path]:
    take = get_take(project_id, take_id)
    rel = take.get("previewRelativePath")
    if not rel:
        raise FileNotFoundError(f"Take {take_id} has no preview audio")
    pdir = store.project_dir(project_id).resolve()
    abs_path = (pdir / rel).resolve()
    if not abs_path.is_relative_to(pdir) or not abs_path.is_file():
        raise FileNotFoundError(f"Preview audio file missing on disk: {rel}")
    return take, abs_path


def reject_take(project_id: str, take_id: str) -> tuple[dict[str, Any], int]:
    proj = store.load_project(project_id)
    target = None
    for t in proj.takes:
        if t.get("id") == take_id:
            t["status"] = "rejected"
            target = t
            break
    if not target:
        raise FileNotFoundError(f"Take not found: {take_id}")
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return target, saved.revision


def apply_take(
    project_id: str,
    take_id: str,
    apply_mode: str = "new_tracks",  # "new_tracks" | "selected_range" | "new_project" | "keep_take"
    target_track_id: str | None = None,
    start_beats: float | None = None,
    add_section_markers: bool = True,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Transactionally import a Take into the Project timeline with 1-click Undo & Revision safety."""
    proj = store.load_project(project_id)
    if expected_revision is not None and proj.revision != expected_revision:
        raise store.RevisionConflictError(expected_revision, proj.revision, proj)

    take = next((t for t in proj.takes if t.get("id") == take_id), None)
    if not take:
        raise FileNotFoundError(f"Take not found: {take_id}")

    if apply_mode == "keep_take":
        take["status"] = "kept"
        saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
        return {"applied": False, "status": "kept", "take": take, "project": saved.model_dump()}

    pdir = store.project_dir(project_id).resolve()

    if apply_mode == "new_project":
        plan = next((p for p in proj.compositionPlans if p.get("id") == take.get("planId")), None)
        new_bpm = float(plan["musicalIdentity"]["tempoBpm"]) if plan and plan.get("musicalIdentity", {}).get("tempoBpm") else proj.bpm
        new_proj = store.create_project(
            name=str(take.get("title") or "AI Composition"),
            bpm=new_bpm,
            with_default_tracks=False,
        )
        # Copy take preview & artifacts into new project and apply there
        new_pdir = store.project_dir(new_proj.id).resolve()
        src_take_dir = pdir / "takes" / take_id
        dst_take_dir = new_pdir / "takes" / take_id
        if src_take_dir.is_dir():
            import shutil

            shutil.copytree(src_take_dir, dst_take_dir, dirs_exist_ok=True)
        new_proj.takes = [dict(take)]
        if plan:
            new_proj.compositionPlans = [dict(plan)]
        store.save_project(new_proj, clear_autosave=False, expected_revision=new_proj.revision)
        res = apply_take(new_proj.id, take_id, apply_mode="new_tracks", add_section_markers=True)
        res["createdNewProject"] = True
        return res

    # Record Undo snapshot BEFORE modifying existing project!
    proposals.record_undo_snapshot(proj)

    # Import artifact files as immutable project assets first
    imported_assets: dict[int, str] = {}
    for idx, art in enumerate(take.get("artifacts", [])):
        rel = art.get("midiRelativePath") if art.get("trackType") == "midi" else art.get("audioRelativePath")
        if rel:
            abs_f = (pdir / rel).resolve()
            if abs_f.is_relative_to(pdir) and abs_f.is_file():
                asset, _ = store.import_asset_bytes(
                    project_id=project_id,
                    filename=abs_f.name,
                    raw_bytes=abs_f.read_bytes(),
                    kind_hint="midi" if art.get("trackType") == "midi" else "audio",
                    source=take.get("provenance", {}).get("engine", "ai-composition"),
                    provenance=f"Take {take_id} ({take.get('title', '')})",
                )
                imported_assets[idx] = asset.id

    # Reload after immutable asset imports so asset list & revision are synchronized
    proj = store.load_project(project_id)
    updated = proj
    bpb = updated.timeSignature.beats_per_bar
    created_track_ids: list[str] = []
    created_clip_ids: list[str] = []

    # Mute original mix if this take is Demucs stem separation (prevents double-summing!)
    if take.get("mode") == "stem_separation":
        for trk in updated.tracks:
            if trk.type == "audio" and not trk.mute:
                updated = commands.apply_command(updated, "track.setMute", {"trackId": trk.id, "mute": True})

    # Optional: align BPM when full_music take is applied to an empty/fresh project
    plan = next((p for p in updated.compositionPlans if p.get("id") == take.get("planId")), None)
    if take.get("mode") == "full_music" and plan and not any(t.clips for t in updated.tracks):
        plan_bpm = plan.get("musicalIdentity", {}).get("tempoBpm")
        if plan_bpm:
            updated = commands.apply_command(updated, "project.setTempo", {"bpm": float(plan_bpm)})

    for idx, art in enumerate(take.get("artifacts", [])):
        art_start = float(start_beats if start_beats is not None else art.get("startBeats", 0.0))
        art_dur = float(art.get("durationBeats", 16.0))
        art_type = str(art.get("trackType", "midi"))
        asset_id = imported_assets.get(idx)

        dst_track_id: str | None = None
        if apply_mode == "selected_range" and target_track_id:
            existing_trk = next((t for t in updated.tracks if t.id == target_track_id), None)
            if existing_trk and ((existing_trk.type == "midi") == (art_type == "midi")):
                dst_track_id = existing_trk.id
                if art_type == "midi" and art.get("instrumentRef"):
                    updated = commands.apply_command(
                        updated,
                        "track.setInstrument",
                        {"trackId": dst_track_id, "instrumentRef": art["instrumentRef"]},
                    )

        if not dst_track_id:
            dst_track_id = make_id("trk")
            updated = commands.apply_command(
                updated,
                "track.add",
                {
                    "id": dst_track_id,
                    "name": art.get("name", f"AI {art.get('role', 'Track')}"),
                    "type": art_type if art_type in ("audio", "stem", "midi") else "midi",
                    "color": art.get("color", "#648ea8"),
                    "stemLabel": art.get("role") if art_type == "stem" else None,
                    "instrumentRef": art.get("instrumentRef") if art_type == "midi" else None,
                },
            )
            if art.get("gainDb") is not None:
                updated = commands.apply_command(updated, "track.setGain", {"trackId": dst_track_id, "gainDb": float(art["gainDb"])})
            if art.get("pan") is not None:
                updated = commands.apply_command(updated, "track.setPan", {"trackId": dst_track_id, "pan": float(art["pan"])})
            created_track_ids.append(dst_track_id)

        clip_id = make_id("clp")
        notes_list = [
            {
                "id": make_id("note"),
                "pitch": int(n["pitch"]),
                "velocity": int(n.get("velocity", 100)),
                "startBeat": float(n["startBeat"]),
                "durationBeats": float(n["durationBeats"]),
            }
            for n in art.get("notes", [])
        ]
        clip_payload: dict[str, Any] = {
            "id": clip_id,
            "name": art.get("name", "AI Clip"),
            "type": "midi" if art_type == "midi" else "audio",
            "assetId": asset_id,
            "timelineStartBeats": art_start,
            "durationBeats": art_dur,
            "sourceOffsetSec": 0.0,
            "sourceDurationSec": round(art_dur * (60.0 / updated.bpm), 3),
            "loop": False,
            "loopLengthSec": None,
            "loopLengthBeats": art_dur if art_type == "midi" else None,
            "gainDb": 0.0,
            "notes": notes_list,
        }
        updated = commands.apply_command(updated, "clip.add", {"trackId": dst_track_id, "clip": clip_payload})
        created_clip_ids.append(clip_id)

        end_beats = art_start + art_dur
        if end_beats > updated.lengthBeats:
            updated = commands.apply_command(updated, "project.setLength", {"lengthBeats": float(int((end_beats + 3) // 4) * 4)})

    # Add clearly labeled Planned section markers for full_music takes when requested
    if add_section_markers and take.get("mode") == "full_music" and take.get("plannedSections"):
        sec_colors = ["#49505e", "#446256", "#554d6b", "#6d5645", "#4c626d", "#5e4959"]
        updated.sections = []
        for s_idx, sec in enumerate(take["plannedSections"]):
            sb = max(0.0, (int(sec["startBar"]) - 1) * bpb)
            eb = max(sb + bpb, int(sec["endBar"]) * bpb)
            updated.sections.append(
                SectionMarker(
                    id=make_id("sec"),
                    name=str(sec["name"])[:64],
                    startBeats=sb,
                    endBeats=eb,
                    color=sec_colors[s_idx % len(sec_colors)],
                )
            )

    for t in updated.takes:
        if t.get("id") == take_id:
            t["status"] = "applied"
            t["appliedAt"] = utc_now_iso()
            take = t
            break

    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"Take 적용됨: {take.get('title', take_id)}",
            "project": saved.model_dump(),
        },
    )
    event_bus.publish("take.applied", {"projectId": project_id, "take": take})
    return {
        "applied": True,
        "applyMode": apply_mode,
        "createdTrackIds": created_track_ids,
        "createdClipIds": created_clip_ids,
        "take": take,
        "project": saved.model_dump(),
        "revision": saved.revision,
    }
