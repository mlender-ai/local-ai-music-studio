"""Address immutable score snapshots by ID. An undo selects the original parent."""

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from engine.paths import DATA
from engine.session.render import write_json

from . import edits, project

DEMO = ("01-reference", "02-region", "03-keys")


def folder(version):
    if version not in DEMO and not re.fullmatch("[0-9a-f]{32}", version):
        raise ValueError("Unknown DAW version ID")
    path = DATA / "daw-session" / version
    if not (path / "session.json").is_file():
        raise ValueError("No such version. Prepare the DAW session first.")
    return path


def inspect(version):
    path = folder(version)
    spec = json.loads((path / "session.json").read_text())
    return {
        "version": version,
        "backend": "session-preview",
        "score": str(path / "Score.RPP"),
        "audio": str(path / "session-preview.wav"),
        "key": spec["music_plan"]["harmony"]["key"],
        "bpm": spec["music_plan"]["rhythm"]["bpm"],
        "tracks": list(spec["sources"]),
        "sections": spec["sections"],
        "keyboard_mapping": spec.get("keyboard_mapping", "session-v1"),
    }


def region(version, first, last):
    spec = json.loads((folder(version) / "session.json").read_text())
    if not 1 <= first <= last <= len(spec["chart"]):
        raise ValueError("Bar range is outside the chart")
    return {
        "bars": [first, last],
        "chords": spec["chart"][first - 1 : last],
        "events": [e for e in spec["events"] if first <= e["bar"] <= last],
    }


def modify(version, command):
    from .demo import render_version

    path = folder(version)
    spec, change = edits.edit(json.loads((path / "session.json").read_text()), command)
    ident = uuid4().hex
    with TemporaryDirectory(dir=path.parent) as temp:
        stage = Path(temp) / "snapshot"
        stage.mkdir()
        render_version(spec, change, stage)
        project.export(spec, stage)
        write_json(stage / "parent.json", {"version": version})
        stage.rename(path.parent / ident)
    return inspect(ident)


def undo(version):
    path = folder(version)
    if version == "01-reference":
        raise ValueError("Reference has no parent")
    parent = (
        DEMO[DEMO.index(version) - 1]
        if version in DEMO
        else json.loads((path / "parent.json").read_text())["version"]
    )
    return inspect(parent)
