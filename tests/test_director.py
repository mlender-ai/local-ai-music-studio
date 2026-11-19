import json
import pytest
from agent.director import preview, compile_director
from engine.schema import Generate
from engine.music_plan import MusicPlan
from engine.paths import ROOT
from fastapi.testclient import TestClient
from app.player.server import app


def sample():
    return json.loads((ROOT / "examples/director/soul.json").read_text())


def test_codex_plan_metadata_and_soft_capabilities():
    c = Generate(prompt="smooth soul", music_plan=sample())
    p = compile_director(c)
    assert p["keyscale"] == "D minor" and p["bpm"] == 116
    assert p["conditioning"]["tokens"] <= 256
    assert "per-track DSP" in p["capabilities"]["not_executed"]
    assert p["music_plan"]["source"] == "codex"
    assert "4.5s: bass and drums enter" in p["caption"]


def test_presets_not_llm_and_vocals_explicit():
    d = preview(Generate(prompt="부드러운 소울 디스코 120BPM"))
    assert d["music_plan"]["source"] == "preset_fallback" and not d["ready"]
    assert d["music_plan"]["rhythm"]["bpm"] == 120
    d = preview(Generate(prompt="딥 하우스 보컬 곡"))
    assert d["ready"] and d["music_plan"]["vocal_mode"] == "vocal"
    with pytest.raises(ValueError):
        preview(Generate(prompt="디스코 기타 없이 instrumental"))


def test_validation_and_budget():
    p = sample()
    p["events"][1]["at_fraction"] = 0
    with pytest.raises(ValueError):
        MusicPlan(**p)
    p = sample()
    p["harmony"]["key"] = "invalid"
    with pytest.raises(ValueError):
        MusicPlan(**p)
    p = sample()
    p["production"]["space"] = "spatial reflection " * 9
    p["sessions"] = [
        {
            "instrument": "guitar",
            "role_and_interaction": "guitar plays short syncopated phrases " * 4,
        }
    ] * 8
    with pytest.raises(ValueError, match="256"):
        preview(Generate(prompt="soul disco", music_plan=p))
    with pytest.raises(ValueError):
        Generate(prompt="soul disco", music_plan=sample(), intent={})
    with pytest.raises(ValueError):
        Generate(prompt="soul disco", duration=60)


def test_director_http_and_legacy_compatibility():
    with TestClient(app) as client:
        r = client.post(
            "/api/director",
            json={"prompt": "deep house instrumental"},
            headers={"x-studio-request": "1"},
        )
        assert r.status_code == 200 and r.json()["ready"]
        r = client.post(
            "/api/plan",
            json={"prompt": "soul disco", "music_plan": sample()},
            headers={"x-studio-request": "1"},
        )
        assert r.status_code == 200 and r.json()["music_plan"]["source"] == "codex"
    from agent.command_parser import generation_plan

    p = generation_plan(Generate(prompt="디스코 instrumental"))
    assert "music_plan" not in p and "inference_profile" not in p
    p = generation_plan(
        Generate(prompt="디스코 instrumental", inference_profile="turbo_8bit")
    )
    assert p["inference_profile"] == "turbo_8bit"


def test_natural_duration_and_no_profile_collision():
    d = preview(Generate(prompt="soul disco instrumental 15초"))
    assert d["duration"] == 15 and "2.25s" in d["caption"]
    with pytest.raises(ValueError):
        preview(Generate(prompt="soul disco instrumental 60초"))
