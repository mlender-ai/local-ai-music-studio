from copy import deepcopy

import pytest

from engine.daw import controller, edits, instruments, project
from engine.music_plan import MusicPlan
from engine.paths import ROOT
from engine.session.render import specification


def chart():
    return specification(
        MusicPlan.model_validate_json(
            (ROOT / "examples/director/soul.json").read_text()
        )
    )


def test_region_is_scoped_and_serializes_note_offs():
    original = chart()
    before = deepcopy(original)
    changed, log = edits.edit(original, edits.ARRANGE)
    assert original == before
    assert log["bars"] == [9, 12]
    notes, _ = project.assignments(changed)
    for key, events in project.assignments(original)[0].items():
        voice, bar = key
        if not 9 <= bar <= 12 or voice not in ("guitar", "chuck", "bass"):
            assert notes[key] == events
        elif voice != "bass":
            assert not notes[key]
        else:
            assert notes[key] != events
        lines = list(project.midi_lines(notes[key]))
        assert sum(int(line.split()[1]) for line in lines) == 4 * project.PPQ
        assert len(lines) == 2 * len(notes[key]) + 1


def test_wurlitzer_layer_boundary_and_pinned_asset():
    for vel, layer in [
        (37, "pp"),
        (38, "mp"),
        (65, "mp"),
        (66, "f"),
        (89, "f"),
        (90, "ff"),
    ]:
        root, _cents, db, source, blob = instruments.key_region(61, vel, "ep200-sfz")
        assert source.endswith(layer + ".flac") and root == 61
        assert len(blob) == 40 and db < 0


def test_unsupported_commands_fail_without_changes():
    spec = chart()
    for command in ("기타를 모두 삭제", edits.ARRANGE.replace("9~12", "12~15")):
        with pytest.raises(ValueError):
            edits.edit(spec, command)
    with pytest.raises(ValueError):
        controller.folder("../session-engine")


def test_host_absence_does_not_create_files(tmp_path, monkeypatch):
    from engine.daw import host

    monkeypatch.setattr(host, "executable", lambda: None)
    with pytest.raises(RuntimeError, match="not found"):
        host.render(tmp_path)
    assert not list(tmp_path.iterdir())
