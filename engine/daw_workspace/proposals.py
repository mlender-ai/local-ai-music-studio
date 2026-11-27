"""Staged AI Change Proposals, Undo/Redo history, and Provider-Agnostic Command Router."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from engine import paths as engine_paths

from . import commands, store
from .schema import Project, make_id, utc_now_iso
from .session import event_bus

_prop_lock = threading.Lock()


def _proposals_path(project_id: str) -> Path:
    d = engine_paths.DATA / "daw" / "proposals"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{project_id}.json"


def _history_path(project_id: str) -> Path:
    d = engine_paths.DATA / "daw" / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{project_id}.json"


def _atomic_write(path: Path, data: Any) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _load_proposals(project_id: str) -> list[dict[str, Any]]:
    p = _proposals_path(project_id)
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_proposals(project_id: str, items: list[dict[str, Any]]) -> None:
    _atomic_write(_proposals_path(project_id), items[-30:])


def _load_history(project_id: str) -> dict[str, list[dict[str, Any]]]:
    p = _history_path(project_id)
    if not p.is_file():
        return {"undo": [], "redo": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {"undo": list(data.get("undo", [])), "redo": list(data.get("redo", []))}
    except Exception:
        return {"undo": [], "redo": []}


def _save_history(project_id: str, hist: dict[str, list[dict[str, Any]]]) -> None:
    _atomic_write(
        _history_path(project_id),
        {"undo": hist["undo"][-30:], "redo": hist["redo"][-30:]},
    )


def record_undo_snapshot(project: Project) -> None:
    with _prop_lock:
        hist = _load_history(project.id)
        hist["undo"].append(project.model_dump())
        hist["redo"] = []
        _save_history(project.id, hist)


def list_proposals(project_id: str, status: str | None = None) -> list[dict[str, Any]]:
    with _prop_lock:
        items = _load_proposals(project_id)
    if status:
        return [i for i in items if i.get("status") == status]
    return items


def create_proposal(
    project_id: str,
    summary: str,
    operations: list[dict[str, Any]],
    base_revision: int | None = None,
    source_agent: str = "external-agent",
) -> dict[str, Any]:
    """Validate and dry-run operations against current project state without mutating disk yet."""
    if not operations:
        raise ValueError("Proposal must include at least one operation")
    proj = store.load_project(project_id)
    expected_rev = base_revision if base_revision is not None else proj.revision
    if expected_rev != proj.revision:
        raise store.RevisionConflictError(expected_rev, proj.revision, proj)

    # Dry-run every operation to validate bounds & track/clip existence before staging
    simulated = proj
    affected_tracks: set[str] = set()
    affected_clips: set[str] = set()
    for op in operations:
        op_type = str(op.get("type", ""))
        op_payload = dict(op.get("payload", {}))
        simulated = commands.apply_command(simulated, op_type, op_payload)
        if "trackId" in op_payload:
            affected_tracks.add(str(op_payload["trackId"]))
        if "clipId" in op_payload:
            affected_clips.add(str(op_payload["clipId"]))

    track_names = [t.name for t in proj.tracks if t.id in affected_tracks]
    for t in proj.tracks:
        if any(c.id in affected_clips for c in t.clips) and t.name not in track_names:
            track_names.append(t.name)

    proposal = {
        "id": make_id("prop"),
        "projectId": project_id,
        "baseRevision": proj.revision,
        "summary": summary.strip() or f"{len(operations)} staged edit(s)",
        "sourceAgent": source_agent,
        "status": "pending",
        "operations": operations,
        "affectedTracks": track_names,
        "affectedClipIds": sorted(affected_clips),
        "operationCount": len(operations),
        "createdAt": utc_now_iso(),
        "resolvedAt": None,
    }

    with _prop_lock:
        items = _load_proposals(project_id)
        items.append(proposal)
        _save_proposals(project_id, items)

    event_bus.publish("proposal.created", {"projectId": project_id, "proposal": proposal})
    return proposal


def apply_proposal(project_id: str, proposal_id: str) -> tuple[dict[str, Any], Project]:
    """Apply a pending ChangeProposal atomically if baseRevision still matches server revision."""
    with _prop_lock:
        items = _load_proposals(project_id)
        prop = next((i for i in items if i["id"] == proposal_id), None)
        if not prop:
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
        if prop["status"] != "pending":
            raise ValueError(f"Proposal {proposal_id} is already {prop['status']}")

    proj = store.load_project(project_id)
    if proj.revision != prop["baseRevision"]:
        raise store.RevisionConflictError(prop["baseRevision"], proj.revision, proj)

    record_undo_snapshot(proj)

    updated = proj
    for op in prop["operations"]:
        updated = commands.apply_command(updated, str(op["type"]), dict(op.get("payload", {})))

    saved = store.save_project(updated, clear_autosave=False, expected_revision=proj.revision)

    with _prop_lock:
        items = _load_proposals(project_id)
        for item in items:
            if item["id"] == proposal_id:
                item["status"] = "applied"
                item["appliedRevision"] = saved.revision
                item["resolvedAt"] = utc_now_iso()
                prop = item
                break
        _save_proposals(project_id, items)

    event_bus.publish(
        "project.updated",
        {
            "projectId": project_id,
            "revision": saved.revision,
            "reason": f"제안 적용됨: {prop['summary']}",
            "project": saved.model_dump(),
        },
    )
    event_bus.publish("proposal.updated", {"projectId": project_id, "proposal": prop})
    return prop, saved


def reject_proposal(project_id: str, proposal_id: str) -> dict[str, Any]:
    with _prop_lock:
        items = _load_proposals(project_id)
        prop = next((i for i in items if i["id"] == proposal_id), None)
        if not prop:
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
        prop["status"] = "rejected"
        prop["resolvedAt"] = utc_now_iso()
        _save_proposals(project_id, items)

    event_bus.publish("proposal.updated", {"projectId": project_id, "proposal": prop})
    return prop


def undo_project(project_id: str) -> Project:
    proj = store.load_project(project_id)
    with _prop_lock:
        hist = _load_history(project_id)
        if not hist["undo"]:
            raise ValueError("Nothing to undo on server history")
        prev_dict = hist["undo"].pop()
        hist["redo"].append(proj.model_dump())
        _save_history(project_id, hist)

    restored = Project.model_validate(store.migrate_project_dict(prev_dict))
    saved = store.save_project(restored, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": "Undo", "project": saved.model_dump()},
    )
    return saved


def redo_project(project_id: str) -> Project:
    proj = store.load_project(project_id)
    with _prop_lock:
        hist = _load_history(project_id)
        if not hist["redo"]:
            raise ValueError("Nothing to redo on server history")
        next_dict = hist["redo"].pop()
        hist["undo"].append(proj.model_dump())
        _save_history(project_id, hist)

    restored = Project.model_validate(store.migrate_project_dict(next_dict))
    saved = store.save_project(restored, clear_autosave=False, expected_revision=proj.revision)
    event_bus.publish(
        "project.updated",
        {"projectId": project_id, "revision": saved.revision, "reason": "Redo", "project": saved.model_dump()},
    )
    return saved


# --- Provider-Agnostic Korean / English Supported Command Interpreter ---

TRACK_ALIASES: list[tuple[list[str], list[str]]] = [
    (["드럼", "drum", "drums"], ["drum"]),
    (["베이스", "bass"], ["bass"]),
    (["기타", "건반", "guitar", "keys"], ["guitar", "keys"]),
    (["신스", "synth", "미디", "midi"], ["synth", "midi"]),
    (["텍스처", "texture", "패드", "pad", "fx"], ["texture", "pad", "fx"]),
]


def _match_track(project: Project, text: str, selected_track_id: str | None):
    low = text.lower()
    for trk in project.tracks:
        if trk.name.lower() in low:
            return trk
    for keywords, hints in TRACK_ALIASES:
        if any(kw in low for kw in keywords):
            for trk in project.tracks:
                if any(h in trk.name.lower() for h in hints):
                    return trk
    if selected_track_id:
        return next((t for t in project.tracks if t.id == selected_track_id), None)
    return None


def interpret_producer_instruction(
    project: Project,
    instruction: str,
    selection: dict[str, Any] | None = None,
    active_reference_id: str | None = None,
) -> dict[str, Any]:
    """Deterministically route ONLY genuinely supported DAW commands into staged proposals.

    Refuses unsupported composition/FX requests honestly without fabricating results.
    """
    text = instruction.strip()
    low = text.lower()
    sel = selection or {}
    sel_track_id = sel.get("selectedTrackId")
    sel_clip_ids = sel.get("selectedClipIds") or []
    bpb = project.timeSignature.beats_per_bar

    # Reject ONLY genuinely unsupported future-phase capabilities honestly!
    # Phase 05 EQ, Compressor, Sidechain, Reverb, Delay, Guitar Amp, Saturation, Chorus, Automation & Pro Instruments are NOW LIVE!
    unsupported_patterns = [
        (["보컬 생성", "가사 노래", "노래 불러", "vocal singing", "sing lyrics"], "Phase 07 (Full Vocal Production)"),
        (["자동 마스터링", "ai 마스터링", "auto mastering"], "Phase 06 (AI Mastering Suite)"),
    ]
    # Allow "구간 만들어줘" / "브리지 만들어줘" as section creation!
    is_section_req = any(k in low for k in ("구간", "브리지", "브릿지", "섹션", "section", "bridge", "chorus", "intro", "outro"))
    for kws, phase_label in unsupported_patterns:
        if any(k in low for k in kws) and not (is_section_req and "만들어" in low):
            return {
                "supported": False,
                "action": "unsupported",
                "messageKo": f"요청하신 기능은 현재 지원되지 않습니다 ({phase_label} 예정). 현재는 AI 작곡, 레퍼런스 정밀 채보, 가상악기·프리셋 변경, EQ/컴프레서/사이드체인/리버브/딜레이/앰프 FX, 오토메이션 및 클립 편집을 지원합니다.",
                "messageEn": f"This request is not supported yet (scheduled for {phase_label}). Currently supported: AI composition, precision transcription, Pro Instruments, EQ/Compressor/Sidechain/Reverb/Delay/Amp FX, Automation, and clip editing.",
            }

    # 0.0 Phase 05 / 05.1 AI Producer Routing Order Guard:
    # NEVER let full-music or reference-conditioned composition prompts ("세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘",
    # "인디 록 만들어줘", "이 레퍼런스처럼 따뜻하고 감각적인 음악 만들어줘") get hijacked by single-track Sound Design!
    is_new_music_compose = (
        any(
            k in low
            for k in (
                "인스트루멘털",
                "인스트루멘탈",
                "instrumental",
                "풀 트랙 만들어",
                "곡을 만들어",
                "곡 만들어",
                "음악 만들어",
                "음악을 만들어",
                "새 곡",
                "트랙 만들어",
                "트랙을 만들어",
                "인디 록 만들어",
                "인디록 만들어",
                "하우스 만들어",
                "힙합 만들어",
                "r&b",
                "알앤비",
                "네오소울",
                "full track",
                "compose a song",
                "make a track",
                "make music",
            )
        )
        and any(k in low for k in ("만들어", "작곡", "생성", "compose", "generate", "make", "create"))
        and not any(k in low for k in ("소리만", "리듬은 그대로", "멜로디는 유지", "먹먹", "이큐", "eq", "컴프", "사이드체인", "필터"))
    )
    if not is_new_music_compose:
        from engine.sound_design import plan_sound_design_operations

        sd_plan = plan_sound_design_operations(
            project,
            text,
            selection=sel,
            active_reference_id=active_reference_id,
        )
        if sd_plan and sd_plan.get("matched"):
            if sd_plan.get("operations"):
                return {
                    "supported": True,
                    "action": "stage_proposal",
                    "soundDesignIntent": sd_plan["intent"],
                    "diagnosis": sd_plan.get("diagnosis"),
                    "soundDesignPlan": sd_plan.get("soundDesignPlan"),
                    "preservedNote": sd_plan.get("preservedNote"),
                    "summary": sd_plan["summary"],
                    "operations": sd_plan["operations"],
                    "messageKo": f"음향 진단 기반 프로덕션 변경 제안을 생성했습니다: {sd_plan['summary']} ({sd_plan.get('preservedNote', '')})",
                    "messageEn": f"Staged acoustic sound design proposal: {sd_plan['summary']}",
                }
            if sd_plan.get("noOpExplanationKo"):
                return {
                    "supported": True,
                    "action": "sound_design_advisory",
                    "soundDesignIntent": sd_plan["intent"],
                    "diagnosis": sd_plan.get("diagnosis"),
                    "soundDesignPlan": sd_plan.get("soundDesignPlan"),
                    "messageKo": sd_plan["noOpExplanationKo"],
                    "messageEn": sd_plan.get("noOpExplanationEn") or sd_plan["noOpExplanationKo"],
                }

    # 0. Phase 03.2 Advanced Reference Intelligence routing (Transcription, Chords, Reconstruct, Feature-Locked Compose)
    default_ref_id = active_reference_id or (project.references[0]["id"] if project.references else None)

    # 0.1 Precision Transcription request
    if any(k in low for k in ("정밀 채보", "채보", "어떤 악기", "악기 분석", "스템 분석", "transcribe", "transcription")):
        if not default_ref_id:
            return {
                "supported": False,
                "action": "no_reference",
                "messageKo": "정밀 채보할 레퍼런스가 없습니다. 좌측 브라우저 '레퍼런스' 탭에서 오디오 파일을 먼저 가져오세요.",
                "messageEn": "No reference found to transcribe. Import an audio file in the References tab first.",
            }
        return {
            "supported": True,
            "action": "transcribe_reference",
            "referenceId": default_ref_id,
            "messageKo": "Demucs 스템 분리 + Basic Pitch ONNX + 코드·드럼 정밀 채보를 실행합니다.",
            "messageEn": "Running precision transcription (Demucs + Basic Pitch ONNX + Drum/Chord analysis).",
        }

    # 0.2 Import Reference Chord Track only
    if (
        any(k in low for k in ("코드 진행만", "코드만 가져", "코드 트랙으로", "코드 가져와", "import chords", "import chord track"))
        and not any(k in low for k in ("만들어", "작곡", "생성", "compose", "generate"))
    ):
        if not default_ref_id:
            return {
                "supported": False,
                "action": "no_reference",
                "messageKo": "코드를 가져올 레퍼런스가 없습니다.",
                "messageEn": "No reference available to import chords from.",
            }
        return {
            "supported": True,
            "action": "import_reference_chords",
            "referenceId": default_ref_id,
            "messageKo": "레퍼런스에서 추출한 코드 진행을 타임라인 Chord Track으로 가져옵니다.",
            "messageEn": "Importing extracted reference chord progression into the Timeline Chord Track.",
        }

    # 0.3 Mode A: Reconstruct Reference to editable MIDI/Stem session
    if any(k in low for k in ("midi 세션으로 재구성", "세션으로 재구성", "미디 세션으로", "세션 재구성", "재구성해줘", "재구성 해줘", "reconstruct")):
        if not default_ref_id:
            return {
                "supported": False,
                "action": "no_reference",
                "messageKo": "세션으로 재구성할 레퍼런스가 없습니다. 먼저 레퍼런스 오디오를 가져오세요.",
                "messageEn": "No reference found to reconstruct. Import a reference audio file first.",
            }
        return {
            "supported": True,
            "action": "reconstruct_reference",
            "referenceId": default_ref_id,
            "messageKo": "레퍼런스 분석·채보 결과를 편집 가능한 MIDI 세션 + Chord Track으로 재구성합니다.",
            "messageEn": "Reconstructing reference transcription into an editable MIDI session & Chord Track.",
        }

    # 0.4 Reference-Conditioned Composition / Reinterpretation with parsed Feature Locks
    is_ref_compose_req = (
        any(k in low for k in ("재해석", "reinterpret"))
        or (
            any(k in low for k in ("레퍼런스", "reference", "이 곡", "이 음악", "코드 진행"))
            and any(
                k in low
                for k in (
                    "만들어",
                    "작곡",
                    "생성",
                    "사용해줘",
                    "참고해서",
                    "바꿔줘",
                    "바꿔 줘",
                    "compose",
                    "generate",
                    "make a",
                    "same chord",
                    "drum rhythm",
                )
            )
            and not any(k in low for k in ("볼륨", "volume", "게인", "gain", "뮤트", "mute", "솔로", "solo", "복제", "duplicate"))
        )
    )
    if is_ref_compose_req:
        parsed_locks: dict[str, str] = {}
        ref_mode = "reinterpret" if any(k in low for k in ("재해석", "reinterpret")) else "reference_compose"
        if any(k in low for k in ("bpm", "템포", "같은 빠르기", "same tempo")):
            parsed_locks["bpm"] = "locked"
        if any(k in low for k in ("코드 진행", "같은 코드", "코드 그대로", "코드 고정", "chord progression", "same chord")):
            parsed_locks["chord_progression"] = "locked"
        if any(k in low for k in ("드럼 리듬", "드럼 그루브", "리듬을 사용", "리듬은 유지", "리듬과 코드", "drum rhythm", "drum groove")):
            parsed_locks["drum_rhythm"] = "locked"
        if any(k in low for k in ("베이스 그루브", "베이스는 유지", "bass groove", "keep bass")):
            parsed_locks["bass_groove"] = "locked"
        if any(k in low for k in ("후반부 전개", "편곡 구조", "전개 방식", "arrangement")):
            parsed_locks["arrangement"] = "locked"
        if any(k in low for k in ("멜로디만 바꿔", "새로운 멜로디", "새 멜로디", "새로운 곡", "new melody", "fresh melody", "멜로디는 새")):
            parsed_locks["melody"] = "free"
        if any(k in low for k in ("공간감", "음색", "timbre", "spatial")):
            parsed_locks["timbre"] = "reference"
            parsed_locks["spatial_character"] = "reference"
        return {
            "supported": True,
            "action": "composition_plan",
            "instruction": text,
            "referenceId": default_ref_id,
            "featureLocks": parsed_locks or None,
            "referenceMode": ref_mode,
            "useProjectChordTrack": bool(project.chordTrack and ("코드" in low or project.chordTrackLocked)),
            "messageKo": f"레퍼런스 조건({ref_mode})이 반영된 작곡 계획(Composition Plan)을 설계합니다.",
            "messageEn": f"Designing a reference-conditioned Composition Plan ({ref_mode}).",
        }

    # 0A. Phase 04 Selective Arrangement, Musical Variation, Fill-in, Strip/Extend, Reverse/Fade
    arrangement_triggers = (
        "변주",
        "필인",
        "필 인",
        "후반부만",
        "뒷부분만",
        "메인 멜로디는 유지",
        "앞부분은 유지",
        "인상적으로 바꿔",
        "다양하게 바꿔",
        "바꿔줘",
        "바꿔 줘",
        "펑키하게",
        "만 남겨",
        "만 남기",
        "더 늘려",
        "연장해",
        "리버스",
        "거꾸로",
        "페이드",
        "크로스페이드",
        "리듬만",
        "벨로시티만",
        "강약만",
        "보이싱",
        "레이어 추가",
        "레이어를 추가",
        "vary",
        "variation",
        "turnaround",
        "drum fill",
        "funkier",
        "extend",
        "only leave",
        "leave only",
        "reverse",
        "crossfade",
        "rhythm only",
        "velocity only",
        "add layer",
    )
    is_arrangement_req = any(k in low for k in arrangement_triggers) and not any(
        k in low for k in ("볼륨", "volume", "게인", "gain", "뮤트", "mute", "솔로", "solo", "복제", "duplicate")
    )
    if is_arrangement_req:
        return {
            "supported": True,
            "action": "arrangement_edit_plan",
            "instruction": text,
            "messageKo": "선택 구간 편곡 및 음악적 변주 계획(Arrangement Edit Plan)을 설계합니다.",
            "messageEn": "Designing a scope-bounded Arrangement Edit Plan.",
        }

    # 0B. Phase 03 AI Composition / Hook / Loop / Instrument Session creation
    is_composition_req = (
        any(k in low for k in ("작곡", "만들어줘", "만들어 줘", "생성해줘", "생성해 줘", "compose", "generate", "create a", "make a", "write a"))
        and not is_section_req
        and not any(k in low for k in ("복제", "duplicate", "뮤트", "mute", "볼륨", "volume", "게인", "gain"))
    ) or any(k in low for k in ("신스 훅", "신스훅", "synth hook", "베이스라인", "드럼 패턴", "미디 루프", "midi loop", "하우스 트랙", "로파이", "신스웨이브"))
    if is_composition_req:
        return {
            "supported": True,
            "action": "composition_plan",
            "instruction": text,
            "messageKo": "음악적 작곡 계획(Composition Plan)을 설계합니다.",
            "messageEn": "Designing a structured Musical Composition Plan.",
        }

    # 1. Reference Analysis request
    if any(k in low for k in ("레퍼런스", "reference")) and any(k in low for k in ("분석", "analyze", "특징")):
        ref_id = active_reference_id or (project.references[0]["id"] if project.references else None)
        if not ref_id:
            return {
                "supported": False,
                "action": "no_reference",
                "messageKo": "분석할 레퍼런스가 없습니다. 좌측 브라우저의 '레퍼런스' 탭에서 오디오/영상 파일을 먼저 가져오세요.",
                "messageEn": "No reference found. Import an audio/video file in the Browser References tab first.",
            }
        return {
            "supported": True,
            "action": "analyze_reference",
            "referenceId": ref_id,
            "messageKo": "레퍼런스 음향 분석을 시작합니다.",
            "messageEn": "Starting real acoustic reference analysis.",
        }

    # 2. Bar-range scoped volume change (e.g. "5~8마디 기타 볼륨을 조금 낮춰줘") -> NEVER blindly alter whole track!
    bar_range_m = re.search(r"(\d+)\s*[~\-–]\s*(\d+)\s*(?:마디|bars?)", low)
    if bar_range_m and any(k in low for k in ("볼륨", "게인", "gain", "volume", "낮춰", "낮추", "줄여", "줄이", "올려", "올리", "높여", "높이")):
        start_bar, end_bar = int(bar_range_m.group(1)), int(bar_range_m.group(2))
        start_beat = max(0.0, (start_bar - 1) * bpb)
        end_beat = max(start_beat + bpb, end_bar * bpb)
        trk = _match_track(project, text, sel_track_id)
        if not trk:
            return {
                "supported": False,
                "action": "target_missing",
                "messageKo": "대상 트랙을 찾지 못했습니다. 트랙을 선택하거나 트랙 이름을 명시해 주세요.",
                "messageEn": "Target track not found. Select a track or specify its name.",
            }
        db_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*db", low)
        delta_db = float(db_m.group(1)) if db_m else (
            -3.0 if any(k in low for k in ("낮춰", "낮추", "줄여", "줄이", "작게", "lower", "down", "quieter")) else 2.5
        )

        ops: list[dict[str, Any]] = []
        for clip in trk.clips:
            c_start = clip.timelineStartBeats
            c_end = clip.timelineStartBeats + clip.durationBeats
            if c_end <= start_beat or c_start >= end_beat:
                continue
            target_clip_id = clip.id
            # If clip extends beyond requested bar range, split cleanly first!
            if c_start < start_beat - 0.05:
                right_id = make_id("clp")
                ops.append({"type": "clip.split", "payload": {"clipId": target_clip_id, "splitBeat": start_beat, "rightClipId": right_id}})
                target_clip_id = right_id
            if c_end > end_beat + 0.05:
                tail_id = make_id("clp")
                ops.append({"type": "clip.split", "payload": {"clipId": target_clip_id, "splitBeat": end_beat, "rightClipId": tail_id}})
            new_gain = max(-24.0, min(12.0, round(clip.gainDb + delta_db, 1)))
            ops.append({"type": "clip.setGain", "payload": {"clipId": target_clip_id, "gainDb": new_gain}})

        if not ops:
            return {
                "supported": False,
                "action": "no_clips_in_range",
                "messageKo": f"{trk.name} 트랙의 {start_bar}–{end_bar}마디에 해당하는 클립이 없습니다. 다른 트랙이나 전체 트랙 볼륨을 임의로 변경하지 않았습니다.",
                "messageEn": f"No clips found on {trk.name} in bars {start_bar}–{end_bar}. Whole track gain was intentionally left untouched.",
            }
        return {
            "supported": True,
            "action": "stage_proposal",
            "summary": f"{trk.name} {start_bar}–{end_bar}마디 클립 Gain {delta_db:+.1f} dB 조정 (다른 트랙 유지)",
            "operations": ops,
        }

    # 3. Duplicate selected clip (e.g. "지금 선택한 기타 구간을 복제해줘")
    if any(k in low for k in ("복제", "duplicate", "복사")):
        clip_id = sel_clip_ids[0] if sel_clip_ids else None
        if not clip_id:
            trk = _match_track(project, text, sel_track_id)
            if trk and trk.clips:
                clip_id = trk.clips[0].id
        if not clip_id:
            return {
                "supported": False,
                "action": "no_clip",
                "messageKo": "복제할 클립이 선택되지 않았습니다. 타임라인에서 클립을 선택해 주세요.",
                "messageEn": "No clip selected to duplicate.",
            }
        return {
            "supported": True,
            "action": "stage_proposal",
            "summary": "선택한 클립 복제",
            "operations": [{"type": "clip.duplicate", "payload": {"clipId": clip_id}}],
        }

    # 4. Mute / Unmute / Solo track (e.g. "드럼 트랙을 잠깐 뮤트해줘")
    if any(k in low for k in ("뮤트", "mute", "음소거", "솔로", "solo")):
        trk = _match_track(project, text, sel_track_id)
        if not trk:
            return {
                "supported": False,
                "action": "no_track",
                "messageKo": "대상 트랙을 선택하거나 트랙 이름을 입력해 주세요.",
                "messageEn": "Select or name a track first.",
            }
        is_solo = any(k in low for k in ("솔로", "solo"))
        turn_off = any(k in low for k in ("해제", "꺼", "풀어", "unmute", "off"))
        if is_solo:
            val = not turn_off
            return {
                "supported": True,
                "action": "stage_proposal",
                "summary": f"{trk.name} 트랙 Solo {'활성화' if val else '해제'}",
                "operations": [{"type": "track.setSolo", "payload": {"trackId": trk.id, "solo": val}}],
            }
        val = not turn_off
        return {
            "supported": True,
            "action": "stage_proposal",
            "summary": f"{trk.name} 트랙 Mute {'활성화' if val else '해제'}",
            "operations": [{"type": "track.setMute", "payload": {"trackId": trk.id, "mute": val}}],
        }

    # 5. Track Volume / Gain adjustment (e.g. "베이스 볼륨을 조금 낮춰줘")
    if any(k in low for k in ("볼륨", "volume", "게인", "gain", "소리")):
        trk = _match_track(project, text, sel_track_id)
        if not trk:
            return {
                "supported": False,
                "action": "no_track",
                "messageKo": "볼륨을 조절할 트랙을 찾지 못했습니다.",
                "messageEn": "Could not identify target track for volume edit.",
            }
        db_m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*db", low)
        if db_m:
            delta = float(db_m.group(1))
        elif any(k in low for k in ("낮춰", "낮추", "줄여", "줄이", "작게", "lower", "down", "quieter")):
            delta = -3.0
        elif any(k in low for k in ("높여", "높이", "올려", "올리", "키워", "키우", "louder", "up", "raise")):
            delta = 2.5
        else:
            delta = -2.0
        new_gain = max(-60.0, min(6.0, round(trk.gainDb + delta, 1)))
        return {
            "supported": True,
            "action": "stage_proposal",
            "summary": f"{trk.name} 트랙 볼륨 {trk.gainDb:+.1f} dB → {new_gain:+.1f} dB",
            "operations": [{"type": "track.setGain", "payload": {"trackId": trk.id, "gainDb": new_gain}}],
        }

    # 6. Section Marker creation (e.g. "9마디부터 새로운 브리지 구간을 만들어줘")
    if is_section_req and any(k in low for k in ("만들어", "추가", "add", "create")):
        bar_m = re.search(r"(\d+)\s*(?:마디|bar)", low)
        start_bar = int(bar_m.group(1)) if bar_m else 9
        start_beats = max(0.0, (start_bar - 1) * bpb)
        name = "BRIDGE" if ("브리지" in low or "브릿지" in low or "bridge" in low) else (
            "CHORUS" if ("코러스" in low or "chorus" in low) else (
                "OUTRO" if ("아웃트로" in low or "outro" in low) else f"SECTION {len(project.sections) + 1}"
            )
        )
        return {
            "supported": True,
            "action": "stage_proposal",
            "summary": f"{start_bar}마디부터 '{name}' 구간 마커 추가",
            "operations": [
                {
                    "type": "section.add",
                    "payload": {
                        "name": name,
                        "startBeats": start_beats,
                        "endBeats": start_beats + bpb * 4,
                        "color": "#554d6b",
                    },
                }
            ],
        }

    return {
        "supported": False,
        "action": "unrecognized",
        "messageKo": "지원되는 로컬 편집 명령으로 해석하지 못했습니다. 예: '이 레퍼런스 분석해줘', '드럼 트랙 뮤트해줘', '베이스 볼륨 낮춰줘', '5~8마디 기타 볼륨 낮춰줘', '9마디부터 브리지 구간 만들어줘'. 외부 MCP 에이전트를 연결하면 더 복합적인 편집 제안을 생성할 수 있습니다.",
        "messageEn": "Instruction did not match a supported local command. Examples: 'Analyze reference', 'Mute drums', 'Lower bass volume', 'Duplicate selected clip', 'Add bridge section at bar 9'. Connect an external MCP agent for multi-step proposals.",
    }
