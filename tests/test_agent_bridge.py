"""Phase 02-B Agent Bridge, MCP tool suite, Test C Agent Editing & Korean Command Router tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import mcp_server
from app.daw_server import app
from engine import paths as engine_paths
from engine.daw_workspace import mcp_tools, proposals, session, store
from engine.daw_workspace.schema import Clip, MidiNote, Track


@pytest.fixture()
def isolated_bridge_env(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path)
    engine_paths.initialize()
    return tmp_path


def test_mcp_server_registers_all_legacy_and_daw_tools():
    """Verify all 9 legacy music.* tools are intact AND all Phase 02 daw.* tools are registered."""
    tool_names = set(mcp_server.server._tool_manager._tools.keys())
    legacy_expected = {
        "music.generate",
        "music.apply_effect",
        "music.render",
        "music.compare",
        "music.get_status",
        "music.export",
        "music.produce",
        "music.list_versions",
        "music.restore",
    }
    daw_expected = {
        "daw.list_projects",
        "daw.get_active_project",
        "daw.get_project",
        "daw.get_selection",
        "daw.get_tracks",
        "daw.get_clips",
        "daw.get_sections",
        "daw.get_midi_notes",
        "daw.get_reference_analysis",
        "daw.get_reference_blueprint",
        "daw.get_capabilities",
        "daw.add_track",
        "daw.move_clip",
        "daw.split_clip",
        "daw.duplicate_clip",
        "daw.set_track_gain",
        "daw.set_track_pan",
        "daw.set_track_mute",
        "daw.edit_midi_notes",
        "daw.add_section",
        "daw.preview_changes",
        "daw.apply_changes",
        "daw.reject_changes",
        "daw.undo",
        "daw.redo",
        "daw.analyze_reference",
        "daw.get_analysis_status",
        "daw.compare_audio",
    }
    assert legacy_expected.issubset(tool_names)
    assert daw_expected.issubset(tool_names)


def test_c_full_agent_editing_workflow_and_undo_reopen(isolated_bridge_env):
    """Test C: Selection sync -> External Agent inspect -> Staged proposal -> Apply -> Undo -> Reopen."""
    client = TestClient(app)
    proj = store.create_project(name="Agent Bridge QA", bpm=128.0, with_default_tracks=False)
    proj.tracks = [
        Track(
            id="trk_drums",
            name="Drums",
            type="audio",
            gainDb=-1.0,
            clips=[
                Clip(
                    id="clp_d1",
                    name="Drums 1",
                    type="audio",
                    assetId=None,
                    timelineStartBeats=0.0,
                    durationBeats=32.0,
                )
            ],
        ),
        Track(
            id="trk_guitar",
            name="Guitar",
            type="audio",
            gainDb=0.0,
            clips=[
                Clip(
                    id="clp_g1",
                    name="Guitar Long",
                    type="audio",
                    assetId=None,
                    timelineStartBeats=0.0,
                    durationBeats=48.0,  # Bars 1..12
                )
            ],
        ),
        Track(
            id="trk_synth",
            name="Synth",
            type="midi",
            clips=[
                Clip(
                    id="clp_m1",
                    name="Synth 1",
                    type="midi",
                    timelineStartBeats=16.0,
                    durationBeats=16.0,
                    notes=[MidiNote(id="n1", pitch=60, velocity=100, startBeat=0.0, durationBeats=1.0)],
                )
            ],
        ),
    ]
    saved = store.save_project(proj)
    assert saved.revision == 2

    # 1. Browser tab pushes live Selection Context (Guitar · Bars 5–8 = beats 16..32)
    sess_res = client.post(
        "/api/session/state",
        json={
            "sessionId": "sess_browser_1",
            "projectId": saved.id,
            "revision": saved.revision,
            "selection": {
                "selectedTrackId": "trk_guitar",
                "selectedClipIds": ["clp_g1"],
                "timeRangeBeats": {"startBeats": 16.0, "endBeats": 32.0},
                "selectedSectionId": None,
            },
            "locale": "ko",
        },
    )
    assert sess_res.status_code == 200

    # 2. External MCP agent reads live Selection Context & active project
    sel = mcp_tools.get_selection()
    assert sel["projectId"] == saved.id
    assert sel["projectRevision"] == 2
    assert sel["selection"]["selectedTrackId"] == "trk_guitar"
    assert sel["barRange"] == {"startBar": 5, "endBar": 8}

    # 3. Korean bar-range scoped instruction splits ONLY bars 5-8 and lowers Clip Gain (leaves track Gain 0.0!)
    inst_res = client.post(
        f"/api/projects/{saved.id}/producer/instruct",
        json={
            "instruction": "5~8마디 기타 트랙의 볼륨을 조금 낮추고 베이스는 유지해줘.",
            "selection": sel["selection"],
            "baseRevision": saved.revision,
        },
    )
    assert inst_res.status_code == 200
    body = inst_res.json()
    assert body["supported"] is True
    assert body["action"] == "proposal_created"
    prop = body["proposal"]
    # Must stage split + clip.setGain, NEVER track.setGain!
    op_types = [op["type"] for op in prop["operations"]]
    assert "clip.split" in op_types
    assert "clip.setGain" in op_types
    assert "track.setGain" not in op_types

    # 4. Apply staged proposal via MCP / API and verify Revision bump + exact clip state
    applied = mcp_tools.apply_changes(prop["id"], saved.id)
    assert applied["revision"] == 3
    reopened = store.load_project(saved.id)
    guitar_track = next(t for t in reopened.tracks if t.id == "trk_guitar")
    assert guitar_track.gainDb == 0.0  # Whole track gain untouched!
    assert len(guitar_track.clips) == 3  # Split into Bars 1-4, Bars 5-8, Bars 9-12
    mid_clip = next(c for c in guitar_track.clips if c.timelineStartBeats == 16.0)
    assert mid_clip.durationBeats == 16.0
    assert mid_clip.gainDb == -3.0

    # 5. Undo via MCP restores original single Guitar clip cleanly
    undone = mcp_tools.undo(saved.id)
    assert undone["undone"] is True
    after_undo = store.load_project(saved.id)
    guitar_after_undo = next(t for t in after_undo.tracks if t.id == "trk_guitar")
    assert len(guitar_after_undo.clips) == 1
    assert guitar_after_undo.clips[0].gainDb == 0.0

    # 6. Phase 05 FX request (EQ / Reverb) is now genuinely supported as a staged proposal,
    #    while Phase 07 singing vocal synthesis still returns an honest refusal!
    fx_prop = client.post(
        f"/api/projects/{saved.id}/producer/instruct",
        json={"instruction": "기타에 리버브랑 EQ 걸어줘", "baseRevision": after_undo.revision},
    )
    assert fx_prop.status_code == 200
    assert fx_prop.json()["supported"] is True
    assert fx_prop.json()["action"] == "proposal_created"

    refusal = client.post(
        f"/api/projects/{saved.id}/producer/instruct",
        json={"instruction": "한국어 가사로 보컬 노래를 직접 불러서 녹음해줘", "baseRevision": after_undo.revision},
    )
    assert refusal.status_code == 200
    assert refusal.json()["supported"] is False
    assert refusal.json()["messageKo"]

    # 7. MCP MIDI note edit defaults to safe staged proposal (Phase 03-A) -> apply -> read roundtrip
    midi_edit = mcp_tools.edit_midi_notes(
        "clp_m1",
        [{"type": "midi.addNote", "payload": {"note": {"id": "n2", "pitch": 67, "velocity": 105, "startBeat": 2.0, "durationBeats": 1.0}}}],
        project_id=saved.id,
        expected_revision=after_undo.revision,
    )
    assert midi_edit["staged"] is True
    assert midi_edit["proposal"]["status"] == "pending"
    applied_midi = mcp_tools.apply_changes(midi_edit["proposal"]["id"], saved.id)
    assert applied_midi["proposal"]["status"] == "applied"
    notes_read = mcp_tools.get_midi_notes("clp_m1", saved.id)
    assert len(notes_read["notes"]) == 2
