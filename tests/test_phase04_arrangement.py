"""Phase 04 Comprehensive Verification Suite (GATE 3–7):
- TEST B: Selective Drum Variation (bars 5–8 + turnaround fill), bars 1–4 & 9–12 bit-for-bit preserved,
  Bass/Synth untouched, Solo/In-Context/Original A/B previews, replace_range zero-overlap + Original Backup + Undo!
- TEST C: Synth Hook Second-Half Variation (first-half motif locked), Alternative Take Lane (zero double-play!),
  Selective Sub-Range Comping (bars 3–4 only), Stereo WAV Export, Original Restore!
- Non-Destructive Audio Arrangement: Reverse (immutable original preserved), Fade-in/Fade-out rendering, Seam Validation!
- Conversational Continuity, Structural Edits (`extend_section`, `strip_to_tracks`), Rhythm-Only & Velocity-Only preservation,
  and Project Music Memory!
- MCP Tool Registry check (all 9 legacy `music.*` + 52 `daw.*` = 61 tools).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from app.mcp_server import server as mcp_server
from engine import paths as engine_paths
from engine.arrangement import (
    create_arrangement_edit_plan,
    execute_arrangement_edit_plan,
    extract_midi_notes_in_range,
    validate_audio_seam,
)
from engine.daw_workspace import commands, mcp_tools, renderer, store
from engine.daw_workspace.schema import Clip, MidiNote, SectionMarker


@pytest.fixture()
def isolated_phase04(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path / "data")
    monkeypatch.setattr(engine_paths, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setenv("DAW_RUNTIME_CONFIG", str(tmp_path / "runtime_config.json"))
    # Keep unit tests deterministic & offline (do not spawn external Claude CLI)
    monkeypatch.setattr(
        "engine.arrangement.scope.invoke_llm_json",
        lambda **kwargs: (None, {"providerId": "local-music-director", "model": "deterministic-test"}),
    )
    engine_paths.initialize()
    return tmp_path


def _seed_multitrack_midi_project():
    """Create a 12-bar (48 beat) multitrack MIDI project with Drums, Bass, Synth Hook & 3 sections."""
    proj = store.create_project(name="Phase04 QA Session", bpm=128.0, length_beats=48.0, with_default_tracks=False)

    # 1. Drums MIDI track (12 bars continuous clip: kick on beats, snare 1 & 3, closed hat 8ths)
    drum_notes: list[MidiNote] = []
    for bar in range(12):
        base = bar * 4.0
        for b in range(4):
            drum_notes.append(MidiNote(pitch=36, velocity=110, startBeat=base + b, durationBeats=0.35))
        for sb in (1.0, 3.0):
            drum_notes.append(MidiNote(pitch=38, velocity=96, startBeat=base + sb, durationBeats=0.25))
        for s in range(8):
            drum_notes.append(MidiNote(pitch=42, velocity=70, startBeat=base + s * 0.5, durationBeats=0.18))

    # 2. Bass MIDI track (12 bars)
    bass_notes: list[MidiNote] = []
    for bar in range(12):
        base = bar * 4.0
        bass_notes.append(MidiNote(pitch=41, velocity=105, startBeat=base, durationBeats=1.5))
        bass_notes.append(MidiNote(pitch=41, velocity=98, startBeat=base + 2.0, durationBeats=1.5))

    # 3. Synth Hook MIDI track (bars 1–4 motif clip + bars 5–8 groove clip)
    hook_notes = [
        # First half (beats 0..8 -> bars 1–2)
        MidiNote(pitch=65, velocity=96, startBeat=0.0, durationBeats=0.75),
        MidiNote(pitch=68, velocity=92, startBeat=1.0, durationBeats=0.75),
        MidiNote(pitch=72, velocity=100, startBeat=2.0, durationBeats=1.0),
        MidiNote(pitch=70, velocity=94, startBeat=4.5, durationBeats=0.75),
        # Second half (beats 8..16 -> bars 3–4)
        MidiNote(pitch=68, velocity=90, startBeat=8.0, durationBeats=0.75),
        MidiNote(pitch=65, velocity=88, startBeat=9.5, durationBeats=0.75),
        MidiNote(pitch=67, velocity=92, startBeat=11.0, durationBeats=0.75),
        MidiNote(pitch=65, velocity=96, startBeat=13.0, durationBeats=1.0),
    ]

    proj = commands.apply_command(
        proj, "track.add", {"id": "trk_drums", "name": "Drums", "type": "midi", "instrumentRef": "drum-kit-electronic"}
    )
    proj = commands.apply_command(
        proj, "track.add", {"id": "trk_bass", "name": "Bass", "type": "midi", "instrumentRef": "analog-sub-bass"}
    )
    proj = commands.apply_command(
        proj, "track.add", {"id": "trk_hook", "name": "Synth Hook", "type": "midi", "instrumentRef": "fm-pluck-lead"}
    )

    proj = commands.apply_command(
        proj,
        "clip.add",
        {
            "trackId": "trk_drums",
            "clip": Clip(id="clp_drums", name="Drums 1-12", type="midi", timelineStartBeats=0.0, durationBeats=48.0, notes=drum_notes).model_dump(),
        },
    )
    proj = commands.apply_command(
        proj,
        "clip.add",
        {
            "trackId": "trk_bass",
            "clip": Clip(id="clp_bass", name="Bass 1-12", type="midi", timelineStartBeats=0.0, durationBeats=48.0, notes=bass_notes).model_dump(),
        },
    )
    proj = commands.apply_command(
        proj,
        "clip.add",
        {
            "trackId": "trk_hook",
            "clip": Clip(id="clp_hook", name="Synth Hook 1-4", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=hook_notes).model_dump(),
        },
    )
    proj.sections = [
        SectionMarker(id="sec_intro", name="INTRO", startBeats=0.0, endBeats=16.0, color="#49505e"),
        SectionMarker(id="sec_break", name="BREAKDOWN", startBeats=16.0, endBeats=32.0, color="#446256"),
        SectionMarker(id="sec_climax", name="CLIMAX", startBeats=32.0, endBeats=48.0, color="#6d5645"),
    ]
    return store.save_project(proj, expected_revision=proj.revision)


def _extract_signature(notes: list[dict]) -> list[tuple[int, float, int]]:
    return [(int(n["pitch"]), round(float(n["startBeat"]), 3), int(n["velocity"])) for n in notes]


def test_b_selective_drum_variation_bars_5_to_8_with_fill_and_undo(isolated_phase04):
    """TEST B: Vary ONLY Drums bars 5–8 + turnaround fill, preserve bars 1–4 & 9–12 + Bass/Synth, Undo restores exact original."""
    proj = _seed_multitrack_midi_project()
    client = TestClient(app)

    orig_drums_trk = next(t for t in proj.tracks if t.id == "trk_drums")
    orig_b1_4, _ = extract_midi_notes_in_range(orig_drums_trk, 0.0, 16.0)
    orig_b5_8, _ = extract_midi_notes_in_range(orig_drums_trk, 16.0, 32.0)
    orig_b9_12, _ = extract_midi_notes_in_range(orig_drums_trk, 32.0, 48.0)
    orig_bass_dump = next(t for t in proj.tracks if t.id == "trk_bass").model_dump()
    orig_hook_dump = next(t for t in proj.tracks if t.id == "trk_hook").model_dump()

    # 1. Conversational Producer Instruction routes directly to ArrangementEditPlan
    resp = client.post(
        f"/api/projects/{proj.id}/producer/instruct",
        json={
            "instruction": "드럼 5~8마디만 좀 더 다양하게 변주해줘. 마지막에는 필인을 넣어줘.",
            "selection": {"selectedTrackId": "trk_drums", "selectedClipIds": [], "timeRangeBeats": None},
            "baseRevision": proj.revision,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["supported"] is True
    assert body["action"] == "arrangement_edit_plan_created"
    plan = body["arrangementPlan"]
    assert plan["variationKind"] == "drum_variation"
    assert plan["scope"]["startBar"] == 5
    assert plan["scope"]["endBarInclusive"] == 8
    assert plan["scope"]["startBeats"] == 16.0
    assert plan["scope"]["endBeats"] == 32.0
    assert plan["addTurnaroundFill"] is True
    assert "trk_bass" in plan["scope"]["preservedTrackIds"]
    assert "trk_hook" in plan["scope"]["preservedTrackIds"]

    # 2. Execute plan -> creates non-destructive Variation Take with Solo + In-Context + Original A/B previews!
    exec_resp = client.post(
        f"/api/projects/{proj.id}/arrangement/execute",
        json={"plan": plan, "seed": 42},
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    take = exec_data["take"]
    assert take["mode"] == "midi_variation"
    assert take["targetTrackId"] == "trk_drums"
    diff = take["qualityReport"]["musical"]["diff"]
    assert diff["fillHitsAdded"] > 0
    assert diff["ghostSnaresAdded"] > 0

    # Verify all 3 contextual preview audio endpoints return real non-silent WAVs
    for variant in ("solo", "in_context", "original_context"):
        aud = client.get(f"/api/projects/{proj.id}/takes/{take['id']}/audio?variant={variant}")
        assert aud.status_code == 200
        assert aud.content[:4] == b"RIFF"
        assert len(aud.content) > 4096

    # 3. Apply Take with replace_range -> zero clip overlap, bars 1-4 & 9-12 exact, Bass/Synth untouched, Original Backup saved!
    apply_resp = client.post(
        f"/api/projects/{proj.id}/takes/{take['id']}/apply",
        json={"applyMode": "replace_range", "targetTrackId": "trk_drums", "startBeats": 16.0},
    )
    assert apply_resp.status_code == 200
    after_proj = store.load_project(proj.id)
    drums_after = next(t for t in after_proj.tracks if t.id == "trk_drums")

    # Verify zero overlap between clips on Drums
    ordered = sorted(drums_after.clips, key=lambda c: c.timelineStartBeats)
    for c_left, c_right in zip(ordered, ordered[1:]):
        assert c_left.timelineStartBeats + c_left.durationBeats <= c_right.timelineStartBeats + 1e-4

    # Verify bars 1–4 and 9–12 bit-for-bit identical, bars 5–8 genuinely varied!
    after_b1_4, _ = extract_midi_notes_in_range(drums_after, 0.0, 16.0)
    after_b5_8, _ = extract_midi_notes_in_range(drums_after, 16.0, 32.0)
    after_b9_12, _ = extract_midi_notes_in_range(drums_after, 32.0, 48.0)
    assert _extract_signature(after_b1_4) == _extract_signature(orig_b1_4)
    assert _extract_signature(after_b9_12) == _extract_signature(orig_b9_12)
    assert _extract_signature(after_b5_8) != _extract_signature(orig_b5_8)

    # Verify Bass & Synth Hook completely untouched
    assert next(t for t in after_proj.tracks if t.id == "trk_bass").model_dump() == orig_bass_dump
    assert next(t for t in after_proj.tracks if t.id == "trk_hook").model_dump() == orig_hook_dump

    # Verify Original Backup Take Lane was automatically saved
    assert any(ln.get("isOriginalBackup") for ln in drums_after.takeLanes)

    # 4. 1-click Undo restores exact pre-apply Drums!
    undo_resp = client.post(f"/api/projects/{proj.id}/undo")
    assert undo_resp.status_code == 200
    undone_proj = store.load_project(proj.id)
    drums_undone = next(t for t in undone_proj.tracks if t.id == "trk_drums")
    undone_b5_8, _ = extract_midi_notes_in_range(drums_undone, 16.0, 32.0)
    assert _extract_signature(undone_b5_8) == _extract_signature(orig_b5_8)


def test_c_hook_variation_take_lane_selective_comping_and_export(isolated_phase04):
    """TEST C: Preserve 1st half of Synth Hook, vary 2nd half, store as Take Lane (no double play!), comp bars 3-4, export WAV."""
    proj = _seed_multitrack_midi_project()
    client = TestClient(app)

    orig_hook_trk = next(t for t in proj.tracks if t.id == "trk_hook")
    orig_first_half, _ = extract_midi_notes_in_range(orig_hook_trk, 0.0, 8.0)
    orig_second_half, _ = extract_midi_notes_in_range(orig_hook_trk, 8.0, 16.0)

    # 1. Request Hook 2nd-half variation
    plan_resp = client.post(
        f"/api/projects/{proj.id}/arrangement/plan",
        json={
            "instruction": "신스 훅의 메인 멜로디는 유지하면서 후반부만 좀 더 인상적으로 바꿔줘.",
            "targetTrackId": "trk_hook",
            "startBeats": 0.0,
            "endBeats": 16.0,
        },
    )
    assert plan_resp.status_code == 200
    plan = plan_resp.json()["plan"]
    assert plan["variationKind"] == "hook_variation"
    assert plan["preserveFirstHalf"] is True

    # 2. Generate Variation Take
    exec_resp = client.post(f"/api/projects/{proj.id}/arrangement/execute", json={"plan": plan, "seed": 7})
    assert exec_resp.status_code == 200
    take = exec_resp.json()["take"]
    var_notes = take["artifacts"][0]["notes"]

    # First half notes (< beat 8.0) MUST match original motif pitches & timing!
    var_first = [(n["pitch"], round(n["startBeat"], 3)) for n in var_notes if n["startBeat"] < 7.95]
    orig_first = [(n["pitch"], round(n["startBeat"], 3)) for n in orig_first_half]
    assert var_first == orig_first

    # Second half notes (>= beat 8.0) MUST be varied!
    var_second = [(n["pitch"], round(n["startBeat"], 3)) for n in var_notes if n["startBeat"] >= 7.95]
    orig_second = [(n["pitch"], round(n["startBeat"], 3)) for n in orig_second_half]
    assert var_second != orig_second

    # 3. Export baseline WAV before adding alternative Take Lane
    base_export = renderer.export_project_wav(store.load_project(proj.id), filename="before_lane.wav", start_beats=0.0, end_beats=16.0)

    # Add Take as Alternative Take Lane (must NOT alter main lane or double-play!)
    lane_apply = client.post(
        f"/api/projects/{proj.id}/takes/{take['id']}/apply",
        json={"applyMode": "alternative_take", "targetTrackId": "trk_hook", "startBeats": 0.0},
    )
    assert lane_apply.status_code == 200
    lane_ids = lane_apply.json()["createdLaneIds"]
    assert len(lane_ids) == 1
    lane_id = lane_ids[0]

    # Render WAV again with unpromoted Take Lane present -> MUST be bit-for-bit identical (zero double-summing!)
    after_lane_export = renderer.export_project_wav(store.load_project(proj.id), filename="with_inactive_lane.wav", start_beats=0.0, end_beats=16.0)
    assert after_lane_export["sha256"] == base_export["sha256"]

    # 4. Selective Sub-Range Comping: promote ONLY bars 3–4 (beats 8..16)!
    comp_resp = client.post(
        f"/api/projects/{proj.id}/tracks/trk_hook/take-lanes/{lane_id}/promote",
        json={"startBeats": 8.0, "endBeats": 16.0},
    )
    assert comp_resp.status_code == 200
    comped_proj = store.load_project(proj.id)
    hook_after_comp = next(t for t in comped_proj.tracks if t.id == "trk_hook")

    comp_first, _ = extract_midi_notes_in_range(hook_after_comp, 0.0, 8.0)
    comp_second, _ = extract_midi_notes_in_range(hook_after_comp, 8.0, 16.0)
    assert [(n["pitch"], round(n["startBeat"], 3)) for n in comp_first] == orig_first
    assert [(n["pitch"], round(n["startBeat"], 3)) for n in comp_second] != orig_second

    # Export Comped Stereo WAV -> clean & non-clipping!
    comp_export = renderer.export_project_wav(comped_proj, filename="comped_hook.wav", start_beats=0.0, end_beats=16.0)
    assert comp_export["clippedSamples"] == 0
    assert comp_export["sha256"] != base_export["sha256"]
    assert comp_export["peakDbfs"] > -30.0

    # 5. Restore Original Backup Take Lane -> bars 3–4 return to original motif!
    restore_resp = client.post(f"/api/projects/{proj.id}/tracks/trk_hook/take-lanes/restore-original", json={})
    assert restore_resp.status_code == 200
    restored_hook = next(t for t in store.load_project(proj.id).tracks if t.id == "trk_hook")
    restored_second, _ = extract_midi_notes_in_range(restored_hook, 8.0, 16.0)
    assert [(n["pitch"], round(n["startBeat"], 3)) for n in restored_second] == orig_second


def test_non_destructive_audio_reverse_fades_and_seam_validation(isolated_phase04):
    """Non-destructive Reverse preserves original WAV; Fade-in/out tapers render; Seam Validator detects clicks vs smooth joins."""
    proj = store.create_project(name="Audio Arr QA", bpm=120.0, length_beats=16.0, with_default_tracks=False)
    proj = commands.apply_command(proj, "track.add", {"id": "trk_aud", "name": "Guitar", "type": "audio"})
    proj = store.save_project(proj, expected_revision=proj.revision)

    # Synthesize an asymmetric growing-envelope Stereo WAV (quiet start 0.05 -> loud end 0.55)
    sr = 48000
    dur_sec = 2.0  # 4 beats at 120 BPM
    t = np.arange(int(sr * dur_sec), dtype=np.float64) / sr
    env = np.linspace(0.05, 0.55, len(t))
    sig = env * np.sin(2.0 * math.pi * 440.0 * t)
    stereo = np.stack([sig, sig], axis=1).astype(np.float32)

    tmp_wav = isolated_phase04 / "ramp.wav"
    sf.write(str(tmp_wav), stereo, sr, subtype="PCM_24")
    asset, _ = store.import_asset_bytes(proj.id, "ramp.wav", tmp_wav.read_bytes(), kind_hint="audio")
    orig_sha = asset.sha256

    proj = store.load_project(proj.id)
    proj = commands.apply_command(
        proj,
        "clip.add",
        {
            "trackId": "trk_aud",
            "clip": Clip(
                id="clp_ramp",
                name="Ramp",
                type="audio",
                assetId=asset.id,
                timelineStartBeats=0.0,
                durationBeats=4.0,
                sourceDurationSec=2.0,
                fadeInBeats=1.0,
                fadeOutBeats=1.0,
            ).model_dump(),
        },
    )
    proj = store.save_project(proj, expected_revision=proj.revision)

    # 1. Verify Fade-in & Fade-out envelope smoothly tapers audio edges!
    rendered_faded, _ = renderer.render_project_to_array(proj, start_beats=0.0, end_beats=4.0)
    edge_rms = float(np.sqrt(np.mean(rendered_faded[:2000] ** 2)))
    mid_rms = float(np.sqrt(np.mean(rendered_faded[44000:52000] ** 2)))
    tail_rms = float(np.sqrt(np.mean(rendered_faded[-2000:] ** 2)))
    assert edge_rms < mid_rms * 0.15
    assert tail_rms < mid_rms * 0.15

    # 2. Non-destructive Audio Reverse via API preserves original asset untouched!
    client = TestClient(app)
    rev_resp = client.post(f"/api/projects/{proj.id}/clips/clp_ramp/reverse", json={})
    assert rev_resp.status_code == 200
    rev_data = rev_resp.json()
    assert rev_data["reversed"] is True
    new_asset_id = rev_data["newAsset"]["id"]
    assert new_asset_id != asset.id

    # Original file is still intact on disk with exact same SHA256!
    _, orig_path = store.resolve_asset_file(proj.id, asset.id)
    assert orig_path.is_file()
    import hashlib
    assert hashlib.sha256(orig_path.read_bytes()).hexdigest() == orig_sha

    # Reversed audio starts louder than it ends!
    _, rev_path = store.resolve_asset_file(proj.id, new_asset_id)
    rev_pcm, _ = sf.read(str(rev_path), dtype="float32", always_2d=True)
    assert float(np.sqrt(np.mean(rev_pcm[:12000] ** 2))) > float(np.sqrt(np.mean(rev_pcm[-12000:] ** 2))) * 2.0

    # 3. Seam Validation catches hard discontinuity & passes smooth zero-crossing join
    left_bad = np.full((4800, 2), 0.45, dtype=np.float32)
    right_bad = np.full((4800, 2), -0.45, dtype=np.float32)
    seam_bad = validate_audio_seam(left_bad, right_bad, sr=sr)
    assert seam_bad["status"] == "WARN"
    assert seam_bad["clickRisk"] is True
    assert seam_bad["recommendedCrossfadeMs"] >= 15.0

    tt = np.arange(9600, dtype=np.float64) / sr
    smooth = np.stack([0.2 * np.sin(2.0 * math.pi * 200.0 * tt)] * 2, axis=1).astype(np.float32)
    seam_ok = validate_audio_seam(smooth[:4800], smooth[4800:], sr=sr)
    assert seam_ok["status"] == "PASS"
    assert seam_ok["clickRisk"] is False


def test_conversational_structural_edits_rhythm_velocity_and_music_memory(isolated_phase04):
    """Test extend_section, strip_to_tracks, rhythm-only, velocity-only & Project Music Memory persistence."""
    proj = _seed_multitrack_midi_project()
    client = TestClient(app)

    # 1. Rhythm-only variation preserves EXACT pitch multiset
    r_plan = create_arrangement_edit_plan(
        proj, "신스 훅 리듬만 바꿔줘", target_track_id="trk_hook", start_beats=0.0, end_beats=16.0
    )
    assert r_plan.variationKind == "rhythm_only"
    assert r_plan.preservePitch is True
    r_res = execute_arrangement_edit_plan(proj.id, r_plan, seed=11)
    orig_pitches = sorted(n.pitch for n in next(t for t in proj.tracks if t.id == "trk_hook").clips[0].notes)
    var_pitches = sorted(n["pitch"] for n in r_res["take"]["artifacts"][0]["notes"])
    assert var_pitches == orig_pitches

    # 2. Velocity-only variation preserves EXACT (pitch, startBeat, durationBeats) while changing velocity!
    v_plan = create_arrangement_edit_plan(
        proj, "신스 훅 벨로시티만 조절해줘", target_track_id="trk_hook", start_beats=0.0, end_beats=16.0
    )
    assert v_plan.variationKind == "velocity_only"
    v_res = execute_arrangement_edit_plan(proj.id, v_plan, seed=12)
    orig_hook_notes = next(t for t in proj.tracks if t.id == "trk_hook").clips[0].notes
    v_notes = v_res["take"]["artifacts"][0]["notes"]
    assert [(n["pitch"], round(n["startBeat"], 3)) for n in v_notes] == [
        (n.pitch, round(n.startBeat, 3)) for n in orig_hook_notes
    ]
    assert [n["velocity"] for n in v_notes] != [n.velocity for n in orig_hook_notes]

    # 3. Structural edit: strip_to_tracks ("1~4마디는 베이스와 드럼만 남겨줘") carves Synth Hook in bars 1–4
    s_plan = create_arrangement_edit_plan(proj, "1~4마디는 베이스와 드럼만 남겨줘")
    assert s_plan.operation == "strip_to_tracks"
    assert set(s_plan.keepTrackIds) == {"trk_drums", "trk_bass"}
    s_res = execute_arrangement_edit_plan(proj.id, s_plan)
    assert s_res["applied"] is True
    after_strip = store.load_project(proj.id)
    assert len(next(t for t in after_strip.tracks if t.id == "trk_hook").clips) == 0
    assert len(next(t for t in after_strip.tracks if t.id == "trk_drums").clips) == 1
    assert len(next(t for t in after_strip.tracks if t.id == "trk_bass").clips) == 1

    # 4. Structural edit: extend_section ("브레이크다운을 4마디 더 늘려줘") shifts CLIMAX right by 16 beats!
    e_plan = create_arrangement_edit_plan(after_strip, "브레이크다운을 4마디 더 늘려줘")
    assert e_plan.operation == "extend_section"
    assert e_plan.extendBars == 4
    e_res = execute_arrangement_edit_plan(proj.id, e_plan)
    assert e_res["applied"] is True
    after_ext = store.load_project(proj.id)
    assert after_ext.lengthBeats == 64.0
    climax = next(s for s in after_ext.sections if s.name == "CLIMAX")
    assert climax.startBeats == 48.0
    assert climax.endBeats == 64.0

    # 5. Project Music Memory API returns populated conversationTurns & roles!
    mem_resp = client.get(f"/api/projects/{proj.id}/memory")
    assert mem_resp.status_code == 200
    mem = mem_resp.json()["musicMemory"]
    assert len(mem["conversationTurns"]) >= 4
    assert len(mem["instrumentRoles"]) == 3


def test_drum_variation_prefers_populated_midi_track_over_empty_default_audio_drum(isolated_phase04):
    """Regression test: default empty Audio 'Drums' track MUST NOT shadow populated MIDI 'Drums (House)' track."""
    proj = store.create_project(name="Default + Generated QA", bpm=128.0, length_beats=64.0, with_default_tracks=True)
    # Default tracks include an empty AUDIO track named "Drums" at index 0!
    assert proj.tracks[0].name == "Drums" and proj.tracks[0].type == "audio" and len(proj.tracks[0].clips) == 0

    # Add populated MIDI "Drums (House)" track
    proj = commands.apply_command(
        proj, "track.add", {"id": "trk_midi_drums", "name": "Drums (House)", "type": "midi", "instrumentRef": "drum-kit-electronic"}
    )
    proj = commands.apply_command(
        proj,
        "clip.add",
        {
            "trackId": "trk_midi_drums",
            "clip": Clip(
                id="clp_md",
                name="Drums House",
                type="midi",
                timelineStartBeats=0.0,
                durationBeats=32.0,
                notes=[MidiNote(pitch=36, velocity=110, startBeat=float(b), durationBeats=0.35) for b in range(32)],
            ).model_dump(),
        },
    )
    proj = store.save_project(proj, expected_revision=proj.revision)

    plan = create_arrangement_edit_plan(proj, "드럼 5~8마디만 좀 더 다양하게 변주해줘. 마지막에는 필인을 넣어줘.")
    assert plan.scope.targetTrackIds == ["trk_midi_drums"]
    res = execute_arrangement_edit_plan(proj.id, plan, seed=42)
    assert res["take"]["targetTrackId"] == "trk_midi_drums"


def test_mcp_tool_registry_includes_all_phase04_tools(isolated_phase04):
    """Verify all 9 legacy `music.*` + 52 `daw.*` = 61 MCP tools are registered and capabilities report Phase 04."""
    tools = set(mcp_server._tool_manager._tools.keys())
    expected_phase04 = {
        "daw.create_arrangement_edit_plan",
        "daw.generate_variation",
        "daw.promote_take_lane",
        "daw.restore_original_take_lane",
        "daw.reverse_audio_clip",
        "daw.get_music_memory",
        "daw.get_runtime_status",
    }
    assert expected_phase04.issubset(tools)
    assert len(tools) >= 61

    caps = mcp_tools.get_capabilities()
    assert caps["phase"] == "04"
    assert caps["schemaVersion"] == "1.4.0"
    assert "selective_bar_variation" in caps["supported"]["aiArrangement"]
    assert "aiArrangementBarRegeneration" not in caps["unsupported"]
