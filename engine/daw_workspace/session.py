"""Shared browser/agent session state registry and SSE event bus for live DAW sync."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

from engine import paths as engine_paths

from .schema import utc_now_iso


def _session_file() -> Path:
    p = engine_paths.DATA / "daw" / "session.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_session_lock = threading.Lock()


def _load_sessions_raw() -> dict[str, Any]:
    sf = _session_file()
    if not sf.is_file():
        return {"activeSessionId": None, "sessions": {}}
    try:
        data = json.loads(sf.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            return data
    except Exception:
        pass
    return {"activeSessionId": None, "sessions": {}}


def _save_sessions_raw(data: dict[str, Any]) -> None:
    sf = _session_file()
    tmp = sf.with_name(f".session.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, sf)


def update_session(
    session_id: str,
    project_id: str | None,
    revision: int | None,
    selection: dict[str, Any] | None = None,
    active_reference_id: str | None = None,
    locale: str = "ko",
    claim_active: bool = True,
) -> dict[str, Any]:
    """Register or refresh a DAW browser tab session so external MCP agents share exact context."""
    with _session_lock:
        data = _load_sessions_raw()
        entry = {
            "sessionId": session_id,
            "projectId": project_id,
            "revision": revision,
            "selection": selection
            or {
                "selectedTrackId": None,
                "selectedClipIds": [],
                "timeRangeBeats": None,
                "selectedSectionId": None,
            },
            "activeReferenceId": active_reference_id,
            "locale": locale,
            "updatedAt": utc_now_iso(),
        }
        data["sessions"][session_id] = entry
        if claim_active or not data.get("activeSessionId"):
            data["activeSessionId"] = session_id
        # Prune stale sessions beyond 16 tabs
        if len(data["sessions"]) > 16:
            ordered = sorted(
                data["sessions"].items(),
                key=lambda kv: kv[1].get("updatedAt", ""),
                reverse=True,
            )[:16]
            data["sessions"] = dict(ordered)
        _save_sessions_raw(data)
        return entry


def get_active_session(session_id: str | None = None) -> dict[str, Any]:
    with _session_lock:
        data = _load_sessions_raw()
        sessions = data.get("sessions", {})
        if session_id and session_id in sessions:
            return dict(sessions[session_id])
        active_id = data.get("activeSessionId")
        if active_id and active_id in sessions:
            return dict(sessions[active_id])
        if sessions:
            latest = max(sessions.values(), key=lambda s: s.get("updatedAt", ""))
            return dict(latest)
        return {
            "sessionId": None,
            "projectId": None,
            "revision": None,
            "selection": {
                "selectedTrackId": None,
                "selectedClipIds": [],
                "timeRangeBeats": None,
                "selectedSectionId": None,
            },
            "activeReferenceId": None,
            "locale": "ko",
            "updatedAt": None,
        }


def list_sessions() -> dict[str, Any]:
    with _session_lock:
        data = _load_sessions_raw()
        return {
            "activeSessionId": data.get("activeSessionId"),
            "sessions": list(data.get("sessions", {}).values()),
        }


class EventBus:
    """In-process async SSE broadcaster for immediate DAW UI updates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with self._lock:
            self._subscribers.add((loop, q))
        return q

    def unsubscribe(self, loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard((loop, q))

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        msg = {"type": event_type, "payload": payload, "timestamp": utc_now_iso()}
        with self._lock:
            subs = list(self._subscribers)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(_enqueue_drop_oldest, q, msg)
            except Exception:
                pass


def _enqueue_drop_oldest(q: asyncio.Queue, msg: dict[str, Any]) -> None:
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


event_bus = EventBus()
