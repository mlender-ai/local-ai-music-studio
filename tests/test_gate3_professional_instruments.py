"""GATE 3 Verification Tests — Professional Virtual Instruments, Sampler, Drum Rack & Plugin Scanner."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine.instruments import (
    apply_articulation,
    get_instrument_catalog,
    probe_fluidsynth_engine,
    render_drum_rack_sequence,
    render_instrument_preview,
    render_pro_synth_sequence,
    render_sampler_sequence,
    render_soundfont_sequence,
    render_track_instrument,
    scan_host_plugins,
    slice_audio_by_transients,
)

client = TestClient(app)


def _rms(pcm: np.ndarray) -> float:
    return float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2))) if len(pcm) else 0.0


def _spectral_centroid(pcm: np.ndarray, sr: int = 48000) -> float:
    mono = pcm.mean(axis=1).astype(np.float64)
    mag = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sr)
    return float((freqs * mag).sum() / (mag.sum() + 1e-12))


def test_instrument_registry_v2_completeness_and_honesty() -> None:
    """Verify full Instrument Registry v2 covers all P0/P1 categories & separates Pro vs Lightweight Preview."""
    cat = get_instrument_catalog()
    by_id = {c["instrumentId"]: c for c in cat}
    for required in (
        "pro-drum-rack",
        "pro-synth-analog",
        "pro-synth-fm",
        "pro-sampler",
        "sf-drums-acoustic",
        "sf-drums-electronic",
        "sf-bass-electric",
        "sf-piano-grand",
        "sf-ep-rhodes",
        "sf-organ-vintage",
        "sf-guitar-clean",
        "sf-guitar-overdrive",
        "sf-strings-ensemble",
        "sf-vibraphone",
        "sf-pad-warm",
    ):
        assert required in by_id, f"Missing required P0/P1 instrument: {required}"
        entry = by_id[required]
        assert entry["engineType"] != "lightweight_preview"
        assert len(entry["presetList"]) >= 1
        assert entry["offlineRenderSupport"] is True

    # Phase 03 legacy preview voices must stay cleanly separated as lightweight_preview
    assert by_id["basic-poly-synth"]["engineType"] == "lightweight_preview"
    assert probe_fluidsynth_engine()["available"] is True


def test_fluidsynth_sf3_real_rendering_velocity_duration_and_tone() -> None:
    """Verify FluidSynth SF3 renders real multi-sampled instruments & responds to velocity, duration & tone cutoff."""
    # 1. Velocity response on Rhodes EP
    soft = render_soundfont_sequence(
        [{"pitch": 60, "velocity": 36, "startBeat": 0.0, "durationBeats": 1.0}],
        instrument_id="sf-ep-rhodes",
        preset_id="rhodes_tine",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    hard = render_soundfont_sequence(
        [{"pitch": 60, "velocity": 122, "startBeat": 0.0, "durationBeats": 1.0}],
        instrument_id="sf-ep-rhodes",
        preset_id="rhodes_tine",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    assert _rms(soft) > 1e-3 and _rms(hard) > _rms(soft) * 1.4

    # 2. Duration response (short staccato vs long held note on Concert Grand Piano)
    short_n = render_soundfont_sequence(
        [{"pitch": 60, "velocity": 100, "startBeat": 0.0, "durationBeats": 0.25}],
        instrument_id="sf-piano-grand",
        bpm=120.0,
        total_beats=3.0,
        sr=48000,
    )
    long_n = render_soundfont_sequence(
        [{"pitch": 60, "velocity": 100, "startBeat": 0.0, "durationBeats": 2.0}],
        instrument_id="sf-piano-grand",
        bpm=120.0,
        total_beats=3.0,
        sr=48000,
    )
    # Tail energy at 0.75..1.0s must be substantially larger for long held note!
    assert _rms(long_n[36000:48000]) > _rms(short_n[36000:48000]) * 1.8

    # 3. Tone / Cutoff parameter shift (dark felt vs bright pop piano)
    dark_p = render_soundfont_sequence(
        [{"pitch": 64, "velocity": 108, "startBeat": 0.0, "durationBeats": 1.0}],
        instrument_id="sf-piano-grand",
        preset_id="warm_felt",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    bright_p = render_soundfont_sequence(
        [{"pitch": 64, "velocity": 108, "startBeat": 0.0, "durationBeats": 1.0}],
        instrument_id="sf-piano-grand",
        preset_id="bright_piano",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    assert _spectral_centroid(bright_p) > _spectral_centroid(dark_p) * 1.25

    # 4. Multi-category audition check: Guitar, Bass, Acoustic Drums all render non-silent finite stereo PCM
    for inst_id in ("sf-guitar-clean", "sf-guitar-overdrive", "sf-bass-electric", "sf-drums-acoustic"):
        pcm = render_instrument_preview(inst_id, sr=44100)
        assert pcm.shape[1] == 2 and np.isfinite(pcm).all() and _rms(pcm) > 0.01


def test_pro_synth_cutoff_fm_and_unison_real_sonic_changes() -> None:
    """Verify Pro Analog/FM Synth responds measurably to Cutoff, FM Depth & Unison Width parameters."""
    notes = [{"pitch": 60, "velocity": 105, "startBeat": 0.0, "durationBeats": 1.5}]
    dark = render_pro_synth_sequence(
        notes,
        instrument_id="pro-synth-analog",
        preset_id="warm-analog-pluck",
        params={"cutoffHz": 450.0, "filterEnvAmount": 200.0},
        bpm=120.0,
        total_beats=2.0,
    )
    bright = render_pro_synth_sequence(
        notes,
        instrument_id="pro-synth-analog",
        preset_id="warm-analog-pluck",
        params={"cutoffHz": 8500.0, "filterEnvAmount": 2500.0},
        bpm=120.0,
        total_beats=2.0,
    )
    assert _spectral_centroid(bright) > _spectral_centroid(dark) * 1.8

    mono_u = render_pro_synth_sequence(
        notes,
        instrument_id="pro-synth-analog",
        preset_id="wide-analog-pad",
        params={"unisonVoices": 1, "stereoSpread": 0.0},
        bpm=120.0,
        total_beats=2.0,
    )
    wide_u = render_pro_synth_sequence(
        notes,
        instrument_id="pro-synth-analog",
        preset_id="wide-analog-pad",
        params={"unisonVoices": 7, "stereoSpread": 0.95, "detuneCents": 24.0},
        bpm=120.0,
        total_beats=2.0,
    )
    side_mono = _rms(mono_u[:, 0] - mono_u[:, 1])
    side_wide = _rms(wide_u[:, 0] - wide_u[:, 1])
    assert side_wide > side_mono + 0.01

    # FM synth preset comparison
    fm_low = render_pro_synth_sequence(notes, instrument_id="pro-synth-fm", params={"fmAmount": 0.0}, total_beats=2.0)
    fm_hi = render_pro_synth_sequence(notes, instrument_id="pro-synth-fm", params={"fmAmount": 4.2, "fmRatio": 3.5}, total_beats=2.0)
    assert _spectral_centroid(fm_hi) > _spectral_centroid(fm_low) * 1.5


def test_drum_rack_true_hihat_choke_group_and_articulation() -> None:
    """Verify Closed Hi-Hat (42) physically chokes a ringing Open Hi-Hat (46) inside Pro Drum Rack!"""
    # Open Hat alone at beat 0.0
    open_only = render_drum_rack_sequence(
        [{"pitch": 46, "velocity": 115, "startBeat": 0.0, "durationBeats": 1.0}],
        kit_preset="house-909",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    # Open Hat at beat 0.0 CHOKED by Closed Hat at beat 0.5 (0.25s)!
    choked = render_drum_rack_sequence(
        [
            {"pitch": 46, "velocity": 115, "startBeat": 0.0, "durationBeats": 1.0},
            {"pitch": 42, "velocity": 95, "startBeat": 0.5, "durationBeats": 0.15},
        ],
        kit_preset="house-909",
        bpm=120.0,
        total_beats=2.0,
        sr=48000,
    )
    # Measure tail at 0.45..0.75s (after closed hat has decayed): choked must be MUCH quieter than open-only!
    tail_open = _rms(open_only[int(0.45 * 48000) : int(0.75 * 48000)])
    tail_choked = _rms(choked[int(0.45 * 48000) : int(0.75 * 48000)])
    assert tail_open > 0.005
    assert tail_choked < tail_open * 0.35, f"Choke group failed! open tail={tail_open:.4f}, choked tail={tail_choked:.4f}"

    # Verify guitar strum articulation spreads simultaneous chord notes deterministically
    chord_notes = [
        {"pitch": 52, "velocity": 92, "startBeat": 0.0, "durationBeats": 1.0},
        {"pitch": 59, "velocity": 92, "startBeat": 0.0, "durationBeats": 1.0},
        {"pitch": 64, "velocity": 92, "startBeat": 0.0, "durationBeats": 1.0},
    ]
    strummed = apply_articulation(chord_notes, category="guitar", articulation="strum_down", bpm=120.0)
    assert strummed[0]["startBeat"] < strummed[1]["startBeat"] < strummed[2]["startBeat"]
    muted = apply_articulation(chord_notes, category="guitar", articulation="palm_mute", bpm=120.0)
    assert muted[0]["durationBeats"] < 0.5


def test_sampler_transient_slice_and_pitch_playback(tmp_path: Path) -> None:
    """Verify Sampler transient detection slices a 4-hit percussive loop & plays transposed / reversed slices."""
    sr = 48000
    dur = 2.0
    t = np.arange(int(sr * dur), dtype=np.float64) / sr
    sig = np.zeros_like(t)
    for k, freq in enumerate((220.0, 440.0, 330.0, 660.0)):
        i0 = int((k * 0.5 + 0.02) * sr)
        n = int(0.18 * sr)
        tt = np.arange(n) / sr
        sig[i0 : i0 + n] += np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 22.0) * 0.8
    wav = tmp_path / "loop4.wav"
    sf.write(str(wav), np.stack([sig, sig], axis=1).astype(np.float32), sr)

    sliced = slice_audio_by_transients(wav, bpm=120.0, sensitivity=0.65)
    assert sliced["sliceCount"] >= 4
    assert len(sliced["midiNotes"]) == sliced["sliceCount"]

    pcm = render_sampler_sequence(
        sliced["midiNotes"],
        sampler_config={"samplePath": str(wav), "slices": sliced["slices"], "playbackMode": "one_shot"},
        bpm=120.0,
        total_beats=4.0,
        sr=sr,
    )
    assert _rms(pcm) > 0.04

    # Chromatic pitch shift +12 semitones raises spectral centroid cleanly!
    lo_p = render_sampler_sequence(
        [{"pitch": 60, "velocity": 100, "startBeat": 0.0, "durationBeats": 0.5}],
        sampler_config={"samplePath": str(wav), "startSec": 0.0, "endSec": 0.4, "rootNote": 60, "playbackMode": "sustain"},
        bpm=120.0,
        total_beats=1.0,
        sr=sr,
    )
    hi_p = render_sampler_sequence(
        [{"pitch": 72, "velocity": 100, "startBeat": 0.0, "durationBeats": 0.5}],
        sampler_config={"samplePath": str(wav), "startSec": 0.0, "endSec": 0.4, "rootNote": 60, "playbackMode": "sustain"},
        bpm=120.0,
        total_beats=1.0,
        sr=sr,
    )
    assert _spectral_centroid(hi_p) > _spectral_centroid(lo_p) * 1.5


def test_plugin_scanner_and_instrument_rest_endpoints() -> None:
    """Verify isolated macOS AU/VST3 scanner & REST endpoints (`/api/instruments/catalog`, `/preview`, `/plugins/scan`)."""
    scan = scan_host_plugins(probe_external=True)
    assert scan["systemCoreAudioAuCount"] >= 20
    assert scan["logicExclusiveAvailable"] is False

    cat_res = client.get("/api/instruments/catalog")
    assert cat_res.status_code == 200
    assert len(cat_res.json()["instruments"]) >= 18

    prev_res = client.post("/api/instruments/preview", json={"instrumentRef": "sf-ep-rhodes", "presetId": "rhodes_tine"})
    assert prev_res.status_code == 200
    assert prev_res.content[:4] == b"RIFF" and len(prev_res.content) > 20000

    plug_res = client.get("/api/plugins/scan?probeExternal=true")
    assert plug_res.status_code == 200
    assert plug_res.json()["systemCoreAudioAuCount"] >= 20
