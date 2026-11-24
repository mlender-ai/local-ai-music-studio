"""Phase 01 AI-Native DAW backend, persistence, MIDI, command & signal-level Audio QA tests."""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine import paths as engine_paths
from engine.daw_workspace import commands, midi, renderer, store
from engine.daw_workspace.schema import Clip, MidiNote, Track


def _make_sine_wav(freq_hz: float, duration_sec: float, amp: float = 0.5, sr: int = 48000) -> bytes:
    n = int(round(duration_sec * sr))
    t = np.arange(n, dtype=np.float32) / sr
    sig = (np.sin(2.0 * math.pi * freq_hz * t) * amp).astype(np.float32)
    stereo = np.stack([sig, sig], axis=1)
    buf = io.BytesIO()
    sf.write(buf, stereo, sr, format="WAV", subtype="PCM_24")
    return buf.getvalue()


@pytest.fixture()
def isolated_daw_env(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path)
    engine_paths.initialize()
    return tmp_path


def test_midi_smf_roundtrip():
    notes = [
        {"pitch": 60, "velocity": 100, "startBeat": 0.0, "durationBeats": 1.0},
        {"pitch": 64, "velocity": 92, "startBeat": 1.0, "durationBeats": 0.5},
        {"pitch": 67, "velocity": 115, "startBeat": 2.0, "durationBeats": 2.0},
    ]
    raw = midi.write_midi_bytes(notes, bpm=124.0, ppq=480)
    parsed = midi.parse_midi_bytes(raw)
    assert parsed["ppq"] == 480
    assert abs(parsed["bpm"] - 124.0) < 0.05
    assert len(parsed["notes"]) == 3
    assert [n["pitch"] for n in parsed["notes"]] == [60, 64, 67]
    assert parsed["notes"][2]["velocity"] == 115
    assert abs(parsed["notes"][2]["startBeat"] - 2.0) < 1e-4


def test_project_persistence_import_and_real_waveforms(isolated_daw_env):
    client = TestClient(app)
    res = client.post("/api/projects", json={"name": "Studio QA", "bpm": 120.0})
    assert res.status_code == 200
    proj = res.json()
    pid = proj["id"]

    # Import two real WAVs with different amplitudes + one real MIDI file
    loud_wav = _make_sine_wav(440.0, 2.0, amp=0.8)
    quiet_wav = _make_sine_wav(220.0, 2.0, amp=0.1)
    mid_bytes = midi.write_midi_bytes(
        [{"pitch": 60, "velocity": 100, "startBeat": 0.0, "durationBeats": 1.0}], bpm=120.0
    )

    r1 = client.post(f"/api/projects/{pid}/assets/import", files={"file": ("loud.wav", loud_wav, "audio/wav")})
    r2 = client.post(f"/api/projects/{pid}/assets/import", files={"file": ("quiet.wav", quiet_wav, "audio/wav")})
    r3 = client.post(f"/api/projects/{pid}/assets/import", files={"file": ("lead.mid", mid_bytes, "audio/midi")})
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200

    a_loud = r1.json()["asset"]
    a_quiet = r2.json()["asset"]
    assert a_loud["sampleRate"] == 48000
    assert a_loud["channels"] == 2
    assert abs(a_loud["durationSec"] - 2.0) < 0.01
    assert len(r3.json()["midi"]["notes"]) == 1

    # Verify extracted waveforms reflect REAL PCM amplitudes (never fabricated!)
    wf_loud = client.get(f"/api/projects/{pid}/assets/{a_loud['id']}/waveform?bins=128").json()
    wf_quiet = client.get(f"/api/projects/{pid}/assets/{a_quiet['id']}/waveform?bins=128").json()
    assert max(wf_loud["peaks"]) > 0.75
    assert max(wf_quiet["peaks"]) < 0.15

    # Execute shared commands via API and verify persistence round-trip
    loaded = client.get(f"/api/projects/{pid}").json()
    first_trk_id = loaded["tracks"][0]["id"]
    cmd_res = client.post(
        f"/api/projects/{pid}/commands",
        json={"type": "track.setGain", "payload": {"trackId": first_trk_id, "gainDb": -3.5}},
    )
    assert cmd_res.status_code == 200
    reopened = client.get(f"/api/projects/{pid}").json()
    assert reopened["tracks"][0]["gainDb"] == -3.5

    # Deleting a track MUST preserve immutable assets
    del_res = client.post(
        f"/api/projects/{pid}/commands",
        json={"type": "track.remove", "payload": {"trackId": first_trk_id}},
    )
    assert del_res.status_code == 200
    after_del = client.get(f"/api/projects/{pid}").json()
    assert len(after_del["assets"]) == 3
    # Asset file is still readable on disk
    file_res = client.get(f"/api/projects/{pid}/assets/{a_loud['id']}/file")
    assert file_res.status_code == 200

    # Save As clones project cleanly
    sa_res = client.post(f"/api/projects/{pid}/save-as", json={"name": "Studio QA Copy"})
    assert sa_res.status_code == 200
    assert sa_res.json()["id"] != pid
    assert sa_res.json()["name"] == "Studio QA Copy"


