from copy import deepcopy

import numpy as np

from engine.daw.instruments import key_region
from engine.daw.project import assignments
from engine.music_plan import MusicPlan
from engine.paths import ROOT
from engine.session.harmony import repair_soul, validate
from engine.session.render import specification
from engine.session.tuning import pitch


def session(name):
    return specification(
        MusicPlan.model_validate_json(
            (ROOT / "examples/director" / f"{name}.json").read_text()
        )
    )


def test_plan_drives_soul_bass_and_marker():
    plan = MusicPlan.model_validate_json(
        (ROOT / "examples/director/soul.json").read_text()
    )
    assert "session_arrangement" not in plan.model_dump()
    plan.harmony.progression = "G13 Dm9"
    spec = specification(plan)
    assert spec["chart"][:4] == ["G13", "Dm9"] * 2
    bass = next(e for e in spec["events"] if e["track"] == "bass")
    assert bass["bar"] == 3 and bass["notes"] == [31]


def test_repair_keeps_ninth_and_original_events():
    original = session("soul")
    e = next(e for e in original["events"] if e["bar"] == 7 and e["track"] == "keys")
    e["notes"] = [57, 60, 64, 65]
    original["music_plan"]["harmony"]["progression"] = "Dm9 G13 Cmaj9 A7"
    old = deepcopy(original)
    issues = validate(original)["issues"]
    assert {"plan_chart_disagreement", "sustained_semitone"} <= {
        i["kind"] for i in issues
    }
    fixed = repair_soul(original)
    assert original == old
    assert fixed["events"][original["events"].index(e)]["notes"] == [53, 57, 60, 64]
    assert validate(fixed)["passed"]


def test_quartet_regions_tensions_passing_and_break():
    spec = session("jazz-hip-hop")
    report = validate(spec)
    assert report["passed"] and report["bars"][3]["bass_approaches"]
    assert spec["frames"] == 1572000
    assert spec["sections"][-2]["name"] == "Break"
    assert "bass" not in report["bars"][10]["notes"]
    assert len(assignments(spec)[0]["keys", 12]) > 0
    # A passing note held across a strong beat must be reported.
    bass = next(e for e in spec["events"] if e["track"] == "bass")
    bass.update(notes=[44], step=0, length=5)
    assert any(
        i["kind"] == "nonchord_tone" and i["strong"] for i in validate(spec)["issues"]
    )


def test_rhodes_region_and_pitch_estimator():
    assert key_region(64, 72, "rhodes-sfz")[3].endswith("F4_4.flac")
    assert key_region(64, 73, "rhodes-sfz")[3].endswith("F4_3.flac")
    t = np.arange(24000) / 48000
    assert (
        abs(
            pitch(
                np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 440 * t), 48000
            )
            - 57
        )
        < 0.02
    )
    assert pitch(t * 0, 48000) is None
