#!/usr/bin/env python3
"""Seed Phase 01 AI-Native DAW demo projects and studio asset library locally.

Demo Project A — V7.2 Magnetic Afterhours (House):
  Imports the real YuE2 V7.2 recording (`examples/v72/magnetic-afterhours/final.wav`)
  from the repository's `codex/v7-2-house-hook-first` branch (no fake stems!) plus a
  real Standard MIDI File derived from the F-minor 128 BPM motif.

Demo Project B — Midnight Studio (5-Track Multitrack Session):
  Synthesizes clean, musical, click-free 48 kHz Stereo WAV loops (Drums, Bass,
  Electric Keys/Guitar, Texture/FX) and a real Standard MIDI File (Synth) so all
  DAW timeline, mixer, clip editor, piano roll, and Stereo WAV export workflows
  work immediately out of the box with zero license issues.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import paths as engine_paths
from engine.daw_workspace import midi, store
from engine.daw_workspace.schema import Clip, LoopRegion, MidiNote, Project, SectionMarker, Track, make_id

SR = 48000
BPM = 128.0
SEC_PER_BEAT = 60.0 / BPM


def _git_extract(ref_path: str) -> bytes | None:
    """Safely read a verified binary asset from an existing git branch without switching branches."""
    try:
        res = subprocess.run(
            ["git", "-C", str(ROOT), "show", ref_path],
            capture_output=True,
            check=True,
        )
        return res.stdout if len(res.stdout) > 1000 else None
    except Exception:
        return None


def _write_wav_bytes(audio: np.ndarray, sr: int = SR) -> bytes:
    import io

    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -0.98, 0.98).astype(np.float32), sr, format="WAV", subtype="PCM_24")
    return buf.getvalue()


def _synth_drums_4bars(bpm: float = BPM, sr: int = SR) -> np.ndarray:
    """Clean, punchy 4-bar (16-beat) 128 BPM house/funk drum loop (stereo 48 kHz)."""
    spb = 60.0 / bpm
    total = int(round(16.0 * spb * sr))
    out = np.zeros((total, 2), dtype=np.float64)
    rng = np.random.default_rng(42)

    def add_mono(start_beat: float, sig: np.ndarray, pan: float = 0.0, gain: float = 1.0):
        idx = int(round(start_beat * spb * sr))
        end = min(total, idx + len(sig))
        if end <= idx or idx < 0:
            return
        n = end - idx
        ang = (pan + 1.0) * 0.25 * math.pi
        out[idx:end, 0] += sig[:n] * gain * math.cos(ang)
        out[idx:end, 1] += sig[:n] * gain * math.sin(ang)

    # Kick on every beat (four-on-the-floor with subtle ghost on bar 4 beat 4.5)
    t_kick = np.arange(int(0.28 * sr)) / sr
    freq_env = 46.0 + 115.0 * np.exp(-38.0 * t_kick)
    phase = 2.0 * math.pi * np.cumsum(freq_env) / sr
    kick = np.sin(phase) * np.exp(-10.5 * t_kick) + 0.18 * np.sin(2.0 * math.pi * 1900.0 * t_kick) * np.exp(-120.0 * t_kick)
    kick = np.tanh(kick * 1.4) * 0.72

    # Crisp snare/clap on beats 2 & 4
    t_snare = np.arange(int(0.22 * sr)) / sr
    noise_s = rng.standard_normal(len(t_snare))
    # Simple 1-pole highpass via diff for crisp snap
    hp_noise = np.concatenate([[0.0], np.diff(noise_s)])
    snare = (0.48 * hp_noise * np.exp(-18.0 * t_snare) + 0.35 * np.sin(2.0 * math.pi * 195.0 * t_snare) * np.exp(-26.0 * t_snare)) * 0.55

    # Closed & open hi-hats
    t_hat = np.arange(int(0.06 * sr)) / sr
    hat_c = np.concatenate([[0.0], np.diff(rng.standard_normal(len(t_hat)))]) * np.exp(-65.0 * t_hat) * 0.22
    t_ohat = np.arange(int(0.18 * sr)) / sr
    hat_o = np.concatenate([[0.0], np.diff(rng.standard_normal(len(t_ohat)))]) * np.exp(-16.0 * t_ohat) * 0.24

    for beat in range(16):
        add_mono(beat, kick, 0.0, 0.95)
        if beat % 2 == 1:
            add_mono(beat, snare, 0.04, 0.85)
        add_mono(beat + 0.5, hat_o if beat % 2 == 1 else hat_c, -0.18 if beat % 2 == 0 else 0.18, 0.85)
        add_mono(beat + 0.25, hat_c, 0.22, 0.42)
        add_mono(beat + 0.75, hat_c, -0.22, 0.50)
    # Turnaround ghost kick at end of bar 4
    add_mono(15.5, kick, 0.0, 0.65)
    return out.astype(np.float32)


def _synth_bass_4bars(bpm: float = BPM, sr: int = SR) -> np.ndarray:
    """Warm FM/analog deep house bassline in F minor (4 bars, stereo 48 kHz)."""
    spb = 60.0 / bpm
    total = int(round(16.0 * spb * sr))
    out = np.zeros((total, 2), dtype=np.float64)
    # (start_beat, dur_beats, midi_pitch, vel)
    pattern = [
        (0.0, 0.75, 41, 0.95), (0.75, 0.5, 41, 0.75), (1.5, 0.5, 44, 0.85), (2.25, 0.75, 48, 0.9), (3.5, 0.5, 46, 0.8),
        (4.0, 0.75, 39, 0.95), (4.75, 0.5, 39, 0.75), (5.5, 0.5, 43, 0.85), (6.25, 0.75, 46, 0.9), (7.5, 0.5, 44, 0.8),
        (8.0, 0.75, 37, 0.95), (8.75, 0.5, 37, 0.75), (9.5, 0.5, 41, 0.85), (10.25, 0.75, 44, 0.9), (11.5, 0.5, 43, 0.8),
        (12.0, 0.75, 36, 0.95), (12.75, 0.5, 36, 0.75), (13.5, 0.5, 43, 0.88), (14.25, 0.75, 48, 0.92), (15.25, 0.5, 46, 0.82),
    ]
    for start_b, dur_b, pitch, amp in pattern:
        idx = int(round(start_b * spb * sr))
        n = int(round((dur_b * spb + 0.04) * sr))
        end = min(total, idx + n)
        if end <= idx:
            continue
        t = np.arange(end - idx) / sr
        f = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
        mod = 1.6 * np.exp(-9.0 * t) * np.sin(2.0 * math.pi * (2.0 * f) * t)
        sig = 0.72 * np.sin(2.0 * math.pi * f * t + mod) + 0.25 * np.sin(2.0 * math.pi * 2.0 * f * t) * np.exp(-5.0 * t)
        env = np.minimum(1.0, t / 0.008) * np.exp(-3.2 * t)
        fade = np.minimum(1.0, np.arange(end - idx)[::-1] / max(1, int(0.015 * sr)))
        mono = sig * env * fade * amp * 0.56
        out[idx:end, 0] += mono
        out[idx:end, 1] += mono
    return out.astype(np.float32)


def _synth_guitar_keys_4bars(bpm: float = BPM, sr: int = SR) -> np.ndarray:
    """Syncopated warm Rhodes/clean-guitar chord stabs in F minor (stereo 48 kHz)."""
    spb = 60.0 / bpm
    total = int(round(16.0 * spb * sr))
    out = np.zeros((total, 2), dtype=np.float64)
    chords = [
        (0.5, 1.25, [53, 56, 60, 63]), (2.5, 1.0, [53, 56, 60, 67]),
        (4.5, 1.25, [51, 55, 58, 62]), (6.5, 1.0, [51, 55, 58, 65]),
        (8.5, 1.25, [49, 53, 56, 60]), (10.5, 1.0, [49, 53, 56, 63]),
        (12.5, 1.25, [48, 55, 58, 62]), (14.5, 1.0, [52, 55, 58, 64]),
    ]
    for start_b, dur_b, notes in chords:
        for j, pitch in enumerate(notes):
            # Subtle guitar-like 12ms upward strum
            idx = int(round((start_b * spb + j * 0.012) * sr))
            n = int(round((dur_b * spb + 0.18) * sr))
            end = min(total, idx + n)
            if end <= idx:
                continue
            t = np.arange(end - idx) / sr
            f = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
            tone = (
                0.65 * np.sin(2.0 * math.pi * f * t)
                + 0.22 * np.sin(2.0 * math.pi * 2.0 * f * t) * np.exp(-6.0 * t)
                + 0.10 * np.sin(2.0 * math.pi * 3.0 * f * t) * np.exp(-12.0 * t)
            )
            env = np.minimum(1.0, t / 0.006) * np.exp(-2.8 * t)
            fade = np.minimum(1.0, np.arange(end - idx)[::-1] / max(1, int(0.03 * sr)))
            voice = tone * env * fade * 0.16
            pan = -0.35 + (j / max(1, len(notes) - 1)) * 0.70
            ang = (pan + 1.0) * 0.25 * math.pi
            out[idx:end, 0] += voice * math.cos(ang)
            out[idx:end, 1] += voice * math.sin(ang)
    return out.astype(np.float32)


def _synth_texture_4bars(bpm: float = BPM, sr: int = SR) -> np.ndarray:
    """Warm stereo ambient pad & air texture in F minor (4 bars, stereo 48 kHz)."""
    spb = 60.0 / bpm
    total = int(round(16.0 * spb * sr))
    t = np.arange(total, dtype=np.float64) / sr
    out = np.zeros((total, 2), dtype=np.float64)
    pitches = [53, 60, 63, 67, 72]
    for i, pitch in enumerate(pitches):
        f = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
        lfo_l = 0.5 + 0.5 * np.sin(2.0 * math.pi * (0.13 + 0.03 * i) * t)
        lfo_r = 0.5 + 0.5 * np.cos(2.0 * math.pi * (0.11 + 0.03 * i) * t)
        out[:, 0] += np.sin(2.0 * math.pi * (f * 0.999) * t) * lfo_l * 0.06
        out[:, 1] += np.sin(2.0 * math.pi * (f * 1.001) * t) * lfo_r * 0.06
    # Gentle bar swell + clean fade in/out for seamless looping
    swell = 0.65 + 0.35 * np.sin(2.0 * math.pi * t / (8.0 * spb) - math.pi / 2)
    out *= swell[:, None]
    fade = int(0.06 * sr)
    ramp = np.linspace(0.0, 1.0, fade)[:, None]
    out[:fade] *= ramp
    out[-fade:] *= ramp[::-1]
    return out.astype(np.float32)


def _demo_midi_notes() -> list[dict]:
    """Musical 4-bar F-minor synth hook motif (matches Midnight Studio & V7.2 Fm 128 BPM)."""
    return [
        # Bar 1 (Fm9)
        {"pitch": 72, "velocity": 98, "startBeat": 0.0, "durationBeats": 0.5},
        {"pitch": 75, "velocity": 106, "startBeat": 0.75, "durationBeats": 0.75},
        {"pitch": 74, "velocity": 92, "startBeat": 1.75, "durationBeats": 0.5},
        {"pitch": 68, "velocity": 102, "startBeat": 2.5, "durationBeats": 1.0},
        # Bar 2 (Eb6)
        {"pitch": 70, "velocity": 96, "startBeat": 4.0, "durationBeats": 0.75},
        {"pitch": 75, "velocity": 108, "startBeat": 5.0, "durationBeats": 0.5},
        {"pitch": 67, "velocity": 90, "startBeat": 5.75, "durationBeats": 0.75},
        {"pitch": 65, "velocity": 104, "startBeat": 6.75, "durationBeats": 1.0},
        # Bar 3 (Dbmaj7)
        {"pitch": 72, "velocity": 100, "startBeat": 8.0, "durationBeats": 0.5},
        {"pitch": 75, "velocity": 110, "startBeat": 8.75, "durationBeats": 0.75},
        {"pitch": 77, "velocity": 114, "startBeat": 9.75, "durationBeats": 0.5},
        {"pitch": 72, "velocity": 98, "startBeat": 10.5, "durationBeats": 1.0},
        # Bar 4 (C7sus -> Fm)
        {"pitch": 70, "velocity": 96, "startBeat": 12.0, "durationBeats": 0.75},
        {"pitch": 75, "velocity": 104, "startBeat": 13.0, "durationBeats": 0.5},
        {"pitch": 67, "velocity": 92, "startBeat": 13.75, "durationBeats": 0.5},
        {"pitch": 72, "velocity": 108, "startBeat": 14.5, "durationBeats": 1.25},
    ]


def seed_library() -> dict[str, bytes]:
    """Populate outputs/daw/library/ with curated existing studio assets + demo loops."""
    lib = engine_paths.DATA / "daw" / "library"
    (lib / "studio-recordings").mkdir(parents=True, exist_ok=True)
    (lib / "samples").mkdir(parents=True, exist_ok=True)
    (lib / "midi").mkdir(parents=True, exist_ok=True)

    generated: dict[str, bytes] = {}
    drums_wav = _write_wav_bytes(_synth_drums_4bars())
    bass_wav = _write_wav_bytes(_synth_bass_4bars())
    guitar_wav = _write_wav_bytes(_synth_guitar_keys_4bars())
    texture_wav = _write_wav_bytes(_synth_texture_4bars())
    synth_mid = midi.write_midi_bytes(_demo_midi_notes(), bpm=BPM, track_name="Fm Synth Hook")

    files = {
        lib / "samples/Drum_loop_128bpm.wav": drums_wav,
        lib / "samples/Bass_groove_Fm_128bpm.wav": bass_wav,
        lib / "samples/Guitar_Keys_Fm_128bpm.wav": guitar_wav,
        lib / "samples/Texture_pad_Fm_128bpm.wav": texture_wav,
        lib / "midi/Synth_hook_Fm_128bpm.mid": synth_mid,
    }
    for path, content in files.items():
        if not path.is_file():
            path.write_bytes(content)

    generated["drums"] = drums_wav
    generated["bass"] = bass_wav
    generated["guitar"] = guitar_wav
    generated["texture"] = texture_wav
    generated["synth_mid"] = synth_mid

    # Extract real existing Music Studio recordings from git branches (without merging unreviewed branches)
    studio_refs = [
        (
            "origin/codex/v7-2-house-hook-first:examples/v72/magnetic-afterhours/final.wav",
            lib / "studio-recordings/V7.2_Magnetic_Afterhours_128bpm.wav",
            "v72_house",
        ),
        (
            "origin/codex/v7-2-house-hook-first:examples/v4/yue2-rock-original.wav",
            lib / "studio-recordings/V4_YuE2_Rock_Original.wav",
            "v4_rock",
        ),
        (
            "origin/codex/v7-2-house-hook-first:examples/audio/jazz-hip-hop-master.wav",
            lib / "studio-recordings/Jazz_Hip_Hop_90bpm_Master.wav",
            "jazz_hiphop",
        ),
    ]
    for ref, dest, key in studio_refs:
        if dest.is_file():
            generated[key] = dest.read_bytes()
        else:
            raw = _git_extract(ref)
            if raw:
                dest.write_bytes(raw)
                generated[key] = raw

    return generated


def seed_demo_project_b(assets_data: dict[str, bytes], force: bool = False) -> Project:
    """Demo Project B · Multitrack Session (5 independent tracks, 16 bars, 128 BPM)."""
    pid = "demo_multitrack_session"
    pfile = store.projects_root() / pid / "project.json"
    if pfile.is_file() and not force:
        return store.load_project(pid)

    proj = store.create_project(
        name="Midnight Studio · Multitrack",
        bpm=128.0,
        numerator=4,
        denominator=4,
        length_beats=64.0,
        project_id=pid,
        with_default_tracks=False,
    )

    a_drums, _ = store.import_asset_bytes(
        pid, "Drum loop.wav", assets_data["drums"], source="demo-multitrack", provenance="Independent 4-bar 128 BPM drums (48 kHz Stereo)"
    )
    a_bass, _ = store.import_asset_bytes(
        pid, "Bass groove.wav", assets_data["bass"], source="demo-multitrack", provenance="Independent 4-bar F-minor bass (48 kHz Stereo)"
    )
    a_guitar, _ = store.import_asset_bytes(
        pid, "Guitar Keys.wav", assets_data["guitar"], source="demo-multitrack", provenance="Independent 4-bar Rhodes/guitar chords (48 kHz Stereo)"
    )
    a_synth, synth_extra = store.import_asset_bytes(
        pid, "Synth.mid", assets_data["synth_mid"], source="demo-multitrack", provenance="Standard MIDI File (.mid) · F-minor hook"
    )
    a_texture, _ = store.import_asset_bytes(
        pid, "Texture pad.wav", assets_data["texture"], source="demo-multitrack", provenance="Independent 4-bar ambient texture pad (48 kHz Stereo)"
    )

    parsed_notes = [MidiNote(**n) for n in synth_extra["midi"]["notes"]]
    proj = store.load_project(pid)
    proj.notes = (
        "Demo Project B (Multitrack Session): 5 independent tracks (Drums, Bass, Guitar/Keys, Synth MIDI, Texture) "
        "in F minor at 128 BPM. All audio is real 48 kHz stereo PCM and Synth is imported from a real .mid file."
    )
    proj.loopRegion = LoopRegion(enabled=True, startBeats=16.0, endBeats=32.0)
    proj.sections = [
        SectionMarker(id="sec_intro", name="INTRO", startBeats=0.0, endBeats=16.0, color="#49505e"),
        SectionMarker(id="sec_groove", name="GROOVE", startBeats=16.0, endBeats=32.0, color="#446256"),
        SectionMarker(id="sec_bridge", name="BRIDGE", startBeats=32.0, endBeats=48.0, color="#554d6b"),
        SectionMarker(id="sec_climax", name="CLIMAX", startBeats=48.0, endBeats=64.0, color="#6d5645"),
    ]
    proj.tracks = [
        Track(
            id="trk_drums",
            name="Drums",
            type="audio",
            color="#6a997c",
            gainDb=-1.5,
            pan=0.0,
            clips=[
                Clip(id="clp_drums_1", name="Drums 1", type="audio", assetId=a_drums.id, timelineStartBeats=0.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_drums.durationSec, loop=True, loopLengthSec=a_drums.durationSec),
                Clip(id="clp_drums_2", name="Drums 2", type="audio", assetId=a_drums.id, timelineStartBeats=16.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_drums.durationSec, loop=True, loopLengthSec=a_drums.durationSec),
                Clip(id="clp_drums_4", name="Drums 4", type="audio", assetId=a_drums.id, timelineStartBeats=48.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_drums.durationSec, loop=True, loopLengthSec=a_drums.durationSec),
            ],
        ),
        Track(
            id="trk_bass",
            name="Bass",
            type="audio",
            color="#867ca8",
            gainDb=-2.0,
            pan=0.0,
            clips=[
                Clip(id="clp_bass_2", name="Bass 2", type="audio", assetId=a_bass.id, timelineStartBeats=16.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_bass.durationSec, loop=True, loopLengthSec=a_bass.durationSec),
                Clip(id="clp_bass_3", name="Bass 3", type="audio", assetId=a_bass.id, timelineStartBeats=32.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_bass.durationSec, loop=True, loopLengthSec=a_bass.durationSec),
                Clip(id="clp_bass_4", name="Bass 4", type="audio", assetId=a_bass.id, timelineStartBeats=48.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_bass.durationSec, loop=True, loopLengthSec=a_bass.durationSec),
            ],
        ),
        Track(
            id="trk_guitar",
            name="Guitar / Keys",
            type="audio",
            color="#b89458",
            gainDb=-1.0,
            pan=-0.12,
            clips=[
                Clip(id="clp_guitar_1", name="Guitar 1", type="audio", assetId=a_guitar.id, timelineStartBeats=0.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_guitar.durationSec, loop=True, loopLengthSec=a_guitar.durationSec),
                Clip(id="clp_guitar_2", name="Guitar 2", type="audio", assetId=a_guitar.id, timelineStartBeats=16.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_guitar.durationSec, loop=True, loopLengthSec=a_guitar.durationSec),
                Clip(id="clp_guitar_4", name="Guitar 4", type="audio", assetId=a_guitar.id, timelineStartBeats=48.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_guitar.durationSec, loop=True, loopLengthSec=a_guitar.durationSec),
            ],
        ),
        Track(
            id="trk_synth",
            name="Synth",
            type="midi",
            color="#648ea8",
            gainDb=-3.0,
            pan=0.14,
            instrumentRef="basic-poly-synth",
            clips=[
                Clip(id="clp_synth_2", name="Synth 2", type="midi", assetId=a_synth.id, timelineStartBeats=16.0, durationBeats=16.0, loop=True, loopLengthBeats=16.0, notes=parsed_notes),
                Clip(id="clp_synth_3", name="Synth 3", type="midi", assetId=a_synth.id, timelineStartBeats=32.0, durationBeats=16.0, loop=True, loopLengthBeats=16.0, notes=[MidiNote(**{**n.model_dump(), "id": make_id("note")}) for n in parsed_notes]),
                Clip(id="clp_synth_4", name="Synth 4", type="midi", assetId=a_synth.id, timelineStartBeats=48.0, durationBeats=16.0, loop=True, loopLengthBeats=16.0, notes=[MidiNote(**{**n.model_dump(), "id": make_id("note")}) for n in parsed_notes]),
            ],
        ),
        Track(
            id="trk_texture",
            name="Texture",
            type="audio",
            color="#9e7389",
            gainDb=-4.5,
            pan=0.0,
            clips=[
                Clip(id="clp_texture_1", name="Texture 1", type="audio", assetId=a_texture.id, timelineStartBeats=0.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_texture.durationSec, loop=True, loopLengthSec=a_texture.durationSec),
                Clip(id="clp_texture_3", name="Texture 3", type="audio", assetId=a_texture.id, timelineStartBeats=32.0, durationBeats=16.0, sourceOffsetSec=0.0, sourceDurationSec=a_texture.durationSec, loop=True, loopLengthSec=a_texture.durationSec),
            ],
        ),
    ]
    return store.save_project(proj)


def seed_demo_project_a(assets_data: dict[str, bytes], force: bool = False) -> Project | None:
    """Demo Project A · House (V7.2 Magnetic Afterhours real YuE2 mix + MIDI guide)."""
    if "v72_house" not in assets_data:
        return None
    pid = "demo_v72_magnetic_afterhours"
    pfile = store.projects_root() / pid / "project.json"
    if pfile.is_file() and not force:
        return store.load_project(pid)

    proj = store.create_project(
        name="V7.2 Magnetic Afterhours · House",
        bpm=128.0,
        numerator=4,
        denominator=4,
        length_beats=208.0,
        project_id=pid,
        with_default_tracks=False,
    )

    a_mix, _ = store.import_asset_bytes(
        pid,
        "V7.2_Magnetic_Afterhours_final.wav",
        assets_data["v72_house"],
        source="yue2-v7.2",
        provenance="Verified YuE2 V7.2 House full mix (codex/v7-2-house-hook-first, 48 kHz Stereo)",
    )
    a_midi, midi_extra = store.import_asset_bytes(
        pid,
        "Magnetic_Afterhours_Hook.mid",
        assets_data["synth_mid"],
        source="score-guide",
        provenance="F-minor 128 BPM hook MIDI guide (muted by default; no fabricated stems)",
    )

    parsed_notes = [MidiNote(**n) for n in midi_extra["midi"]["notes"]]
    mix_beats = round(a_mix.durationSec * (128.0 / 60.0), 3)
    proj = store.load_project(pid)
    proj.lengthBeats = max(208.0, math.ceil(mix_beats / 4.0) * 4.0)
    proj.notes = (
        "Demo Project A (House): Real YuE2 V7.2 Magnetic Afterhours full mix (96.0s, 128 BPM, Fm). "
        "No separated stems exist in this branch; fake stems are intentionally NOT fabricated."
    )
    proj.loopRegion = LoopRegion(enabled=True, startBeats=112.0, endBeats=128.0)
    proj.sections = [
        SectionMarker(id="sec_v72_intro", name="INTRO", startBeats=0.0, endBeats=32.0, color="#49505e"),
        SectionMarker(id="sec_v72_groove", name="MAIN GROOVE", startBeats=32.0, endBeats=84.0, color="#446256"),
        SectionMarker(id="sec_v72_break", name="BREAKDOWN", startBeats=84.0, endBeats=100.0, color="#554d6b"),
        SectionMarker(id="sec_v72_build", name="BUILD", startBeats=100.0, endBeats=112.0, color="#6d5645"),
        SectionMarker(id="sec_v72_drop", name="DROP / RETURN", startBeats=112.0, endBeats=176.0, color="#4e6b5e"),
        SectionMarker(id="sec_v72_outro", name="OUTRO", startBeats=176.0, endBeats=208.0, color="#49505e"),
    ]
    proj.tracks = [
        Track(
            id="trk_v72_mix",
            name="Magnetic Afterhours (Mix)",
            type="audio",
            color="#6a997c",
            gainDb=0.0,
            pan=0.0,
            clips=[
                Clip(
                    id="clp_v72_full",
                    name="V7.2 Full Mix",
                    type="audio",
                    assetId=a_mix.id,
                    timelineStartBeats=0.0,
                    durationBeats=mix_beats,
                    sourceOffsetSec=0.0,
                    sourceDurationSec=a_mix.durationSec,
                    loop=False,
                )
            ],
        ),
        Track(
            id="trk_v72_midi_guide",
            name="Hook Guide (MIDI)",
            type="midi",
            color="#648ea8",
            gainDb=-6.0,
            pan=0.0,
            mute=True,
            instrumentRef="basic-poly-synth",
            clips=[
                Clip(
                    id="clp_v72_hook_1",
                    name="Hook Motif A",
                    type="midi",
                    assetId=a_midi.id,
                    timelineStartBeats=16.0,
                    durationBeats=16.0,
                    loop=False,
                    notes=parsed_notes,
                ),
                Clip(
                    id="clp_v72_hook_2",
                    name="Hook Return",
                    type="midi",
                    assetId=a_midi.id,
                    timelineStartBeats=112.0,
                    durationBeats=16.0,
                    loop=False,
                    notes=[MidiNote(**{**n.model_dump(), "id": make_id("note")}) for n in parsed_notes],
                ),
            ],
        ),
    ]
    return store.save_project(proj)


def main() -> None:
    force = "--force" in sys.argv
    engine_paths.initialize()
    assets_data = seed_library()
    proj_a = seed_demo_project_a(assets_data, force=force)
    proj_b = seed_demo_project_b(assets_data, force=force)
    print(f"Seeded studio library at: {engine_paths.DATA / 'daw' / 'library'}")
    if proj_a:
        print(f"Seeded Demo Project A: {proj_a.name} ({proj_a.id})")
    else:
        print("Demo Project A skipped (V7.2 git ref not found in current checkout).")
    print(f"Seeded Demo Project B: {proj_b.name} ({proj_b.id})")


if __name__ == "__main__":
    main()
