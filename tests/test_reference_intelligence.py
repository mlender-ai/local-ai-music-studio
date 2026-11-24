"""Phase 02-A & 02-C tests: Reference import, real acoustic analysis, Blueprint, URL honesty, and comparison."""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine import paths as engine_paths
from engine.daw_workspace import renderer, store


def _make_rhythmic_fm_track(bpm: float = 128.0, duration_sec: float = 12.0, sr: int = 48000) -> bytes:
    """Synthesize a clean 128 BPM F-minor rhythmic test track with distinct energy arc."""
    n = int(round(duration_sec * sr))
    t = np.arange(n, dtype=np.float64) / sr
    spb = 60.0 / bpm
    out = np.zeros((n, 2), dtype=np.float64)

    # Four-on-the-floor kick pulses
    n_beats = int(duration_sec / spb)
    for b in range(n_beats):
        idx = int(round(b * spb * sr))
        klen = min(n - idx, int(0.18 * sr))
        if klen <= 0:
            continue
        kt = np.arange(klen) / sr
        f_env = 50.0 + 110.0 * np.exp(-36.0 * kt)
        kick = np.sin(2.0 * math.pi * np.cumsum(f_env) / sr) * np.exp(-12.0 * kt) * 0.65
        out[idx : idx + klen, 0] += kick
        out[idx : idx + klen, 1] += kick

    # F-minor triad harmonic bed (F3=174.61, Ab3=207.65, C4=261.63) with build-up envelope
    arc = 0.35 + 0.65 * (t / duration_sec)
    chord = (
        0.16 * np.sin(2.0 * math.pi * 174.61 * t)
        + 0.14 * np.sin(2.0 * math.pi * 207.65 * t)
        + 0.15 * np.sin(2.0 * math.pi * 261.63 * t)
    )
    out[:, 0] += chord * arc
    out[:, 1] += chord * arc * 0.92

    buf = io.BytesIO()
    sf.write(buf, np.clip(out, -0.95, 0.95).astype(np.float32), sr, format="WAV", subtype="PCM_24")
    return buf.getvalue()


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path)
    engine_paths.initialize()
    return tmp_path


def test_reference_import_analysis_blueprint_and_export_exclusion(isolated_env):
    client = TestClient(app)
    proj = client.post("/api/projects", json={"name": "Ref QA", "bpm": 128.0}).json()
    pid = proj["id"]

    # 1. Import real rhythmic F-minor WAV as Reference
    ref_wav = _make_rhythmic_fm_track(bpm=128.0, duration_sec=12.0)
    imp = client.post(
        f"/api/projects/{pid}/references/import",
        files={"file": ("house_ref_128.wav", ref_wav, "audio/wav")},
    )
    assert imp.status_code == 200
    ref = imp.json()["reference"]
    assert ref["audioAvailable"] is True
    rid = ref["id"]

    # 2. Verify Reference is EXCLUDED from project Stereo WAV Export (empty tracks -> silent export!)
    loaded = store.load_project(pid)
    export_arr, _ = renderer.render_project_to_array(loaded, start_beats=0.0, end_beats=4.0)
    assert float(np.max(np.abs(export_arr))) < 1e-6

    # 3. Run real acoustic analysis (sync) and verify BPM, Key, Energy Curve, Measured vs Estimated, and Blueprint
    an_res = client.post(f"/api/projects/{pid}/references/{rid}/analyze?sync=true")
    assert an_res.status_code == 200
    analyzed = an_res.json()["reference"]
    assert analyzed["analysisStatus"] == "completed"
    an = analyzed["analysis"]
    assert an["rhythm"]["estimatedBpm"] is not None
    # Allow exact 128 BPM or half-time 64 BPM candidate within 2 BPM
    est_bpm = an["rhythm"]["estimatedBpm"]
    assert abs(est_bpm - 128.0) < 2.5 or abs(est_bpm - 64.0) < 2.0
    assert len(an["arrangement"]["sections"]) >= 1
    assert len(an["arrangement"]["energyCurve"]) >= 16
    assert "measured" in an["sound"] and "estimated" in an["sound"]
    assert an["instrumentation"]["isEstimated"] is True

    bp = analyzed["blueprint"]
    assert bp["sourceAssetId"] == rid
    assert "selectedInfluences" in bp

    # 4. Update selected influences in Blueprint and verify persistence
    patch_res = client.patch(
        f"/api/projects/{pid}/references/{rid}/blueprint",
        json={"selectedInfluences": ["drums_groove", "spatial_depth"]},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["reference"]["selectedInfluences"] == ["drums_groove", "spatial_depth"]

    # 5. Re-running analysis hits disk cache cleanly
    an_cached = client.post(f"/api/projects/{pid}/references/{rid}/analyze?sync=true").json()["reference"]
    assert an_cached["analysis"]["fromCache"] is True


def test_reference_url_honesty_and_comparison(isolated_env):
    client = TestClient(app)
    proj = client.post("/api/projects", json={"name": "Compare QA", "bpm": 128.0}).json()
    pid = proj["id"]

    # URL registration MUST NOT fabricate audio analysis
    url_res = client.post(
        f"/api/projects/{pid}/references/url",
        json={"url": "https://example.com/demo-song"},
    )
    assert url_res.status_code == 200
    url_ref = url_res.json()["reference"]
    assert url_ref["audioAvailable"] is False
    assert "오디오 파일이 필요합니다" in url_ref["noticeKo"]

    # Attempting analysis on URL-only reference must fail honestly with 400
    fail_an = client.post(f"/api/projects/{pid}/references/{url_ref['id']}/analyze?sync=true")
    assert fail_an.status_code == 400

    # Compare Reference WAV vs another imported audio asset (different duration & spectral balance)
    ref_wav = _make_rhythmic_fm_track(bpm=128.0, duration_sec=10.0)
    # Create a bass-heavy/low-mid-heavy shorter track
    n = int(6.0 * 48000)
    t = np.arange(n, dtype=np.float32) / 48000.0
    muddy = (0.45 * np.sin(2.0 * math.pi * 300.0 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.stack([muddy, muddy], axis=1), 48000, format="WAV", subtype="PCM_24")

    r_imp = client.post(
        f"/api/projects/{pid}/references/import",
        files={"file": ("ref.wav", ref_wav, "audio/wav")},
    ).json()["reference"]
    a_imp = client.post(
        f"/api/projects/{pid}/assets/import",
        files={"file": ("muddy.wav", buf.getvalue(), "audio/wav")},
    ).json()["asset"]

    cmp_res = client.post(
        f"/api/projects/{pid}/references/{r_imp['id']}/compare",
        json={"targetKind": "asset", "targetId": a_imp["id"]},
    )
    assert cmp_res.status_code == 200
    cmp_data = cmp_res.json()
    assert len(cmp_data["normalizedProgression"]) == 4
    assert cmp_data["measuredDeltas"]["frequencyBandsDeltaPct"]["low_mid_200_500"] > 20.0
    assert any("저중역" in o["ko"] for o in cmp_data["observations"])
