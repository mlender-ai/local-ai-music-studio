"""Phase 05.1 · Native Music Engine Integration & Permanent Production Policy Tests (TESTS 03–08 Automated Gate)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine.composition.director import create_composition_plan
from engine.daw_workspace import commands, mcp_tools, proposals, store
from engine.fx.studio_preview import get_studio_preview_status, render_studio_preview
from engine.generation.adapters.yue2_adapter import (
    build_yue2_request_from_plan,
    check_resting_voice,
    compile_instrumental_abc_for_plan,
    normalize_chord_for_yue2,
    screen_vocal_leakage,
)
from engine.production import (
    evaluate_five_gate_quality,
    get_full_production_policy_snapshot,
    get_taste_profile,
    record_user_feedback,
    reset_taste_profile,
    resolve_production_instrument,
    update_taste_profile,
    validate_instrument_selection,
)

client = TestClient(app)


def _make_sine_wav_bytes(tmp_path: Path, name: str = "native_test.wav", dur_sec: float = 2.0, sr: int = 48000) -> bytes:
    t = np.linspace(0.0, dur_sec, int(sr * dur_sec), endpoint=False, dtype=np.float32)
    # Warm low-mid heavy chord so acoustic diagnosis sees realistic spectral content
    l = 0.25 * np.sin(2 * math.pi * 293.66 * t) + 0.20 * np.sin(2 * math.pi * 349.23 * t) + 0.12 * np.sin(2 * math.pi * 440.0 * t)
    r = 0.24 * np.sin(2 * math.pi * 293.66 * t + 0.2) + 0.19 * np.sin(2 * math.pi * 349.23 * t + 0.1) + 0.13 * np.sin(2 * math.pi * 523.25 * t)
    pcm = np.stack([l, r], axis=1).astype(np.float32)
    p = tmp_path / name
    sf.write(str(p), pcm, sr, subtype="PCM_24")
    return p.read_bytes()


def test_permanent_policy_files_rest_and_mcp_parity():
    snap = get_full_production_policy_snapshot()
    pol = snap["policy"]
    assert pol["defaultFullMusicEngine"] == "yue2-native"
    assert pol["allowSilentMidiFallback"] is False
    assert pol["allowPreviewInstrumentsInProduction"] is False
    assert pol["preserveNativeAudio"] is True
    assert pol["instrumentalByDefault"] is True

    rest_resp = client.get("/api/production/policy")
    assert rest_resp.status_code == 200
    assert rest_resp.json()["policy"]["defaultFullMusicEngine"] == "yue2-native"

    mcp_pol = mcp_tools.get_production_policy()
    assert mcp_pol["policy"]["allowSilentMidiFallback"] is False

    caps = mcp_tools.get_capabilities()
    assert caps["currentPhase"] in ("05.1", "05.2")
    assert caps["productionPolicy"]["policy"]["defaultFullMusicEngine"] == "yue2-native"


def test_03_no_silent_midi_fallback_when_yue2_unavailable(monkeypatch, tmp_path):
    """TEST 03: When YuE2 is unavailable (simulated without deleting any real models), NEVER fall back to MIDI!"""
    fake_cfg = tmp_path / "empty_runtime.json"
    fake_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DAW_RUNTIME_CONFIG", str(fake_cfg))
    monkeypatch.setenv("DAW_SHARED_RUNTIME_DIR", str(tmp_path / "no_runtime"))
    monkeypatch.delenv("YUE2_BIN", raising=False)
    monkeypatch.delenv("YUE2_MODEL_PATH", raising=False)
    monkeypatch.delenv("YUE2_VAE_PATH", raising=False)
    # Also ensure default engine_paths.RUNTIME doesn't have binaries in this test scope
    import engine.runtime.registry as reg_mod

    monkeypatch.setattr(reg_mod, "_candidate_runtime_roots", lambda _ov: [tmp_path / "no_runtime"])

    proj = store.create_project(name="Test 03 No Silent Fallback", bpm=90.0, with_default_tracks=False)
    try:
        # 1. REST auto full_music -> MUST block honestly and NOT create any MIDI take!
        res = client.post(
            f"/api/projects/{proj.id}/generation/jobs",
            json={
                "instruction": "세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘.",
                "mode": "full_music",
                "engine": "auto",
                "sync": True,
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["engineUnavailable"] is True
        assert body["silentFallbackBlocked"] is True
        assert body["requestedEngine"] == "yue2-native"
        assert len(body.get("alternatives", [])) >= 1
        assert len(store.load_project(proj.id).takes) == 0

        # 2. MCP generate_music -> MUST enforce the exact same policy!
        mcp_res = mcp_tools.generate_music(
            instruction="인디 록 만들어줘.",
            engine_choice="auto",
            sync=True,
            project_id=proj.id,
        )
        assert mcp_res["engineUnavailable"] is True
        assert mcp_res["silentFallbackBlocked"] is True
        assert len(store.load_project(proj.id).takes) == 0

        # 3. Explicit Editable MIDI choice DOES work and uses PRODUCTION_CANDIDATE instruments (zero PREVIEW!)
        midi_res = client.post(
            f"/api/projects/{proj.id}/generation/jobs",
            json={
                "instruction": "4마디 R&B 코드 스케치 (4마디)",
                "mode": "full_music",
                "engine": "local-multitrack-composer",
                "productionMode": "editable_midi",
                "sync": True,
            },
        )
        assert midi_res.status_code == 200
        take = midi_res.json()["take"]
        assert take["provenance"]["engine"] == "local-multitrack-composer"
        for art in take["artifacts"]:
            assert art["instrumentRef"] not in (
                "drum-kit-electronic",
                "bass-fm-sub",
                "keys-electric-ep",
                "guitar-clean-pluck",
                "synth-fm-hook",
                "pad-warm-analog",
                "basic-poly-synth",
            )
    finally:
        store.delete_project(proj.id)


def test_04_instrument_quality_policy_across_ui_rest_and_mcp():
    """TEST 04: PREVIEW instruments are explicitly tagged and blocked from automatic production selection."""
    preview_ids = {
        "drum-kit-electronic",
        "bass-fm-sub",
        "keys-electric-ep",
        "guitar-clean-pluck",
        "synth-fm-hook",
        "pad-warm-analog",
        "basic-poly-synth",
    }

    # REST Catalog check
    cat_resp = client.get("/api/instruments/catalog")
    assert cat_resp.status_code == 200
    by_id = {x["id"]: x for x in cat_resp.json()["instruments"]}
    for pid in preview_ids:
        assert by_id[pid]["qualityTier"] == "PREVIEW"
        assert by_id[pid]["autoSelectInProduction"] is False

    # REST Validate endpoint blocks PREVIEW by default, allows only on explicit override
    blocked = client.post("/api/production/instruments/validate", json={"instrumentRef": "guitar-clean-pluck"})
    assert blocked.status_code == 200
    assert blocked.json()["allowed"] is False
    allowed = client.post(
        "/api/production/instruments/validate",
        json={"instrumentRef": "guitar-clean-pluck", "allowPreviewInstruments": True},
    )
    assert allowed.json()["allowed"] is True

    # Production Instrument Resolver never auto-picks PREVIEW and reports honest guitar limitation
    for role in ("drums", "bass", "keys", "guitar", "synth_hook", "pad"):
        resolved = resolve_production_instrument(role, genre="rnb_neosoul")
        assert resolved["instrumentRef"] not in preview_ids
        assert resolved["qualityTier"] in ("PRODUCTION_CANDIDATE", "USER_APPROVED")
    guitar_res = resolve_production_instrument("guitar", genre="rnb_neosoul")
    assert guitar_res.get("limitationNoteKo")

    # MCP assign_instrument_preset blocks PREVIEW unless allow_preview=True
    proj = store.create_project(name="Test 04 Instrument Policy", bpm=90.0, with_default_tracks=True)
    try:
        midi_trk = next(t for t in proj.tracks if t.type == "midi")
        with pytest.raises(ValueError, match="PREVIEW"):
            mcp_tools.assign_instrument_preset(
                track_id=midi_trk.id,
                instrument_ref="guitar-clean-pluck",
                project_id=proj.id,
            )
        # Explicit opt-in succeeds
        ok_res = mcp_tools.assign_instrument_preset(
            track_id=midi_trk.id,
            instrument_ref="guitar-clean-pluck",
            project_id=proj.id,
            allow_preview=True,
        )
        assert ok_res["applied"] is True
    finally:
        store.delete_project(proj.id)


def test_official_yue2_abc_compiler_korean_negation_and_honest_vocal_qa():
    assert normalize_chord_for_yue2("Dm9") == "Dm7"
    assert normalize_chord_for_yue2("G13") == "G7"
    assert normalize_chord_for_yue2("Cmaj9") == "Cmaj7"
    assert normalize_chord_for_yue2("A7(b9)") == "A7"

    proj = store.create_project(name="Test ABC & Negation", bpm=90.0, with_default_tracks=False)
    try:
        plan = create_composition_plan(
            project=proj,
            instruction="보컬과 허밍은 전혀 사용하지 말고 세련된 R&B 힙합 인스트루멘탈을 짧게 만들어줘.",
        )
        assert plan.musicalIdentity["genre"] == "rnb_neosoul"
        assert plan.musicalIdentity["instrumentalOnly"] is True
        assert 15.0 <= float(plan.musicalIdentity["durationSec"]) <= 30.0
        assert plan.generationStrategy["productionMode"] == "neural_audio"

        for cot_mode in ("melody", "full"):
            compiled = compile_instrumental_abc_for_plan(plan, cot=cot_mode)
            assert compiled["validInstrumentalYuE2"] is True
            assert compiled["source"] in ("official_v6_compile_score", "builtin_resting_voice_abc_compiler")
            ok, issues = check_resting_voice(compiled["abc"])
            assert ok, f"ABC failed resting voice check: {issues}"

        req = build_yue2_request_from_plan(plan, seed=1185, cot="melody")
        assert "abc" in req and "V:Vocal" in req["abc"] or "V: Vocal" in req["abc"]
        assert 15 <= req["duration"] <= 30

        # Honest vocal screening: neural audio WITHOUT running Demucs MUST return UNCERTAIN, never PASS!
        sr = 48000
        t = np.linspace(0, 2.0, sr * 2, dtype=np.float32)
        synth_wave = np.stack([0.2 * np.sin(2 * math.pi * 220 * t), 0.2 * np.sin(2 * math.pi * 330 * t)], axis=1)
        qa = screen_vocal_leakage(synth_wave, sr, source_kind="neural_audio", use_demucs=False)
        assert qa["status"] == "UNCERTAIN"
        assert qa["autoApprovedInstrumental"] is False
    finally:
        store.delete_project(proj.id)


def test_05_native_audio_sound_design_and_studio_preview_parity(tmp_path):
    """TEST 05: Native audio gets gentle mix-safe FX + Studio Preview transitions Original -> Realtime -> Studio -> Outdated."""
    proj = store.create_project(name="Test 05 Studio Preview", bpm=90.0, length_beats=8.0, with_default_tracks=False)
    try:
        wav_bytes = _make_sine_wav_bytes(tmp_path, dur_sec=2.0)
        asset, _ = store.import_asset_bytes(
            project_id=proj.id,
            filename="yue2_native_short.wav",
            raw_bytes=wav_bytes,
            kind_hint="audio",
            source="yue2-native",
        )
        loaded = store.load_project(proj.id)
        loaded = commands.apply_command(
            loaded,
            "track.add",
            {
                "id": "trk_native_01",
                "name": "R&B Native Mix",
                "type": "audio",
                "stemMeta": {"assetKind": "native_audio_original", "protectedFromMidiOverwrite": True, "sourceEngine": "yue2-native"},
            },
        )
        loaded = commands.apply_command(
            loaded,
            "clip.add",
            {
                "trackId": "trk_native_01",
                "clip": {
                    "id": "clp_native_01",
                    "name": "R&B Native Mix",
                    "type": "audio",
                    "assetId": asset.id,
                    "timelineStartBeats": 0.0,
                    "durationBeats": 3.0,
                    "sourceOffsetSec": 0.0,
                    "sourceDurationSec": 2.0,
                },
            },
        )
        store.save_project(loaded, expected_revision=loaded.revision)

        # 1. Pure Native Audio -> Original Audio status!
        st0 = get_studio_preview_status(proj.id)
        assert st0["previewStatus"] == "Original Audio"
        assert st0["upToDate"] is True

        # 2. Natural-language sound design on Native Audio mix -> mix-safe EQ + Natural Room send!
        resp = client.post(
            f"/api/projects/{proj.id}/producer/instruct",
            json={"instruction": "전체적으로 먹먹하지 않게 정리하고 공간감을 자연스럽게 만들어줘."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "proposal_created"
        prop_id = body["proposal"]["id"]
        apply_resp = client.post(f"/api/projects/{proj.id}/proposals/{prop_id}/apply")
        assert apply_resp.status_code == 200

        # 3. After applying FX, Studio Preview is required -> status = Realtime Preview
        st1 = get_studio_preview_status(proj.id)
        assert st1["previewStatus"] == "Realtime Preview"
        assert st1["needsStudioRender"] is True

        # 4. Render Studio Preview -> Studio Preview status + playable WAV
        st2 = render_studio_preview(proj.id)
        assert st2["previewStatus"] == "Studio Preview"
        assert st2["upToDate"] is True
        audio_resp = client.get(f"/api/projects/{proj.id}/studio-preview/audio")
        assert audio_resp.status_code == 200
        assert audio_resp.content[:4] == b"RIFF"

        # 5. Modify track gain -> immediately invalidates to Outdated Preview!
        cur = store.load_project(proj.id)
        cur = commands.apply_command(cur, "track.setGain", {"trackId": "trk_native_01", "gainDb": -2.5})
        store.save_project(cur, expected_revision=cur.revision)
        st3 = get_studio_preview_status(proj.id)
        assert st3["previewStatus"] == "Outdated Preview"
        assert st3["upToDate"] is False
    finally:
        store.delete_project(proj.id)


def test_07_persistent_policy_routing_and_taste_profile(monkeypatch, tmp_path):
    """TEST 07: New project + '인디 록 만들어줘.' routes cleanly to YuE2 First, zero PREVIEW instruments, persistent taste profile."""
    monkeypatch.setenv("DAW_TASTE_PROFILE_PATH", str(tmp_path / "taste_test.json"))
    t0 = get_taste_profile()
    assert t0["globalPreferences"]["defaultFullMusicEngine"] == "yue2-native"
    assert t0["globalPreferences"]["defaultInstrumentalOnly"] is True

    updated = update_taste_profile(project_id="proj_x", project_patch={"moodBias": "bright_indie"})
    assert updated["effectiveForProject"]["moodBias"] == "bright_indie"
    assert "moodBias" not in get_taste_profile()["effectiveForProject"]

    fb = record_user_feedback(note="Good groove, keep natural drums", verdict="approved", tags=["natural_groove"])
    assert any(x["noteKo"] == "Good groove, keep natural drums" for x in fb["feedbackHistory"])
    reset_taste_profile(project_id="proj_x")
    assert "moodBias" not in get_taste_profile(project_id="proj_x")["effectiveForProject"]

    proj = store.create_project(name="Test 07 New Indie Project", bpm=120.0, with_default_tracks=False)
    try:
        res = client.post(
            f"/api/projects/{proj.id}/producer/instruct",
            json={"instruction": "인디 록 만들어줘."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["action"] == "composition_plan_created"
        plan = body["plan"]
        assert plan["musicalIdentity"]["genre"] == "indie_rock"
        assert plan["generationStrategy"]["productionMode"] == "neural_audio"
        assert plan["generationStrategy"]["actualEngine"] == "yue2-native"
        for role in plan["instrumentRoles"]:
            assert role["qualityTier"] != "PREVIEW"
    finally:
        store.delete_project(proj.id)


def test_08_reference_binding_honesty_for_yue2_and_five_gate_quality_gate():
    """TEST 08: Reference Blueprint v3 binds BPM/chords to YuE2 and honestly warns on exact drum LOCK; 5-Gate stays honest."""
    proj = store.create_project(name="Test 08 Ref Binding", bpm=120.0, with_default_tracks=False)
    try:
        proj.references = [
            {
                "id": "ref_v72_mock",
                "name": "V7.2 Magnetic Afterhours",
                "analysis": {
                    "rhythm": {"adoptedTempoBpm": 128.0, "grooveFeel": "four_on_the_floor_groove", "swingRatio": 0.54},
                    "harmony": {"estimatedKey": "F minor"},
                    "sound": {"measured": {"spectralCentroidHz": 1850.0, "stereoWidth": 0.42, "integratedLufs": -12.5}},
                },
                "blueprint": {
                    "tempoMap": {"bpm": 128.0, "meter": "4/4"},
                    "harmonicCharacter": {"key": "F minor", "sampleChords": ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"]},
                    "chordTimeline": [
                        {"startBeat": 0.0, "endBeat": 4.0, "symbol": "Fm7"},
                        {"startBeat": 4.0, "endBeat": 8.0, "symbol": "Dbmaj7"},
                        {"startBeat": 8.0, "endBeat": 12.0, "symbol": "Abmaj7"},
                        {"startBeat": 12.0, "endBeat": 16.0, "symbol": "Eb6"},
                    ],
                    "drumPerformance": {"totalBars": 4, "quantizedPerformance": [{"startBeat": 0.0, "pitch": 36}]},
                },
            }
        ]
        # 1. BPM + Chord progression reference (no strict note-level drum/bass LOCK) -> routes to YuE2 First!
        plan_yue2_default = create_composition_plan(
            project=proj,
            instruction="이 레퍼런스의 BPM과 코드 진행을 참고해서 짧게 만들어줘.",
            reference_ids=["ref_v72_mock"],
            feature_locks={"bpm": "locked", "chord_progression": "locked", "drum_rhythm": "reference"},
        )
        assert plan_yue2_default.musicalIdentity["tempoBpm"] == 128.0
        assert plan_yue2_default.harmonyAndGroove["chordProgression"][:4] == ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"]
        assert plan_yue2_default.generationStrategy["actualEngine"] == "yue2-native"

        # 2. Explicit YuE2 request + strict drum_rhythm=locked -> MUST honestly mark drum_rhythm as unsupported with warning!
        plan = create_composition_plan(
            project=proj,
            instruction="이 레퍼런스의 BPM과 코드 진행을 참고해서 짧게 만들어줘.",
            reference_ids=["ref_v72_mock"],
            engine_preference="yue2-native",
            feature_locks={"bpm": "locked", "chord_progression": "locked", "drum_rhythm": "locked"},
        )
        assert plan.musicalIdentity["tempoBpm"] == 128.0
        assert plan.harmonyAndGroove["chordProgression"][:4] == ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"]
        # YuE2 cannot hard-guarantee exact note-level drum LOCK -> MUST be marked unsupported with honest warning!
        lock_report = plan.referenceBinding.appliedFeatures["featureLockReport"]
        assert lock_report["effectiveLocks"]["drum_rhythm"] == "unsupported"
        assert len(lock_report["warningsKo"]) >= 1

        # 5-Gate Quality Gate honesty tests
        fg_bad_engine = evaluate_five_gate_quality(
            requested_engine="yue2-native",
            actual_engine="local-multitrack-composer",
            production_mode="neural_audio",
            silent_fallback_occurred=True,
        )
        assert fg_bad_engine["gates"]["gateA"]["status"] == "FAIL"
        assert fg_bad_engine["subjectiveMusicality"] == "UNVERIFIED"
        assert fg_bad_engine["humanListeningRequired"] is True

        fg_bad_inst = evaluate_five_gate_quality(
            requested_engine="local-multitrack-composer",
            actual_engine="local-multitrack-composer",
            production_mode="editable_midi",
            instruments_used=["guitar-clean-pluck"],
        )
        assert fg_bad_inst["gates"]["gateB"]["status"] == "FAIL"
    finally:
        store.delete_project(proj.id)
