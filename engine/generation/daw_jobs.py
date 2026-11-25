"""Background single-worker Generation Job Manager, Safe Take Apply & Revision/Concurrency Protection (Phase 03.1 + 04).

Fixes ALL 4 Phase 03 `apply_take()` flaws (Section 7) and enforces Sections 3.1, 10, 15, and 16:
1. Never silently substitutes local MIDI when user explicitly requests `yue2-native`, `ace-step-local`, or `neural_audio`.
2. True process-group cancellation (`SIGTERM` -> `SIGKILL`) via `process_guard`; cancelled jobs NEVER flip to `ready_for_preview`.
3. `apply_take()` cleanly distinguishes `add` (`new_tracks`), `replace_range` (`selected_range`), `alternative_take`,
   `extend`, `new_project`, and `keep_take`:
   - `replace_range` ACTUALLY splits/trims/replaces ONLY `[startBeats, endBeats]` on target track(s) with zero overlapping old clips!
   - NEVER clobbers an existing MIDI track's `instrumentRef`.
   - Stem separation records `sourceTrackId`/`parentSourceAssetId`/`separationModel`/`separationJobId` and mutes ONLY `sourceTrackId`.
   - NEVER wipes existing section markers unless explicitly requested or project is empty.
4. Concurrent-edit safe Revision protection (TEST E):
   - Records `baseRevision` and per-track fingerprints when generation starts.
   - If the user edited an UNRELATED track while AI was generating, merges safely onto latest revision preserving user's edit!
   - Prevents accidental duplicate apply of the same Take unless `force_reapply=True`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any

import soundfile as sf

from engine.composition.schemas import CompositionPlan, QualityReport, Take, TakeArtifact, TakeProvenance
from engine.daw_workspace import commands, loudness, proposals, store
from engine.daw_workspace.schema import Clip, MidiNote, Project, SectionMarker, Track, make_id, utc_now_iso
from engine.daw_workspace.session import event_bus
from engine.generation.process_guard import GenerationCancelledError

from .adapters import (
    execute_local_composition,
    probe_acestep,
    probe_demucs,
    probe_yue2,
    run_yue2_generation,
    separate_stems_demucs,
)


def track_fingerprint(track: Track) -> str:
    payload = json.dumps(track.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def snapshot_track_fingerprints(project: Project) -> dict[str, str]:
    return {t.id: track_fingerprint(t) for t in project.tracks}


def _carve_out_range_on_track(
    project: Project,
    track_id: str,
    start_beats: float,
    end_beats: float,
) -> Project:
    """Non-destructively split & remove ONLY `[start_beats, end_beats]` on `track_id`, preserving everything outside!"""
    updated = deepcopy(project)
    trk = next((t for t in updated.tracks if t.id == track_id), None)
    if not trk:
        return updated

    # Snapshot clips to inspect before mutating
    orig_clips = list(trk.clips)
    for clp in orig_clips:
        c0 = clp.timelineStartBeats
        c1 = clp.timelineStartBeats + clp.durationBeats
        # Completely outside replacement range -> preserve untouched!
        if c1 <= start_beats + 1e-4 or c0 >= end_beats - 1e-4:
            continue
        # Completely inside replacement range -> delete only this clip
        if c0 >= start_beats - 1e-4 and c1 <= end_beats + 1e-4:
            updated = commands.apply_command(updated, "clip.delete", {"clipId": clp.id})
            continue
        # Spans across BOTH start_beats and end_beats -> split at start_beats, split middle at end_beats, delete middle!
        if c0 < start_beats - 0.05 and c1 > end_beats + 0.05:
            mid_id = make_id("clp")
            tail_id = make_id("clp")
            updated = commands.apply_command(
                updated, "clip.split", {"clipId": clp.id, "splitBeat": start_beats, "rightClipId": mid_id}
            )
            updated = commands.apply_command(
                updated, "clip.split", {"clipId": mid_id, "splitBeat": end_beats, "rightClipId": tail_id}
            )
            updated = commands.apply_command(updated, "clip.delete", {"clipId": mid_id})
            continue
        # Overlaps the LEFT edge (c0 < start_beats < c1 <= end_beats) -> split at start_beats and delete right piece
        if c0 < start_beats - 0.05 < c1:
            right_id = make_id("clp")
            updated = commands.apply_command(
                updated, "clip.split", {"clipId": clp.id, "splitBeat": start_beats, "rightClipId": right_id}
            )
            updated = commands.apply_command(updated, "clip.delete", {"clipId": right_id})
            continue
        # Overlaps the RIGHT edge (start_beats <= c0 < end_beats < c1) -> split at end_beats and delete left piece
        if c0 < end_beats - 0.05 < c1:
            right_id = make_id("clp")
            updated = commands.apply_command(
                updated, "clip.split", {"clipId": clp.id, "splitBeat": end_beats, "rightClipId": right_id}
            )
            updated = commands.apply_command(updated, "clip.delete", {"clipId": clp.id})
            continue
    return updated


class GenerationJobManager:
    """Single-worker background job queue with true process cancellation, logs, retry & SSE updates."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daw-gen")
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._retry_specs: dict[str, dict[str, Any]] = {}

    def _emit_job(self, job: dict[str, Any]) -> None:
        event_bus.publish("generation.job.updated", {"projectId": job["projectId"], "job": dict(job)})

    def _update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[job_id]
            # Never allow a cancelled job to transition back to ready/applied!
            if job["status"] == "cancelled" and fields.get("status") in ("ready_for_preview", "applied", "generating", "decoding", "validating_quality"):
                return dict(job)
            job.update(fields)
            job["updatedAt"] = utc_now_iso()
            snap = dict(job)
        self._emit_job(snap)
        return snap

    def _append_log(self, job_id: str, stage: str, progress: int, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] == "cancelled" and stage != "cancelled":
                return
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
                job["logs"].append({"at": utc_now_iso(), "stage": "cancelled", "message": "Cancelled by user (process termination requested)"})
                job["updatedAt"] = utc_now_iso()
            snap = dict(job)
        self._emit_job(snap)
        return snap

    def retry_job(self, job_id: str, sync: bool = False) -> dict[str, Any]:
        with self._lock:
            spec = self._retry_specs.get(job_id)
        if not spec:
            raise FileNotFoundError(f"Retry metadata not available for job: {job_id}")
        if spec["kind"] == "composition":
            plan = CompositionPlan.model_validate(spec["plan"])
            return self.start_composition_job(
                project_id=spec["projectId"],
                plan=plan,
                engine_choice=spec["engineChoice"],
                seed=spec.get("seed"),
                sync=sync,
            )
        raise ValueError(f"Retry not supported for job kind: {spec['kind']}")

    def start_composition_job(
        self,
        project_id: str,
        plan: CompositionPlan,
        engine_choice: str = "auto",
        seed: int | None = None,
        sync: bool = False,
        production_mode: str | None = None,
    ) -> dict[str, Any]:
        """Queue (or run synchronously) a generation job with strict engine honesty (Section 3.1)."""
        resolved_prod_mode = production_mode or str(plan.generationStrategy.get("productionMode") or "")

        # STRICT HONESTY GATE (Section 3.1): NEVER silently run MIDI when user explicitly requested Neural Audio / YuE2 / ACE-Step!
        if engine_choice == "yue2-native":
            yue = probe_yue2()
            if not yue["available"]:
                return {
                    "engineUnavailable": True,
                    "requestedEngine": "yue2-native",
                    "state": yue["state"],
                    "missingItems": yue.get("missingItems", []),
                    "suggestedAlternative": "local-multitrack-composer",
                    "messageKo": yue["statusNoteKo"] + " 편집 가능한 MIDI 세션으로 생성하려면 제작 방식을 '편집 가능 MIDI'로 선택하세요.",
                    "messageEn": yue["statusNoteEn"] + " Switch explicitly to Editable MIDI if you want synthesized MIDI tracks instead.",
                }
        elif engine_choice == "ace-step-local":
            ace = probe_acestep()
            if not ace["available"]:
                return {
                    "engineUnavailable": True,
                    "requestedEngine": "ace-step-local",
                    "state": ace["state"],
                    "missingItems": ace.get("missingItems", []),
                    "suggestedAlternative": "local-multitrack-composer",
                    "messageKo": ace["statusNoteKo"] + " ACE-Step 미설치 상태에서 자체 MIDI로 몰래 대체하지 않습니다.",
                    "messageEn": ace["statusNoteEn"] + " Refusing to silently substitute local MIDI when ACE-Step was requested.",
                }
        elif engine_choice == "neural_audio" or resolved_prod_mode == "neural_audio":
            yue = probe_yue2()
            ace = probe_acestep()
            if yue["available"]:
                engine_choice = "yue2-native"
            elif ace["available"]:
                engine_choice = "ace-step-local"
            else:
                return {
                    "engineUnavailable": True,
                    "requestedEngine": "neural_audio",
                    "state": yue["state"],
                    "missingItems": yue.get("missingItems", []),
                    "suggestedAlternative": "editable_midi",
                    "messageKo": "신경망 오디오 엔진(YuE2 / ACE-Step)이 현재 환경에 설치되어 있지 않습니다. 가짜 신경망 오디오를 만들지 않으며, 원하시면 '편집 가능 MIDI' 모드로 전환해 제작할 수 있습니다.",
                    "messageEn": "No neural audio engine (YuE2 / ACE-Step) is installed locally. Switch explicitly to Editable MIDI to compose MIDI tracks instead.",
                }
        elif engine_choice == "auto" and plan.mode == "full_music":
            # Prefer real YuE2 when actually ready/verified; otherwise execute explicitly-labeled local-multitrack-composer
            if probe_yue2()["available"]:
                engine_choice = "yue2-native"

        # Capture baseRevision & track fingerprints BEFORE generation starts (Section 15 concurrent edit safety!)
        save_composition_plan(project_id, plan)
        snap_proj = store.load_project(project_id)
        base_rev = snap_proj.revision
        base_fps = snapshot_track_fingerprints(snap_proj)

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
            "baseRevision": base_rev,
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
            self._retry_specs[job_id] = {
                "kind": "composition",
                "projectId": project_id,
                "plan": plan.model_dump(),
                "engineChoice": engine_choice,
                "seed": actual_seed,
            }
        self._emit_job(job_record)

        def runner() -> dict[str, Any]:
            try:
                proj = store.load_project(project_id)
                if cancel_ev.is_set():
                    raise GenerationCancelledError("Generation cancelled before execution")

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

                if engine_choice == "yue2-native":
                    self._update(job_id, status="generating", stage="generating", progress=35)
                    self._append_log(job_id, "generating", 40, "Running native YuE2 synthesis (yue-plan gate + yue-synth)")
                    out_wav = take_dir / "preview.wav"
                    yue_res = run_yue2_generation(plan, out_wav, seed=actual_seed, cancel_event=cancel_ev)
                    audio, sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
                    loud = loudness.measure_loudness(audio, sr)
                    lvl_gain = round(max(-12.0, min(12.0, -16.0 - float(loud["integratedLufs"]))), 2)
                    vocal_sc = yue_res["vocalScreening"]
                    warn_list: list[str] = []
                    if vocal_sc.get("status") == "REJECT":
                        warn_list.append("Vocal leakage REJECTED — do not approve as instrumental.")
                    elif vocal_sc.get("status") == "UNCERTAIN":
                        warn_list.append("Vocal screening UNCERTAIN — manual listening required before instrumental approval.")
                    verdict = "fail" if vocal_sc.get("status") == "REJECT" else ("warn" if warn_list else "pass")
                    take = Take(
                        id=take_id,
                        projectId=project_id,
                        jobId=job_id,
                        planId=plan.id,
                        title=f"{plan.musicalIdentity.get('title', 'YuE2')} (YuE2 Native)",
                        mode="full_music",
                        status="ready",
                        baseRevision=base_rev,
                        baseTrackFingerprints=base_fps,
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
                            verdict=verdict,  # type: ignore[arg-type]
                            warnings=warn_list,
                        ),
                        provenance=TakeProvenance(
                            engine="yue2-native",
                            engineLabel="YuE2 Native Audio Generator",
                            mode="full_music",
                            providerId=str(plan.providerProvenance.get("providerId") or "local-music-director"),
                            model="YuE2-3B-Q8_0",
                            seed=actual_seed,
                            planId=plan.id,
                            referenceIds=list(plan.referenceBinding.referenceIds),
                        ),
                    )
                else:
                    def cb(stage: str, pct: int, msg: str) -> None:
                        if cancel_ev.is_set():
                            raise GenerationCancelledError("Cancelled by user")
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
                    take.baseRevision = base_rev
                    take.baseTrackFingerprints = base_fps

                if cancel_ev.is_set():
                    raise GenerationCancelledError("Cancelled before persisting take")

                persist_take(project_id, take)
                self._update(job_id, status="ready_for_preview", stage="ready_for_preview", progress=100, takeId=take.id)
                self._append_log(job_id, "ready_for_preview", 100, f"Take ready for preview ({take.title})")
                event_bus.publish("take.created", {"projectId": project_id, "take": take.model_dump()})
                return take.model_dump()
            except Exception as exc:
                msg = str(exc)
                is_cancel = isinstance(exc, GenerationCancelledError) or cancel_ev.is_set() or "cancelled" in msg.lower()
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
        source_track_id: str | None = None,
        model_name: str = "htdemucs",
        sync: bool = False,
    ) -> dict[str, Any]:
        """Run real Demucs stem separation recording exact `sourceTrackId` (Section 10 · TEST D)."""
        demucs_info = probe_demucs()
        if not demucs_info["available"]:
            return {
                "available": False,
                "state": demucs_info["state"],
                "error": demucs_info["statusNoteEn"],
                "messageKo": demucs_info["statusNoteKo"],
                "messageEn": demucs_info["statusNoteEn"],
            }

        proj = store.load_project(project_id)
        asset, abs_path = store.resolve_asset_file(project_id, asset_id)
        if asset.kind == "midi":
            raise ValueError("Stem separation requires an audio asset, not MIDI")

        # Resolve exact sourceTrackId so apply_take ONLY mutes this source track (never other tracks!)
        resolved_src_trk = source_track_id
        if not resolved_src_trk:
            for trk in proj.tracks:
                if any(c.assetId == asset_id for c in trk.clips):
                    resolved_src_trk = trk.id
                    break

        base_rev = proj.revision
        base_fps = snapshot_track_fingerprints(proj)
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
            "baseRevision": base_rev,
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
                cur_proj = store.load_project(project_id)
                pdir = store.project_dir(project_id)
                take_dir = pdir / "takes" / take_id
                stems = separate_stems_demucs(abs_path, take_dir, model_name=model_name, cancel_event=cancel_ev)
                if cancel_ev.is_set():
                    raise GenerationCancelledError("Stem separation cancelled")
                dur_beats = round((asset.durationSec or 16.0) / (60.0 / cur_proj.bpm), 2)
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
                    baseRevision=base_rev,
                    baseTrackFingerprints=base_fps,
                    sourceTrackId=resolved_src_trk,
                    parentSourceAssetId=asset_id,
                    separationModel=model_name,
                    separationJobId=job_id,
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
                is_cancel = isinstance(exc, GenerationCancelledError) or cancel_ev.is_set()
                self._update(job_id, status="cancelled" if is_cancel else "failed", stage="cancelled" if is_cancel else "failed", error=None if is_cancel else str(exc))
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
    proj.takes = existing[-30:]
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
    # Record rejection into Project Music Memory
    mem = dict(proj.musicMemory or {})
    rej = list(mem.get("rejectedTakes") or [])
    rej.append({"takeId": take_id, "title": target.get("title"), "at": utc_now_iso()})
    mem["rejectedTakes"] = rej[-15:]
    proj.musicMemory = mem
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return target, saved.revision


