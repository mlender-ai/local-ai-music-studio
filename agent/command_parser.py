"""Transparent Korean/English rules, without a separate LLM or code execution."""

import re
from engine.schema import Generate, Chain

GENRES = [
    (
        ("트립합", "trip-hop", "trip hop"),
        "Dark 1990s trip-hop, heavy breakbeat drums, deep sub bass, dreamy analog synthesizers",
        85,
    ),
    (
        ("앰비언트", "ambient"),
        "Peaceful space ambient, slowly evolving warm pads, long reverberation, floating through space",
        60,
    ),
    (
        ("딥하우스", "deep house", "하우스", "house"),
        "Warm deep house, solid four-on-the-floor kick, repeating synth bass, smooth warm chord progression",
        120,
    ),
]


def dance_caption(prompt: str) -> str | None:
    """Expand disco/funk directions into audible parts; retain the raw prompt in the plan."""
    text = prompt.lower()
    disco = bool(re.search(r"디스코|\bdisco\b", text))
    funk = bool(re.search(r"펑키|펑크|\bfunk(?:y)?\b", text))
    if not (disco or funk) or re.search(r"펑크\s*(?:록|락)|punk\s*rock", text):
        return None
    parts = ["Funky disco" if disco and funk else "Disco" if disco else "Funk"]
    if re.search(r"90년대|1990|\b90s\b", text):
        parts.append("1990s pop production")
    if re.search(r"\bmj\b|michael jackson|마이클\s*잭슨", text):
        parts.append("Michael Jackson-inspired pop-funk arrangement")
    no_drums = re.search(r"드럼\s*(?:없음|없는|없이)|no drums|without drums", text)
    if disco and not no_drums:
        parts.append(
            "steady four-on-the-floor kick, snare and handclaps on beats 2 and 4, straight sixteenth-note hi-hats"
        )
    if funk:
        parts.append("tight syncopated electric bass groove")
    no_guitar = re.search(r"기타\s*(?:없음|없는|없이)|no guitar|without guitar", text)
    if re.search(r"기타|\bguitar\b", text) and not no_guitar:
        parts.append(
            "prominent clean muted rhythm guitar, catchy syncopated sixteenth-note funk guitar riff"
        )
    if re.search(r"신나|신나는|경쾌|energetic|upbeat|joyful", text):
        parts.append("joyful, energetic dance groove")
    # Preserve unrecognized directions instead of silently dropping modifiers.
    known = r"(?:90년대|1990s?|90s)\s*|펑키|펑크|디스코|\bfunk(?:y)?\b|\bdisco\b|\bmj\b|michael jackson|마이클\s*잭슨|스타일|느낌|style|inspired|\d{2,3}\s*bpm|신나는|신나게|경쾌한|energetic|upbeat|joyful|기타|guitar|리프|riff|리듬|rhythm|보컬\s*없는|보컬\s*없음|instrumental|no vocals|\d+(?:\.\d+)?\s*(?:초|seconds?|sec\b)|음악|[\s,.;·]"
    remainder = re.sub(known, "", text, flags=re.I)
    if remainder:
        parts.append("Additional user direction: " + prompt)
    return ", ".join(parts)


