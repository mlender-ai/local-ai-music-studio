from engine.music_plan import MusicPlan
from engine.paths import ROOT
from engine.session.score import compose, CHORDS, CHART
from engine.session.render import specification
from app.player.server import app
from fastapi.testclient import TestClient


def test_chart_and_variants():
    plan = MusicPlan.model_validate_json(
        (ROOT / "examples/director/soul.json").read_text()
    )
    session = specification(plan)
    a = session["events"]
    d = session["variation_events"]
    assert session["frames"] == 1440000
    assert {e["track"] for e in a if e["bar"] <= 2} == {"drums", "keys"}
    for bar, chord in enumerate(CHART[2:], 3):
        bass = [e for e in a if e["bar"] == bar and e["track"] == "bass"]
        assert bass[0]["notes"] == [CHORDS[chord][0]]
        if bar < 14 and bar != 11:
            assert bass[-1]["notes"][0] + 1 == CHORDS[CHART[bar]][0]
    assert all(e["step"] < 9 for e in a if e["bar"] == 11)
    for instrument in ("drums", "bass", "guitar"):
        assert [e for e in a if e["track"] == instrument] != [
            e for e in d if e["track"] == instrument
        ]
    assert a == compose(plan)
    assert not [e for e in a if not 0 <= e["step"] < 16]


def test_session_lab_only_serves_published_labels():
    with TestClient(app) as c:
        assert c.get("/session-lab").status_code == 200
        assert c.get("/session-audio/unrelated.wav").status_code == 404
