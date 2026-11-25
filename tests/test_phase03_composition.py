"""Phase 03 End-to-End Verification: Tests A, B, C, YuE2/Demucs Honesty, Providers & 54 MCP Tools."""

from __future__ import annotations

import math

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import mcp_server
from app.daw_server import app
from engine import paths as engine_paths
from engine.composition import list_library_catalog
from engine.daw_workspace import mcp_tools, proposals, references, renderer, store
from engine.daw_workspace.schema import Clip, Track
from engine.generation.adapters import check_resting_voice, detect_generation_engines, probe_demucs, probe_yue2
from engine.instruments import list_instruments
from engine.providers import detect_providers


@pytest.fixture()
def isolated_phase03_env(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path)
    engine_paths.initialize()
    return tmp_path


def _make_ref_house_wav(path, bpm=128.0, duration_sec=10.0, sr=48000):
    t = np.arange(int(sr * duration_sec), dtype=np.float64) / sr
    beat_hz = bpm / 60.0
    kick = np.sin(2 * math.pi * (55.0 + 70.0 * np.exp(-20 * ((t * beat_hz) % 1.0))) * t) * np.exp(-9.0 * ((t * beat_hz) % 1.0))
    bass = 0.28 * np.sin(2 * math.pi * 87.31 * t) + 0.14 * np.sin(2 * math.pi * 130.81 * t)
    chord = 0.12 * np.sin(2 * math.pi * 207.65 * t) + 0.10 * np.sin(2 * math.pi * 261.63 * t)
    # Build energy arc from 0.45 -> 0.95 -> 0.50
    env = 0.45 + 0.50 * np.sin(math.pi * t / duration_sec)
    sig = (0.45 * kick + bass + chord) * env
    stereo = np.stack([sig * 0.96, sig * 1.02], axis=1).astype(np.float32)
    sf.write(str(path), stereo, sr, subtype="PCM_24")
    return path


def test_mcp_registers_all_54_tools_legacy_phase02_and_phase03():
    """All 9 music.* + 28 Phase 02 daw.* + 17 Phase 03 daw.* tools must be registered."""
    names = set(mcp_server.server._tool_manager._tools.keys())
    phase03_expected = {
        "daw.create_composition_plan",
        "daw.get_composition_plan",
        "daw.generate_music",
        "daw.generate_instrument",
        "daw.generate_loop",
        "daw.generate_midi",
        "daw.separate_stems",
        "daw.list_generation_jobs",
        "daw.get_generation_status",
        "daw.cancel_generation",
        "daw.get_generation_result",
        "daw.preview_generation",
        "daw.stage_generation_import",
        "daw.list_takes",
        "daw.select_take",
        "daw.list_providers",
        "daw.list_instruments",
    }
    assert phase03_expected.issubset(names)
    assert len(names) >= 54


