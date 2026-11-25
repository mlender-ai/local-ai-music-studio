"""GATE 1 Verification Tests — Phase 03.2.1 Advanced Reference Fidelity.

Proves:
1. Full-length audio analysis coverage & Actual Beat Grid vs Fixed BPM Grid
2. 15-quality chord tracker + passing chord + top-3 candidates + chord.split/merge commands
3. Full-length 8-bar unique-per-bar drum transcription, Variation Map & STRICT BAR-BY-BAR LOCK (0% 2-bar collapse!)
4. Full-length Bass performance lock (rhythm & duration preserved while re-harmonizing to new Chord Track)
5. Multi-Reference independent feature binding (`feature_source_map`), pre-generation conflict detection & strict Lock honesty
6. Acoustic Sound & Spatial Profiler + Blueprint v3 + Honest 5-category Instrument Classification
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.composition.director import create_composition_plan
from engine.composition.midi_composer import parse_chord
from engine.composition.reference_context import build_reference_binding
from engine.daw_workspace import analysis, commands
from engine.daw_workspace.schema import ChordEvent, Project, make_id
from engine.generation.adapters.local_composer_adapter import execute_local_composition
from engine.transcription.chord_tracker import (
    SUPPORTED_CHORD_QUALITIES,
    extract_chord_timeline,
    parse_chord_metadata,
)
from engine.transcription.drum_transcriber import transcribe_drum_groove
from engine.transcription.pipeline import build_reference_blueprint_v2, validate_feature_locks_for_engine
from engine.transcription.sound_profiler import (
    analyze_bass_performance,
    classify_instruments_honestly,
    extract_sound_and_spatial_profile,
)


def _synth_chord_audio(chords: list[tuple[list[int], float]], sr: int = 24000, bpm: float = 120.0) -> np.ndarray:
    """Synthesize clean additive harmonic audio for known chord sequences [(midi_notes, beats), ...]."""
    sec_per_beat = 60.0 / bpm
    segs: list[np.ndarray] = []
    for notes, beats in chords:
        n_samp = int(round(beats * sec_per_beat * sr))
        t = np.arange(n_samp, dtype=np.float64) / sr
        sig = np.zeros(n_samp, dtype=np.float64)
        env = np.minimum(1.0, t / 0.015) * np.minimum(1.0, (beats * sec_per_beat - t) / 0.025)
        env = np.clip(env, 0.0, 1.0)
        for idx, m in enumerate(notes):
            f0 = 440.0 * (2.0 ** ((m - 69) / 12.0))
            amp = 0.28 if idx == 0 else 0.18
            sig += amp * (np.sin(2 * np.pi * f0 * t) + 0.30 * np.sin(4 * np.pi * f0 * t))
        segs.append((sig * env).astype(np.float32))
    mono = np.concatenate(segs)
    return np.stack([mono, mono], axis=1)


def _synth_drum_audio(hits: list[tuple[float, int, float]], total_beats: float, bpm: float = 120.0, sr: int = 22050) -> np.ndarray:
    """Synthesize acoustically distinct Kick (36), Snare (38), Hat (42/46), Crash (49), Tom (45) hits."""
    sec_per_beat = 60.0 / bpm
    n_tot = int(round((total_beats * sec_per_beat + 0.5) * sr))
    buf = np.zeros(n_tot, dtype=np.float64)
    rng = np.random.default_rng(1234)

    for beat, pitch, vel_norm in hits:
        idx = int(round(beat * sec_per_beat * sr))
        if pitch == 36:  # Kick: 110 -> 50 Hz punchy sine
            dur = int(0.18 * sr)
            t = np.arange(dur) / sr
            freq = 50.0 + 95.0 * np.exp(-t * 32.0)
            sig = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 18.0) * vel_norm
        elif pitch in (37, 38, 39):  # Snare: 220 Hz body + mid bandpass noise
            dur = int(0.15 * sr)
            t = np.arange(dur) / sr
            body = np.sin(2 * np.pi * 210.0 * t) * np.exp(-t * 28.0)
            noise = rng.normal(0, 1, dur)
            # Band-shape noise around ~1.2 kHz
            noise = np.convolve(noise, [0.25, 0.5, 0.25], mode="same") - np.convolve(noise, np.ones(12) / 12.0, mode="same")
            sig = (0.45 * body + 0.75 * noise * np.exp(-t * 24.0)) * vel_norm
        elif pitch == 42:  # Closed hat: sharp 7 kHz burst
            dur = int(0.06 * sr)
            t = np.arange(dur) / sr
            noise = np.diff(rng.normal(0, 1, dur + 1))
            sig = noise * np.exp(-t * 80.0) * 0.65 * vel_norm
        elif pitch == 46:  # Open hat: longer high-band tail (~180ms)
            dur = int(0.24 * sr)
            t = np.arange(dur) / sr
            noise = np.diff(rng.normal(0, 1, dur + 1))
            sig = noise * np.exp(-t * 10.0) * 0.55 * vel_norm
        elif pitch == 49:  # Crash: long high-band wash (>450ms)
            dur = int(0.65 * sr)
            t = np.arange(dur) / sr
            noise = np.diff(rng.normal(0, 1, dur + 1))
            sig = noise * np.exp(-t * 3.8) * 0.85 * vel_norm
        else:  # Tom (45)
            dur = int(0.18 * sr)
            t = np.arange(dur) / sr
            sig = np.sin(2 * np.pi * 165.0 * t) * np.exp(-t * 15.0) * vel_norm

        end = min(n_tot, idx + len(sig))
        if end > idx >= 0:
            buf[idx:end] += sig[: end - idx]

    peak = float(np.max(np.abs(buf))) + 1e-9
    buf = (buf / peak * 0.85).astype(np.float32)
    return np.stack([buf, buf], axis=1)


def test_beat_grid_and_analysis_coverage(tmp_path: Path) -> None:
    """Verify actualBeatGrid vs fixedBpmGrid, tempoVariationBpmStd, and honest analysisCoverage."""
    hits = [(float(b), 36, 1.0) for b in range(32)] + [(b + 0.5, 42, 0.6) for b in range(32)]
    audio = _synth_drum_audio(hits, total_beats=32.0, bpm=124.0)
    wav = tmp_path / "steady_124.wav"
    sf.write(str(wav), audio, 22050)

    res = analysis.analyze_audio_file(wav, source_asset_id="ref_1", sha256="abc123", cache_dir=tmp_path / "cache")
    cov = res["analysisCoverage"]
    assert cov["isComplete"] is True
    assert cov["truncated"] is False
    assert cov["coveragePct"] >= 99.0

    rhy = res["rhythm"]
    assert len(rhy["actualBeatGrid"]) >= 24
    assert len(rhy["fixedBpmGrid"]) == len(rhy["actualBeatGrid"])
    assert "tempoVariationBpmStd" in rhy
    assert rhy["tempoStability"] in ("steady", "slight_drift", "expressive_rubato")
    assert "timeSeconds" in rhy["actualBeatGrid"][0] and "localBpm" in rhy["actualBeatGrid"][0]


def test_15_quality_chord_tracker_candidates_and_split_merge(tmp_path: Path) -> None:
    """Verify all 15 chord qualities parse cleanly, audio recognition returns top-3 candidates, and split/merge work."""
    assert len(SUPPORTED_CHORD_QUALITIES) >= 15
    for sym, expected_q in [
        ("C", "major"), ("Am", "minor"), ("G7", "dom7"), ("Fmaj7", "maj7"), ("Dm7", "min7"),
        ("Dsus2", "sus2"), ("Gsus4", "sus4"), ("Cadd9", "add9"), ("Bdim", "dim"),
        ("Bm7b5", "half_dim"), ("Caug", "aug"), ("C6", "sixth"), ("G9", "dom9"),
        ("E5", "power"), ("C/E", "major"),
    ]:
        meta = parse_chord_metadata(sym)
        assert meta["quality"] == expected_q, f"{sym} parsed as {meta}"
        root_pc, ints = parse_chord(sym)
        assert len(ints) >= 2 and 0 <= root_pc < 12

    # Synthesize real harmonic progression with Major, Minor7, Maj7, Dom7, Sus4, Slash C/E
    seq = [
        ([48, 60, 64, 67], 4.0),          # C major
        ([57, 60, 64, 67], 4.0),          # Am7
        ([53, 60, 64, 69], 4.0),          # Fmaj7
        ([55, 59, 62, 65], 4.0),          # G7
        ([52, 60, 64, 67], 4.0),          # C/E (slash inversion!)
    ]
    wav = tmp_path / "chords_test.wav"
    sf.write(str(wav), _synth_chord_audio(seq, bpm=120.0), 24000)

    timeline = extract_chord_timeline(wav, bpm=120.0, key_hint="C major", slice_beats=1.0)
    assert len(timeline) >= 4
    for ev in timeline:
        assert "candidates" in ev and len(ev["candidates"]) == 3
        assert "isPassing" in ev
    symbols = [e["symbol"] for e in timeline]
    assert any(s.startswith("C") for s in symbols)
    assert any(s.startswith("F") for s in symbols)
    assert any(s.startswith("G") for s in symbols)

    # Test chord.split and chord.merge commands on Project
    proj = Project(name="Chord Edit Test", bpm=120.0)
    proj = commands.apply_command(
        proj,
        "chord.setTrack",
        {"chords": [ChordEvent(id="chd_a", symbol="Fm7", root="F", quality="min7", startBeat=0.0, endBeat=4.0).model_dump()]},
    )
    proj = commands.apply_command(
        proj,
        "chord.split",
        {"chordId": "chd_a", "splitBeat": 2.0, "rightChordId": "chd_b", "rightSymbol": "Bb7", "rightRoot": "Bb", "rightQuality": "dom7"},
    )
    assert len(proj.chordTrack) == 2
    assert proj.chordTrack[0].endBeat == 2.0 and proj.chordTrack[1].startBeat == 2.0 and proj.chordTrack[1].symbol == "Bb7"
    proj = commands.apply_command(proj, "chord.merge", {"leftChordId": "chd_a", "rightChordId": "chd_b", "symbol": "Fm9"})
    assert len(proj.chordTrack) == 1 and proj.chordTrack[0].endBeat == 4.0 and proj.chordTrack[0].symbol == "Fm9"


def test_strict_8bar_unique_drum_lock_zero_2bar_collapse(tmp_path: Path) -> None:
    """CRITICAL GATE 1 QA: 8-bar drum performance with unique bars, fill (Bar 4), breakdown (Bar 5), crash re-entry (Bar 6) MUST NOT collapse into 2 bars!"""
    # Build 8 genuinely distinct bars of drums at 120 BPM (4 beats/bar = 32 beats total)
    hits: list[tuple[float, int, float]] = []
    # Bar 1 (0..4): straight 4-on-floor kick + 2/4 snare + 8th closed hats
    for b in (0.0, 1.0, 2.0, 3.0):
        hits.append((b, 36, 1.0))
    hits += [(1.0, 38, 0.9), (3.0, 38, 0.9)]
    for b in (0.5, 1.5, 2.5, 3.5):
        hits.append((b, 42, 0.7))
    # Bar 2 (4..8): syncopated kick at 6.5 (beat 3.5)
    hits += [(4.0, 36, 1.0), (5.0, 38, 0.9), (6.5, 36, 0.95), (7.0, 38, 0.9)]
    # Bar 3 (8..12): double kick + open hat at 10.5
    hits += [(8.0, 36, 1.0), (8.75, 36, 0.85), (9.0, 38, 0.9), (10.0, 36, 1.0), (10.5, 46, 0.8), (11.0, 38, 0.9)]
    # Bar 4 (12..16): snare/tom turnaround fill on beats 3..4!
    hits += [(12.0, 36, 1.0), (13.0, 38, 0.9), (14.5, 38, 0.85), (15.0, 38, 0.9), (15.25, 38, 0.9), (15.5, 45, 0.95), (15.75, 45, 0.95)]
    # Bar 5 (16..20): BREAKDOWN (silent drum dropout!)
    # Bar 6 (20..24): CRASH cymbal re-entry at 20.0 + driving kick
    hits += [(20.0, 49, 1.0), (20.0, 36, 1.0), (21.0, 38, 0.95), (22.0, 36, 1.0), (23.0, 38, 0.95)]
    # Bar 7 (24..28): sparse halftime pocket
    hits += [(24.0, 36, 1.0), (26.0, 38, 0.95), (27.5, 36, 0.9)]
    # Bar 8 (28..32): big climax fill
    hits += [(28.0, 36, 1.0), (29.0, 38, 0.95), (30.0, 36, 1.0), (30.75, 38, 0.85), (31.0, 38, 0.9), (31.5, 38, 0.95), (31.75, 45, 1.0)]

    wav = tmp_path / "drums_8bar.wav"
    sf.write(str(wav), _synth_drum_audio(hits, total_beats=32.0, bpm=120.0), 22050)

    tr = transcribe_drum_groove(wav, bpm=120.0, bpb=4.0, source_kind="demucs_drums_stem")
    assert tr["analysisCoverage"]["isComplete"] is True
    assert tr["hasDrums"] is True
    assert tr["variationMap"]["totalBars"] >= 8
    assert tr["variationMap"]["hasBarByBarVariation"] is True
    assert 5 in tr["breakdownBars"], f"Bar 5 breakdown must be detected! Got: {tr['breakdownBars']}"
    assert len(tr["fillBars"]) >= 1, f"Fill bars must be detected! Got: {tr['fillBars']}"
    # Check full canonical Drum Event Schema fields
    sample_ev = tr["quantizedMidiNotes"][0]
    for field in ("eventId", "timeSeconds", "startBeat", "barIndex", "beatInBar", "drumClass", "midiPitch", "velocityEstimate", "timingDeviationMs", "confidence", "isGhostNote"):
        assert field in sample_ev, f"Missing canonical drum schema field: {field}"

    # Now feed FULL 8-bar drum performance into LOCKED generation and prove ZERO 2-bar collapse!
    proj = Project(name="Strict Drum Lock QA", bpm=120.0, lengthBeats=32.0)
    ref_id = make_id("ref")
    dsp_stub = {
        "durationSec": 16.0,
        "analysisCoverage": tr["analysisCoverage"],
        "rhythm": {"adoptedTempoBpm": 120.0, "estimatedBpm": 120.0, "meterEstimate": "4/4", "confidence": 0.92, "beatGridSec": [0.0], "downbeatsSec": [0.0]},
        "harmony": {"estimatedKey": "F minor", "confidence": 0.8},
        "arrangement": {"sections": [{"id": "s1", "label": "A", "startSec": 0.0, "endSec": 16.0, "relativeEnergy": 0.8}]},
        "sound": {"measured": {"stereoWidth": 0.25, "spectralCentroidHz": 1600.0, "frequencyBandsPct": {}, "integratedLufs": -14.0}, "estimated": {"transientCharacter": "punchy", "reverbCharacter": "tight / dry"}},
        "instrumentation": {"elements": []},
    }
    bp = build_reference_blueprint_v2(
        ref_id=ref_id,
        sha256="drum8barsha",
        dsp_analysis=dsp_stub,
        transcription={"drums": tr, "chordTimeline": [{"id": "c1", "symbol": "Fm7", "root": "F", "quality": "min7", "startBeat": 0.0, "endBeat": 32.0, "confidence": 0.9}], "modelsUsed": []},
    )
    assert bp["blueprintVersion"] == "3.0.0"
    proj.references.append({"id": ref_id, "name": "8-Bar Unique Drums", "analysis": dsp_stub, "blueprint": bp, "transcription": {"drums": tr}})

    plan = create_composition_plan(
        proj,
        "이 레퍼런스의 8마디 드럼 연주를 완전 고정해서 8마디 풀 트랙을 만들어줘",
        mode="full_music",
        reference_ids=[ref_id],
        feature_locks={"bpm": "locked", "drum_rhythm": "locked", "chord_progression": "locked"},
    )
    take = execute_local_composition(proj, plan, tmp_path / "take_drum_lock", job_id="job_1", seed=7)
    fv = take.qualityReport.musical["featureVerification"]
    assert fv is not None
    df = fv["drumFidelity"]
    assert df["f1"] >= 0.95, f"Strict locked drum F1 must be >= 0.95, got {df}"
    assert df["minBarF1"] >= 0.90, f"Every individual bar must match without 2-bar collapse! Got {df['perBarF1']}"
    assert "drumGroovePattern" in fv["verifiedFeatures"]

    # Verify Bar 5 (beats 16..20) remained empty (breakdown preserved, NOT overwritten by Bar 1/3 2-bar loop!)
    drums_art = next(a for a in take.artifacts if a.role == "drums")
    bar5_hits = [n for n in drums_art.notes if 16.0 <= n["startBeat"] < 20.0]
    assert len(bar5_hits) == 0, f"Bar 5 breakdown was overwritten! Found {len(bar5_hits)} hits"


def test_bass_rhythm_and_duration_lock_with_reharmonized_chords(tmp_path: Path) -> None:
    """Verify full-length Bass Lock preserves exact bar-by-bar timing/durations/rests while adapting pitches to a new Chord Track."""
    ref_bass_notes = [
        # Bar 1: long root + syncopated short octave jump
        {"pitch": 36, "velocity": 105, "startBeat": 0.0, "quantizedStartBeat": 0.0, "durationBeats": 1.5, "quantizedDurationBeats": 1.5},
        {"pitch": 48, "velocity": 95, "startBeat": 2.5, "quantizedStartBeat": 2.5, "durationBeats": 0.5, "quantizedDurationBeats": 0.5},
        # Bar 2: different rhythm! 3 staccato hits + rest
        {"pitch": 36, "velocity": 102, "startBeat": 4.0, "quantizedStartBeat": 4.0, "durationBeats": 0.5, "quantizedDurationBeats": 0.5},
        {"pitch": 43, "velocity": 96, "startBeat": 5.25, "quantizedStartBeat": 5.25, "durationBeats": 0.5, "quantizedDurationBeats": 0.5},
        {"pitch": 36, "velocity": 108, "startBeat": 6.0, "quantizedStartBeat": 6.0, "durationBeats": 1.0, "quantizedDurationBeats": 1.0},
        # Bar 3: syncopated single held pedal note (distinct from Bar 1!)
        {"pitch": 36, "velocity": 100, "startBeat": 8.5, "quantizedStartBeat": 8.5, "durationBeats": 2.5, "quantizedDurationBeats": 2.5},
        # Bar 4: turnaround pickup
        {"pitch": 36, "velocity": 104, "startBeat": 12.0, "quantizedStartBeat": 12.0, "durationBeats": 1.0, "quantizedDurationBeats": 1.0},
        {"pitch": 41, "velocity": 98, "startBeat": 14.5, "quantizedStartBeat": 14.5, "durationBeats": 0.5, "quantizedDurationBeats": 0.5},
        {"pitch": 43, "velocity": 102, "startBeat": 15.25, "quantizedStartBeat": 15.25, "durationBeats": 0.5, "quantizedDurationBeats": 0.5},
    ]
    bass_perf = analyze_bass_performance(ref_bass_notes, bpb=4.0, duration_sec=8.0, bpm=120.0)
    assert bass_perf["totalBars"] == 4
    assert bass_perf["uniqueBarRhythmCount"] == 4
    assert bass_perf["octaveJumpCount"] >= 1

    proj = Project(name="Bass Lock Reharm", bpm=120.0, lengthBeats=16.0)
    proj.chordTrackLocked = True
    proj.chordTrack = [
        ChordEvent(symbol="Fm7", root="F", quality="min7", startBeat=0.0, endBeat=4.0),
        ChordEvent(symbol="Dbmaj7", root="Db", quality="maj7", startBeat=4.0, endBeat=8.0),
        ChordEvent(symbol="Abmaj7", root="Ab", quality="maj7", startBeat=8.0, endBeat=12.0),
        ChordEvent(symbol="Eb7", root="Eb", quality="dom7", startBeat=12.0, endBeat=16.0),
    ]
    ref_id = make_id("ref")
    proj.references.append(
        {
            "id": ref_id,
            "name": "C-Minor Bass Ref",
            "analysis": {"rhythm": {"adoptedTempoBpm": 120.0}, "harmony": {"estimatedKey": "C minor"}},
            "blueprint": {
                "blueprintVersion": "3.0.0",
                "tempoMap": {"bpm": 120.0},
                "bassPerformance": bass_perf,
                "bassEvents": {"notes": bass_perf["notes"], "noteCount": len(ref_bass_notes)},
            },
        }
    )

    plan = create_composition_plan(
        proj,
        "4마디 베이스 리듬과 음가를 고정하고 프로젝트 코드 트랙에 맞춰 만들어줘",
        mode="loop_midi",
        target_instrument="bass",
        reference_ids=[ref_id],
        feature_locks={"bass_groove": "locked", "chord_progression": "locked"},
        bass_lock_mode="rhythm_and_duration",
        use_project_chord_track=True,
    )
    take = execute_local_composition(proj, plan, tmp_path / "take_bass_lock", job_id="job_2", seed=11)
    fv = take.qualityReport.musical["featureVerification"]
    assert fv["bassFidelity"]["f1"] >= 0.99
    assert fv["bassFidelity"]["meanDurationErrorBeats"] <= 0.05
    assert fv["bassChordMatchRatio"] >= 0.95
    assert "bassGroovePattern" in fv["verifiedFeatures"]

    # Confirm Bar 1 starts on F (pc 5), Bar 2 starts on Db (pc 1), Bar 3 starts on Ab (pc 8), Bar 4 starts on Eb (pc 3)!
    bass_notes = take.artifacts[0].notes
    assert len(bass_notes) == len(ref_bass_notes)
    assert bass_notes[0]["pitch"] % 12 == 5  # F
    assert bass_notes[2]["pitch"] % 12 == 1  # Db
    assert bass_notes[5]["pitch"] % 12 == 8 and abs(bass_notes[5]["startBeat"] - 8.5) < 0.01  # Ab at 8.5!
    assert bass_notes[6]["pitch"] % 12 == 3  # Eb


def test_multi_reference_independent_binding_conflicts_and_strict_lock_honesty() -> None:
    """Verify Ref A (BPM+Drums) + Ref B (Chords) independent featureSourceMap, BPM conflict alert, and zero silent LOCK downgrade."""
    proj = Project(name="Multi-Ref QA", bpm=120.0)
    ref_a = {
        "id": "ref_a",
        "name": "House 128 Ref",
        "analysis": {"rhythm": {"adoptedTempoBpm": 128.0, "meterEstimate": "4/4"}, "harmony": {"estimatedKey": "F minor"}},
        "blueprint": {
            "tempoMap": {"bpm": 128.0, "meter": "4/4"},
            "drumPerformance": {"totalBars": 4, "quantizedPerformance": [{"pitch": 36, "startBeat": 0.0, "durationBeats": 0.35, "velocity": 110}]},
            "drumEvents": {"quantizedNotes": [{"pitch": 36, "startBeat": 0.0, "durationBeats": 0.35, "velocity": 110}]},
            "harmonicCharacter": {"key": "F minor"},
        },
    }
    ref_b = {
        "id": "ref_b",
        "name": "Jazz 90 Ref",
        "analysis": {"rhythm": {"adoptedTempoBpm": 90.0, "meterEstimate": "4/4"}, "harmony": {"estimatedKey": "D minor"}},
        "blueprint": {
            "tempoMap": {"bpm": 90.0, "meter": "4/4"},
            "chordTimeline": [{"id": "c1", "symbol": "Dm9", "root": "D", "quality": "min9", "startBeat": 0.0, "endBeat": 4.0, "confidence": 0.9}],
            "harmonicCharacter": {"key": "D minor", "sampleChords": ["Dm9", "G13"]},
        },
    }
    proj.references = [ref_a, ref_b]

    binding = build_reference_binding(
        proj,
        reference_ids=["ref_a", "ref_b"],
        feature_source_map={"bpm": "ref_a", "drum_rhythm": "ref_a", "chord_progression": "ref_b"},
        feature_locks={"bpm": "locked", "drum_rhythm": "locked", "chord_progression": "locked"},
    )
    assert binding.appliedFeatures["tempoBpm"] == 128.0
    assert binding.appliedFeatures["referenceChords"] == ["Dm9"]
    assert binding.featureSourceMap["bpm"] == "ref_a"
    assert binding.featureSourceMap["drum_rhythm"] == "ref_a"
    assert binding.featureSourceMap["chord_progression"] == "ref_b"
    assert any(c["type"] == "bpm_mismatch" for c in binding.conflicts)

    # Strict Lock Honesty: Neural engine MUST mark drum_rhythm="locked" as "unsupported", NEVER silently downgrade to "reference"!
    report = validate_feature_locks_for_engine(
        {"drum_rhythm": "locked", "bass_groove": "locked"},
        engine_id="yue2-native",
        has_transcribed_drums=True,
        has_transcribed_bass=True,
        has_chord_timeline=True,
    )
    assert report["effectiveLocks"]["drum_rhythm"] == "unsupported"
    assert report["effectiveLocks"]["bass_groove"] == "unsupported"
    assert report["allLockedSatisfied"] is False


def test_sound_spatial_profiler_and_honest_instrument_classification(tmp_path: Path) -> None:
    """Verify Sound/Spatial profiler distinguishes dry mono vs wide reverberant stereo and honest 5-class labeling."""
    sr = 24000
    t = np.arange(sr * 3, dtype=np.float64) / sr
    # Dry mono percussive plucks
    dry_m = np.zeros_like(t)
    for k in range(6):
        idx = int(k * 0.5 * sr)
        dur = int(0.08 * sr)
        tt = np.arange(dur) / sr
        dry_m[idx : idx + dur] += np.sin(2 * np.pi * 440.0 * tt) * np.exp(-tt * 38.0) * 0.7
    dry_wav = tmp_path / "dry_mono.wav"
    sf.write(str(dry_wav), np.stack([dry_m, dry_m], axis=1).astype(np.float32), sr)

    # Wide reverberant stereo pad + diffused tail
    rng = np.random.default_rng(99)
    wet_l = np.convolve(dry_m, rng.normal(0, 1, int(0.9 * sr)) * np.exp(-np.arange(int(0.9 * sr)) / (0.35 * sr)), mode="same")
    wet_r = np.convolve(dry_m, rng.normal(0, 1, int(0.9 * sr)) * np.exp(-np.arange(int(0.9 * sr)) / (0.35 * sr)), mode="same")
    wet_stereo = np.stack([wet_l, wet_r], axis=1)
    wet_stereo /= float(np.max(np.abs(wet_stereo))) + 1e-9
    wet_wav = tmp_path / "wet_wide.wav"
    sf.write(str(wet_wav), (wet_stereo * 0.7).astype(np.float32), sr)

    p_dry = extract_sound_and_spatial_profile(dry_wav, role="other", bpm=120.0)
    p_wet = extract_sound_and_spatial_profile(wet_wav, role="other", bpm=120.0)
    assert p_wet["soundProfile"]["stereoWidth"] > p_dry["soundProfile"]["stereoWidth"] + 0.3
    assert p_wet["spatialProfile"]["reverbTailSecEstimate"] > p_dry["spatialProfile"]["reverbTailSecEstimate"]
    assert p_wet["spatialProfile"]["relativeDistance"] == "distant_ambient"
    assert "플러그인 파라미터" in p_wet["honestyDisclaimer"]

    # Honest 5-category classification: `other` stem MUST be "Mixed Harmonic Content"
    classes = classify_instruments_honestly(
        stem_analyses={"drums": {"active": True}, "bass": {"active": True}, "other": {"active": True}, "vocals": {"active": False}},
        drum_result={"quantizedMidiNotes": [{}] * 12},
        bass_result={"noteCount": 8, "meanConfidence": 0.8},
        melody_result={"noteCount": 6},
        other_result={"noteCount": 20, "meanConfidence": 0.7},
        dsp_elements=[],
    )
    by_role = {c["role"]: c["classification"] for c in classes}
    assert by_role["drums"] == "Separated Stem"
    assert by_role["bass"] == "Transcribed Instrument"
    assert by_role["other"] == "Mixed Harmonic Content"
    assert by_role["vocals"] == "Unknown"
