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


def verified_host(snapshot):
    # Incomplete jobs and projects built by older versions have no replay proof.
    for report in sorted(
        snapshot.glob("host-*/render.json"),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    ):
        try:
            qa = json.loads(report.read_text())
        except (OSError, ValueError):
            continue
        if qa.get("reopen_pcm_identical") and all(
            (report.parent / name).is_file()
            for name in (
                "Studio.RPP",
                "master.wav",
                "dry-Master.wav",
                "reaper-mixed.wav",
            )
        ):
            return report.parent
    return None


def inspect(version):
    path = folder(version)
    spec = json.loads((path / "session.json").read_text())
    result = {
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
    host = verified_host(path)
    if host:
        result["reaper"] = {
            "project": str(host / "Studio.RPP"),
            "master": str(host / "master.wav"),
            "mix": str(host / "reaper-mixed.wav"),
            "dry": str(host / "dry-Master.wav"),
        }
    return result


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


def export(version):
    """Bundle the MIDI score, separate sample recordings, attributions and preview."""
    from zipfile import ZIP_STORED, ZipFile

    path = folder(version)
    host = verified_host(path)
    archive = host / "reaper-session.zip" if host else path / "soul-session.zip"
    if not archive.exists():
        spec = json.loads((path / "session.json").read_text())
        with TemporaryDirectory(dir=path) as temp:
            target = Path(temp) / archive.name
            with ZipFile(target, "x", compression=ZIP_STORED) as bundle:
                for name in (
                    "Score.RPP",
                    "session.json",
                    "session-preview.wav",
                    "zones.tsv",
                    "mix.tsv",
                ):
                    source = (
                        host
                        if host and name in ("Score.RPP", "zones.tsv", "mix.tsv")
                        else path
                    )
                    bundle.write(source / name, name)
                if host:
                    for name in (
                        "Studio.RPP",
                        "Dry.RPP",
                        "dry-Master.wav",
                        "reaper-mixed.wav",
                        "master.wav",
                        "render.json",
                    ):
                        bundle.write(host / name, name)
                # The script and TSV parameter layout must come from the same export.
                bundle.write((host or path) / "build.lua", "build.lua")
                for sample in sorted(((host or path) / "Samples").iterdir()):
                    bundle.write(sample, "Samples/" + sample.name)
                credits = [
                    "Session Engine preview. Score.RPP contains editable MIDI.",
                    "Run build.lua within an approved REAPER installation to build the instrument project.",
                    "Host playback remains unverified. The WAV was rendered using Session Engine.",
                    "Sources were mapped, transposed, enveloped and mixed for this arrangement.",
                ]
                if host:
                    credits[:3] = [
                        "Open Studio.RPP in REAPER with Samples/ alongside it.",
                        "REAPER rendered dry-Master.wav and reaper-mixed.wav. master.wav includes the Session Engine master chain.",
                        "session-preview.wav is the Python preview of the arrangement.",
                    ]
                for info in spec["sources"].values():
                    credits.append(
                        f"{info['author']} | {info['license']} | https://github.com/{info['repo']}/tree/{info['revision']}"
                    )
                credits.append(
                    "Wurlitzer EP200 and CP80 by Greg Sullivan. SFZ mapping by kinwie. https://creativecommons.org/licenses/by/3.0/"
                )
                bundle.writestr("CREDITS.txt", "\n".join(credits) + "\n")
                if (path / "edit.json").is_file():
                    bundle.write(path / "edit.json", "edit.json")
            with ZipFile(target) as verify:
                if verify.testzip():
                    raise ValueError("Archive integrity check failed")
            # Independent concurrent exports publish the same immutable score.
            target.replace(archive)
    return {
        "version": version,
        "archive": str(archive),
        "audio": str(host / "master.wav" if host else path / "session-preview.wav"),
        "backend": "reaper" if host else "session-preview",
    }