def test_a_full_128bpm_house_production_end_to_end(isolated_phase03_env):
    """TEST A: 128 BPM House Plan -> Generation -> QA -> Apply -> Save/Reopen -> Stereo WAV Export."""
    client = TestClient(app)
    proj = store.create_project(name="Test A House", bpm=128.0, with_default_tracks=False)

    # 1. Create Composition Plan
    plan_res = client.post(
        f"/api/projects/{proj.id}/composition/plan",
        json={
            "instruction": "128 BPM 어두운 하우스 풀 트랙 만들어줘. 훅이 분명하고 인스트루멘탈로 구성해줘.",
            "mode": "full_music",
        },
    )
    assert plan_res.status_code == 200
    plan = plan_res.json()["plan"]
    assert plan["musicalIdentity"]["genre"] == "house"
    assert plan["musicalIdentity"]["tempoBpm"] == 128.0
    assert plan["musicalIdentity"]["instrumentalOnly"] is True
    assert len(plan["arrangement"]) >= 4
    assert len(plan["instrumentRoles"]) >= 4

    # 2. Generate Take (sync=True for deterministic test verification)
    gen_res = client.post(
        f"/api/projects/{proj.id}/generation/jobs",
        json={"planId": plan["id"], "engine": "auto", "seed": 77, "sync": True},
    )
    assert gen_res.status_code == 200
    body = gen_res.json()
    assert body["job"]["status"] == "ready_for_preview"
    take = body["take"]
    assert take["provenance"]["engine"] == "local-multitrack-composer"  # Never fakes YuE2!
    assert take["qualityReport"]["technical"]["nonSilent"] is True
    assert take["qualityReport"]["technical"]["finitePcm"] is True
    assert take["qualityReport"]["technical"]["loudnessStandard"] == "ITU-R BS.1770-4"
    assert take["qualityReport"]["vocalScreening"]["checked"] is True
    assert len(take["plannedSections"]) >= 4
    assert len(take["detectedSections"]) >= 1

    # Preview audio endpoint serves real playable WAV
    aud_res = client.get(f"/api/projects/{proj.id}/takes/{take['id']}/audio")
    assert aud_res.status_code == 200
    assert aud_res.content[:4] == b"RIFF"

    # 3. Apply Take transactionally to timeline
    apply_res = client.post(
        f"/api/projects/{proj.id}/takes/{take['id']}/apply",
        json={"applyMode": "new_tracks", "addSectionMarkers": True},
    )
    assert apply_res.status_code == 200
    applied = apply_res.json()
    assert applied["applied"] is True
    assert len(applied["createdTrackIds"]) >= 4

    # 4. Reopen project from disk & verify persistence + schema v1.4.0
    reopened = store.load_project(proj.id)
    assert reopened.schemaVersion == "1.4.0"
    assert len(reopened.tracks) >= 4
    assert any(t.instrumentRef == "drum-kit-electronic" for t in reopened.tracks)
    assert any(t.instrumentRef == "bass-fm-sub" for t in reopened.tracks)
    assert any(t.instrumentRef == "synth-fm-hook" for t in reopened.tracks)

    # 5. Offline 48 kHz Stereo WAV export of first 16 beats verifies multi-timbre audio is real & clean
    exp = renderer.export_project_wav(reopened, filename="test_a_house.wav", start_beats=0.0, end_beats=16.0)
    assert exp["sampleRate"] == 48000
    assert exp["channels"] == 2
    assert exp["peakLinear"] > 0.05
    assert exp["clippedSamples"] == 0


def test_b_reference_guided_composition_and_traceability(isolated_phase03_env, tmp_path):
    """TEST B: Reference analysis -> Blueprint selection -> Traceable generation -> Reference comparison."""
    client = TestClient(app)
    proj = store.create_project(name="Test B Reference", bpm=128.0, with_default_tracks=False)

    # Import & analyze a 128 BPM F-minor House reference
    ref_wav = _make_ref_house_wav(tmp_path / "v72_ref_mock.wav", bpm=128.0, duration_sec=10.0)
    ref_item, _ = references.import_reference_file(proj.id, "V72_Magnetic_Afterhours_Ref.wav", ref_wav.read_bytes())
    analyzed_ref, _ = references.run_reference_analysis_sync(proj.id, ref_item["id"])
    assert analyzed_ref["analysisStatus"] == "completed"

    # Select real ReferenceBlueprint influences (drums_groove + bass_movement + arrangement_arc)
    references.update_reference_blueprint(
        proj.id,
        ref_item["id"],
        selected_influences=["drums_groove", "bass_movement", "arrangement_arc"],
    )

    # Create Reference-guided Plan & verify traceability (appliedFeatures vs unmappedFeatures)
    plan_res = client.post(
        f"/api/projects/{proj.id}/composition/plan",
        json={
            "instruction": "선택한 레퍼런스의 그루브와 전개를 반영한 하우스 트랙 만들어줘.",
            "mode": "full_music",
            "referenceIds": [ref_item["id"]],
        },
    )
    assert plan_res.status_code == 200
    plan = plan_res.json()["plan"]
    binding = plan["referenceBinding"]
    assert ref_item["id"] in binding["referenceIds"]
    assert "tempoBpm" in binding["appliedFeatures"]
    assert len(binding["unmappedFeatures"]) >= 1

    # Generate Take & verify Reference vs Generated comparison is attached
    gen_res = client.post(
        f"/api/projects/{proj.id}/generation/jobs",
        json={"planId": plan["id"], "sync": True},
    )
    assert gen_res.status_code == 200
    take = gen_res.json()["take"]
    ref_cmp = take["qualityReport"]["referenceComparison"]
    assert ref_cmp is not None
    assert "measuredDeltas" in ref_cmp
    assert len(ref_cmp["observations"]) >= 1


