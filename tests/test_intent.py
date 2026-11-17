import pytest
from agent.music_intent import preview, compile_plan, FUNK_DISCO
from engine.schema import Generate, MusicIntent
from app.mcp_server import plan
from fastapi.testclient import TestClient
from app.player.server import app


def test_ambiguous_vocals_require_explicit_choice():
    assert preview(Generate(prompt="funk disco"))["ready"] is False
    with pytest.raises(ValueError, match="보컬"):
        compile_plan(Generate(prompt="funk disco"))
    assert (
        compile_plan(Generate(prompt="funk disco", instrumental=False))["instrumental"]
        is False
    )
    assert compile_plan(Generate(prompt="보컬 없는 디스코"))["instrumental"] is True
    assert (
        compile_plan(Generate(prompt="리드 보컬과 코러스 디스코"))["instrumental"]
        is False
    )


def test_structured_intent_is_authoritative_and_preview_matches_generation():
    intent = MusicIntent(
        **FUNK_DISCO,
        vocal_mode="vocal",
        vocal_character="original alto lead",
        exclusions=["guitar"],
    )
    cmd = Generate(
        prompt="120bpm 디스코", intent=intent, lyrics="[Verse]\nDance into the light"
    )
    planned = compile_plan(cmd)
    assert planned["caption"] == preview(cmd)["caption"]
    assert planned["intent"]["rhythm_guitar"] == ""
    assert "guitar and bass trade accents" not in planned["caption"]
    assert planned["lyrics"] == cmd.lyrics and not planned["instrumental"]
    assert planned["timesignature"] == "4"
    assert plan(cmd.prompt, intent=intent)["caption"] == planned["caption"]


def test_player_plan_roundtrip():
    with TestClient(app) as c:
        r = c.post(
            "/api/plan",
            json={"prompt": "펑키 디스코"},
            headers={"X-Studio-Request": "1"},
        )
        assert r.status_code == 200 and not r.json()["ready"]
        draft = r.json()["intent"]
        draft["vocal_mode"] = "instrumental"
        draft["bpm"] = 118
        r = c.post(
            "/api/plan",
            json={"prompt": "펑키 디스코", "intent": draft},
            headers={"X-Studio-Request": "1"},
        )
        assert r.json()["ready"] and r.json()["intent"]["bpm"] == 118
