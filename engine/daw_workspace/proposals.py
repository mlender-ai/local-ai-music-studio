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

    # Reject clearly unsupported Phase 03–07 capabilities honestly!
    unsupported_patterns = [
        (["eq", "이큐", "컴프레서", "compressor", "리버브", "reverb", "딜레이", "delay", "디스토션", "vst", "au"], "Phase 05 (Sound Design / FX Rack)"),
        (["작곡", "만들어줘", "생성해줘", "변주", "솔로 추가", "compose", "generate", "regenerate"], "Phase 03–04 (AI Composition & Arrangement)"),
        (["보컬", "가사", "vocal", "lyrics"], "Phase 07 (Full Music Production)"),
        (["마스터링", "mastering", "사이드체인", "sidechain"], "Phase 06 (Mixing & Mastering)"),
    ]
    # Allow "구간 만들어줘" / "브리지 만들어줘" as section creation!
    is_section_req = any(k in low for k in ("구간", "브리지", "브릿지", "섹션", "section", "bridge", "chorus", "intro", "outro"))
    for kws, phase_label in unsupported_patterns:
        if any(k in low for k in kws) and not (is_section_req and "만들어" in low):
            return {
                "supported": False,
                "action": "unsupported",
                "messageKo": f"요청하신 기능은 현재 지원되지 않습니다 ({phase_label} 예정). 현재는 레퍼런스 분석, 트랙 Mute/Solo/볼륨/패닝, 클립 복제·분할·이동, 구간 마커 추가 명령을 실행할 수 있습니다.",
                "messageEn": f"This request is not supported yet (scheduled for {phase_label}). Currently supported: reference analysis, track mute/solo/gain/pan, clip duplicate/split/move, and section markers.",
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