def test_c_4bar_synth_hook_preserves_drums_bass_edits_midi_exports_and_undoes(isolated_phase03_env):
    """TEST C: 4-bar Synth Hook MIDI -> preserves existing Drums & Bass -> edit note -> Export -> Undo."""
    client = TestClient(app)
    proj = store.create_project(name="Test C Hook", bpm=128.0, with_default_tracks=False)
    proj.tracks = [
        Track(
            id="trk_drums",
            name="Drums",
            type="midi",
            instrumentRef="drum-kit-electronic",
            gainDb=-1.0,
            clips=[
                Clip(
                    id="clp_d1",
                    name="Drums 1",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=16.0,
                    notes=[{"id": "dk1", "pitch": 36, "velocity": 115, "startBeat": 0.0, "durationBeats": 0.4}],
                )
            ],
        ),
        Track(
            id="trk_bass",
            name="Bass",
            type="midi",
            instrumentRef="bass-fm-sub",
            gainDb=-2.0,
            clips=[
                Clip(
                    id="clp_b1",
                    name="Bass 1",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=16.0,
                    notes=[{"id": "bs1", "pitch": 41, "velocity": 105, "startBeat": 0.0, "durationBeats": 1.0}],
                )
            ],
        ),
    ]
    saved = store.save_project(proj)

    # 1. Natural Korean instruction via AI Producer endpoint
    inst_res = client.post(
        f"/api/projects/{saved.id}/producer/instruct",
        json={
            "instruction": "현재 코드 진행에 맞는 4마디 신스 훅을 만들어줘. 기존 드럼과 베이스는 유지해줘.",
            "baseRevision": saved.revision,
        },
    )
    assert inst_res.status_code == 200
    body = inst_res.json()
    assert body["supported"] is True
    assert body["action"] == "composition_plan_created"
    plan = body["plan"]
    assert plan["mode"] == "loop_midi"
    assert plan["musicalIdentity"]["barCount"] == 4
    assert plan["generationStrategy"]["targetInstrument"] == "synth_hook"
    assert plan["generationStrategy"]["preserveExistingTracks"] is True

    # 2. Generate 4-bar Synth Hook MIDI Take
    gen_res = client.post(
        f"/api/projects/{saved.id}/generation/jobs",
        json={"planId": plan["id"], "seed": 123, "sync": True},
    )
    assert gen_res.status_code == 200
    take = gen_res.json()["take"]
    assert len(take["artifacts"]) == 1
    hook_art = take["artifacts"][0]
    assert hook_art["instrumentRef"] == "synth-fm-hook"
    assert len(hook_art["notes"]) >= 12
    # Must show real musical variation across bars (not identical 1-bar loop copy-paste!)
    assert take["qualityReport"]["musical"]["parts"][0]["uniqueBarPatterns"] >= 2

    # 3. Apply Take to timeline -> Drums & Bass MUST remain untouched!
    apply_res = client.post(
        f"/api/projects/{saved.id}/takes/{take['id']}/apply",
        json={"applyMode": "new_tracks"},
    )
    assert apply_res.status_code == 200
    after_apply = store.load_project(saved.id)
    assert len(after_apply.tracks) == 3
    assert after_apply.tracks[0].id == "trk_drums"
    assert after_apply.tracks[0].clips[0].notes[0].pitch == 36
    assert after_apply.tracks[1].id == "trk_bass"
    assert after_apply.tracks[1].clips[0].notes[0].pitch == 41

    hook_track = after_apply.tracks[2]
    assert hook_track.instrumentRef == "synth-fm-hook"
    hook_clip = hook_track.clips[0]
    orig_note_count = len(hook_clip.notes)

    # 4. Edit generated MIDI clip directly (add a climax note) & switch instrument voice
    cmd_res = client.post(
        f"/api/projects/{saved.id}/commands",
        json={
            "type": "midi.addNote",
            "payload": {
                "clipId": hook_clip.id,
                "note": {"id": "n_user_edit", "pitch": 77, "velocity": 118, "startBeat": 15.0, "durationBeats": 0.75},
            },
            "expectedRevision": after_apply.revision,
        },
    )
    assert cmd_res.status_code == 200
    edited_proj = store.load_project(saved.id)
    assert len(edited_proj.tracks[2].clips[0].notes) == orig_note_count + 1

    # 5. Export Stereo WAV -> verifies all 3 multi-timbre tracks (Drums + Bass + edited Synth Hook) render cleanly
    exp = renderer.export_project_wav(edited_proj, filename="test_c_hook.wav", start_beats=0.0, end_beats=16.0)
    assert exp["peakLinear"] > 0.1
    assert exp["clippedSamples"] == 0

    # 6. Undo restores pre-apply 2-track project (Drums + Bass only) cleanly!
    undo_res = mcp_tools.undo(saved.id)
    assert undo_res["undone"] is True
    after_undo = store.load_project(saved.id)
    assert len(after_undo.tracks) == 2


