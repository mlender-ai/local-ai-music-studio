"""Phase 03.1 + GATE 2 Verification:
- Shared Runtime Registry 6-state lifecycle
- YuE2 exact V7.2 CLI flags + preflight ABC resting-voice gate + 3-state vocal screening
- No silent fallback from Neural Audio / YuE2 / ACE-Step to local MIDI
- Real subprocess process-group cancellation (TEST F)
- Real authenticated Claude Code CLI isolated music authoring
- Multi-reference binding & 5-state feature consumption
- All 4 apply_take() fixes, Stem Isolation (TEST D), Concurrent Edit Merge (TEST E)
"""

from __future__ import annotations

import json
import math
import os
import stat
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.daw_server import app
from engine import paths as engine_paths
from engine.composition import build_reference_binding, create_composition_plan
from engine.composition.schemas import QualityReport, Take, TakeArtifact, TakeProvenance
from engine.daw_workspace import commands, references, store
from engine.daw_workspace.schema import Clip, MidiNote, SectionMarker, Track
from engine.generation import apply_take, generation_jobs
from engine.generation.adapters import check_resting_voice, run_yue2_generation, screen_vocal_leakage
from engine.generation.daw_jobs import persist_take, snapshot_track_fingerprints
from engine.generation.process_guard import GenerationCancelledError, run_cancellable_guarded
from engine.providers import detect_providers
from engine.runtime import get_runtime_registry, record_engine_verification, save_local_runtime_overrides


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_paths, "DATA", tmp_path / "data")
    monkeypatch.setattr(engine_paths, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setenv("DAW_RUNTIME_CONFIG", str(tmp_path / "runtime_config.json"))
    engine_paths.initialize()
    return tmp_path


def _write_wav(path: Path, freq=220.0, duration=4.0, sr=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    sig = 0.25 * np.sin(2 * math.pi * freq * t)
    stereo = np.stack([sig, sig], axis=1).astype(np.float32)
    sf.write(str(path), stereo, sr, subtype="PCM_24")
    return path


def test_shared_runtime_registry_six_state_lifecycle(isolated_env):
    """Runtime Registry accurately distinguishes uninstalled -> binary_found -> ready -> verified."""
    reg0 = get_runtime_registry()
    yue0 = next(e for e in reg0["engines"] if e["id"] == "yue2-native")
    assert yue0["state"] == "uninstalled"
    assert yue0["available"] is False

    # Create dummy executable yue-synth -> state MUST become binary_found (NOT ready!)
    bin_dir = isolated_env / "shared_rt" / "v4" / "yue2cpp" / "build"
    bin_dir.mkdir(parents=True)
    fake_bin = bin_dir / "yue-synth"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC)
    save_local_runtime_overrides({"sharedRuntimeRoot": str(isolated_env / "shared_rt")})

    reg1 = get_runtime_registry()
    yue1 = next(e for e in reg1["engines"] if e["id"] == "yue2-native")
    assert yue1["state"] == "binary_found"
    assert yue1["available"] is False  # Binary alone is NEVER ready!

    # Add dummy model & VAE -> state becomes ready (NOT verified until real WAV generation succeeds!)
    mdl_dir = isolated_env / "shared_rt" / "v4" / "models"
    mdl_dir.mkdir(parents=True)
    (mdl_dir / "YuE2-3B-Q8_0.gguf").write_bytes(b"gguf")
    (mdl_dir / "YuE2-Vae-F32.gguf").write_bytes(b"vae")

    reg2 = get_runtime_registry()
    yue2 = next(e for e in reg2["engines"] if e["id"] == "yue2-native")
    assert yue2["state"] == "ready"
    assert yue2["available"] is True
    assert yue2["verified"] is False

    # Record verified WAV smoke test -> state becomes verified!
    record_engine_verification("yue2-native", True, wav_path="/tmp/smoke.wav")
    reg3 = get_runtime_registry()
    yue3 = next(e for e in reg3["engines"] if e["id"] == "yue2-native")
    assert yue3["state"] == "verified"
    assert yue3["verified"] is True


def test_yue2_v72_cli_and_preflight_abc_gate_blocks_vocals(isolated_env):
    """YuE2 adapter invokes exact V7.2 flags AND check_resting_voice blocks vocal preflight before synthesis."""
    rt = isolated_env / "runtime" / "v4"
    bin_dir = rt / "yue2cpp" / "build"
    mdl_dir = rt / "models"
    bin_dir.mkdir(parents=True)
    mdl_dir.mkdir(parents=True)
    (mdl_dir / "YuE2-3B-Q8_0.gguf").write_bytes(b"mock-q8")
    (mdl_dir / "YuE2-Vae-F32.gguf").write_bytes(b"mock-vae")

    # 1. Mock yue-plan emitting SUNG VOCAL NOTES -> check_resting_voice MUST reject before yue-synth runs!
    plan_bin = bin_dir / "yue-plan"
    synth_bin = bin_dir / "yue-synth"
    synth_marker = isolated_env / "synth_was_called.txt"

    plan_bin.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
        "out.write_text('X:1\\nM:4/4\\nK:Fm\\n% intro\\nV:Vocal\\nF2 G2 A2 c2|\\nV:Ins\\nF4|\\n')\n"
    )
    plan_bin.chmod(0o755)
    synth_bin.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib, json\n"
        f"pathlib.Path({str(synth_marker)!r}).write_text(json.dumps(sys.argv))\n"
    )
    synth_bin.chmod(0o755)

    proj = store.create_project(name="YuE2 Gate QA", bpm=128.0)
    plan = create_composition_plan(proj, "128 BPM instrumental house track", mode="full_music")

    with pytest.raises(ValueError, match="preflight ABC rejected"):
        run_yue2_generation(plan, isolated_env / "out1" / "original.wav", seed=1185)
    assert not synth_marker.exists(), "yue-synth MUST NOT execute after preflight ABC gate rejects vocal lane!"

    # 2. Now mock yue-plan emitting VALID resting Vocal + sounding Ins -> yue-synth runs with exact V7.2 flags!
    plan_bin.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
        "out.write_text('X:1\\nM:4/4\\nK:Fm\\n% intro\\nV:Vocal\\nZ4|\\nV:Ins\\nF2 A2 c2 f2|\\n')\n"
    )
    synth_bin.write_text(
        f"#!{sys.executable}\n"
        "import sys, pathlib, json, numpy as np, soundfile as sf\n"
        f"pathlib.Path({str(synth_marker)!r}).write_text(json.dumps(sys.argv))\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])\n"
        "sr = 48000; t = np.arange(sr * 2) / sr\n"
        "sig = (0.2 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)\n"
        "sf.write(str(out), np.stack([sig, sig], axis=1), sr)\n"
    )
    res = run_yue2_generation(plan, isolated_env / "out2" / "original.wav", seed=1185)
    argv = json.loads(synth_marker.read_text())
    assert "--model" in argv and "--vae" in argv and "--request" in argv and "--max-seq" in argv and "--out" in argv and "--score" in argv
    assert res["scoreSource"] == "native_preflight_verified"
    # Without PANNs/Whisper installed, neural audio vocal screening MUST honestly return UNCERTAIN (never false PASS!)
    assert res["vocalScreening"]["status"] == "UNCERTAIN"
    assert res["vocalScreening"]["autoApprovedInstrumental"] is False


