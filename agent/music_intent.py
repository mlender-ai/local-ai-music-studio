"""Editable, deterministic planning. No artist/voice cloning or hidden LLM calls."""

import re
from engine.schema import Generate, MusicIntent

FUNK_DISCO = dict(
    genre="funk disco-pop",
    subgenre="dancefloor funk with pop hooks",
    era="late 1970s / early 1980s",
    production_character="warm analog color, punchy dry drums, clear separation",
    rhythmic_feel="straight sixteenth-note dance groove with interlocking syncopation",
    drum_pattern="four-on-the-floor kick; snare and claps on beats 2 and 4; rhythmic sixteenth-note hi-hats",
    bass_character="syncopated electric bass, short notes locking with the kick",
    rhythm_guitar="prominent muted clean electric guitar cutting, short sixteenth-note chord chops",
    synth_and_keys="Rhodes electric piano, short brass stabs and analog synth accents",
    arrangement="short rhythmic phrases; establish groove immediately; guitar and bass trade accents; small fills into a returning hook",
    bpm=120,
    time_signature="4/4",
)


def plan_intent(command: Generate) -> MusicIntent:
    if command.intent is not None:
        return command.intent.model_copy(deep=True)
    from agent.command_parser import legacy_generation_plan

    text = command.prompt.lower()
    legacy = legacy_generation_plan(command)
    disco = bool(re.search(r"디스코|\bdisco\b", text))
    intent = (
        MusicIntent(**FUNK_DISCO)
        if disco
        else MusicIntent(
            genre="user-directed",
            arrangement=legacy["caption"]
            .removesuffix(", instrumental, no vocals")
            .removesuffix(", vocals"),
        )
    )
    intent.bpm = legacy["bpm"]
    if legacy.get("timesignature"):
        intent.time_signature = {"2": "2/4", "3": "3/4", "4": "4/4", "6": "6/8"}[
            legacy["timesignature"]
        ]
    if disco and re.search(r"90년대|1990|\b90s\b", text):
        intent.era = "1990s"
    for pattern, field, exclusion in [
        (
            r"드럼\s*(?:없|없이)|no drums|without drums",
            "drum_pattern",
            "drums and percussion",
        ),
        (r"기타\s*(?:없|없이)|no guitar|without guitar", "rhythm_guitar", "guitar"),
        (r"베이스\s*(?:없|없이)|no bass|without bass", "bass_character", "bass"),
        (
            r"신스\s*(?:없|없이)|no synth|without synth",
            "synth_and_keys",
            "synthesizers",
        ),
    ]:
        if re.search(pattern, text):
            setattr(intent, field, "")
            intent.exclusions.append(exclusion)
    if disco:
        intent.additional_direction = re.sub(
            r"(?i)\bmj\b|michael jackson|마이클\s*잭슨", "pop-funk", command.prompt
        )
    if disco and intent.exclusions:
        intent.arrangement = "short rhythmic phrases; establish groove immediately; small fills into a returning hook"
    return intent


def vocal_mode(command, intent):
    if command.instrumental is not None:
        return "instrumental" if command.instrumental else "vocal"
    if intent.vocal_mode != "unspecified":
        return intent.vocal_mode
    text = command.prompt.lower()
    if re.search(
        r"보컬\s*(?:없|없이)|연주곡|instrumental|no vocals|without vocals", text
    ):
        return "instrumental"
    if command.lyrics.strip() or re.search(
        r"보컬|코러스|노래하는|vocals?|singing|choir|chorus", text
    ):
        return "vocal"
    return "unspecified"


def preview(command: Generate) -> dict:
    intent = plan_intent(command)
    intent.vocal_mode = vocal_mode(command, intent)
    from agent.arrangement import requested, draft_arrangement, arrangement_caption
    from agent.command_parser import legacy_generation_plan

    duration = legacy_generation_plan(command)["duration"]
    if (
        intent.arrangement_plan is None
        and command.intent is None
        and requested(command.prompt)
    ):
        intent.arrangement_plan = draft_arrangement(
            command.prompt, duration, intent.exclusions
        )
    if (
        intent.arrangement_plan
        and abs(intent.arrangement_plan.sections[-1].end - duration) > 1e-6
    ):
        raise ValueError("Arrangement end must equal the requested audio duration.")
    for field, terms in {
        "drum_pattern": ["drums", "percussion"],
        "bass_character": ["bass"],
        "rhythm_guitar": ["guitar"],
        "synth_and_keys": ["synth", "keys"],
    }.items():
        if any(
            term in exclusion.lower()
            for term in terms
            for exclusion in intent.exclusions
        ):
            setattr(intent, field, "")
    if intent.exclusions and intent.arrangement == FUNK_DISCO["arrangement"]:
        intent.arrangement = "short rhythmic phrases; establish groove immediately; small fills into a returning hook"
    if intent.vocal_mode == "instrumental":
        intent.vocal_character = "instrumental, no vocals"
    elif intent.vocal_mode == "vocal" and (
        not intent.vocal_character
        or intent.vocal_character == "instrumental, no vocals"
    ):
        intent.vocal_character = (
            "expressive original lead singing and rhythmic backing chorus"
        )
    parts = [
        getattr(intent, k)
        for k in (
            "era",
            "genre",
            "subgenre",
            "production_character",
            "rhythmic_feel",
            "drum_pattern",
            "bass_character",
            "rhythm_guitar",
            "synth_and_keys",
            "vocal_character",
            "arrangement",
            "additional_direction",
        )
        if getattr(intent, k)
        and not (
            intent.arrangement_plan and k in ("arrangement", "additional_direction")
        )
    ]
    if intent.arrangement_plan:
        parts = [
            intent.era,
            intent.genre,
            intent.production_character,
            intent.vocal_character,
            arrangement_caption(intent.arrangement_plan),
        ]
    if intent.exclusions:
        parts.append("Exclude: " + ", ".join(intent.exclusions))
    return dict(
        intent=intent.model_dump(
            exclude={"arrangement_plan"} if intent.arrangement_plan is None else set()
        ),
        caption=". ".join(parts),
        ready=intent.vocal_mode != "unspecified",
        notice="규칙 기반 초안입니다. 누락된 음악적 지시는 Music Intent를 직접 수정하세요. 특정 음성·기존 곡을 복제하는 기획은 사용하지 마세요.",
    )


def compile_plan(command: Generate) -> dict:
    from agent.command_parser import legacy_generation_plan

    draft = preview(command)
    if not draft["ready"]:
        raise ValueError(
            "보컬 여부를 선택하세요: instrumental=true/false 또는 intent.vocal_mode."
        )
    intent = MusicIntent(**draft["intent"])
    instrumental = intent.vocal_mode == "instrumental"
    base = legacy_generation_plan(
        command.model_copy(update={"instrumental": instrumental})
    )
    base.update(
        caption=draft["caption"],
        bpm=intent.bpm,
        timesignature=intent.time_signature.split("/")[0],
        intent=intent.model_dump(
            exclude={"arrangement_plan"} if intent.arrangement_plan is None else set()
        ),
        planner="music-intent-v1",
    )
    return base