def test_honesty_guarantees_yue2_abc_demucs_providers_and_library(isolated_phase03_env):
    """Verify strict honesty on YuE2 ABC screening, Demucs availability, Providers & Library Catalog."""
    # 1. YuE2 ABC Resting Vocal Gate
    good_abc = "X:1\nM:4/4\nK:Fm\nV:Vocal\nz4 | z4 |\nV:Ins\nF2 A2 c2 f2 | e2 c2 A2 F2 |\n"
    ok, issues = check_resting_voice(good_abc)
    assert ok is True and issues == []

    bad_abc = "X:1\nM:4/4\nK:Fm\nV:Vocal\nF2 G2 A2 c2 |\nw: hel-lo world\nV:Ins\nF4 | c4 |\n"
    ok_bad, bad_issues = check_resting_voice(bad_abc)
    assert ok_bad is False and len(bad_issues) >= 2

    # 2. Honest engine & provider reporting
    engines = detect_generation_engines()
    assert any(e["id"] == "local-multitrack-composer" and e["available"] is True for e in engines)
    assert probe_yue2()["id"] == "yue2-native"
    demucs = probe_demucs()
    if not demucs["available"]:
        proj = store.create_project(name="Stem Check", bpm=128.0)
        stem_res = mcp_tools.separate_stems("ast_none", project_id=proj.id)
        assert stem_res["available"] is False

    provs = detect_providers()
    assert any(p["id"] == "local-music-director" and p["available"] is True for p in provs)
    assert any(p["id"] == "mcp-external" and p["available"] is True for p in provs)
    assert len(list_instruments()) >= 6

    # 3. Sample & Loop Library Intelligence
    lib_dir = engine_paths.DATA / "daw" / "library" / "loops"
    lib_dir.mkdir(parents=True, exist_ok=True)
    _make_ref_house_wav(lib_dir / "house_drums_128.wav", bpm=128.0, duration_sec=4.0)
    catalog = list_library_catalog(project_bpm=128.0)
    assert len(catalog) == 1
    assert catalog[0]["role"] == "drums"
    assert catalog[0]["isLoop"] is True
    assert catalog[0]["integratedLufs"] is not None
