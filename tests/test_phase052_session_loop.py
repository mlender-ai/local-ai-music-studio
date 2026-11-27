"""Phase 05.2 Automated Verification Suite: AI Session & Loop Production.

Covers:
1. Honest empirical YuE2 solo capability matrix & 6-family Performance Vocabulary
2. Layered Session workflow (Drums -> Bass -> Rhodes -> Guitar A/B Take Lanes -> Percussion -> Guitar Solo -> Bridge + Transition)
   with cryptographic Layer Protection & 3-mode level-matched previews
3. Loop Integrity, Click-free Bar Alignment, Tempo Drift Detection & Jazz-aware Harmonic Compatibility
4. Secondary performers (D2/D3, B2/B3, P2/P3, PC1/PC3, Synth) & Structured Variation Engine
5. Persistent Studio Session Library + Taste Profile Feedback Sync
6. Section 50 Natural-Language AI Producer Routing + Phase 05.1 YuE2 First protection
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine.daw_workspace import mcp_tools, store
from engine.session_lab import (
    align_audio_loop_to_bars,
    build_session_context,
    check_tempo_alignment,
    compose_bass_performance,
    compose_drum_performance,
    compose_guitar_performance,
    compose_keys_performance,
    compose_percussion_performance,
    compose_synth_performance,
    compute_layer_integrity_hash,
    evaluate_harmonic_compatibility,
    get_instrument_capability_matrix,
    save_session_asset,
    search_session_assets,
    submit_performance_feedback,
    validate_loop_integrity,
    vary_layer_notes,
)

client = TestClient(app)


def test_01_capability_matrix_and_vocabulary_honesty():
    """GATE 0 & Section 8: Empirical YuE2 capability matrix and honest UNSUPPORTED markers."""
    resp = client.get("/api/session-lab/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["yue2InstrumentFocused"]["full_band_instrumental"]["status"] == "VERIFIED"
    assert data["yue2InstrumentFocused"]["accompaniment_free_overdub"]["status"] == "UNSUPPORTED"
    assert len(data["strategies"]) == 5
    for fam in ("guitar", "keys", "bass", "drums", "percussion", "synth"):
        assert fam in data["vocabulary"]
    assert data["vocabulary"]["guitar"]["vibrato_authentic_finger"]["supportStatus"] == "UNSUPPORTED"

    caps = mcp_tools.get_capabilities()
    assert caps["phase"] == "04"  # Backward-compatible Phase 04 contract
    assert caps["currentPhase"] == "05.2"
    assert "sessionLoopProduction" in caps["supported"]


def test_02_layered_session_build_take_lanes_and_layer_protection():
    """GATES 1–7: Full Late Night layered workflow with cryptographic Layer Protection & Take Lane A/B."""
    proj = store.create_project(name="Test Late Night Session", bpm=90.0, with_default_tracks=False)
    try:
        # Lock shared D minor Neo-Soul Chord Timeline
        ch_res = client.post(f"/api/projects/{proj.id}/session-lab/chords", json={"key": "D minor", "lock": True})
        assert ch_res.status_code == 200
        assert ch_res.json()["chordTrackLocked"] is True
        assert len(ch_res.json()["chordTrack"]) == 8

        # Layer 01: Drums (D1 Pocket Groove)
        d_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "drums", "performanceType": "pocket_groove", "bars": 8, "seed": 101},
        )
        assert d_res.status_code == 200
        d_data = d_res.json()
        drum_tid = d_data["trackId"]
        assert d_data["instrumentUsed"]["instrumentRef"] == "pro-drum-rack"
        assert d_data["instrumentUsed"]["qualityTier"] != "PREVIEW"
        assert d_data["instrumentUsed"]["qualityTier"] in ("PRODUCTION", "PRODUCTION_CANDIDATE")
        assert d_data["qualityGate"]["gates"]["engineIntegrity"]["status"] == "PASS"
        assert d_data["qualityGate"]["gates"]["performanceIntegrity"]["metrics"]["uniqueBarPatterns"] >= 4
        assert d_data["qualityGate"]["gates"]["userListening"]["status"] == "UNVERIFIED"
        assert d_data["qualityGate"]["humanListeningRequired"] is True
        assert Path(d_data["previewAudio"]["solo"]["path"]).is_file()
        assert Path(d_data["previewAudio"]["in_context"]["path"]).is_file()

        # Approve & Lock Drums -> record SHA-256 hash
        lock_d = client.post(f"/api/projects/{proj.id}/session-lab/layers/{drum_tid}/state", json={"state": "Locked"})
        assert lock_d.status_code == 200
        drums_hash = lock_d.json()["layerState"]["integrityHash"]

        # Verify attempting to overwrite Locked Drums directly is BLOCKED!
        blocked = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "drums", "targetTrackId": drum_tid, "asAlternativeTake": False},
        )
        assert blocked.status_code == 400

        # Layer 02: Bass (B1 Kick-Locked Pocket) -> Drums MUST stay cryptographically untouched!
        b_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "bass", "performanceType": "pocket_groove", "bars": 8, "seed": 202},
        )
        assert b_res.status_code == 200
        b_data = b_res.json()
        bass_tid = b_data["trackId"]
        assert b_data["instrumentUsed"]["instrumentRef"] == "sf-bass-electric"
        assert b_data["protectedLayersCheck"]["allProtectedIntact"] is True
        assert drum_tid in b_data["protectedLayersCheck"]["verifiedProtectedTrackIds"]
        assert b_data["qualityGate"]["gates"]["layerIntegrity"]["harmonicCompatibility"]["status"] in ("STRONG_MATCH", "REFERENCE_MATCH")
        assert compute_layer_integrity_hash(store.load_project(proj.id), drum_tid) == drums_hash

        # Lock Bass
        bass_hash = client.post(f"/api/projects/{proj.id}/session-lab/layers/{bass_tid}/state", json={"state": "Locked"}).json()["layerState"]["integrityHash"]

        # Layer 03: Rhodes (P1 Neo Soul Rootless Comping)
        k_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "keys", "performanceType": "neo_soul_comping", "bars": 8, "seed": 303},
        )
        assert k_res.status_code == 200
        k_data = k_res.json()
        keys_tid = k_data["trackId"]
        assert k_data["instrumentUsed"]["instrumentRef"] == "sf-ep-rhodes"
        assert k_data["protectedLayersCheck"]["allProtectedIntact"] is True
        keys_hash = client.post(f"/api/projects/{proj.id}/session-lab/layers/{keys_tid}/state", json={"state": "Locked"}).json()["layerState"]["integrityHash"]

        # Layer 04: Guitar Take A (Funk Riff) + Take B (Clean Melodic) on SAME Guitar track!
        ga_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "guitar", "performanceType": "funk_riff", "bars": 8, "seed": 404},
        )
        assert ga_res.status_code == 200
        ga_data = ga_res.json()
        gtr_tid = ga_data["trackId"]
        lane_a_id = ga_data["laneId"]
        assert ga_data["instrumentUsed"]["instrumentRef"] == "sf-guitar-clean"
        assert ga_data["instrumentUsed"]["preset"] == "muted_funk"

        gb_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={
                "targetInstrument": "guitar",
                "performanceType": "clean_melodic",
                "bars": 8,
                "asAlternativeTake": True,
                "targetTrackId": gtr_tid,
                "seed": 405,
            },
        )
        assert gb_res.status_code == 200
        gb_data = gb_res.json()
        assert gb_data["trackId"] == gtr_tid
        lane_b_id = gb_data["laneId"]
        assert lane_b_id != lane_a_id

        # Check Take Lanes cleanly stored with ONLY 1 active clip (ZERO double-playing!)
        p_mid = store.load_project(proj.id)
        gtr_trk = next(t for t in p_mid.tracks if t.id == gtr_tid)
        assert len(gtr_trk.takeLanes) == 2
        assert len(gtr_trk.clips) == 1
        assert gtr_trk.instrumentConfig.get("preset") == "jazz_hollow"

        # Switch back to Take A (Funk) non-destructively
        sw_res = client.post(f"/api/projects/{proj.id}/session-lab/layers/{gtr_tid}/takes/{lane_a_id}/activate")
        assert sw_res.status_code == 200
        assert sw_res.json()["performanceType"] == "funk_riff"
        p_sw = store.load_project(proj.id)
        assert next(t for t in p_sw.tracks if t.id == gtr_tid).instrumentConfig.get("preset") == "muted_funk"
        gtr_hash = client.post(f"/api/projects/{proj.id}/session-lab/layers/{gtr_tid}/state", json={"state": "Approved"}).json()["layerState"]["integrityHash"]

        # Layer 05: Percussion (PC2 Syncopated Riff — real SF3 GM Percussion, NEVER Kick/Snare duplication!)
        pc_res = client.post(
            f"/api/projects/{proj.id}/session-lab/layers/generate",
            json={"targetInstrument": "percussion", "performanceType": "syncopated_riff", "bars": 8, "seed": 505},
        )
        assert pc_res.status_code == 200
        pc_data = pc_res.json()
        perc_tid = pc_data["trackId"]
        assert pc_data["instrumentUsed"]["preset"] == "percussion-latin-studio"
        p_perc = store.load_project(proj.id)
        perc_pitches = {n.pitch for c in next(t for t in p_perc.tracks if t.id == perc_tid).clips for n in c.notes}
        assert 36 not in perc_pitches and 38 not in perc_pitches  # Zero Kick/Snare copy!
        assert 70 in perc_pitches  # Real Shaker present

        # Layer 06: Expressive Guitar Solo (with real pitchBendSemitones!)
        solo_res = client.post(
            f"/api/projects/{proj.id}/session-lab/solo",
            json={"instrument": "guitar", "bars": 8, "seed": 606},
        )
        assert solo_res.status_code == 200
        s_data = solo_res.json()
        assert s_data["qualityGate"]["gates"]["performanceIntegrity"]["metrics"]["pitchBendEvents"] >= 4
        assert s_data["qualityGate"]["gates"]["performanceIntegrity"]["metrics"]["uniqueDurations"] >= 3

        # Layer Preview HTTP endpoint serves real WAVs across all 3 modes (solo, in_context, before_mix)
        for mode in ("solo", "in_context", "before_mix"):
            pr = client.get(f"/api/projects/{proj.id}/session-lab/layers/{s_data['trackId']}/preview?mode={mode}")
            assert pr.status_code == 200
            assert pr.content[:4] == b"RIFF"

        # Bridge + Transition (Bars 9–12, beats 32–48) -> Main Groove protected hashes remain 100% IDENTICAL!
        br_res = client.post(
            f"/api/projects/{proj.id}/session-lab/bridge",
            json={"bars": 4, "includeTransition": True, "seed": 707},
        )
        assert br_res.status_code == 200
        br_data = br_res.json()
        assert br_data["protectedLayersCheck"]["allProtectedIntact"] is True
        assert len(br_data["bridgeChords"]) == 4
        assert br_data["bridgeChords"][0]["symbol"] == "Bbmaj9"
        assert len(br_data["transitionTrackIds"]) == 2
        assert len(br_data["bridgeTrackIds"]) == 5

        final_proj = store.load_project(proj.id)
        assert compute_layer_integrity_hash(final_proj, drum_tid) == drums_hash
        assert compute_layer_integrity_hash(final_proj, bass_tid) == bass_hash
        assert compute_layer_integrity_hash(final_proj, keys_tid) == keys_hash
        assert compute_layer_integrity_hash(final_proj, gtr_tid) == gtr_hash
        assert any(s.name == "BRIDGE" for s in final_proj.sections)
        assert len(final_proj.chordTrack) == 12  # 8 Main + 4 Bridge chords
    finally:
        store.delete_project(proj.id)


def test_03_loop_integrity_tempo_drift_and_harmonic_compatibility(tmp_path):
    """Part D & F: Honest loop alignment, tempo drift blocking, and jazz-tension-aware harmony check."""
    sr = 48000
    bpm = 90.0
    bars = 4
    expected_sec = bars * 4.0 * (60.0 / bpm)  # 10.667s
    # Create a WAV with 250ms leading silence + extra tail + sine tone
    t = np.linspace(0.0, expected_sec + 0.5, int(sr * (expected_sec + 0.5)), endpoint=False)
    sig = 0.25 * np.sin(2.0 * np.pi * 220.0 * t).astype(np.float32)
    stereo = np.stack([sig, sig], axis=1)
    pad = np.zeros((int(0.25 * sr), 2), dtype=np.float32)
    raw = np.vstack([pad, stereo])
    raw_wav = tmp_path / "raw_loop.wav"
    sf.write(str(raw_wav), raw, sr, subtype="PCM_24")
    orig_bytes = raw_wav.read_bytes()

    aligned_wav = tmp_path / "aligned_loop.wav"
    res = align_audio_loop_to_bars(raw_wav, aligned_wav, target_bpm=bpm, target_bars=bars)
    assert raw_wav.read_bytes() == orig_bytes  # Original audio preserved untouched!
    assert res["trimmedLeadingMs"] > 200.0
    assert res["loopIntegrity"]["exactBarBoundaryMatch"] is True
    assert res["loopIntegrity"]["seamClickRisk"] is False

    # Tempo Drift detection (never lies via metadata!)
    ok_drift = check_tempo_alignment(90.0, 90.0, bars=8)
    assert ok_drift["status"] == "ALIGNED"
    assert ok_drift["safeForDirectLoopLayering"] is True

    bad_drift = check_tempo_alignment(90.8, 90.0, bars=8)
    assert bad_drift["status"] == "DRIFT_RISK"
    assert bad_drift["safeForDirectLoopLayering"] is False
    assert bad_drift["driftOverLoopMs"] > 150.0

    # Harmonic compatibility: jazz 9th (E=64) over Dm9 is compatible, long Db (61) is clash!
    chords = [{"symbol": "Dm9", "startBeat": 0.0, "endBeat": 4.0}]
    jazz_notes = [
        {"pitch": 62, "startBeat": 0.0, "durationBeats": 1.0},  # D (root)
        {"pitch": 65, "startBeat": 1.0, "durationBeats": 1.0},  # F (b3)
        {"pitch": 64, "startBeat": 2.0, "durationBeats": 1.0},  # E (9th tension!)
        {"pitch": 72, "startBeat": 3.0, "durationBeats": 1.0},  # C (b7)
    ]
    h_ok = evaluate_harmonic_compatibility(jazz_notes, chord_timeline=chords, key="D minor", scale="dorian")
    assert h_ok["status"] == "STRONG_MATCH"
    assert h_ok["clashNoteCount"] == 0

    clash_notes = [
        {"pitch": 61, "startBeat": 0.0, "durationBeats": 2.0},  # C# long clash on Dm9
        {"pitch": 66, "startBeat": 2.0, "durationBeats": 2.0},  # F# long clash on Dm9
    ]
    h_bad = evaluate_harmonic_compatibility(clash_notes, chord_timeline=chords, key="D minor", scale="dorian")
    assert h_bad["status"] == "PARTIAL_MISMATCH"
    assert h_bad["clashNoteCount"] == 2


def test_04_secondary_performers_and_variation_engine():
    """Part B & E: Verify all secondary presets (D2/D3, B2/B3, P2/P3, PC1/PC3, Synth) & Variation diff."""
    proj = store.create_project(name="Perf Test", bpm=90.0, with_default_tracks=False)
    try:
        ctx = build_session_context(proj)
        for fn, ptypes in [
            (compose_drum_performance, ("syncopated_hiphop", "drum_fill_transition")),
            (compose_bass_performance, ("syncopated_riff", "melodic_bassline")),
            (compose_keys_performance, ("piano_melody", "piano_solo")),
            (compose_guitar_performance, ("funk_riff", "clean_melodic", "solo")),
            (compose_percussion_performance, ("subtle_layer", "percussion_break")),
            (compose_synth_performance, ("lead_solo", "textural_pad")),
        ]:
            for pt in ptypes:
                notes, meta = fn(ctx, performance_type=pt, bars=8, seed=42)
                assert len(notes) >= 12, f"{pt} produced too few notes"
                assert meta

        # Structured variation preserves core groove & reports diff
        g_notes, _ = compose_guitar_performance(ctx, performance_type="clean_melodic", bars=8, seed=11)
        varied, rep = vary_layer_notes(g_notes, role="guitar", intensity="moderate", style_hint="펑키하게", ctx=ctx, seed=22)
        assert len(varied) >= 20
        assert rep["variationType"] == "funk_syncopation"
        assert len(rep["preservedElements"]) >= 1
        assert len(rep["changedElements"]) >= 1
    finally:
        store.delete_project(proj.id)


def test_05_session_library_persistence_and_taste_feedback_sync(monkeypatch, tmp_path):
    """Part G: Persistent Studio Session Library save/search/feedback linked to Taste Profile."""
    monkeypatch.setenv("DAW_SESSION_LIBRARY_PATH", str(tmp_path / "session_lib.json"))
    monkeypatch.setenv("DAW_TASTE_PROFILE_PATH", str(tmp_path / "taste_prof.json"))

    saved = save_session_asset(
        name="Late Night Funk Guitar Riff 90BPM Dm",
        category="guitar_funk_riff",
        instrument="guitar",
        performance_type="funk_riff",
        bpm=90.0,
        key="D minor",
        bars=8,
        chord_progression=["Dm9", "G13", "Cmaj9", "A7"],
        instrument_ref="sf-guitar-clean",
        instrument_preset="muted_funk",
        tags=["funk", "neosoul", "late_night"],
        recipe={"promptTemplate": "펑키한 뮤트 기타 리프 추가해줘"},
    )
    asset_id = saved["asset"]["id"]
    assert saved["recipe"] is not None

    found = search_session_assets(instrument="guitar", key="D minor", bpm_min=85.0, bpm_max=95.0)
    assert found["matchedCount"] == 1
    assert found["assets"][0]["id"] == asset_id

    fb = submit_performance_feedback(
        asset_id,
        rating="good",
        comment="리듬과 톤이 세션에 잘 붙음",
        detail_tags=["tight_pocket", "clean_tone"],
    )
    assert fb["rating"] == "good"
    assert fb["tasteProfileUpdated"] is True
    assert fb["tasteFeedbackCount"] >= 2


def test_06_natural_language_section50_routing_and_phase051_protection():
    """Phase 05.3 Section 18: General musical performance prompts route to YuE2 Native Performance Mode by default,
    while explicit editable MIDI / layer prompts route cleanly to Phase 05.2 session_layer_action!"""
    proj = store.create_project(name="NL Routing Test", bpm=90.0, with_default_tracks=False)
    try:
        # 1. General musical performance prompts -> Native Performance Mode (`composition_plan_created`, `yue2-native`!)
        native_perf_prompts = [
            "기타 리프 만들어줘.",
            "피아노 솔로 만들어줘.",
            "독특한 드럼 그루브 만들어줘.",
            "베이스 리프 만들어줘.",
            "이제 브릿지를 만들어줘.",
            "인디 록 만들어줘.",
            "세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘.",
        ]
        for text in native_perf_prompts:
            r = client.post(f"/api/projects/{proj.id}/producer/instruct", json={"instruction": text})
            assert r.status_code == 200, f"Failed on prompt: {text}"
            body = r.json()
            assert body["supported"] is True
            assert body["action"] == "composition_plan_created", f"Prompt '{text}' routed to {body['action']}"
            assert body["plan"]["generationStrategy"]["actualEngine"] == "yue2-native"

        # 2. Explicit editable MIDI / layer requests -> Phase 05.2 Session Layer Action (opt-in preserved!)
        explicit_midi_prompts = [
            ("편집 가능한 MIDI 드럼 루프 만들어줘.", "session_layer_created", "drums", None),
            ("MIDI 레이어로 베이스 추가해줘.", "session_layer_created", "bass", None),
            ("현재 드럼과 베이스에 어울리는 Neo Soul 건반 레이어 추가해줘.", "session_layer_created", "keys", "neo_soul_comping"),
            ("기타 리프를 펑키하게 테이크로 바꿔줘.", "session_layer_created", "guitar", "funk_riff"),
            ("MIDI 퍼커션 레이어 독특하게 추가해줘.", "session_layer_created", "percussion", "syncopated_riff"),
            ("편집 가능한 MIDI 기타 솔로 넣어줘.", "session_layer_created", "guitar", "solo"),
            ("편집 가능한 MIDI 브릿지를 만들어줘.", "session_bridge_created", None, None),
        ]
        for text, expected_action, expected_inst, expected_perf in explicit_midi_prompts:
            r = client.post(f"/api/projects/{proj.id}/producer/instruct", json={"instruction": text})
            assert r.status_code == 200, f"Failed on prompt: {text}"
            body = r.json()
            assert body["supported"] is True
            assert body["action"] == expected_action, f"Prompt '{text}' routed to {body['action']}"
            if expected_inst:
                assert body["layerResult"]["targetInstrument"] == expected_inst
            if expected_perf:
                assert body["layerResult"]["performanceType"] == expected_perf
    finally:
        store.delete_project(proj.id)