def test_no_silent_substitution_when_neural_engine_requested(isolated_env):
    """Requesting yue2-native, ace-step-local, or neural_audio when uninstalled MUST NOT silently run local MIDI."""
    proj = store.create_project(name="Honest Engine", bpm=128.0)
    plan = create_composition_plan(proj, "128 BPM house track", mode="full_music")
    for eng in ("yue2-native", "ace-step-local", "neural_audio"):
        res = generation_jobs.start_composition_job(proj.id, plan, engine_choice=eng, sync=True)
        assert res.get("engineUnavailable") is True
        assert res.get("requestedEngine") == eng
        assert "take" not in res


def test_f_real_subprocess_cancellation_kills_child_process_and_frees_lock(isolated_env):
    """TEST F: Cancelling a running heavy subprocess actually kills the OS child process cleanly."""
    pid_file = isolated_env / "child.pid"
    cancel_ev = threading.Event()
    script = (
        f"import os, time, pathlib; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        f"time.sleep(30)"
    )

    def trigger_cancel():
        deadline = time.monotonic() + 5.0
        while not pid_file.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.1)
        cancel_ev.set()

    t = threading.Thread(target=trigger_cancel, daemon=True)
    t.start()

    started = time.monotonic()
    with pytest.raises(GenerationCancelledError):
        run_cancellable_guarded(
            [sys.executable, "-c", script],
            isolated_env / "cancel_test.log",
            cancel_event=cancel_ev,
            timeout_sec=15.0,
        )
    elapsed = time.monotonic() - started
    t.join(timeout=2.0)

    assert elapsed < 4.0, f"Cancellation took too long ({elapsed:.2f}s)"
    child_pid = int(pid_file.read_text().strip())
    time.sleep(0.15)
    assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE


def test_multi_reference_binding_and_five_state_feature_consumption(isolated_env, tmp_path):
    """Multi-reference binding tracks Ref A & Ref B independently and distinguishes Mapped vs Consumed."""
    proj = store.create_project(name="Multi Ref QA", bpm=128.0)
    wav_a = _write_wav(tmp_path / "ref_a_drums.wav", freq=110.0, duration=5.0)
    wav_b = _write_wav(tmp_path / "ref_b_space.wav", freq=440.0, duration=5.0)
    ref_a, _ = references.import_reference_file(proj.id, "RefA_Groove.wav", wav_a.read_bytes())
    ref_b, _ = references.import_reference_file(proj.id, "RefB_Space.wav", wav_b.read_bytes())
    references.run_reference_analysis_sync(proj.id, ref_a["id"])
    references.run_reference_analysis_sync(proj.id, ref_b["id"])
    proj = store.load_project(proj.id)

    # 1. Empty reference_ids=[] MUST NOT auto-attach any reference!
    empty_b = build_reference_binding(proj, reference_ids=[])
    assert empty_b.referenceIds == []
    assert empty_b.appliedFeatures == {}

    # 2. Multi-reference binding with per-reference distinct purposes
    multi = build_reference_binding(
        proj,
        reference_ids=[ref_a["id"], ref_b["id"]],
        per_reference_influences={
            ref_a["id"]: ["drums_groove"],
            ref_b["id"]: ["arrangement_arc", "spatial_depth"],
        },
        target_engine="local-multitrack-composer",
    )
    assert set(multi.referenceIds) == {ref_a["id"], ref_b["id"]}
    assert len(multi.perReferenceBindings) == 2
    by_feat = {f["feature"]: f for f in multi.featureLifecycle}
    assert by_feat["grooveFeel"]["sourceReferenceId"] == ref_a["id"]
    assert by_feat["grooveFeel"]["consumed"] is True
    assert by_feat["arrangementArc"]["sourceReferenceId"] == ref_b["id"]
    assert by_feat["arrangementArc"]["consumed"] is True
    # Stereo width MUST honestly stay `consumed: False` for MIDI composer!
    assert by_feat["stereoWidthTarget"]["sourceReferenceId"] == ref_b["id"]
    assert by_feat["stereoWidthTarget"]["mapped"] is True
    assert by_feat["stereoWidthTarget"]["consumed"] is False


