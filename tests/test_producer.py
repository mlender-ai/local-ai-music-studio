import pytest
from agent.command_parser import generation_plan, production_plan
from engine.schema import Generate


def test_trip_hop_korean_intent():
    p = generation_plan(Generate(prompt="90년대 트립합. 85BPM, 보컬 없는 30초 음악."))
    assert p["bpm"] == 85 and p["duration"] == 30 and p["instrumental"]
    assert "trip-hop" in p["caption"]


def test_ambient_without_drums_and_requested_duration():
    p = generation_plan(
        Generate(prompt="드럼 없음, 우주 앰비언트", duration=15, instrumental=True)
    )
    assert p["duration"] == 15 and "no drums" in p["caption"]
    with pytest.raises(ValueError):
        generation_plan(Generate(prompt="트립합 300초"))


def test_editing_limits_and_plan():
    assert production_plan("멜로디를 바꿔줘")["status"] == "requires_regeneration"
    assert production_plan("알 수 없는 요청")["status"] == "unsupported"
    p = production_plan("베이스를 더 묵직하게, 조금 몽환적으로")
    assert [x["type"] for x in p["effects"]] == [
        "eq",
        "compressor",
        "eq",
        "reverb",
        "limiter",
    ]


def test_shell_payload_is_never_executed():
    assert production_plan("$(touch /tmp/unsafe)")["status"] == "unsupported"


def test_vocal_intent_and_non_dsp_changes():
    assert (
        generation_plan(Generate(prompt="여성 보컬의 따뜻한 하우스"))["instrumental"]
        is False
    )
    assert generation_plan(Generate(prompt="보컬 없는 하우스"))["instrumental"] is True
    assert (
        generation_plan(Generate(prompt="warm house with vocals", instrumental=True))[
            "instrumental"
        ]
        is True
    )
    for text in ["템포를 올려줘", "베이스 제거", "드럼을 빼줘"]:
        assert production_plan(text)["status"] == "requires_regeneration"


def test_funky_disco_preserves_tempo_and_expands_rhythm_and_guitar():
    prompt = (
        "90년대 펑키 디스코, MJ 스타일, 124bpm , 신나는 펑키 기타 리프, 디스코 리듬. "
    )
    plan = generation_plan(Generate(prompt=prompt, instrumental=True))
    assert plan["original_prompt"] == prompt
    assert plan["bpm"] == 124 and plan["timesignature"] == "4"
    for term in [
        "funk disco-pop",
        "1990s",
        "muted clean electric guitar",
        "four-on-the-floor",
        "chord chops",
        "syncopated",
        "interlocking",
    ]:
        assert term in plan["caption"]
    assert "[Instrumental]" == plan["lyrics"]
    assert "트립합" not in plan["caption"]


def test_dance_translation_keeps_unrecognized_modifiers_and_vocal_intent():
    plan = generation_plan(
        Generate(prompt="70bpm 펑키 디스코, 여성 보컬, 신스 없이 첼로")
    )
    assert plan["bpm"] == 70 and not plan["instrumental"]
    assert "신스 없이 첼로" in plan["caption"]


def test_dance_expansion_does_not_add_explicitly_excluded_instruments():
    plan = generation_plan(
        Generate(prompt="펑키 디스코, 드럼 없는, 기타 없이", instrumental=True)
    )
    assert "four-on-the-floor" not in plan["caption"]
    assert "guitar riff" not in plan["caption"]
    assert "drums and percussion" in plan["intent"]["exclusions"]
