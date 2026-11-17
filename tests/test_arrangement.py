import pytest
from engine.schema import Generate, ArrangementPlan
from agent.music_intent import preview, compile_plan
from agent.arrangement import draft_arrangement

PROMPT = "펑키 디스코 120BPM. 처음에는 뮤트 기타 커팅과 하이햇, 잠시 후 킥과 베이스, 메인에는 브라스와 신스. 보컬 없는 음악."


def test_natural_intro_compiles_without_immediate_full_band_instruction():
    plan = compile_plan(Generate(prompt=PROMPT))
    sections = plan["intent"]["arrangement_plan"]["sections"]
    assert [(s["start"], s["end"]) for s in sections] == [
        (0, 4),
        (4, 12),
        (12, 28),
        (28, 30),
    ]
    assert "kick" in sections[0]["withhold"]
    assert "establish groove immediately" not in plan["caption"]
    assert "12–28s main_groove" in plan["caption"]
    assert plan["caption"] == preview(Generate(prompt=PROMPT))["caption"]


def test_genres_and_global_exclusions():
    ambient = draft_arrangement("ambient intro", 30)
    assert all(not any("kick" in i for i in s.instruments) for s in ambient.sections)
    house = draft_arrangement("house intro", 30)
    assert "filtered chord stab" in house.sections[0].instruments
    funk = draft_arrangement("funk intro", 30, ["guitar"])
    assert all(not any("guitar" in i for i in s.instruments) for s in funk.sections)


def test_invalid_timeline_and_duration():
    plan = draft_arrangement("funk intro", 30).model_dump()
    plan["sections"][1]["start"] = 3
    with pytest.raises(ValueError):
        ArrangementPlan(**plan)
    intent = preview(Generate(prompt=PROMPT))["intent"]
    with pytest.raises(ValueError, match="duration"):
        compile_plan(Generate(prompt="funk instrumental", duration=15, intent=intent))
    short = compile_plan(Generate(prompt=PROMPT, duration=15))
    assert short["intent"]["arrangement_plan"]["sections"][-1]["end"] == 15


def test_existing_non_arranged_generation_preserves_compatibility():
    plan = compile_plan(Generate(prompt="디스코 instrumental"))
    assert "arrangement_plan" not in plan["intent"]
    assert "establish groove immediately" in plan["caption"]