def _normalize_apply_mode(raw: str) -> str:
    aliases = {
        "new_tracks": "add",
        "add": "add",
        "selected_range": "replace_range",
        "replace_range": "replace_range",
        "alternative_take": "alternative_take",
        "extend": "extend",
        "new_project": "new_project",
        "keep_take": "keep_take",
    }
    if raw not in aliases:
        raise ValueError(f"Unsupported applyMode '{raw}'. Allowed: {sorted(set(aliases.values()))}")
    return aliases[raw]


def apply_take(
    project_id: str,
    take_id: str,
    apply_mode: str = "add",
    target_track_id: str | None = None,
    start_beats: float | None = None,
    add_section_markers: bool = False,
    replace_sections: bool = False,
    expected_revision: int | None = None,
    force_reapply: bool = False,
) -> dict[str, Any]:
    """Transactionally apply a Take with fixed range replacement, stem isolation & concurrent-edit preservation."""
    mode = _normalize_apply_mode(apply_mode)
    proj = store.load_project(project_id)

    take = next((t for t in proj.takes if t.get("id") == take_id), None)
    if not take:
        raise FileNotFoundError(f"Take not found: {take_id}")

    # Duplicate-apply protection (Section 15)
    if take.get("status") == "applied" and not force_reapply and mode not in ("new_project", "alternative_take"):
        raise ValueError(f"Take {take_id} has already been applied (pass forceReapply=true to apply again).")

    # Concurrent edit & revision check (Section 15 / TEST E):
    # Allow safe merge if ONLY UNRELATED tracks changed while AI was generating!
    resolved_target_trk = target_track_id or take.get("targetTrackId")
    base_fps: dict[str, str] = dict(take.get("baseTrackFingerprints") or {})
    concurrent_merge = False
    preserved_concurrent_tracks: list[str] = []

    if expected_revision is not None and proj.revision != expected_revision:
        target_modified = False
        for trk in proj.tracks:
            old_fp = base_fps.get(trk.id)
            cur_fp = track_fingerprint(trk)
            if old_fp and old_fp != cur_fp:
                if resolved_target_trk and trk.id == resolved_target_trk and mode == "replace_range":
                    target_modified = True
                else:
                    preserved_concurrent_tracks.append(trk.name)
        if target_modified:
            raise store.RevisionConflictError(expected_revision, proj.revision, proj)
        concurrent_merge = True

    if mode == "keep_take":
        take["status"] = "kept"
        saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
        return {"applied": False, "status": "kept", "take": take, "project": saved.model_dump()}

    pdir = store.project_dir(project_id).resolve()

    if mode == "new_project":
        plan = next((p for p in proj.compositionPlans if p.get("id") == take.get("planId")), None)
        new_bpm = float(plan["musicalIdentity"]["tempoBpm"]) if plan and plan.get("musicalIdentity", {}).get("tempoBpm") else proj.bpm
        new_proj = store.create_project(
            name=str(take.get("title") or "AI Composition"),
            bpm=new_bpm,
            with_default_tracks=False,
        )
        new_pdir = store.project_dir(new_proj.id).resolve()
        src_take_dir = pdir / "takes" / take_id
        dst_take_dir = new_pdir / "takes" / take_id
        if src_take_dir.is_dir():
            shutil.copytree(src_take_dir, dst_take_dir, dirs_exist_ok=True)
        cloned_take = deepcopy(take)
        cloned_take["status"] = "ready"
        new_proj.takes = [cloned_take]
        if plan:
            new_proj.compositionPlans = [deepcopy(plan)]
        store.save_project(new_proj, clear_autosave=False, expected_revision=new_proj.revision)
        res = apply_take(new_proj.id, take_id, apply_mode="add", add_section_markers=True, replace_sections=True)
        res["createdNewProject"] = True
        return res

    # Record ONE atomic Undo snapshot BEFORE any project mutation (preserving latest concurrent edits!)
    pre_apply_snapshot = deepcopy(proj)
    proposals.record_undo_snapshot(pre_apply_snapshot)

    # Import artifact files as immutable assets (rollback on failure)
    imported_assets: dict[int, str] = {}
    newly_created_files: list[Path] = []
    try:
        for idx, art in enumerate(take.get("artifacts", [])):
            rel = art.get("midiRelativePath") if art.get("trackType") == "midi" else art.get("audioRelativePath")
            if rel:
                abs_f = (pdir / rel).resolve()
                if abs_f.is_relative_to(pdir) and abs_f.is_file():
                    before_ids = {a.id for a in store.load_project(project_id).assets}
                    asset, _ = store.import_asset_bytes(
                        project_id=project_id,
                        filename=abs_f.name,
                        raw_bytes=abs_f.read_bytes(),
                        kind_hint="midi" if art.get("trackType") == "midi" else "audio",
                        source=take.get("provenance", {}).get("engine", "ai-composition"),
                        provenance=f"Take {take_id} ({take.get('title', '')})",
                    )
                    imported_assets[idx] = asset.id
                    if asset.id not in before_ids:
                        newly_created_files.append((pdir / asset.relativePath).resolve())

        proj = store.load_project(project_id)
        updated = proj
        bpb = updated.timeSignature.beats_per_bar
        created_track_ids: list[str] = []
        created_clip_ids: list[str] = []
        created_lane_ids: list[str] = []

        # FIX BUG #3 (Section 7 & Section 10 / TEST D):
        # Stem separation mutes ONLY the exact `sourceTrackId` — NEVER unrelated audio tracks!
        if take.get("mode") == "stem_separation":
            src_tid = take.get("sourceTrackId")
            if not src_tid and take.get("parentSourceAssetId"):
                for trk in updated.tracks:
                    if any(c.assetId == take["parentSourceAssetId"] for c in trk.clips):
                        src_tid = trk.id
                        break
            if src_tid:
                src_track = next((t for t in updated.tracks if t.id == src_tid), None)
                if src_track and not src_track.mute:
                    updated = commands.apply_command(updated, "track.setMute", {"trackId": src_tid, "mute": True})

        # Align BPM ONLY if full_music take is applied to a brand-new empty project
        plan = next((p for p in updated.compositionPlans if p.get("id") == take.get("planId")), None)
        is_empty_timeline = not any(t.clips for t in updated.tracks)
        if take.get("mode") == "full_music" and plan and is_empty_timeline:
            plan_bpm = plan.get("musicalIdentity", {}).get("tempoBpm")
            if plan_bpm:
                updated = commands.apply_command(updated, "project.setTempo", {"bpm": float(plan_bpm)})

        for idx, art in enumerate(take.get("artifacts", [])):
            art_dur = float(art.get("durationBeats", 16.0))
            art_type = str(art.get("trackType", "midi"))
            asset_id = imported_assets.get(idx)

            # Determine placement beat cleanly per apply mode
            if mode == "extend":
                target_trk_obj = next((t for t in updated.tracks if t.id == resolved_target_trk), None)
                if target_trk_obj and target_trk_obj.clips:
                    art_start = max(c.timelineStartBeats + c.durationBeats for c in target_trk_obj.clips)
                else:
                    art_start = max((c.timelineStartBeats + c.durationBeats for t in updated.tracks for c in t.clips), default=0.0)
            else:
                art_start = float(start_beats if start_beats is not None else art.get("startBeats", 0.0))

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
                "id": make_id("clp"),
                "name": art.get("name", "AI Clip"),
                "type": "midi" if art_type == "midi" else "audio",
                "assetId": asset_id,
                "timelineStartBeats": round(art_start, 4),
                "durationBeats": round(art_dur, 4),
                "sourceOffsetSec": 0.0,
                "sourceDurationSec": round(art_dur * (60.0 / updated.bpm), 3),
                "loop": False,
                "loopLengthSec": None,
                "loopLengthBeats": art_dur if art_type == "midi" else None,
                "gainDb": 0.0,
                "fadeInBeats": 0.0,
                "fadeOutBeats": 0.0,
                "reversed": False,
                "notes": notes_list,
            }

            # MODE: ALTERNATIVE TAKE -> Store non-destructively in target Track's `takeLanes` (NEVER double-plays!)
            if mode == "alternative_take" and resolved_target_trk:
                existing_trk = next((t for t in updated.tracks if t.id == resolved_target_trk), None)
                if existing_trk and ((existing_trk.type == "midi") == (art_type == "midi")):
                    lane_id = make_id("lane")
                    lane_obj = {
                        "id": lane_id,
                        "takeId": take_id,
                        "name": str(take.get("title") or art.get("name") or f"Take {len(existing_trk.takeLanes) + 2}"),
                        "startBeats": round(art_start, 4),
                        "endBeats": round(art_start + art_dur, 4),
                        "clip": clip_payload,
                        "previewRelativePath": take.get("previewRelativePath"),
                        "levelMatchedGainDb": take.get("levelMatchedGainDb", 0.0),
                        "active": False,
                        "createdAt": utc_now_iso(),
                    }
                    updated = commands.apply_command(
                        updated,
                        "track.addTakeLane",
                        {"trackId": existing_trk.id, "lane": lane_obj},
                    )
                    created_lane_ids.append(lane_id)
                    continue

            # MODE: REPLACE_RANGE -> FIX BUG #1 & #2: carve out ONLY `[art_start, art_start + art_dur]`
            # and NEVER overwrite existing track's `instrumentRef`!
            dst_track_id: str | None = None
            if mode in ("replace_range", "extend") and resolved_target_trk:
                existing_trk = next((t for t in updated.tracks if t.id == resolved_target_trk), None)
                if existing_trk and ((existing_trk.type == "midi") == (art_type == "midi")):
                    dst_track_id = existing_trk.id
                    if mode == "replace_range":
                        # Save original range clips into an automatic "Original Backup" Take Lane before replacing!
                        orig_in_range = [
                            c.model_dump()
                            for c in existing_trk.clips
                            if (c.timelineStartBeats + c.durationBeats) > art_start + 1e-4
                            and c.timelineStartBeats < (art_start + art_dur) - 1e-4
                        ]
                        if orig_in_range and not any(ln.get("isOriginalBackup") and ln.get("startBeats") == round(art_start, 4) for ln in existing_trk.takeLanes):
                            updated = commands.apply_command(
                                updated,
                                "track.addTakeLane",
                                {
                                    "trackId": dst_track_id,
                                    "lane": {
                                        "id": make_id("lane"),
                                        "takeId": None,
                                        "name": f"Original ({int(art_start // bpb) + 1}–{int((art_start + art_dur - 0.01) // bpb) + 1}마디)",
                                        "startBeats": round(art_start, 4),
                                        "endBeats": round(art_start + art_dur, 4),
                                        "clips": orig_in_range,
                                        "isOriginalBackup": True,
                                        "active": False,
                                    },
                                },
                            )
                        updated = _carve_out_range_on_track(updated, dst_track_id, art_start, art_start + art_dur)
                    # Only assign instrumentRef if track currently has NONE (NEVER clobber user's voice!)
                    if art_type == "midi" and not existing_trk.instrumentRef and art.get("instrumentRef"):
                        updated = commands.apply_command(
                            updated,
                            "track.setInstrument",
                            {"trackId": dst_track_id, "instrumentRef": art["instrumentRef"]},
                        )

            if not dst_track_id:
                dst_track_id = make_id("trk")
                stem_meta = (
                    {
                        "parentSourceAssetId": take.get("parentSourceAssetId"),
                        "sourceTrackId": take.get("sourceTrackId"),
                        "separationModel": take.get("separationModel"),
                        "separationJobId": take.get("separationJobId"),
                        "stemRole": art.get("role"),
                    }
                    if art_type == "stem"
                    else None
                )
                updated = commands.apply_command(
                    updated,
                    "track.add",
                    {
                        "id": dst_track_id,
                        "name": art.get("name", f"AI {art.get('role', 'Track')}"),
                        "type": art_type if art_type in ("audio", "stem", "midi") else "midi",
                        "color": art.get("color", "#648ea8"),
                        "stemLabel": art.get("role") if art_type == "stem" else None,
                        "stemMeta": stem_meta,
                        "instrumentRef": art.get("instrumentRef") if art_type == "midi" else None,
                    },
                )
                if art.get("gainDb") is not None:
                    updated = commands.apply_command(updated, "track.setGain", {"trackId": dst_track_id, "gainDb": float(art["gainDb"])})
                if art.get("pan") is not None:
                    updated = commands.apply_command(updated, "track.setPan", {"trackId": dst_track_id, "pan": float(art["pan"])})
                created_track_ids.append(dst_track_id)

            updated = commands.apply_command(updated, "clip.add", {"trackId": dst_track_id, "clip": clip_payload})
            created_clip_ids.append(clip_payload["id"])

            end_beats = art_start + art_dur
            if end_beats > updated.lengthBeats:
                updated = commands.apply_command(
                    updated, "project.setLength", {"lengthBeats": float(int((end_beats + 3) // 4) * 4)}
                )

        # FIX BUG #4 (Section 7): NEVER wipe existing sections unless `replace_sections=True` OR project was empty!
        should_write_sections = (
            add_section_markers
            and take.get("mode") == "full_music"
            and take.get("plannedSections")
            and (replace_sections or is_empty_timeline or not updated.sections)
        )
        if should_write_sections:
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
                t["status"] = "applied" if mode != "alternative_take" else "kept"
                t["appliedAt"] = utc_now_iso()
                take = t
                break

        # Record accepted take in Project Music Memory
        mem = dict(updated.musicMemory or {})
        liked = list(mem.get("likedTakes") or [])
        liked.append({"takeId": take_id, "title": take.get("title"), "applyMode": mode, "at": utc_now_iso()})
        mem["likedTakes"] = liked[-20:]
        mem["lastAppliedTakeId"] = take_id
        updated.musicMemory = mem

        saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)
    except Exception:
        # Clean up any orphaned newly imported asset files on failure
        for fpath in newly_created_files:
            if fpath.is_file():
                fpath.unlink(missing_ok=True)
        raise

    event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"Take 적용됨 ({mode}): {take.get('title', take_id)}",
            "project": saved.model_dump(),
        },
    )
    event_bus.publish("take.applied", {"projectId": project_id, "take": take})
    return {
        "applied": True,
        "applyMode": mode,
        "concurrentMergeApplied": concurrent_merge,
        "preservedConcurrentTracks": preserved_concurrent_tracks,
        "createdTrackIds": created_track_ids,
        "createdClipIds": created_clip_ids,
        "createdLaneIds": created_lane_ids,
        "take": take,
        "project": saved.model_dump(),
        "revision": saved.revision,
    }
