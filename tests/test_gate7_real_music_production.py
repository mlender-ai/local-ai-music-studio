"""GATE 7 — Real Music Production QA Tests (TEST A through TEST E) + AI Sound Design & MCP Verification.

Verifies end-to-end real studio music production across 5 real-world genres & workflows:
- TEST A: Reference Reconstruction + Pro Instrument Studio Render (8-bar reference -> transcription -> MIDI -> SF3/DrumRack -> 48kHz WAV)
- TEST B: 128 BPM House Track (909 Drum Rack, Pro Analog Synth, Cutoff Automation, External Kick->Bass Sidechain, Dotted Delay, Room Reverb Return Bus, Vocal Leakage Gate PASS, 48kHz WAV)
- TEST C: Jazzy Hip-Hop 90 BPM (FluidSynth Rhodes EP + Upright Bass + Vintage Boom-Bap Drum Rack + Maj7/m7/Dom7 Chord Track + Tape Saturation + Room Reverb)
- TEST D: Indie Alternative Rock 118 BPM (FluidSynth Clean & Overdrive Guitars + Tube Guitar Amp & 2x12 British Cab IR + Acoustic Drum Rack + Picked Bass + Second-Half Delay Wet Automation + Hall Reverb)
- TEST E: 5-Turn Conversational Production + Staged Sound Design Proposals + Before/After Acoustic Measurement + Server WAV Export + Phase 05 MCP Tools (Section 56)
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from scipy import signal

from app.daw_server import app
from engine.daw_workspace import commands, loudness, mcp_tools, renderer, store
from engine.daw_workspace.schema import Clip, MidiNote, Project, SectionMarker, Track, make_id
from engine.generation.adapters.yue2_adapter import screen_vocal_leakage

client = TestClient(app)


def _cleanup_project(project_id: str) -> None:
    shutil.rmtree(store.project_dir(project_id), ignore_errors=True)


def _spectral_centroid(pcm: np.ndarray, sr: int) -> float:
    mono = pcm.mean(axis=1).astype(np.float64) if pcm.ndim == 2 else pcm.astype(np.float64)
    if len(mono) < 256 or float(np.sqrt(np.mean(mono * mono))) < 1e-6:
        return 0.0
    freqs, psd = signal.welch(mono, fs=sr, nperseg=min(4096, len(mono)))
    return float((freqs * psd).sum() / (psd.sum() + 1e-18))


def _render_project_wav(proj: Project, out_wav: Path) -> Path:
    audio, sr = renderer.render_project_to_array(proj)
    sf.write(str(out_wav), np.clip(audio, -1.0, 1.0), sr, subtype="PCM_24")
    return out_wav


def _assert_studio_wav_valid(wav_path: Path, min_duration_sec: float = 3.0) -> dict[str, float]:
    assert wav_path.exists() and wav_path.stat().st_size > 8000
    pcm, sr = sf.read(str(wav_path), dtype="float32")
    assert sr == 48000
    assert pcm.ndim == 2 and pcm.shape[1] == 2
    assert np.all(np.isfinite(pcm))
    dur_sec = pcm.shape[0] / sr
    assert dur_sec >= min_duration_sec
    peak = float(np.max(np.abs(pcm)))
    assert 0.03 < peak <= 1.01, f"Unexpected peak amplitude: {peak}"
    meas = loudness.measure_loudness(pcm, sr)
    assert -45.0 < meas["integratedLufs"] < -2.0, f"Unexpected loudness: {meas}"
    return {
        "durationSec": dur_sec,
        "peakLinear": peak,
        "integratedLufs": float(meas["integratedLufs"]),
        "centroidHz": _spectral_centroid(pcm, sr),
    }


def _synth_reference_wav(out_path: Path, bpm: float = 124.0, bars: int = 8, sr: int = 44100) -> Path:
    """Synthesize a clean 8-bar musical reference WAV (drums with bar-4 fill & bar-5 breakdown + Fm7-Dbmaj7-Ab-Eb chords)."""
    beat_sec = 60.0 / bpm
    total_sec = bars * 4 * beat_sec
    n = int(total_sec * sr)
    t = np.arange(n, dtype=np.float64) / sr
    mix = np.zeros(n, dtype=np.float64)

    chord_freqs = [
        (174.61, 207.65, 261.63, 311.13),  # Fm7
        (138.59, 174.61, 207.65, 261.63),  # Dbmaj7
        (207.65, 261.63, 311.13, 415.30),  # Ab
        (155.56, 196.00, 233.08, 311.13),  # Eb
    ]
    for bar in range(bars):
        s_idx = int(bar * 4 * beat_sec * sr)
        e_idx = min(n, int((bar + 1) * 4 * beat_sec * sr))
        tb = t[s_idx:e_idx] - bar * 4 * beat_sec
        env = np.minimum(1.0, tb / 0.02) * np.exp(-tb * 0.4)
        for f in chord_freqs[bar % 4]:
            mix[s_idx:e_idx] += 0.08 * np.sin(2 * math.pi * f * tb) * env

        # Drums: skip bar 4 (index 4 = 5th bar breakdown), add 16th snare fill on bar 3 beat 4!
        if bar == 4:
            continue
        for beat in range(4):
            ks = int((bar * 4 + beat) * beat_sec * sr)
            klen = min(n - ks, int(0.16 * sr))
            if klen > 0:
                tk = np.arange(klen) / sr
                f_sweep = 135.0 * np.exp(-tk * 26.0) + 48.0
                phase = 2 * math.pi * np.cumsum(f_sweep) / sr
                mix[ks : ks + klen] += 0.34 * np.sin(phase) * np.exp(-tk * 14.0)
            if beat in (1, 3):
                ss = int((bar * 4 + beat) * beat_sec * sr)
                slen = min(n - ss, int(0.11 * sr))
                if slen > 0:
                    ts = np.arange(slen) / sr
                    rng = np.random.default_rng(100 + bar * 10 + beat)
                    mix[ss : ss + slen] += 0.16 * rng.standard_normal(slen) * np.exp(-ts * 24.0)
        if bar == 3:
            for sub in range(4):
                fs = int((bar * 4 + 3 + sub * 0.25) * beat_sec * sr)
                flen = min(n - fs, int(0.06 * sr))
                if flen > 0:
                    tf = np.arange(flen) / sr
                    rng = np.random.default_rng(700 + sub)
                    mix[fs : fs + flen] += 0.20 * rng.standard_normal(flen) * np.exp(-tf * 35.0)

    peak = np.max(np.abs(mix)) + 1e-9
    stereo = np.stack([mix / peak * 0.72, mix / peak * 0.72], axis=1).astype(np.float32)
    sf.write(str(out_path), stereo, sr, subtype="PCM_16")
    return out_path


# ---------------------------------------------------------------------------
# TEST A — Reference-conditioned Reconstruction + Pro Instrument Studio Render
# ---------------------------------------------------------------------------

def test_gate7_a_reference_reconstruction_and_studio_render(tmp_path: Path):
    ref_wav = _synth_reference_wav(tmp_path / "gate7_ref_8bar.wav", bpm=124.0, bars=8)
    created = client.post("/api/projects", json={"name": "GATE7 Test A Ref", "bpm": 124.0}).json()
    pid = created["id"]
    try:
        with ref_wav.open("rb") as fh:
            imp = client.post(
                f"/api/projects/{pid}/references/import",
                files={"file": ("gate7_ref_8bar.wav", fh, "audio/wav")},
            )
        assert imp.status_code == 200, imp.text
        ref_id = imp.json()["reference"]["id"]

        # Run full transcription pipeline synchronously (without slow Demucs stem separation for speed; tests librosa/harmonic/drum extraction)
        tr = client.post(
            f"/api/projects/{pid}/references/{ref_id}/transcribe?sync=true&useDemucs=false",
        )
        assert tr.status_code == 200, tr.text
        proj_after = store.load_project(pid)
        ref_obj = next(r for r in proj_after.references if r["id"] == ref_id)
        tr_data = ref_obj.get("transcription") or {}
        assert tr_data
        chords_list = tr_data.get("chordTimeline") or tr_data.get("chords") or []
        drums_obj = tr_data.get("drums") or {}
        drum_hits = (
            drums_obj.get("quantizedMidiNotes")
            or drums_obj.get("rawMidiNotes")
            or drums_obj.get("drumEvents")
            or []
        )
        assert len(chords_list) >= 4
        assert len(drum_hits) >= 8

        # Reconstruct into editable DAW MIDI tracks + Chord Track
        rec = client.post(
            f"/api/projects/{pid}/references/{ref_id}/reconstruct",
            json={
                "importChords": True,
                "importDrumsMidi": True,
                "importBassMidi": True,
                "importMelodyMidi": False,
                "importStems": False,
                "importSections": True,
                "applyBpm": True,
            },
        )
        assert rec.status_code == 200, rec.text
        proj = store.load_project(pid)
        assert len(proj.chordTrack) >= 4
        midi_tracks = [t for t in proj.tracks if t.type == "midi" and any(c.notes for c in t.clips)]
        assert len(midi_tracks) >= 1

        # Upgrade reconstructed tracks to Pro Phase 05 Instruments + Studio EQ
        for trk in midi_tracks:
            low = trk.name.lower()
            if "drum" in low:
                proj = commands.apply_command(
                    proj,
                    "track.setInstrument",
                    {"trackId": trk.id, "instrumentRef": "pro-drum-rack", "preset": "house-909"},
                )
            elif "bass" in low:
                proj = commands.apply_command(
                    proj,
                    "track.setInstrument",
                    {"trackId": trk.id, "instrumentRef": "sf-bass-electric", "preset": "fingered"},
                )
            else:
                proj = commands.apply_command(
                    proj,
                    "track.setInstrument",
                    {"trackId": trk.id, "instrumentRef": "sf-ep-rhodes", "preset": "rhodes_tine"},
                )
            proj = commands.apply_command(
                proj,
                "fx.add",
                {"trackId": trk.id, "type": "parametric_eq", "preset": "low_mid_clean"},
            )
        store.save_project(proj)

        out_wav = tmp_path / "gate7_test_a_reconstructed_48k.wav"
        _render_project_wav(proj, out_wav)
        stats = _assert_studio_wav_valid(out_wav, min_duration_sec=8.0)
        assert stats["centroidHz"] > 120.0
    finally:
        _cleanup_project(pid)


# ---------------------------------------------------------------------------
# TEST B — 128 BPM House Track (909 Rack + Analog Synth + Cutoff Auto + Sidechain + Return Bus)
# ---------------------------------------------------------------------------

def test_gate7_b_128bpm_house_full_studio_chain(tmp_path: Path):
    # 8-bar 128 BPM House project (32 beats = 15.0s)
    drum_notes = []
    for beat in range(32):
        drum_notes.append(MidiNote(pitch=36, startBeat=float(beat), durationBeats=0.25, velocity=118))
        if beat % 4 in (1, 3):
            drum_notes.append(MidiNote(pitch=39, startBeat=float(beat), durationBeats=0.25, velocity=102))
        drum_notes.append(MidiNote(pitch=42, startBeat=float(beat) + 0.5, durationBeats=0.2, velocity=86))
        if beat % 8 == 7:
            drum_notes.append(MidiNote(pitch=46, startBeat=float(beat) + 0.25, durationBeats=0.45, velocity=95))

    bass_roots = [41, 37, 44, 39]  # F2, Db2, Ab2, Eb2
    bass_notes = []
    for bar in range(8):
        root = bass_roots[bar % 4]
        for step in (0.0, 0.75, 1.5, 2.0, 2.75, 3.5):
            bass_notes.append(
                MidiNote(pitch=root, startBeat=bar * 4.0 + step, durationBeats=0.45, velocity=108)
            )

    hook_pattern = [(65, 0.0), (68, 0.75), (72, 1.5), (70, 2.25), (68, 3.0), (65, 3.5)]
    hook_notes = []
    for bar in range(8):
        shift = 0 if bar % 4 in (0, 2) else (-4 if bar % 4 == 1 else -2)
        for p, sb in hook_pattern:
            hook_notes.append(MidiNote(pitch=p + shift, startBeat=bar * 4.0 + sb, durationBeats=0.45, velocity=98))

    proj = Project(
        id=make_id("proj"),
        name="GATE7 Test B House 128",
        bpm=128.0,
        lengthBeats=32.0,
        sections=[
            SectionMarker(name="GROOVE", startBeats=0.0, endBeats=16.0, color="#4f7a65"),
            SectionMarker(name="BUILD & CLIMAX", startBeats=16.0, endBeats=32.0, color="#8a5f4f"),
        ],
        tracks=[
            Track(
                id="trk_drums",
                name="Drums 909",
                type="midi",
                instrumentRef="pro-drum-rack",
                instrumentConfig={"preset": "house-909"},
                clips=[Clip(name="House 909", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=drum_notes)],
            ),
            Track(
                id="trk_bass",
                name="Sub Bass",
                type="midi",
                instrumentRef="pro-synth-analog",
                instrumentConfig={"preset": "acid-bass"},
                clips=[Clip(name="House Bass", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=bass_notes)],
            ),
            Track(
                id="trk_hook",
                name="Synth Hook",
                type="midi",
                instrumentRef="pro-synth-analog",
                instrumentConfig={"preset": "warm-analog-pluck"},
                clips=[Clip(name="Analog Hook", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=hook_notes)],
            ),
        ],
    )
    # Add External Kick->Bass Sidechain, EQ + Tempo-Synced Delay + Cutoff Automation on Synth, Room Reverb Return Bus
    proj = commands.apply_command(
        proj,
        "fx.add",
        {
            "trackId": "trk_bass",
            "type": "sidechain_compressor",
            "sidechainTrackId": "trk_drums",
            "parameters": {"thresholdDb": -24.0, "ratio": 7.0, "attackMs": 2.0, "releaseMs": 95.0, "depth": 1.0},
        },
    )
    proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_hook", "type": "parametric_eq", "preset": "low_mid_clean"})
    proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_hook", "type": "delay", "preset": "dotted_eighth", "wetDry": 0.24})
    proj = commands.apply_command(
        proj,
        "automation.upsertLane",
        {
            "trackId": "trk_hook",
            "lane": {
                "id": "auto_house_cut",
                "targetType": "instrument",
                "parameterId": "cutoffHz",
                "enabled": True,
                "points": [
                    {"beat": 0.0, "value": 420.0},
                    {"beat": 16.0, "value": 1800.0},
                    {"beat": 32.0, "value": 9800.0},
                ],
            },
        },
    )
    proj = commands.apply_command(proj, "bus.add", {"id": "bus_room", "name": "Room Reverb", "kind": "return"})
    proj = commands.apply_command(
        proj,
        "fx.add",
        {"target": "bus", "busId": "bus_room", "type": "reverb", "preset": "studio_room", "wetDry": 1.0},
    )
    proj = commands.apply_command(proj, "send.set", {"trackId": "trk_hook", "busId": "bus_room", "levelDb": -7.5})

    out_wav = tmp_path / "gate7_test_b_house_128bpm.wav"
    _render_project_wav(proj, out_wav)
    stats = _assert_studio_wav_valid(out_wav, min_duration_sec=14.0)

    # Verify Synth Cutoff Sweep actually brightened bar 5-8 vs bar 1-2!
    pcm_hook, sr, _ = renderer.render_single_track_pre_fader(proj, proj.tracks[2], start_beats=0.0, end_beats=32.0)
    early_c = _spectral_centroid(pcm_hook[: sr * 3], sr)
    late_c = _spectral_centroid(pcm_hook[-sr * 3 :], sr)
    assert late_c > early_c * 1.20, f"Expected cutoff automation brightening: early={early_c:.1f}Hz, late={late_c:.1f}Hz"

    # Verify Instrumental Vocal Leakage Gate PASSES on clean House instrumental
    house_pcm, house_sr = sf.read(str(out_wav), dtype="float32")
    leak = screen_vocal_leakage(house_pcm, house_sr, source_kind="deterministic_midi_synth")
    assert leak["status"] == "PASS", f"Expected instrumental PASS, got: {leak}"
    assert stats["durationSec"] >= 14.5


# ---------------------------------------------------------------------------
# TEST C — Jazzy Hip-Hop 90 BPM (FluidSynth Rhodes + Upright Bass + Vintage Drums + Maj7/m7/Dom7)
# ---------------------------------------------------------------------------

def test_gate7_c_jazzy_hiphop_90bpm_fluidsynth(tmp_path: Path):
    # 4 bars at 90 BPM (~10.67s): Dm9 -> G13 -> Cmaj9 -> A7
    chords = [
        ("Dm9", 0.0, 4.0, [50, 57, 60, 64, 69]),
        ("G13", 4.0, 8.0, [43, 53, 59, 64, 69]),
        ("Cmaj9", 8.0, 12.0, [48, 55, 59, 62, 64]),
        ("A7", 12.0, 16.0, [45, 55, 61, 64]),
    ]
    ep_notes = []
    bass_notes = []
    drum_notes = []
    for sym, sb, eb, pitches in chords:
        for p in pitches:
            ep_notes.append(MidiNote(pitch=p, startBeat=sb + 0.05, durationBeats=3.2, velocity=84))
        root = pitches[0] - 12 if pitches[0] >= 48 else pitches[0]
        for off, vel in ((0.0, 102), (1.5, 88), (2.5, 94), (3.5, 82)):
            bass_notes.append(MidiNote(pitch=root, startBeat=sb + off, durationBeats=0.8, velocity=vel))

    for bar in range(4):
        b0 = bar * 4.0
        drum_notes.append(MidiNote(pitch=36, startBeat=b0 + 0.0, durationBeats=0.3, velocity=112))
        drum_notes.append(MidiNote(pitch=38, startBeat=b0 + 1.0, durationBeats=0.3, velocity=100))
        drum_notes.append(MidiNote(pitch=36, startBeat=b0 + 2.35, durationBeats=0.3, velocity=96))
        drum_notes.append(MidiNote(pitch=38, startBeat=b0 + 3.0, durationBeats=0.3, velocity=104))
        for h in range(8):
            swing = 0.08 if h % 2 == 1 else 0.0
            drum_notes.append(MidiNote(pitch=42, startBeat=b0 + h * 0.5 + swing, durationBeats=0.2, velocity=78))

    proj = Project(
        id=make_id("proj"),
        name="GATE7 Test C Jazz Hip-Hop 90",
        bpm=90.0,
        lengthBeats=16.0,
        tracks=[
            Track(
                id="trk_ep",
                name="Rhodes Keys",
                type="midi",
                instrumentRef="sf-ep-rhodes",
                instrumentConfig={"preset": "jazz_warm_ep"},
                clips=[Clip(name="Jazz Chords", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=ep_notes)],
            ),
            Track(
                id="trk_ubass",
                name="Upright Bass",
                type="midi",
                instrumentRef="sf-bass-electric",
                instrumentConfig={"preset": "upright"},
                clips=[Clip(name="Walking Bass", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=bass_notes)],
            ),
            Track(
                id="trk_jdrums",
                name="Boombap Drums",
                type="midi",
                instrumentRef="pro-drum-rack",
                instrumentConfig={"preset": "boombap-vintage"},
                clips=[Clip(name="Boombap", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=drum_notes)],
            ),
        ],
    )
    proj = commands.apply_command(
        proj,
        "chord.setTrack",
        {
            "locked": True,
            "chords": [
                {"id": f"c_{i}", "symbol": sym, "startBeat": sb, "endBeat": eb, "isEstimate": False, "userCorrected": True}
                for i, (sym, sb, eb, _) in enumerate(chords)
            ],
        },
    )
    proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_ep", "type": "saturation", "preset": "warm_tape"})
    proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_ep", "type": "reverb", "preset": "studio_room", "wetDry": 0.25})

    out_wav = tmp_path / "gate7_test_c_jazz_hiphop_90bpm.wav"
    _render_project_wav(proj, out_wav)
    stats = _assert_studio_wav_valid(out_wav, min_duration_sec=10.0)
    assert len(proj.chordTrack) == 4
    assert stats["durationSec"] >= 10.5


# ---------------------------------------------------------------------------
# TEST D — Indie Alternative Rock 118 BPM (SF3 Guitars + Tube Amp/2x12 Cab IR + Second-Half Delay Wet Auto)
# ---------------------------------------------------------------------------

def test_gate7_d_indie_rock_118bpm_guitar_amp_and_delay_auto(tmp_path: Path):
    # 8 bars at 118 BPM (~16.27s)
    gtr_notes = []
    prog = [[52, 59, 64, 67], [48, 55, 60, 64], [55, 62, 67, 71], [50, 57, 62, 66]]  # Em-C-G-D
    for bar in range(8):
        voicing = prog[bar % 4]
        for strum in (0.0, 0.5, 1.5, 2.0, 3.0, 3.5):
            for p in voicing:
                gtr_notes.append(MidiNote(pitch=p, startBeat=bar * 4.0 + strum, durationBeats=0.42, velocity=100))

    bass_notes = []
    drum_notes = []
    for bar in range(8):
        root = prog[bar % 4][0] - 12
        for eighth in range(8):
            bass_notes.append(MidiNote(pitch=root, startBeat=bar * 4.0 + eighth * 0.5, durationBeats=0.4, velocity=98))
        b0 = bar * 4.0
        for k in (0.0, 1.5, 2.0):
            drum_notes.append(MidiNote(pitch=36, startBeat=b0 + k, durationBeats=0.25, velocity=115))
        for s in (1.0, 3.0):
            drum_notes.append(MidiNote(pitch=38, startBeat=b0 + s, durationBeats=0.25, velocity=110))
        for h in range(8):
            drum_notes.append(MidiNote(pitch=42, startBeat=b0 + h * 0.5, durationBeats=0.2, velocity=86))

    proj = Project(
        id=make_id("proj"),
        name="GATE7 Test D Indie Rock 118",
        bpm=118.0,
        lengthBeats=32.0,
        tracks=[
            Track(
                id="trk_gtr",
                name="Crunch Guitar",
                type="midi",
                instrumentRef="sf-guitar-overdrive",
                instrumentConfig={"preset": "overdrive_rock"},
                clips=[Clip(name="Indie Riff", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=gtr_notes)],
            ),
            Track(
                id="trk_rbass",
                name="Picked Bass",
                type="midi",
                instrumentRef="sf-bass-electric",
                instrumentConfig={"preset": "picked"},
                clips=[Clip(name="Rock Bass", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=bass_notes)],
            ),
            Track(
                id="trk_rdrums",
                name="Acoustic Kit",
                type="midi",
                instrumentRef="pro-drum-rack",
                instrumentConfig={"preset": "indie-rock-acoustic"},
                clips=[Clip(name="Rock Kit", type="midi", timelineStartBeats=0.0, durationBeats=32.0, notes=drum_notes)],
            ),
        ],
    )
    # Add Tube Guitar Amp + 2x12 British Cab IR + Tempo-Synced Delay + Hall Reverb
    proj = commands.apply_command(
        proj,
        "fx.add",
        {
            "trackId": "trk_gtr",
            "type": "guitar_amp",
            "preset": "crunch",
            "parameters": {"mode": "crunch", "drive": 0.58, "cabinet": "2x12_british"},
        },
    )
    proj = commands.apply_command(
        proj,
        "fx.add",
        {"trackId": "trk_gtr", "id": "fx_gtr_delay", "type": "delay", "preset": "dotted_eighth", "wetDry": 0.25},
    )
    proj = commands.apply_command(
        proj,
        "automation.upsertLane",
        {
            "trackId": "trk_gtr",
            "lane": {
                "id": "auto_delay_wet",
                "targetType": "fx",
                "targetId": "fx_gtr_delay",
                "parameterId": "wetDry",
                "enabled": True,
                "points": [
                    {"beat": 0.0, "value": 0.05},
                    {"beat": 16.0, "value": 0.08},
                    {"beat": 16.5, "value": 0.46},
                    {"beat": 32.0, "value": 0.50},
                ],
            },
        },
    )
    proj = commands.apply_command(proj, "fx.add", {"trackId": "trk_gtr", "type": "reverb", "preset": "hall", "wetDry": 0.22})

    out_wav = tmp_path / "gate7_test_d_indie_rock_118bpm.wav"
    _render_project_wav(proj, out_wav)
    stats = _assert_studio_wav_valid(out_wav, min_duration_sec=15.5)
    assert stats["centroidHz"] > 450.0


# ---------------------------------------------------------------------------
# TEST E — 5-Turn Conversational Production + Sound Design Proposals + MCP Tools (Section 56)
# ---------------------------------------------------------------------------

def test_gate7_e_five_turn_conversational_production_and_mcp():
    created = client.post("/api/projects", json={"name": "GATE7 Test E 5-Turn", "bpm": 128.0}).json()
    pid = created["id"]
    try:
        # Turn 1: Populate editable multi-track MIDI session (Drums, Bass, Synth Hook, Guitar)
        proj = store.load_project(pid)
        proj.lengthBeats = 16.0
        drum_notes = [
            MidiNote(pitch=36, startBeat=float(b), durationBeats=0.25, velocity=115) for b in range(16)
        ] + [MidiNote(pitch=38, startBeat=float(b), durationBeats=0.25, velocity=100) for b in (1, 3, 5, 7, 9, 11, 13, 15)]
        bass_notes = [MidiNote(pitch=41, startBeat=float(b), durationBeats=0.75, velocity=105) for b in range(0, 16, 2)]
        synth_notes = [
            MidiNote(pitch=p, startBeat=float(i), durationBeats=0.5, velocity=96)
            for i, p in enumerate([65, 68, 72, 70, 65, 68, 75, 72, 65, 68, 72, 70, 68, 65, 63, 65])
        ]
        proj.tracks = [
            Track(
                id="trk_drums",
                name="Drums",
                type="midi",
                instrumentRef="pro-drum-rack",
                instrumentConfig={"preset": "house-909"},
                clips=[Clip(name="Drums Clip", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=drum_notes)],
            ),
            Track(
                id="trk_bass",
                name="Bass",
                type="midi",
                instrumentRef="sf-bass-electric",
                instrumentConfig={"preset": "fingered"},
                clips=[Clip(name="Bass Clip", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=bass_notes)],
            ),
            Track(
                id="trk_synth",
                name="Synth Hook",
                type="midi",
                instrumentRef="basic-poly-synth",
                clips=[Clip(name="Hook Clip", type="midi", timelineStartBeats=0.0, durationBeats=16.0, notes=synth_notes)],
            ),
        ]
        proj = store.save_project(proj)
        orig_drum_pitches = [(n.pitch, n.startBeat) for n in proj.tracks[0].clips[0].notes]
        orig_synth_pitches = [(n.pitch, n.startBeat) for n in proj.tracks[2].clips[0].notes]

        # Turn 2 (Request D): Swap drum timbre to vintage while preserving 100% of drum MIDI rhythm!
        r2 = client.post(
            f"/api/projects/{pid}/producer/instruct",
            json={
                "instruction": "드럼 리듬은 그대로 두고 드럼 소리만 더 빈티지하게 바꿔줘",
                "selection": {"selectedTrackId": "trk_drums"},
                "baseRevision": proj.revision,
            },
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["supported"] is True and d2["action"] == "proposal_created"
        prop2_id = d2["proposal"]["id"]
        app2 = client.post(f"/api/projects/{pid}/proposals/{prop2_id}/apply")
        assert app2.status_code == 200
        proj = store.load_project(pid)
        assert proj.tracks[0].instrumentRef == "pro-drum-rack"
        assert proj.tracks[0].instrumentConfig.get("preset") == "boombap-vintage"
        assert [(n.pitch, n.startBeat) for n in proj.tracks[0].clips[0].notes] == orig_drum_pitches

        # Turn 3 (Request C): Redesign Synth Hook to analog + space, compare Before/After acoustics, preserve MIDI!
        r3 = client.post(
            f"/api/projects/{pid}/producer/instruct",
            json={
                "instruction": "신스 훅의 멜로디는 유지하고 좀 더 아날로그 느낌으로, 공간감도 넓혀줘",
                "selection": {"selectedTrackId": "trk_synth"},
                "baseRevision": proj.revision,
            },
        )
        assert r3.status_code == 200, r3.text
        d3 = r3.json()
        assert d3["supported"] is True and d3["action"] == "proposal_created"
        prop3_id = d3["proposal"]["id"]

        # Acoustic Before/After verification endpoint!
        cmp3 = client.post(f"/api/projects/{pid}/proposals/{prop3_id}/compare-sound")
        assert cmp3.status_code == 200, cmp3.text
        cmp_data = cmp3.json()
        assert cmp_data["before"]["integratedLufs"] > -60.0
        assert cmp_data["after"]["integratedLufs"] > -60.0

        app3 = client.post(f"/api/projects/{pid}/proposals/{prop3_id}/apply")
        assert app3.status_code == 200
        proj = store.load_project(pid)
        syn = next(t for t in proj.tracks if t.id == "trk_synth")
        assert syn.instrumentRef == "pro-synth-analog"
        assert len(proj.buses) >= 1
        assert len(syn.sends) >= 1
        assert [(n.pitch, n.startBeat) for n in syn.clips[0].notes] == orig_synth_pitches

        # Turn 4 (Request B): Kick & Bass external sidechain!
        r4 = client.post(
            f"/api/projects/{pid}/producer/instruct",
            json={
                "instruction": "킥이랑 베이스가 뭉쳐. 베이스에 사이드체인 걸어줘",
                "selection": {"selectedTrackId": "trk_bass"},
                "baseRevision": proj.revision,
            },
        )
        assert r4.status_code == 200, r4.text
        d4 = r4.json()
        assert d4["supported"] is True and d4["action"] == "proposal_created"
        app4 = client.post(f"/api/projects/{pid}/proposals/{d4['proposal']['id']}/apply")
        assert app4.status_code == 200
        proj = store.load_project(pid)
        bass = next(t for t in proj.tracks if t.id == "trk_bass")
        sc_slots = [e for e in bass.effects if e.get("type") == "sidechain_compressor"]
        assert len(sc_slots) == 1
        assert sc_slots[0].get("sidechainTrackId") == "trk_drums"

        # Turn 5 (Request E): Buildup Synth Filter Cutoff Automation!
        r5 = client.post(
            f"/api/projects/{pid}/producer/instruct",
            json={
                "instruction": "빌드업에서 신스 필터가 서서히 열리게 해줘",
                "selection": {"selectedTrackId": "trk_synth"},
                "baseRevision": proj.revision,
            },
        )
        assert r5.status_code == 200, r5.text
        d5 = r5.json()
        assert d5["supported"] is True and d5["action"] == "proposal_created"
        app5 = client.post(f"/api/projects/{pid}/proposals/{d5['proposal']['id']}/apply")
        assert app5.status_code == 200
        proj = store.load_project(pid)
        syn = next(t for t in proj.tracks if t.id == "trk_synth")
        assert any(l.get("parameterId") == "cutoffHz" for l in (syn.automationLanes or []))

        # Verify Acoustic Diagnosis API + Studio Server WAV Export API
        diag = client.post(f"/api/projects/{pid}/tracks/trk_synth/diagnose")
        assert diag.status_code == 200
        assert diag.json()["silent"] is False

        exp = client.post(f"/api/projects/{pid}/export/studio-wav", json={"useLoopRange": False})
        assert exp.status_code == 200
        assert exp.headers["content-type"].startswith("audio/wav")
        assert len(exp.content) > 40000

        # Verify Phase 05 MCP tools execute cleanly directly
        inst_res = mcp_tools.list_pro_instruments()
        assert len(inst_res["instruments"]) >= 12
        fx_res = mcp_tools.list_fx_catalog()
        assert len(fx_res["effects"]) >= 16
        diag_mcp = mcp_tools.diagnose_track_audio(track_id="trk_bass", project_id=pid)
        assert diag_mcp["silent"] is False
    finally:
        _cleanup_project(pid)
