"""GATE 2 Verification Tests — Native Audio Recovery, Demucs Vocal Leakage Gate & Hybrid Mode."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from app.daw_server import app
from engine.daw_workspace import store
from engine.generation.adapters.yue2_adapter import check_resting_voice, screen_vocal_leakage
from engine.generation.golden_references import (
    V72_MAGNETIC_AFTERHOURS_ABC,
    YUE2_RECOVERY_GUIDE,
    create_hybrid_session,
    list_golden_references,
)
from engine.runtime import get_runtime_registry

client = TestClient(app)


def test_v72_golden_reference_and_runtime_honesty() -> None:
    """Verify V7.2 Golden Native Reference catalog, strict ABC gate, and honest runtime engine probes."""
    ok, issues = check_resting_voice(V72_MAGNETIC_AFTERHOURS_ABC)
    assert ok is True, f"V7.2 ABC must pass strict resting-voice gate: {issues}"

    grefs = list_golden_references()
    v72 = next(g for g in grefs if g["id"] == "v72-magnetic-afterhours")
    assert v72["bpm"] == 128.0
    assert v72["seed"] == 1185
    assert v72["available"] is True
    assert v72["durationSec"] is not None and v72["durationSec"] >= 90.0

    reg = get_runtime_registry()
    by_id = {e["id"]: e for e in reg["engines"]}
    assert by_id["spotify-pedalboard"]["available"] is True
    assert by_id["fluidsynth-sf3"]["available"] is True
    assert by_id["demucs-htdemucs"]["available"] is True
    assert by_id["basic-pitch-onnx"]["available"] is True
    # YuE2 must stay honestly reported as uninstalled when local binary/weights are absent
    if not by_id["yue2-native"]["available"]:
        assert by_id["yue2-native"]["state"] in ("uninstalled", "binary_found", "model_found")
        assert len(by_id["yue2-native"]["missingItems"]) >= 1
    assert YUE2_RECOVERY_GUIDE["pinnedCommit"] == "e646d5228911ae1b81ac2a261115a255848ce85f"


def test_vocal_leakage_three_state_and_demucs_isolated_stem_screening() -> None:
    """Verify strict 3-state PASS/REJECT/UNCERTAIN vocal gate including Demucs-isolated vocal stem path."""
    sr = 24000
    t = np.arange(sr * 5, dtype=np.float64) / sr
    # Instrumental bass + synth chord signal
    inst = 0.25 * np.sin(2 * np.pi * 87.3 * t) + 0.15 * np.sin(2 * np.pi * 349.2 * t)
    stereo_inst = np.stack([inst, inst * 0.85], axis=1).astype(np.float32)

    # 1) Deterministic MIDI/SoundFont synth -> PASS
    res_det = screen_vocal_leakage(stereo_inst, sr, source_kind="deterministic_midi_synth")
    assert res_det["status"] == "PASS" and res_det["autoApprovedInstrumental"] is True

    # 2) Neural audio WITHOUT Demucs/PANNs/Whisper -> UNCERTAIN (never auto-approved!)
    res_unc = screen_vocal_leakage(stereo_inst, sr, source_kind="neural_audio")
    assert res_unc["status"] == "UNCERTAIN" and res_unc["autoApprovedInstrumental"] is False

    # 3) Neural audio WITH Demucs silent vocal stem (-65 dBFS) -> PASS!
    silent_v = (np.random.default_rng(7).normal(0, 1e-4, stereo_inst.shape)).astype(np.float32)
    res_demucs_pass = screen_vocal_leakage(
        stereo_inst, sr, source_kind="neural_audio", vocals_stem_audio=silent_v, vocals_stem_sr=sr
    )
    assert res_demucs_pass["status"] == "PASS"
    assert res_demucs_pass["method"] == "demucs_isolated_vocal_stem_screen"

    # 4) Neural audio WITH Demucs active humming/vocal stem (-14 dBFS) -> REJECT!
    hum = (0.20 * np.sin(2 * np.pi * 520.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 5.0 * t))).astype(np.float32)
    active_v = np.stack([hum, hum], axis=1)
    res_demucs_rej = screen_vocal_leakage(
        stereo_inst, sr, source_kind="neural_audio", vocals_stem_audio=active_v, vocals_stem_sr=sr
    )
    assert res_demucs_rej["status"] == "REJECT"
    assert res_demucs_rej["suspectedVocal"] is True
    assert res_demucs_rej["autoApprovedInstrumental"] is False


def test_hybrid_mode_preserves_native_audio_untouched_and_layers_editable_midi() -> None:
    """Section 15 Native Audio Protection: Hybrid mode keeps V7.2 WAV untouched & layers MIDI tracks."""
    created = client.post("/api/projects", json={"name": "GATE2 Hybrid QA", "bpm": 120.0})
    assert created.status_code == 200
    body = created.json()
    pid = body["project"]["id"] if "project" in body else body["id"]
    try:
        g_res = client.get("/api/generation/golden-references")
        assert g_res.status_code == 200
        assert len(g_res.json()["goldenReferences"]) >= 3

        h_res = client.post(
            f"/api/projects/{pid}/hybrid/layer",
            json={"goldenReferenceId": "v72-magnetic-afterhours", "layerRoles": ["synth_hook", "pad"], "bars": 8},
        )
        assert h_res.status_code == 200, h_res.text
        data = h_res.json()
        assert data["mode"] == "hybrid"
        assert data["nativeAudioPreservedUntouched"] is True
        proj = data["project"]
        assert proj["bpm"] == 128.0
        native_trk = next(t for t in proj["tracks"] if t["id"] == data["nativeTrackId"])
        assert native_trk["type"] == "audio"
        assert native_trk["stemMeta"]["assetKind"] == "native_audio_original"
        assert native_trk["stemMeta"]["protectedFromMidiOverwrite"] is True
        assert len(data["layeredTrackIds"]) == 2
        for lid in data["layeredTrackIds"]:
            ltrk = next(t for t in proj["tracks"] if t["id"] == lid)
            assert ltrk["type"] == "midi" and len(ltrk["clips"][0]["notes"]) >= 8
    finally:
        store.delete_project(pid)