def test_signal_level_audio_qa_alignment_mute_solo_gain_pan_edit_midi(isolated_daw_env):
    """Verify real PCM output reflects timeline timing, mute/solo, gain, pan, clip edits, and MIDI."""
    proj = store.create_project(name="Audio QA", bpm=120.0, length_beats=8.0, with_default_tracks=False)
    # At 120 BPM: 1 beat = 0.5 sec, 8 beats = 4.0 sec
    a1, _ = store.import_asset_bytes(proj.id, "tone_a.wav", _make_sine_wav(440.0, 1.0, amp=0.4))
    a2, _ = store.import_asset_bytes(proj.id, "tone_b.wav", _make_sine_wav(660.0, 1.0, amp=0.4))

    proj = store.load_project(proj.id)
    proj.tracks = [
        Track(
            id="t1",
            name="Left Tone",
            type="audio",
            gainDb=0.0,
            pan=-1.0,  # Hard Left
            clips=[
                Clip(
                    id="c1",
                    name="C1",
                    type="audio",
                    assetId=a1.id,
                    timelineStartBeats=0.0,  # 0.0s .. 1.0s
                    durationBeats=2.0,
                    sourceOffsetSec=0.0,
                    sourceDurationSec=1.0,
                )
            ],
        ),
        Track(
            id="t2",
            name="Right Tone",
            type="audio",
            gainDb=-6.02,  # Half amplitude
            pan=1.0,  # Hard Right
            clips=[
                Clip(
                    id="c2",
                    name="C2",
                    type="audio",
                    assetId=a2.id,
                    timelineStartBeats=4.0,  # 2.0s .. 3.0s
                    durationBeats=2.0,
                    sourceOffsetSec=0.0,
                    sourceDurationSec=1.0,
                )
            ],
        ),
        Track(
            id="t3",
            name="Synth MIDI",
            type="midi",
            gainDb=0.0,
            pan=0.0,
            clips=[
                Clip(
                    id="c3",
                    name="MIDI C3",
                    type="midi",
                    timelineStartBeats=6.0,  # 3.0s .. 3.5s
                    durationBeats=2.0,
                    notes=[MidiNote(id="n1", pitch=69, velocity=110, startBeat=0.0, durationBeats=1.0)],
                )
            ],
        ),
    ]
    store.save_project(proj)

    audio, sr = renderer.render_project_to_array(proj)
    assert sr == 48000
    assert audio.shape == (4 * sr, 2)

    # Window 0.1s..0.9s: ONLY Track 1 (Hard Left) active -> Left loud, Right silent
    seg1 = audio[int(0.1 * sr) : int(0.9 * sr)]
    rms1_l = float(np.sqrt(np.mean(seg1[:, 0] ** 2)))
    rms1_r = float(np.sqrt(np.mean(seg1[:, 1] ** 2)))
    assert rms1_l > 0.20
    assert rms1_r < 1e-5

    # Window 1.2s..1.8s: silence gap between clips
    gap = audio[int(1.2 * sr) : int(1.8 * sr)]
    assert float(np.max(np.abs(gap))) < 1e-5

    # Window 2.1s..2.9s: ONLY Track 2 (Hard Right, -6.02 dB -> ~half RMS of Track 1)
    seg2 = audio[int(2.1 * sr) : int(2.9 * sr)]
    rms2_l = float(np.sqrt(np.mean(seg2[:, 0] ** 2)))
    rms2_r = float(np.sqrt(np.mean(seg2[:, 1] ** 2)))
    assert rms2_l < 1e-5
    assert abs((rms2_r / rms1_l) - 0.5) < 0.03

    # Window 3.05s..3.45s: MIDI synth note active on both stereo channels
    seg3 = audio[int(3.05 * sr) : int(3.45 * sr)]
    assert float(np.sqrt(np.mean(seg3[:, 0] ** 2))) > 0.03
    assert float(np.sqrt(np.mean(seg3[:, 1] ** 2))) > 0.03

    # Mute Track 1 -> Window 0.1s..0.9s becomes completely silent
    muted = commands.apply_command(proj, "track.setMute", {"trackId": "t1", "mute": True})
    audio_muted, _ = renderer.render_project_to_array(muted)
    assert float(np.max(np.abs(audio_muted[int(0.1 * sr) : int(0.9 * sr)]))) < 1e-6

    # Solo Track 2 -> Track 1 & MIDI track silenced, Track 2 audible
    soloed = commands.apply_command(proj, "track.setSolo", {"trackId": "t2", "solo": True})
    audio_soloed, _ = renderer.render_project_to_array(soloed)
    assert float(np.max(np.abs(audio_soloed[int(0.1 * sr) : int(0.9 * sr)]))) < 1e-6
    assert float(np.max(np.abs(audio_soloed[int(3.05 * sr) : int(3.45 * sr)]))) < 1e-6
    assert float(np.sqrt(np.mean(audio_soloed[int(2.1 * sr) : int(2.9 * sr), 1] ** 2))) > 0.10

    # Split C1 at beat 1 (0.5s) and delete right half -> 0.55s..0.95s becomes silent!
    split_proj = commands.apply_command(proj, "clip.split", {"clipId": "c1", "splitBeat": 1.0, "rightClipId": "c1_r"})
    split_proj = commands.apply_command(split_proj, "clip.delete", {"clipId": "c1_r"})
    audio_split, _ = renderer.render_project_to_array(split_proj)
    assert float(np.sqrt(np.mean(audio_split[int(0.1 * sr) : int(0.4 * sr), 0] ** 2))) > 0.20
    assert float(np.max(np.abs(audio_split[int(0.55 * sr) : int(0.95 * sr)]))) < 1e-6

    # Export actual Stereo WAV file and verify PCM header + zero clipping
    export_meta = renderer.export_project_wav(proj)
    assert export_meta["channels"] == 2
    assert export_meta["sampleRate"] == 48000
    assert export_meta["clippedSamples"] == 0
    assert export_meta["bytes"] > 100000


def test_path_safety_rejects_traversal(isolated_daw_env):
    client = TestClient(app)
    res = client.get("/api/projects/..%2F..%2Fetc")
    assert res.status_code in (400, 404)
