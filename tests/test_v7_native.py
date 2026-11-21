import hashlib
import json

import pytest

from engine.paths import ROOT
from scripts import v4_study, v7_native


def test_instrumental_brief_dispatches_to_native_yue2_without_score(
    monkeypatch, tmp_path
):
    request = {}

    def run(engine, genre, seed, brief, *, output_root, score, cot, plan_gate):
        request.update(engine=engine, genre=genre, seed=seed, **brief)
        assert score is None and cot == "full" and plan_gate is None
        return output_root / "take"

    monkeypatch.setattr(v7_native, "DATA", tmp_path)
    monkeypatch.setattr(v7_native, "run", run)
    assert v7_native.generate("Grunge guitars", 42, 120) == tmp_path / "v7/take"
    assert request == {
        "engine": "yue2",
        "genre": "instrumental-rock",
        "seed": 42,
        "duration": 120,
        "style": "Grunge guitars Instrumental.",
        "lyrics": "",
        "instrumental": True,
    }


def test_native_score_gate_blocks_audio_decode(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(v7_native, "DATA", tmp_path)

    def guarded(command, log):
        commands.append(command)
        (log.parent / "planned.abc").write_text("V: Vocal\nA4|\nV: Ins\nA4|\n")
        return {}

    monkeypatch.setattr(v4_study, "run_guarded", guarded)
    out = v7_native.generate(
        "Analog pluck, four on the floor",
        14,
        90,
        genre="house-techno-128",
        bpm=128,
        screen_score=True,
    )
    request = json.loads((out / "planner-request.json").read_text())
    assert request["style"] == "128 BPM. Analog pluck, four on the floor Instrumental."
    assert request["cot"] == "full" and "bpm" not in request
    assert request["lyrics"] == ""
    assert len(commands) == 1 and commands[0][0].endswith("yue-plan")
    assert json.loads((out / "experiment.json").read_text())["status"] == "rejected"
    assert not (out / "original.wav").exists()


def test_instrumental_abc_accepts_chords_on_rests_but_rejects_lyrics():
    v7_native.check_resting_voice('V: Vocal\n"Am"z4|\nV: Ins\nA4|\n')
    with pytest.raises(v4_study.ScoreRejected):
        v7_native.check_resting_voice("V: Vocal\nZ|\nV: Ins\nA4|\nw: Yeah\n")


def test_golden_rock_audio_matches_pr6_and_preserved_metadata():
    directory = ROOT / "examples/v7/golden"
    manifest = json.loads((directory / "manifest.json").read_text())
    pr6 = json.loads((ROOT / "examples/challengers/results.json").read_text())

    for track, entry in zip(
        manifest["tracks"], pr6["genres"]["rock"][::2], strict=True
    ):
        assert track["files"]["original.wav"]["sha256"] == entry["sha256"]
        for record in track["files"].values():
            with (directory / record["file"]).open("rb") as handle:
                assert (
                    hashlib.file_digest(handle, "sha256").hexdigest()
                    == record["sha256"]
                )
        preview = track["preview"]
        with (ROOT / preview["file"]).open("rb") as handle:
            assert (
                hashlib.file_digest(handle, "sha256").hexdigest() == preview["sha256"]
            )
