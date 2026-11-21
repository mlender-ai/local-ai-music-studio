import hashlib
import json

from engine.paths import ROOT
from scripts import v7_native


def test_instrumental_brief_dispatches_to_native_yue2_without_score(
    monkeypatch, tmp_path
):
    request = {}

    def run(engine, genre, seed, brief, *, output_root):
        request.update(engine=engine, genre=genre, seed=seed, **brief)
        return output_root / "take"

    monkeypatch.setattr(v7_native, "DATA", tmp_path)
    monkeypatch.setattr(v7_native, "run", run)
    assert v7_native.generate("Grunge guitars", 42, 120) == tmp_path / "v7/take"
    assert request == {
        "engine": "yue2",
        "genre": "instrumental-rock",
        "seed": 42,
        "duration": 120,
        "style": "Instrumental guitar rock. Grunge guitars",
        "lyrics": "",
    }


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