def generation_plan(command: Generate) -> dict:
    text = command.prompt.lower()
    caption, bpm = command.prompt, None
    for words, translated, default_bpm in GENRES:
        if any(w in text for w in words):
            # Keep original text as well: presets must not discard modifiers.
            caption, bpm = (
                translated + ". User direction: " + command.prompt,
                default_bpm,
            )
            break
    dance = dance_caption(command.prompt)
    if dance:
        caption, bpm = dance, 120
    match = re.search(r"(\d{2,3})\s*bpm", text, re.I)
    if match:
        bpm = int(match.group(1))
        if not 30 <= bpm <= 300:
            raise ValueError("BPM must be between 30 and 300.")
    length = re.search(r"(\d+(?:\.\d+)?)\s*(?:초|seconds?|sec\b)", text)
    duration = float(length.group(1)) if length else command.duration
    if not 15 <= duration <= 30:
        raise ValueError(
            "Phase 1 supports 15–30 seconds; shorten the requested duration."
        )
    if any(w in text for w in ["드럼 없음", "드럼 없는", "no drums", "without drums"]):
        caption += ", no drums, no percussion"
    no_vocals = any(
        w in text
        for w in [
            "보컬 없는",
            "보컬 없음",
            "instrumental",
            "no vocals",
            "without vocals",
        ]
    )
    wants_vocals = any(w in text for w in ["보컬", "vocals", "singing"])
    instrumental = (
        command.instrumental
        if command.instrumental is not None
        else (no_vocals or not wants_vocals)
    )
    caption += ", instrumental, no vocals" if instrumental else ", vocals"
    plan = dict(
        action="generate_music",
        original_prompt=command.prompt,
        caption=caption,
        bpm=bpm,
        duration=duration,
        seed=command.seed,
        instrumental=instrumental,
        lyrics="[Instrumental]" if instrumental else command.lyrics,
    )
    # Metadata conditions the model; it is not a hard audio quantization grid.
    signature = re.search(r"\b([2346])\s*/\s*[48]\b", text)
    if signature:
        plan["timesignature"] = signature.group(1)
    elif dance or re.search(r"4분의\s*4", text):
        plan["timesignature"] = "4"
    return plan


def production_plan(text: str) -> dict:
    if not text.strip() or len(text) > 2000:
        raise ValueError("A production instruction of 1–2000 characters is required.")
    lower = text.lower()
    if any(
        w in lower
        for w in [
            "멜로디",
            "편곡",
            "악기 교체",
            "악기를",
            "피아노로",
            "보컬 제거",
            "드럼 제거",
            "스템",
            "tempo",
            "melody",
            "replace instrument",
            "remove vocals",
            "베이스 제거",
            "베이스 빼",
            "드럼을 빼",
            "드럼 없애",
            "보컬을 빼",
            "템포",
            "속도",
            "bpm",
            "조옮김",
            "키를 바꿔",
        ]
    ):
        return dict(
            status="requires_regeneration",
            effects=[],
            message="멜로디·악기·편곡·스템 변경은 이 믹스의 DSP로 구현할 수 없습니다. 재생성 또는 별도 스템이 필요합니다.",
        )
    effects = []
    if any(w in lower for w in ["묵직", "베이스", "저음", "bass"]):
        effects += [
            dict(type="eq", mode="low_shelf", frequency=110, gain_db=4, q=0.707),
            dict(
                type="compressor",
                threshold_db=-18,
                ratio=3,
                attack_ms=25,
                release_ms=140,
                makeup_db=1,
            ),
        ]
    if any(w in lower for w in ["몽환", "공간", "잔향", "reverb", "dream"]):
        effects += [
            dict(type="eq", mode="high_shelf", frequency=5000, gain_db=-3, q=0.707),
            dict(type="reverb", wet=0.28, decay=3.5, pre_delay_ms=30),
        ]
    if any(w in lower for w in ["거칠", "왜곡", "포화", "distort", "saturat"]):
        effects += [dict(type="distortion", drive_db=9, tone_hz=5500, output_db=-6)]
    if any(w in lower for w in ["압축", "compress"]):
        effects += [
            dict(
                type="compressor",
                threshold_db=-20,
                ratio=4,
                attack_ms=10,
                release_ms=100,
            )
        ]
    if any(w in lower for w in ["리미터", "클리핑", "limiter"]):
        effects += [dict(type="limiter")]
    if not effects:
        return dict(
            status="unsupported",
            effects=[],
            message="지원 명령: 베이스를 묵직하게, 더 몽환적으로, 왜곡/포화, 압축, 리미터. 변경을 적용하지 않았습니다.",
        )
    if effects[-1]["type"] != "limiter":
        effects.append(dict(type="limiter", ceiling_db=-1))
    chain = Chain(effects=effects)
    return dict(
        status="ready",
        target="stereo_mix",
        instruction=text,
        actions=["apply_" + e.type for e in chain.effects]
        + ["render_audio", "compare_versions"],
        effects=chain.model_dump()["effects"],
    )