def test_gate2_apply_take_fixes_replace_range_stem_isolation_and_concurrent_merge(isolated_env):
    """GATE 2: Fixes all 4 apply_take bugs, TEST D (Stem Isolation), and TEST E (Concurrent Editing)."""
    proj = store.create_project(name="Gate 2 Safety", bpm=128.0, with_default_tracks=False)
    proj.sections = [
        SectionMarker(id="sec_custom_1", name="CUSTOM INTRO", startBeats=0.0, endBeats=16.0, color="#49505e"),
        SectionMarker(id="sec_custom_2", name="CUSTOM DROP", startBeats=16.0, endBeats=48.0, color="#446256"),
    ]
    proj.tracks = [
        Track(
            id="trk_drums",
            name="Drums",
            type="midi",
            instrumentRef="drum-kit-electronic",
            gainDb=-1.0,
            clips=[
                Clip(
                    id="clp_d_full",
                    name="Drums 1-12",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=48.0,  # Bars 1..12
                    notes=[
                        MidiNote(id="dn1", pitch=36, velocity=110, startBeat=0.0, durationBeats=0.5),
                        MidiNote(id="dn2", pitch=36, velocity=110, startBeat=20.0, durationBeats=0.5),  # inside bars 5..8
                        MidiNote(id="dn3", pitch=36, velocity=110, startBeat=36.0, durationBeats=0.5),  # bars 9..12
                    ],
                )
            ],
        ),
        Track(
            id="trk_bass",
            name="Bass",
            type="midi",
            instrumentRef="bass-fm-sub",
            gainDb=-2.0,
            clips=[],
        ),
        Track(id="trk_mix", name="Full Mix", type="audio", gainDb=0.0, mute=False, clips=[]),
        Track(id="trk_guitar_live", name="Live Guitar", type="audio", gainDb=-1.5, mute=False, clips=[]),
    ]
    saved = store.save_project(proj)
    base_rev = saved.revision
    base_fps = snapshot_track_fingerprints(saved)

    # --- TEST E: User edits Bass gainDb WHILE AI Drum Variation Take is staged at base_rev ---
    updated_bass = commands.apply_command(saved, "track.setGain", {"trackId": "trk_bass", "gainDb": -5.5})
    saved_after_user = store.save_project(updated_bass, expected_revision=base_rev)
    assert saved_after_user.revision == base_rev + 1

    # Create a Drum Variation Take targeting bars 5..8 (beats 16..32) recorded at `base_rev`
    drum_take = Take(
        id="take_drum_var",
        projectId=saved.id,
        jobId="gjob_1",
        title="Drums Bars 5–8 Fill",
        mode="midi_variation",
        status="ready",
        baseRevision=base_rev,
        baseTrackFingerprints=base_fps,
        targetTrackId="trk_drums",
        targetRangeBeats={"startBeats": 16.0, "endBeats": 32.0},
        artifacts=[
            TakeArtifact(
                role="drums",
                name="Drums Var 5-8",
                trackType="midi",
                instrumentRef="basic-poly-synth",  # Intentionally different to test Bug #2 fix (must NOT overwrite drum-kit-electronic!)
                startBeats=16.0,
                durationBeats=16.0,
                notes=[{"id": "nv1", "pitch": 38, "velocity": 118, "startBeat": 14.0, "durationBeats": 0.25}],
            )
        ],
        provenance=TakeProvenance(
            engine="midi-variation-v4",
            engineLabel="MIDI Variation Engine",
            mode="midi_variation",
            providerId="local-music-director",
            model="music-director-v4",
            seed=42,
        ),
    )
    persist_take(saved.id, drum_take)

    # Apply with `replace_range` using stale `expected_revision=base_rev`!
    res = apply_take(
        project_id=saved.id,
        take_id="take_drum_var",
        apply_mode="replace_range",
        target_track_id="trk_drums",
        start_beats=16.0,
        expected_revision=base_rev,
    )
    assert res["applied"] is True
    assert res["concurrentMergeApplied"] is True
    assert "Bass" in res["preservedConcurrentTracks"]

    after = store.load_project(saved.id)
    # 1. Bass user edit (-5.5 dB) MUST be preserved!
    bass_trk = next(t for t in after.tracks if t.id == "trk_bass")
    assert bass_trk.gainDb == -5.5
    # 2. Drums track instrumentRef MUST remain `drum-kit-electronic` (Bug #2 fixed!)
    drums_trk = next(t for t in after.tracks if t.id == "trk_drums")
    assert drums_trk.instrumentRef == "drum-kit-electronic"
    # 3. Drums clips MUST have zero overlap: [0..16], [16..32 (new)], [32..48]! (Bug #1 fixed!)
    ranges = sorted((c.timelineStartBeats, c.timelineStartBeats + c.durationBeats) for c in drums_trk.clips)
    assert ranges == [(0.0, 16.0), (16.0, 32.0), (32.0, 48.0)]
    # Automatic Original Backup Take Lane created!
    assert any(ln.get("isOriginalBackup") for ln in drums_trk.takeLanes)
    # 4. Existing custom section markers MUST be preserved (Bug #4 fixed!)
    assert [s.name for s in after.sections] == ["CUSTOM INTRO", "CUSTOM DROP"]
    # 5. Duplicate apply guard blocks applying the same take twice!
    with pytest.raises(ValueError, match="already been applied"):
        apply_take(project_id=saved.id, take_id="take_drum_var", apply_mode="replace_range", target_track_id="trk_drums")

    # --- TEST D: Stem Separation Isolation ---
    # Must mute ONLY `trk_mix` (sourceTrackId) and leave `trk_guitar_live` UNMUTED!
    stem_wav = _write_wav(store.project_dir(saved.id) / "takes" / "take_stems" / "drums.wav", freq=80.0, duration=2.0)
    stem_take = Take(
        id="take_stems",
        projectId=saved.id,
        jobId="gjob_stems",
        title="Stems: Full Mix",
        mode="stem_separation",
        status="ready",
        sourceTrackId="trk_mix",
        parentSourceAssetId="ast_mix",
        separationModel="htdemucs",
        separationJobId="gjob_stems",
        artifacts=[
            TakeArtifact(
                role="drums",
                name="Drums (Stem)",
                trackType="stem",
                color="#6a997c",
                audioRelativePath=stem_wav.relative_to(store.project_dir(saved.id)).as_posix(),
                startBeats=0.0,
                durationBeats=8.0,
            )
        ],
        provenance=TakeProvenance(
            engine="demucs-htdemucs",
            engineLabel="Demucs Stem Separator",
            mode="stem_separation",
            providerId="local-dsp",
            model="htdemucs",
            seed=0,
        ),
    )
    persist_take(saved.id, stem_take)
    apply_take(project_id=saved.id, take_id="take_stems", apply_mode="add")

    after_stems = store.load_project(saved.id)
    mix_trk = next(t for t in after_stems.tracks if t.id == "trk_mix")
    gtr_trk = next(t for t in after_stems.tracks if t.id == "trk_guitar_live")
    stem_trk = next(t for t in after_stems.tracks if t.type == "stem")
    assert mix_trk.mute is True, "Original separated source track must be muted"
    assert gtr_trk.mute is False, "TEST D FAIL: Unrelated Live Guitar audio track was wrongly muted!"
    assert stem_trk.stemMeta["sourceTrackId"] == "trk_mix"
    assert stem_trk.stemMeta["separationModel"] == "htdemucs"


