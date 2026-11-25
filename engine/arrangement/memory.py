"""Project Music Memory & Conversational Reference Resolution (Phase 04-D · Section 17)."""

from __future__ import annotations

import re
from typing import Any

from engine.daw_workspace import store
from engine.daw_workspace.schema import Project, Track, utc_now_iso


def ensure_music_memory(project: Project) -> dict[str, Any]:
    """Build or refresh compact Project Music Memory directly from live project state."""
    mem = dict(project.musicMemory or {})
    bpb = project.timeSignature.beats_per_bar
    latest_plan = project.compositionPlans[-1] if project.compositionPlans else None

    mem.setdefault("genre", (latest_plan or {}).get("musicalIdentity", {}).get("genre", "house"))
    mem["bpm"] = project.bpm
    mem.setdefault("key", (latest_plan or {}).get("musicalIdentity", {}).get("key", "F minor"))
    mem.setdefault("chords", (latest_plan or {}).get("harmonyAndGroove", {}).get("chordProgression", ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"]))
    mem.setdefault("mainHookSummary", (latest_plan or {}).get("signatureMotif", {}).get("concept", ""))
    mem["referenceIds"] = [r.get("id") for r in project.references if r.get("id")]
    mem["instrumentRoles"] = [
        {"trackId": t.id, "name": t.name, "type": t.type, "instrumentRef": t.instrumentRef}
        for t in project.tracks
    ]
    mem.setdefault("likedTakes", [])
    mem.setdefault("rejectedTakes", [])
    mem.setdefault("preservedTraits", [])
    mem.setdefault("recentEdits", [])
    mem.setdefault("conversationTurns", [])
    mem["lengthBars"] = round(project.lengthBeats / bpb, 1)
    mem["updatedAt"] = utc_now_iso()
    return mem


def update_project_music_memory(
    project_id: str,
    patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proj = store.load_project(project_id)
    mem = ensure_music_memory(proj)
    if patch:
        for k, v in patch.items():
            mem[k] = v
    proj.musicMemory = mem
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return saved.musicMemory


def record_conversation_turn(
    project_id: str,
    user_text: str,
    producer_reply_ko: str,
    action: str,
    target_track_id: str | None = None,
    bar_range: tuple[int, int] | None = None,
    take_id: str | None = None,
) -> dict[str, Any]:
    proj = store.load_project(project_id)
    mem = ensure_music_memory(proj)
    turns = list(mem.get("conversationTurns") or [])
    turns.append(
        {
            "at": utc_now_iso(),
            "user": user_text[:280],
            "producerKo": producer_reply_ko[:280],
            "action": action,
            "targetTrackId": target_track_id,
            "barRange": list(bar_range) if bar_range else None,
            "takeId": take_id,
        }
    )
    mem["conversationTurns"] = turns[-16:]
    if target_track_id:
        mem["lastTargetTrackId"] = target_track_id
    if bar_range:
        mem["lastBarRange"] = list(bar_range)
    if take_id:
        mem["lastTakeId"] = take_id
    proj.musicMemory = mem
    saved = store.save_project(proj, clear_autosave=False, expected_revision=proj.revision)
    return saved.musicMemory


def resolve_contextual_reference(
    project: Project,
    text: str,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve Korean contextual phrases ('방금', '이전 버전', '그 기타', '마지막 후렴', '브레이크다운') to real DAW IDs."""
    low = text.lower()
    mem = ensure_music_memory(project)
    sel = selection or {}
    bpb = project.timeSignature.beats_per_bar

    resolved: dict[str, Any] = {
        "targetTrackId": None,
        "sectionId": None,
        "startBeats": None,
        "endBeats": None,
        "referencedTakeId": None,
        "hints": [],
    }

    # 1. Resolve "방금" / "이전" Take references
    if any(k in low for k in ("방금", "직전", "just now", "last take")):
        last_tid = mem.get("lastTakeId") or (project.takes[-1]["id"] if project.takes else None)
        if last_tid:
            resolved["referencedTakeId"] = last_tid
            resolved["hints"].append(f"Resolved '방금' to take {last_tid}")

    # 2. Resolve named sections ("마지막 후렴", "브레이크다운", "브리지", "클라이맥스", "인트로", "아웃트로")
    sec_keywords = [
        (["마지막 후렴", "final chorus", "클라이맥스", "climax", "하이라이트"], ["climax", "final", "chorus", "hook"], True),
        (["브레이크다운", "브레이크", "breakdown", "break"], ["break", "bridge"], False),
        (["브리지", "브릿지", "bridge"], ["bridge", "break"], False),
        (["인트로", "intro"], ["intro"], False),
        (["아웃트로", "outro"], ["outro"], False),
        (["그루브", "groove", "벌스", "verse"], ["groove", "verse"], False),
    ]
    for triggers, name_hints, prefer_last in sec_keywords:
        if any(tr in low for tr in triggers):
            matches = [s for s in project.sections if any(h in s.name.lower() for h in name_hints)]
            if matches:
                sec = matches[-1] if prefer_last else matches[0]
                resolved["sectionId"] = sec.id
                resolved["startBeats"] = sec.startBeats
                resolved["endBeats"] = sec.endBeats
                resolved["hints"].append(f"Resolved section '{sec.name}' ({int(sec.startBeats // bpb) + 1}–{int((sec.endBeats - 0.01) // bpb) + 1}마디)")
                break

    # 3. Resolve explicit bar range ("5~8마디", "9-16마디", "8마디 마지막")
    m_range = re.search(r"(\d+)\s*[~\-–]\s*(\d+)\s*(?:마디|bars?)", low)
    if m_range:
        sb = max(0.0, (int(m_range.group(1)) - 1) * bpb)
        eb = max(sb + bpb, int(m_range.group(2)) * bpb)
        resolved["startBeats"] = sb
        resolved["endBeats"] = eb
    else:
        m_single = re.search(r"(\d+)\s*(?:마디|bars?)\s*(?:마지막|끝|end)", low)
        if m_single:
            bar_n = int(m_single.group(1))
            resolved["startBeats"] = max(0.0, (bar_n - 1) * bpb)
            resolved["endBeats"] = bar_n * bpb

    # 4. Resolve track name / Korean alias / "그 기타" / "방금 트랙"
    # Prefer longest exact name match, populated tracks, and MIDI tracks for MIDI musical variations!
    aliases: list[tuple[list[str], list[str]]] = [
        (["드럼", "drum", "drums", "비트", "킥", "스네어", "하이햇", "필인"], ["drum"]),
        (["베이스", "bass", "서브"], ["bass"]),
        (["신스 훅", "신스훅", "훅", "hook", "신스", "synth", "멜로디", "리드"], ["hook", "synth", "lead"]),
        (["기타", "guitar"], ["guitar", "gtr"]),
        (["건반", "피아노", "코드", "keys", "piano", "ep", "rhodes"], ["key", "piano", "ep", "chord"]),
        (["패드", "pad", "텍스처", "texture"], ["pad", "texture"]),
    ]
    cleaned_for_target = re.sub(r"[^.,?!]*(?:유지|보존|그대로|keep|preserve)[^.,?!]*", "", low)
    search_text = cleaned_for_target.strip() or low
    wants_audio_edit = any(k in low for k in ("리버스", "거꾸로", "reverse", "페이드", "fade", "크로스페이드", "crossfade"))
    sel_tid = sel.get("selectedTrackId")
    req_sb = resolved.get("startBeats")
    req_eb = resolved.get("endBeats")

    def _track_score(trk: Track, base_match_score: int) -> tuple[int, int, int, int, int]:
        has_clips_in_range = 0
        if req_sb is not None and req_eb is not None:
            has_clips_in_range = 1 if any(
                (c.timelineStartBeats + c.durationBeats) > float(req_sb) + 1e-4 and c.timelineStartBeats < float(req_eb) - 1e-4
                for c in trk.clips
            ) else 0
        has_any_clips = 1 if trk.clips else 0
        type_pref = (1 if trk.type != "midi" else 0) if wants_audio_edit else (1 if trk.type == "midi" else 0)
        is_selected = 1 if trk.id == sel_tid else 0
        return (type_pref, has_clips_in_range, has_any_clips, base_match_score, is_selected)

    candidates: list[tuple[tuple[int, int, int, int, int], Track]] = []
    for trk in project.tracks:
        tname = trk.name.lower()
        if tname and tname in search_text:
            candidates.append((_track_score(trk, 100 + len(tname)), trk))

    if not candidates or all(not c[1].clips for c in candidates):
        for kws, hints in aliases:
            if any(kw in search_text for kw in kws):
                for trk in project.tracks:
                    if any(h in trk.name.lower() or h in (trk.instrumentRef or "").lower() for h in hints):
                        if not any(existing_t.id == trk.id for _, existing_t in candidates):
                            candidates.append((_track_score(trk, 50), trk))

    matched_track: Track | None = None
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        matched_track = candidates[0][1]

    if not matched_track:
        fallback_tid = sel_tid or mem.get("lastTargetTrackId")
        if fallback_tid:
            matched_track = next((t for t in project.tracks if t.id == fallback_tid), None)

    if matched_track:
        resolved["targetTrackId"] = matched_track.id

    # Fallback range from live selection or target track's clip span
    if resolved["startBeats"] is None or resolved["endBeats"] is None:
        tr = sel.get("timeRangeBeats") or {}
        if isinstance(tr, dict) and tr.get("startBeats") is not None and tr.get("endBeats") is not None:
            resolved["startBeats"] = float(tr["startBeats"])
            resolved["endBeats"] = float(tr["endBeats"])
        elif matched_track and matched_track.clips:
            c0 = min(c.timelineStartBeats for c in matched_track.clips)
            c1 = max(c.timelineStartBeats + c.durationBeats for c in matched_track.clips)
            resolved["startBeats"] = c0
            resolved["endBeats"] = c1
        else:
            resolved["startBeats"] = 0.0
            resolved["endBeats"] = min(project.lengthBeats, bpb * 4)

    return resolved
