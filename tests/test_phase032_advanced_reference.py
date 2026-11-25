"""Phase 03.2 Advanced Reference Intelligence Verification Suite (Tests A–E + MCP + Runtime).

All transcription, Demucs stem separation, Basic Pitch ONNX, sub-bar Chord Track,
Groove Transfer, Reference-Conditioned Composition, and Mode A Reconstruct tests run
against REAL generated studio audio and real studio recordings (never mocked!).
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import daw_server, mcp_server
from engine import paths as engine_paths
from engine.composition import create_composition_plan
from engine.daw_workspace import mcp_tools, proposals, store
from engine.generation.adapters.local_composer_adapter import execute_local_composition
from engine.generation.adapters.yue2_adapter import build_yue2_request_from_plan, check_resting_voice
from engine.instruments import synth_note_for_instrument
from engine.runtime import get_runtime_registry

client = TestClient(daw_server.app)

STUDIO_V72_WAV = engine_paths.DATA / "daw" / "library" / "studio-recordings" / "V7.2_Magnetic_Afterhours_128bpm.wav"


def _render_notes_stereo(
    notes: list[tuple[int, float, float, int]],
    instrument_ref: str,
    bpm: float,
    total_beats: float,
    sr: int = 44100,
) -> np.ndarray:
    sec_per_beat = 60.0 / bpm
    total_samples = int(round((total_beats * sec_per_beat + 0.3) * sr))
    buf = np.zeros((total_samples, 2), dtype=np.float64)
    for pitch, start_b, dur_b, vel in notes:
        voice = synth_note_for_instrument(instrument_ref, pitch, vel, dur_b * sec_per_beat, sr)
        dst = int(round(start_b * sec_per_beat * sr))
        w = min(len(voice), total_samples - dst)
        if dst >= 0 and w > 0:
            buf[dst : dst + w] += voice[:w]
    return buf.astype(np.float32)


def _synthesize_ground_truth_multitrack_wav(out_path: Path, bpm: float = 124.0, sr: int = 44100) -> Path:
    """Create a real 4-bar studio multitrack WAV with known BPM, Chords (Am -> F -> C/G -> Am), Drums, Bass & Melody."""
    total_beats = 16.0
    drum_notes: list[tuple[int, float, float, int]] = []
    for bar in range(4):
        base = bar * 4.0
        drum_notes.extend(
            [
                (36, base + 0.0, 0.25, 118),
                (38, base + 1.0, 0.25, 112),
                (36, base + 2.0, 0.25, 115),
                (36, base + 2.5, 0.25, 98),
                (38, base + 3.0, 0.25, 116),
            ]
        )
        for step in range(8):
            drum_notes.append((42, base + step * 0.5, 0.15, 86 if step % 2 == 0 else 68))

    bass_notes = [
        # Bar 1: Am (A2 = 45)
        (45, 0.0, 1.5, 110), (45, 2.0, 1.5, 106),
        # Bar 2: F (F2 = 41)
        (41, 4.0, 1.5, 110), (41, 6.0, 1.5, 106),
        # Bar 3: C (C2 = 36) beats 8-10, G (G2 = 43) beats 10-12
        (36, 8.0, 1.5, 110), (43, 10.0, 1.5, 108),
        # Bar 4: Am (A2 = 45)
        (45, 12.0, 1.5, 110), (45, 14.0, 1.5, 105),
    ]

    chord_notes = [
        # Bar 1: Am
        (57, 0.0, 3.8, 86), (60, 0.0, 3.8, 84), (64, 0.0, 3.8, 84),
        # Bar 2: F
        (53, 4.0, 3.8, 86), (57, 4.0, 3.8, 84), (60, 4.0, 3.8, 84),
        # Bar 3: C (8..10) -> G (10..12)
        (60, 8.0, 1.8, 86), (64, 8.0, 1.8, 84), (67, 8.0, 1.8, 84),
        (55, 10.0, 1.8, 86), (59, 10.0, 1.8, 84), (62, 10.0, 1.8, 84),
        # Bar 4: Am
        (57, 12.0, 3.8, 86), (60, 12.0, 3.8, 84), (64, 12.0, 3.8, 84),
    ]

    melody_notes = [
        (76, 0.5, 0.75, 108), (79, 1.5, 0.75, 110), (81, 2.5, 1.0, 114),
        (77, 4.5, 0.75, 108), (81, 5.5, 0.75, 112), (76, 6.5, 1.0, 106),
        (79, 8.5, 0.75, 110), (74, 10.5, 1.0, 108),
        (72, 12.5, 0.75, 108), (76, 13.5, 1.5, 112),
    ]

    d = _render_notes_stereo(drum_notes, "drum-kit-electronic", bpm, total_beats, sr) * 0.75
    b = _render_notes_stereo(bass_notes, "bass-fm-sub", bpm, total_beats, sr) * 0.80
    c = _render_notes_stereo(chord_notes, "keys-electric-piano", bpm, total_beats, sr) * 0.55
    m = _render_notes_stereo(melody_notes, "synth-fm-hook", bpm, total_beats, sr) * 0.65

    mix = d + b + c + m
    peak = float(np.max(np.abs(mix))) + 1e-9
    if peak > 0.88:
        mix = mix * (0.88 / peak)
    sf.write(str(out_path), mix.astype(np.float32), sr, subtype="PCM_24")
    return out_path


def _synthesize_syncopated_drum_wav(out_path: Path, bpm: float = 120.0, sr: int = 44100) -> Path:
    """Create a distinct 4-bar syncopated drum WAV (Kick 0, 1.5, 2.5; Snare 1, 3; Hats on 8ths) for TEST C."""
    total_beats = 16.0
    drum_notes: list[tuple[int, float, float, int]] = []
    for bar in range(4):
        base = bar * 4.0
        drum_notes.extend(
            [
                (36, base + 0.0, 0.2, 122),
                (38, base + 1.0, 0.2, 115),
                (36, base + 1.5, 0.2, 108),
                (36, base + 2.5, 0.2, 114),
                (38, base + 3.0, 0.2, 120),
            ]
        )
        for s in range(8):
            drum_notes.append((42, base + s * 0.5, 0.1, 88 if s % 2 == 0 else 64))
    audio = _render_notes_stereo(drum_notes, "drum-kit-electronic", bpm, total_beats, sr)
    peak = float(np.max(np.abs(audio))) + 1e-9
    audio = (audio * min(1.0, 0.88 / peak)).astype(np.float32)
    sf.write(str(out_path), audio, sr, subtype="PCM_24")
    return out_path


def _create_temp_project(name: str = "Phase032 Test", bpm: float = 124.0) -> str:
    res = client.post("/api/projects", json={"name": name, "bpm": bpm, "lengthBeats": 64.0})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_a_and_d_and_e_real_transcription_compose_and_reconstruct(tmp_path: Path):
    """TEST A (Real Demucs + Basic Pitch + Drums + Chords + ABC) + TEST D (Reference Compose) + TEST E (Mode A Reconstruct + Undo)."""
    pid = _create_temp_project("Phase032 Ground Truth", bpm=124.0)
    try:
        gt_wav = _synthesize_ground_truth_multitrack_wav(tmp_path / "gt_multitrack_124bpm.wav", bpm=124.0)

        # Import Reference
        with gt_wav.open("rb") as fh:
            imp = client.post(
                f"/api/projects/{pid}/references/import",
                files={"file": ("gt_multitrack_124bpm.wav", fh.read(), "audio/wav")},
            )
        assert imp.status_code == 200, imp.text
        ref_id = imp.json()["reference"]["id"]

        # --- TEST A: Real Demucs MPS + Basic Pitch ONNX + Drum Groove + Sub-bar Chords ---
        tr_res = client.post(f"/api/projects/{pid}/references/{ref_id}/transcribe?sync=true&useDemucs=true")
        assert tr_res.status_code == 200, tr_res.text
        ref = tr_res.json()["reference"]
        assert ref["transcriptionStatus"] == "completed"
        tr = ref["transcription"]
        bp = ref["blueprint"]

        assert bp["blueprintVersion"] in ("2.0.0", "3.0.0")
        assert len(bp["featureLocks"]) == 10
        assert len(tr["stemReferences"]) == 4
        stems_by_role = {s["role"]: s for s in tr["stemReferences"]}
        assert stems_by_role["drums"]["active"] is True
        assert stems_by_role["bass"]["active"] is True
        assert stems_by_role["other"]["active"] is True
        assert stems_by_role["vocals"]["rmsDbfs"] < -30.0  # Instrumental track -> quiet vocals stem!

        # Verify real Basic Pitch ONNX extracted real Bass & Melody MIDI notes
        assert tr["bass"]["noteCount"] >= 4
        assert tr["bass"]["pitchMin"] is not None and tr["bass"]["pitchMax"] <= 64
        assert tr["melody"]["noteCount"] >= 4
        assert tr["melody"]["pitchMin"] is not None and tr["melody"]["pitchMin"] >= 55

        # Verify real Drum & Groove extraction
        assert tr["drums"]["hasDrums"] is True
        assert tr["drums"]["hitCounts"].get("kick", 0) >= 4
        assert tr["drums"]["hitCounts"].get("snare", 0) >= 3
        assert len(tr["drums"]["patternTemplate2Bar"]) >= 6

        # Verify Sub-bar Chord Timeline & YuE2 ABC Gate PASS
        assert len(bp["chordTimeline"]) >= 3
        abc_info = bp["abcScore"]
        assert abc_info["validInstrumentalYuE2"] is True
        ok_abc, issues_abc = check_resting_voice(abc_info["abc"])
        assert ok_abc is True, issues_abc

        # Verify Separated Stem Audio Preview endpoint works!
        stem_audio = client.get(f"/api/projects/{pid}/references/{ref_id}/stems/drums/audio")
        assert stem_audio.status_code == 200
        assert stem_audio.content[:4] == b"RIFF"

        # Verify ABC endpoint
        abc_ep = client.get(f"/api/projects/{pid}/references/{ref_id}/abc?mode=reinterpret")
        assert abc_ep.status_code == 200
        assert abc_ep.json()["abcScore"]["validInstrumentalYuE2"] is True

        # --- TEST D: Mode B Reference Compose with Feature Locks + Honest 5-State Verification ---
        locks = {
            "bpm": "locked",
            "chord_progression": "locked",
            "drum_rhythm": "locked",
            "bass_groove": "reference",
            "melody": "free",
            "arrangement": "reference",
            "timbre": "reference",
            "spatial_character": "reference",
        }
        lock_patch = client.patch(
            f"/api/projects/{pid}/references/{ref_id}/locks",
            json={"featureLocks": locks},
        )
        assert lock_patch.status_code == 200

        proj_loaded = store.load_project(pid)
        plan = create_composition_plan(
            project=proj_loaded,
            instruction="이 레퍼런스의 BPM, 코드 진행, 드럼 그루브는 고정하고 새로운 하우스 멜로디로 풀 트랙 만들어줘.",
            mode="full_music",
            reference_ids=[ref_id],
            feature_locks=locks,
            reference_mode="reference_compose",
        )
        assert plan.referenceBinding.appliedFeatures.get("referenceMode") == "reference_compose"
        assert plan.referenceBinding.appliedFeatures.get("chordTimeline")
        assert plan.referenceBinding.appliedFeatures.get("drumGroovePattern")

        # Verify YuE2 Request auto-wires validated Blueprint v2 ABC score!
        yue_req = build_yue2_request_from_plan(plan, seed=42)
        assert "abc" in yue_req and "V:Vocal" in yue_req["abc"] and "V:Ins" in yue_req["abc"]

        take = execute_local_composition(
            project=proj_loaded,
            plan=plan,
            take_dir=tmp_path / "take_test_d",
            job_id="job_test_d",
            seed=77,
        )
        fv = take.qualityReport.musical["featureVerification"]
        assert fv is not None
        by_feat = {item["feature"]: item for item in fv["featureLifecycle"]}

        # Consumed & Verified features
        assert by_feat["tempoBpm"]["consumed"] is True and by_feat["tempoBpm"]["verified"] is True
        assert by_feat["chordTimeline"]["consumed"] is True and by_feat["chordTimeline"]["verified"] is True
        assert by_feat["drumGroovePattern"]["consumed"] is True and by_feat["drumGroovePattern"]["verified"] is True
        assert fv["chordMatchRatio"] >= 0.78
        assert fv["grooveHitMatchRatio"] is not None and fv["grooveHitMatchRatio"] >= 0.65

        # HONESTY INVARIANT: stereoWidthTarget & spectralCentroidTargetHz MUST NOT claim verified on MIDI synth!
        assert by_feat["stereoWidthTarget"]["consumed"] is False
        assert by_feat["stereoWidthTarget"]["verified"] is False
        assert by_feat["spectralCentroidTargetHz"]["consumed"] is False
        assert by_feat["spectralCentroidTargetHz"]["verified"] is False

        # Verify melody is genuinely NEW (not an identical copy of reference melody!)
        hook_art = next((a for a in take.artifacts if a.role == "synth_hook"), None)
        assert hook_art is not None and len(hook_art.notes) >= 6
        ref_mel_sig = [(int(n["pitch"]), round(float(n["startBeat"]), 2)) for n in tr["melody"]["notes"][:10]]
        gen_mel_sig = [(int(n["pitch"]), round(float(n["startBeat"]), 2)) for n in hook_art.notes[:10]]
        assert gen_mel_sig != ref_mel_sig

        # --- TEST E: Mode A Reconstruct + Stems Provenance + Export Safety + 1-Click Undo ---
        pre_proj = store.load_project(pid)
        pre_track_count = len(pre_proj.tracks)

        rec_res = client.post(
            f"/api/projects/{pid}/references/{ref_id}/reconstruct",
            json={
                "importChords": True,
                "importDrumsMidi": True,
                "importBassMidi": True,
                "importMelodyMidi": True,
                "importStems": True,
                "importSections": True,
            },
        )
        assert rec_res.status_code == 200, rec_res.text
        rec_data = rec_res.json()
        assert rec_data["reconstructed"] is True
        assert len(rec_data["createdTrackIds"]) >= 4  # MIDI tracks + Demucs stem tracks
        rec_proj = rec_data["project"]
        assert len(rec_proj["chordTrack"]) >= 3
        stem_tracks = [t for t in rec_proj["tracks"] if t["type"] == "stem"]
        assert len(stem_tracks) >= 2
        assert all((t.get("stemMeta") or {}).get("assetKind") == "separated_stem" for t in stem_tracks)

        # Verify original Reference audio is NEVER exported as a track!
        assert not any(t["name"] == "gt_multitrack_124bpm" for t in rec_proj["tracks"])
        exp_res = client.post(
            f"/api/projects/{pid}/export/server",
            json={"filename": "test_e_reconstruct.wav", "startBeats": 0.0, "endBeats": 8.0},
        )
        assert exp_res.status_code == 200, exp_res.text

        # Verify 1-click Undo restores pre-reconstruct state cleanly!
        undo_res = client.post(f"/api/projects/{pid}/undo")
        assert undo_res.status_code == 200
        restored = undo_res.json()["project"]
        assert len(restored["tracks"]) == pre_track_count
        assert restored["chordTrack"] == []
    finally:
        store.delete_project(pid)


def test_b_sub_bar_chord_track_lock_enforced_note_for_note(tmp_path: Path):
    """TEST B: Locked Project Chord Track with mid-bar chord change strictly governs generated Bass & Keys notes."""
    pid = _create_temp_project("Phase032 Chord Lock", bpm=120.0)
    try:
        custom_chords = [
            {"id": "ch1", "symbol": "Dm7", "startBeat": 0.0, "endBeat": 4.0, "userCorrected": True, "isEstimate": False, "locked": True},
            {"id": "ch2", "symbol": "G7", "startBeat": 4.0, "endBeat": 6.0, "userCorrected": True, "isEstimate": False, "locked": True},
            {"id": "ch3", "symbol": "Cmaj7", "startBeat": 6.0, "endBeat": 8.0, "userCorrected": True, "isEstimate": False, "locked": True},
            {"id": "ch4", "symbol": "A7", "startBeat": 8.0, "endBeat": 12.0, "userCorrected": True, "isEstimate": False, "locked": True},
            {"id": "ch5", "symbol": "Dm7", "startBeat": 12.0, "endBeat": 16.0, "userCorrected": True, "isEstimate": False, "locked": True},
        ]
        put_res = client.put(f"/api/projects/{pid}/chords", json={"chords": custom_chords, "locked": True})
        assert put_res.status_code == 200, put_res.text
        assert put_res.json()["chordTrackLocked"] is True
        assert len(put_res.json()["chordTrack"]) == 5

        proj = store.load_project(pid)
        plan = create_composition_plan(
            project=proj,
            instruction="코드 트랙 진행에 맞춘 4마디 일렉트릭 피아노와 베이스 만들어줘.",
            mode="full_music",
            use_project_chord_track=True,
        )
        # Ensure we test exact 4-bar locked chord alignment
        plan.musicalIdentity["barCount"] = 4
        take = execute_local_composition(
            project=proj,
            plan=plan,
            take_dir=tmp_path / "take_test_b",
            job_id="job_test_b",
            seed=19,
        )

        # Verify mid-bar chord change (beat 4..6 = G7 {7, 11, 2, 5}; beat 6..8 = Cmaj7 {0, 4, 7, 11})!
        bass_art = next(a for a in take.artifacts if a.role == "bass")
        g7_pcs = {7, 11, 2, 5}
        cmaj7_pcs = {0, 4, 7, 11}
        dm7_pcs = {2, 5, 9, 0}

        beat0_bass = [n for n in bass_art.notes if 0.0 <= n["startBeat"] < 4.0]
        beat4_bass = [n for n in bass_art.notes if 4.0 <= n["startBeat"] < 6.0]
        beat6_bass = [n for n in bass_art.notes if 6.0 <= n["startBeat"] < 8.0]
        assert beat0_bass and all((n["pitch"] % 12) in dm7_pcs for n in beat0_bass)
        assert beat4_bass and all((n["pitch"] % 12) in g7_pcs for n in beat4_bass)
        assert beat6_bass and all((n["pitch"] % 12) in cmaj7_pcs for n in beat6_bass)

        fv = take.qualityReport.musical["featureVerification"]
        assert fv["chordMatchRatio"] >= 0.88
        assert "chordTimeline" in fv["verifiedFeatures"]
    finally:
        store.delete_project(pid)


def test_c_real_drum_groove_transfer(tmp_path: Path):
    """TEST C: Extract syncopated drum groove from WAV -> Lock drum_rhythm -> Generate groove-matched Drum MIDI."""
    pid = _create_temp_project("Phase032 Groove Transfer", bpm=120.0)
    try:
        drum_wav = _synthesize_syncopated_drum_wav(tmp_path / "syncopated_drums_120.wav", bpm=120.0)
        with drum_wav.open("rb") as fh:
            imp = client.post(
                f"/api/projects/{pid}/references/import",
                files={"file": ("syncopated_drums_120.wav", fh.read(), "audio/wav")},
            )
        assert imp.status_code == 200
        ref_id = imp.json()["reference"]["id"]

        # Solo drum WAV -> fast transcription with real multi-band drum groove extractor
        tr_res = client.post(f"/api/projects/{pid}/references/{ref_id}/transcribe?sync=true&useDemucs=false")
        assert tr_res.status_code == 200, tr_res.text
        drums_tr = tr_res.json()["reference"]["transcription"]["drums"]
        assert drums_tr["hasDrums"] is True
        assert drums_tr["hitCounts"]["kick"] >= 6
        assert drums_tr["hitCounts"]["snare"] >= 6

        proj = store.load_project(pid)
        plan = create_composition_plan(
            project=proj,
            instruction="이 레퍼런스의 드럼 리듬 그대로 4마디 드럼 루프 만들어줘.",
            mode="loop_midi",
            target_instrument="drums",
            reference_ids=[ref_id],
            feature_locks={"bpm": "locked", "drum_rhythm": "locked"},
            reference_mode="reference_compose",
        )
        take = execute_local_composition(
            project=proj,
            plan=plan,
            take_dir=tmp_path / "take_test_c",
            job_id="job_test_c",
            seed=101,
        )
        fv = take.qualityReport.musical["featureVerification"]
        assert fv["grooveHitMatchRatio"] is not None
        assert fv["grooveHitMatchRatio"] >= 0.75
        assert "drumGroovePattern" in fv["verifiedFeatures"]
    finally:
        store.delete_project(pid)


def test_real_studio_v72_excerpt_transcription(tmp_path: Path):
    """Run real Demucs MPS + Basic Pitch ONNX transcription on a real 10s studio recording excerpt."""
    if not STUDIO_V72_WAV.is_file():
        pytest.skip("V7.2 studio master WAV not present in local library")
    data, sr = sf.read(str(STUDIO_V72_WAV), dtype="float32", always_2d=True)
    # Use a 10s groove window (20s..30s) where full drums, bass, and hook are active!
    i0 = min(len(data) - sr * 4, int(20 * sr))
    i1 = min(len(data), i0 + int(10 * sr))
    excerpt = tmp_path / "v72_groove_excerpt.wav"
    sf.write(str(excerpt), data[i0:i1], sr, subtype="PCM_24")

    pid = _create_temp_project("Phase032 V72 Real Audio", bpm=128.0)
    try:
        with excerpt.open("rb") as fh:
            imp = client.post(
                f"/api/projects/{pid}/references/import",
                files={"file": ("v72_groove_excerpt.wav", fh.read(), "audio/wav")},
            )
        assert imp.status_code == 200
        ref_id = imp.json()["reference"]["id"]

        tr_res = client.post(f"/api/projects/{pid}/references/{ref_id}/transcribe?sync=true&useDemucs=true")
        assert tr_res.status_code == 200, tr_res.text
        tr = tr_res.json()["reference"]["transcription"]
        assert len(tr["stemReferences"]) == 4
        assert tr["bass"]["noteCount"] >= 4
        assert len(tr["chordTimeline"]) >= 2
        assert tr["abcScore"]["validInstrumentalYuE2"] is True
    finally:
        store.delete_project(pid)


def test_phase032_nl_routing_runtime_honesty_and_68_mcp_tools():
    """Verify Korean NL routing, honest Runtime Registry states (Basic Pitch/Demucs vs SheetSage2), and all 68 MCP tools."""
    pid = _create_temp_project("Phase032 NL & MCP", bpm=128.0)
    try:
        proj = store.load_project(pid)
        proj.references.append({"id": "ref_fake", "name": "DemoRef"})

        r1 = proposals.interpret_producer_instruction(proj, "이 레퍼런스 정밀 채보해줘", active_reference_id="ref_fake")
        assert r1["action"] == "transcribe_reference"

        r2 = proposals.interpret_producer_instruction(proj, "코드 진행만 가져와줘", active_reference_id="ref_fake")
        assert r2["action"] == "import_reference_chords"

        r3 = proposals.interpret_producer_instruction(proj, "내가 만든 음악을 분석해서 MIDI 세션으로 재구성해줘", active_reference_id="ref_fake")
        assert r3["action"] == "reconstruct_reference"

        r4 = proposals.interpret_producer_instruction(
            proj,
            "이 곡과 같은 BPM과 코드 진행으로 드럼 리듬은 유지하고 새로운 멜로디 만들어줘",
            active_reference_id="ref_fake",
        )
        assert r4["action"] == "composition_plan"
        assert r4["featureLocks"]["bpm"] == "locked"
        assert r4["featureLocks"]["chord_progression"] == "locked"
        assert r4["featureLocks"]["drum_rhythm"] == "locked"
        assert r4["featureLocks"]["melody"] == "free"

        # Runtime Registry Honesty Check
        reg = get_runtime_registry()
        assert reg["transcriptionReady"] is True
        by_id = {e["id"]: e for e in reg["engines"]}
        assert by_id["basic-pitch-onnx"]["available"] is True
        assert by_id["demucs-htdemucs"]["available"] is True
        assert by_id["sheetsage2"]["state"] == "uninstalled"
        assert "CC BY-NC 4.0" in by_id["sheetsage2"]["statusNoteEn"]

        # MCP 68 tools + Capabilities Schema 1.4.0
        tools = asyncio.run(mcp_server.server.list_tools())
        tool_names = {t.name for t in tools}
        assert len(tools) >= 68
        for expected_tool in (
            "daw.transcribe_reference",
            "daw.get_chord_track",
            "daw.set_chord_track",
            "daw.update_reference_locks",
            "daw.import_reference_transcription",
            "daw.reconstruct_from_reference",
            "daw.get_reference_abc_score",
        ):
            assert expected_tool in tool_names

        caps = mcp_tools.get_capabilities()
        assert caps["schemaVersion"] == "1.4.0"
        assert "advancedReferenceIntelligence" in caps["supported"]
    finally:
        store.delete_project(pid)
