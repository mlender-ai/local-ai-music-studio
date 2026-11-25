"""GATE 4 Verification Tests — Professional FX DSP Measurements, External Sidechain, Buses, Automation & Track Freeze."""

from __future__ import annotations

import math

import numpy as np
from fastapi.testclient import TestClient

from app.daw_server import app
from engine.daw_workspace import commands, renderer, store
from engine.daw_workspace.schema import Clip, MidiNote, Project, make_id
from engine.fx import (
    apply_compressor,
    apply_delay,
    apply_guitar_amp,
    apply_parametric_eq,
    apply_reverb,
    apply_sidechain_compressor,
    apply_transient_shaper,
    compute_delay_ms,
    compute_eq_response_curve,
    list_fx_catalog,
)

client = TestClient(app)


def _sine(freq: float, dur_sec: float, sr: int = 48000, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(round(dur_sec * sr)), dtype=np.float64) / sr
    s = (np.sin(2.0 * math.pi * freq * t) * amp).astype(np.float32)
    return np.stack([s, s], axis=1)


def _rms_db(pcm: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
    return 20.0 * math.log10(max(r, 1e-9))


def _centroid(pcm: np.ndarray, sr: int = 48000) -> float:
    m = pcm.mean(axis=1).astype(np.float64)
    mag = np.abs(np.fft.rfft(m))
    f = np.fft.rfftfreq(len(m), 1.0 / sr)
    return float((f * mag).sum() / (mag.sum() + 1e-12))


def test_parametric_eq_real_frequency_gain_and_analytical_curve_parity() -> None:
    """Verify Pedalboard EQ boosts/cuts target frequencies accurately & analytical curve matches DSP 1:1."""
    sr = 48000
    bands = [
        {"id": "hpf", "type": "highpass", "freqHz": 260.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
        {"id": "pk", "type": "peak", "freqHz": 1000.0, "gainDb": 6.0, "q": 1.2, "enabled": True},
    ]
    s_100 = _sine(100.0, 0.5, sr=sr, amp=0.3)
    s_1k = _sine(1000.0, 0.5, sr=sr, amp=0.3)

    out_100 = apply_parametric_eq(s_100, sr, {"bands": bands})
    out_1k = apply_parametric_eq(s_1k, sr, {"bands": bands})

    delta_100 = _rms_db(out_100[4800:]) - _rms_db(s_100[4800:])
    delta_1k = _rms_db(out_1k[4800:]) - _rms_db(s_1k[4800:])
    assert delta_100 <= -10.0, f"HPF 260Hz must cut 100Hz by >=10 dB, got {delta_100:.2f} dB"
    assert 4.8 <= delta_1k <= 7.2, f"Peak +6 dB @ 1kHz must boost 1kHz by ~6 dB, got {delta_1k:.2f} dB"

    curve = compute_eq_response_curve(bands, sr=sr, n_points=96)
    idx_1k = int(np.argmin(np.abs(np.array(curve["frequenciesHz"]) - 1000.0)))
    assert abs(curve["magnitudeDb"][idx_1k] - 6.0) < 0.8


def test_compressor_real_gain_reduction_and_true_external_sidechain() -> None:
    """Verify Compressor real GR metering AND External Sidechain ducks ONLY during real Kick hits (0 dB when Kick silent!)."""
    sr = 48000
    loud = _sine(200.0, 1.0, sr=sr, amp=0.55)  # ~ -8.2 dBFS RMS
    quiet = _sine(200.0, 1.0, sr=sr, amp=0.01)  # ~ -43 dBFS RMS

    comp_loud, m_loud = apply_compressor(loud, sr, {"thresholdDb": -22.0, "ratio": 6.0, "attackMs": 4.0, "releaseMs": 80.0})
    _, m_quiet = apply_compressor(quiet, sr, {"thresholdDb": -22.0, "ratio": 6.0, "attackMs": 4.0, "releaseMs": 80.0})
    assert m_loud["peakGrDb"] >= 6.0, f"Loud signal must trigger >=6 dB GR, got {m_loud}"
    assert m_quiet["peakGrDb"] < 0.3, f"Quiet signal below threshold must have ~0 dB GR, got {m_quiet}"
    assert _rms_db(comp_loud) < _rms_db(loud) - 5.0

    # External Sidechain: 2s constant bass + Kick pulse ONLY at 0.0..0.12s and 1.0..1.12s!
    bass = _sine(65.0, 2.0, sr=sr, amp=0.45)
    kick = np.zeros_like(bass)
    k_dur = int(0.12 * sr)
    kt = np.arange(k_dur) / sr
    k_sig = (np.sin(2.0 * math.pi * 60.0 * kt) * np.exp(-kt * 14.0) * 0.92).astype(np.float32)
    kick[:k_dur, 0] = kick[:k_dur, 1] = k_sig
    kick[sr : sr + k_dur, 0] = kick[sr : sr + k_dur, 1] = k_sig

    ducked, sc_m = apply_sidechain_compressor(bass, kick, sr, {"thresholdDb": -24.0, "ratio": 8.0, "attackMs": 2.0, "releaseMs": 95.0})
    assert sc_m["sidechainActive"] is True and sc_m["peakGrDb"] >= 6.0
    # During Kick (0.02..0.10s), bass is ducked heavily; between Kicks (0.65..0.90s), bass recovers to ~0 dB!
    db_during_kick = _rms_db(ducked[int(0.02 * sr) : int(0.10 * sr)]) - _rms_db(bass[int(0.02 * sr) : int(0.10 * sr)])
    db_between = _rms_db(ducked[int(0.65 * sr) : int(0.90 * sr)]) - _rms_db(bass[int(0.65 * sr) : int(0.90 * sr)])
    assert db_during_kick <= -5.5, f"Bass must duck >=5.5 dB during kick, got {db_during_kick:.2f} dB"
    assert abs(db_between) <= 0.8, f"Bass must recover between kicks, got {db_between:.2f} dB"

    # Silent sidechain MUST produce strictly 0.0 dB ducking (proving zero fake periodic LFO!)
    silent_kick = np.zeros_like(bass)
    not_ducked, sc_zero = apply_sidechain_compressor(bass, silent_kick, sr, {"thresholdDb": -24.0, "ratio": 8.0})
    assert sc_zero["peakGrDb"] == 0.0
    assert np.allclose(not_ducked, bass, atol=1e-5)


def test_convolution_reverb_tempo_delay_and_guitar_amp_cabinet_ir() -> None:
    """Verify real Convolution IR Reverb tail, exact BPM-synced Ping-Pong Delay timing, and Guitar Amp + Cab IR."""
    sr = 48000
    # 1. Realistic 440 Hz percussive burst into Small Room vs Hall Reverb
    imp = np.zeros((sr * 2, 2), dtype=np.float32)
    bt = np.arange(int(0.08 * sr)) / sr
    burst = (np.sin(2.0 * math.pi * 440.0 * bt) * np.exp(-bt * 25.0) * 0.85).astype(np.float32)
    imp[1000 : 1000 + len(burst), 0] = imp[1000 : 1000 + len(burst), 1] = burst
    rev_small = apply_reverb(imp, sr, {"roomType": "small_room", "wetDry": 1.0})
    rev_hall = apply_reverb(imp, sr, {"roomType": "hall", "wetDry": 1.0})
    tail_small = _rms_db(rev_small[int(0.55 * sr) : int(1.4 * sr)])
    tail_hall = _rms_db(rev_hall[int(0.55 * sr) : int(1.4 * sr)])
    assert tail_hall > -48.0 and tail_hall > tail_small + 6.0

    # 2. Tempo-synced 1/8 dotted delay at 120 BPM = 375.0 ms exact!
    assert compute_delay_ms({"tempoSync": True, "subdivision": "1/8 dotted"}, bpm=120.0) == 375.0
    click = np.zeros((sr * 2, 2), dtype=np.float32)
    click[100:160] = 0.9
    delayed = apply_delay(click, sr, {"tempoSync": True, "subdivision": "1/8 dotted", "feedback": 0.5, "pingPong": True, "wetDry": 0.5}, bpm=120.0)
    expected_tap1 = 100 + int(round(0.375 * sr))
    peak_win = np.abs(delayed[expected_tap1 - 240 : expected_tap1 + 240, 0])
    assert float(np.max(peak_win)) > 0.15, "First tempo-synced echo missing at exact 375ms!"
    # Ping-pong tap 2 (750 ms) lands on RIGHT channel!
    expected_tap2 = 100 + int(round(0.750 * sr))
    assert float(np.max(np.abs(delayed[expected_tap2 - 240 : expected_tap2 + 240, 1]))) > 0.05

    # 3. Guitar Amp harmonic enrichment + Cabinet IR speaker roll-off
    clean_gtr = _sine(220.0, 0.6, sr=sr, amp=0.35)
    amp_di = apply_guitar_amp(clean_gtr, sr, {"ampModel": "high_gain", "drive": 0.85, "cabinet": "direct_di"})
    assert _centroid(amp_di, sr) > 650.0
    # Feed bright broadband guitar signal to verify real 4x12 Cabinet IR rolls off >5.5 kHz digital fizz!
    bright_in = _sine(330.0, 0.5, sr=sr, amp=0.25) + _sine(7800.0, 0.5, sr=sr, amp=0.22)
    cab_di = apply_guitar_amp(bright_in, sr, {"ampModel": "clean", "drive": 0.25, "cabinet": "direct_di"})
    cab_412 = apply_guitar_amp(bright_in, sr, {"ampModel": "clean", "drive": 0.25, "cabinet": "4x12_modern"})

    def _hi_band_ratio(x: np.ndarray) -> float:
        m = np.abs(np.fft.rfft(x[:, 0])) ** 2
        f = np.fft.rfftfreq(len(x), 1.0 / sr)
        return float(m[f > 6000.0].sum() / (m.sum() + 1e-12))

    assert _hi_band_ratio(cab_412) < _hi_band_ratio(cab_di) * 0.35


def test_full_routing_graph_buses_automation_and_track_freeze_api() -> None:
    """End-to-end GATE 4 test: Send/Return Reverb Bus, Cutoff Automation Sweep, Track Freeze & Cache Invalidation."""
    created = client.post("/api/projects", json={"name": "GATE4 Routing QA", "bpm": 120.0})
    assert created.status_code == 200
    body = created.json()
    pid = body["project"]["id"] if "project" in body else body["id"]
    try:
        proj = store.load_project(pid)
        proj = commands.apply_command(proj, "project.setLength", {"lengthBeats": 16.0})
        # Add Synth Track + Resonant Filter + Cutoff Automation opening from 300 Hz (Bar 1) -> 8500 Hz (Bar 4)!
        proj = commands.apply_command(
            proj,
            "track.add",
            {"id": "trk_syn", "name": "Build Synth", "type": "midi", "instrumentRef": "pro-synth-analog"},
        )
        proj = commands.apply_command(
            proj,
            "instrument.setPreset",
            {"trackId": "trk_syn", "preset": "supersaw-anthem"},
        )
        proj = commands.apply_command(
            proj,
            "clip.add",
            {
                "trackId": "trk_syn",
                "clip": Clip(
                    id="clp_syn",
                    name="Chords",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=16.0,
                    notes=[
                        MidiNote(pitch=p, velocity=105, startBeat=b, durationBeats=1.8)
                        for b in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0)
                        for p in (53, 60, 65)
                    ],
                ).model_dump(),
            },
        )
        proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_syn", "id": "fx_filt", "type": "filter", "parameters": {"cutoffHz": 400.0, "resonance": 0.45}})
        proj = commands.apply_command(
            proj,
            "automation.upsertLane",
            {
                "trackId": "trk_syn",
                "lane": {
                    "id": "auto_cut",
                    "targetType": "fx",
                    "targetId": "fx_filt",
                    "parameterId": "cutoffHz",
                    "points": [
                        {"beat": 0.0, "value": 240.0, "interpolation": "linear"},
                        {"beat": 4.0, "value": 420.0, "interpolation": "linear"},
                        {"beat": 15.0, "value": 9000.0, "interpolation": "linear"},
                    ],
                },
            },
        )
        # Add Return Reverb Bus + Post-Fader Send!
        proj = commands.apply_command(proj, "bus.add", {"id": "bus_rev", "name": "Hall Return", "kind": "return"})
        proj = commands.apply_command(proj, "fx.add", {"target": "bus", "busId": "bus_rev", "type": "reverb", "preset": "hall", "wetDry": 1.0})
        proj = commands.apply_command(proj, "send.set", {"trackId": "trk_syn", "busId": "bus_rev", "levelDb": -4.0, "preFader": False})
        saved = store.save_project(proj, clear_autosave=False)

        # Render full graph and verify Bar 4 is dramatically brighter than Bar 1 (real automation sweep!)
        pcm_with_bus, sr = renderer.render_project_to_array(saved)  # type: ignore[misc]
        bar1 = pcm_with_bus[: sr * 2]
        bar4 = pcm_with_bus[sr * 6 : sr * 8]
        assert _centroid(bar4, sr) > _centroid(bar1, sr) * 1.75, "Filter cutoff automation sweep must brighten Bar 4!"

        # Mute Return Bus -> verify audible difference (proving Send/Return routing + Bus Mute work!)
        muted_bus = commands.apply_command(saved, "bus.setMute", {"busId": "bus_rev", "mute": True})
        pcm_dry, _ = renderer.render_project_to_array(muted_bus)  # type: ignore[misc]
        diff_rms = float(np.sqrt(np.mean((pcm_with_bus - pcm_dry) ** 2)))
        assert diff_rms > 0.01, "Muting active Reverb Return Bus must change rendered audio!"

        # Test Track Freeze API + Cache Hit + Invalidation on FX change + Unfreeze!
        fr1 = client.post(f"/api/projects/{pid}/tracks/trk_syn/freeze")
        assert fr1.status_code == 200, fr1.text
        assert fr1.json()["frozen"] is True and fr1.json()["fromCache"] is False
        hash1 = fr1.json()["freezeState"]["stateHash"]

        fr2 = client.post(f"/api/projects/{pid}/tracks/trk_syn/freeze")
        assert fr2.status_code == 200 and fr2.json()["fromCache"] is True

        # Mutate FX -> automatically invalidates freezeState!
        p_mut = store.load_project(pid)
        p_mut = commands.apply_command(p_mut, "fx.setBypass", {"trackId": "trk_syn", "fxId": "fx_filt", "bypass": True})
        syn_mut = next(t for t in p_mut.tracks if t.id == "trk_syn")
        assert syn_mut.freezeState is None
        store.save_project(p_mut, clear_autosave=False)

        fr3 = client.post(f"/api/projects/{pid}/tracks/trk_syn/freeze")
        assert fr3.status_code == 200 and fr3.json()["freezeState"]["stateHash"] != hash1

        unfr = client.post(f"/api/projects/{pid}/tracks/trk_syn/unfreeze")
        assert unfr.status_code == 200 and unfr.json()["frozen"] is False
        # Original MIDI notes & FX preserved intact!
        p_final = store.load_project(pid)
        syn_final = next(t for t in p_final.tracks if t.id == "trk_syn")
        assert len(syn_final.clips[0].notes) == 24 and len(syn_final.effects) == 1

        # Verify FX catalog & EQ curve REST endpoints
        assert client.get("/api/fx/catalog").status_code == 200
        assert len(list_fx_catalog()) >= 15
        eq_res = client.post("/api/fx/eq-curve", json={"bands": [{"type": "peak", "freqHz": 1000, "gainDb": 4.0, "q": 1.0, "enabled": True}]})
        assert eq_res.status_code == 200 and len(eq_res.json()["frequenciesHz"]) == 96
    finally:
        store.delete_project(pid)
