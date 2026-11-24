"""Real separate-process STDIO MCP Client integration test (Phase 03-A)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from engine import paths as engine_paths
from engine.daw_workspace import session as daw_session
from engine.daw_workspace import store
from engine.daw_workspace.schema import Track


def test_real_subprocess_stdio_mcp_client_end_to_end(tmp_path, monkeypatch):
    """Spawn `.venv/bin/python -m app.mcp_server` over STDIO and verify live cross-process edits."""
    monkeypatch.setattr(engine_paths, "DATA", tmp_path)
    engine_paths.initialize()

    # Seed project & active session in tmp_path
    proj = store.create_project(name="Subprocess MCP QA", bpm=126.0, with_default_tracks=False)
    proj.tracks = [
        Track(id="trk_drums", name="Drums", type="audio", gainDb=0.0),
        Track(id="trk_bass", name="Bass", type="audio", gainDb=-2.0),
    ]
    saved = store.save_project(proj)
    daw_session.update_session(
        session_id="sess_stdio_qa",
        project_id=saved.id,
        revision=saved.revision,
        selection={"selectedTrackId": "trk_drums", "selectedClipIds": [], "timeRangeBeats": {"startBeats": 0.0, "endBeats": 16.0}},
        claim_active=True,
    )

    async def run_client():
        env = dict(os.environ)
        env["MUSIC_DATA_DIR"] = str(tmp_path)
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
            cwd=str(engine_paths.ROOT),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools_res = await client.list_tools()
                names = {t.name for t in tools_res.tools}
                assert "music.generate" in names
                assert "daw.get_selection" in names
                assert "daw.set_track_gain" in names
                assert "daw.apply_changes" in names
                assert "daw.undo" in names

                # 1. Read active selection from separate process
                sel_call = await client.call_tool("daw.get_selection", {})
                sel_data = json.loads(sel_call.content[0].text)
                assert sel_data["projectId"] == saved.id
                assert sel_data["selection"]["selectedTrackId"] == "trk_drums"

                # 2. Call daw.set_track_gain WITHOUT stage_only -> MUST safely stage proposal by default!
                gain_call = await client.call_tool(
                    "daw.set_track_gain",
                    {"track_id": "trk_drums", "gain_db": -4.5, "project_id": saved.id},
                )
                gain_data = json.loads(gain_call.content[0].text)
                assert gain_data["staged"] is True
                prop_id = gain_data["proposal"]["id"]

                # Project on disk must NOT be mutated yet!
                assert store.load_project(saved.id).tracks[0].gainDb == 0.0

                # 3. Apply staged proposal across process boundary
                apply_call = await client.call_tool(
                    "daw.apply_changes",
                    {"proposal_id": prop_id, "project_id": saved.id},
                )
                apply_data = json.loads(apply_call.content[0].text)
                assert apply_data["proposal"]["status"] == "applied"
                assert store.load_project(saved.id).tracks[0].gainDb == -4.5

                # 4. Undo across process boundary
                undo_call = await client.call_tool("daw.undo", {"project_id": saved.id})
                undo_data = json.loads(undo_call.content[0].text)
                assert undo_data["undone"] is True
                assert store.load_project(saved.id).tracks[0].gainDb == 0.0

    asyncio.run(run_client())