def test_real_authenticated_claude_cli_provider_authors_structured_music_plan(isolated_env):
    """When native authenticated Claude Code CLI is present on this Mac, verify real isolated JSON authoring."""
    provs = detect_providers()
    claude = next(p for p in provs if p["id"] == "claude-cli")
    mcp_p = next(p for p in provs if p["id"] == "mcp-external")
    # Honest MCP status: ready_for_client, never falsely connected!
    assert mcp_p["connected"] is False
    assert mcp_p["providerState"] == "ready_for_client"

    if not claude["available"]:
        pytest.skip("Authenticated local Claude CLI not available in this environment")

    proj = store.create_project(name="Claude Live Authoring QA", bpm=124.0)
    plan = create_composition_plan(
        proj,
        "124 BPM 몽환적인 딥하우스 4마디 신스 훅 만들어줘. 코드는 감성적인 마이너 9th 느낌으로.",
        mode="loop_midi",
        target_instrument="synth_hook",
        provider_id="claude-cli",
    )
    prov = plan.providerProvenance
    assert prov["providerId"] == "claude-cli"
    assert prov["llmUsed"] is True
    assert prov["isolatedNoTools"] is True
    assert len(prov["llmAuthoredFields"]) >= 2
    assert len(plan.harmonyAndGroove["chordProgression"]) == 4
