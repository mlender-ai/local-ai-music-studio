"""Validated planning boundary and capability-aware ACE-Step compiler.

Codex supplies MusicPlan JSON. Offline UI fallback is explicitly a preset, not an LLM.
"""

import re
from functools import lru_cache
from engine.music_plan import MusicPlan
from engine.paths import ROOT

CAPABILITIES = {
    "parameter_conditioning": ["bpm", "meter", "key", "vocal_mode"],
    "soft_text_targets": [
        "rhythm",
        "harmony",
        "sessions",
        "events",
        "production",
        "exclusions",
    ],
    "not_executed": [
        "independent instrument tracks",
        "per-track DSP",
        "exact notes",
        "exact event timing",
    ],
    "output_source_type": "model_full_mix",
}


@lru_cache(maxsize=1)
def tokenizer():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        str(ROOT / ".runtime/models/checkpoints/Qwen3-Embedding-0.6B"),
        local_files_only=True,
    )


def conditioning_budget(caption, bpm, meter, key, duration):
    # Pinned ACE-Step SFT_GEN_PROMPT; parity checked against actual worker logs.
    text = f"# Instruction\nFill the audio semantic mask based on the given conditions:\n\n# Caption\n{caption}\n\n# Metas\n- bpm: {bpm}\n- timesignature: {meter}\n- keyscale: {key}\n- duration: {duration:g} seconds\n<|endoftext|>\n"
    return {"text": text, "tokens": len(tokenizer().encode(text)), "limit": 256}


def draft(command):
    import json
    from agent.music_intent import vocal_mode, plan_intent

    text = command.prompt.lower()
    family = (
        "ambient"
        if re.search(r"ambient|cinematic|앰비언트|시네마", text)
        else "house"
        if re.search(r"house|하우스", text)
        else "soul"
        if re.search(r"disco|soul|funk|디스코|소울|펑크|펑키", text)
        else None
    )
    if family is None:
        raise ValueError(
            "Director fallback supports soul/disco, house and ambient. Supply Music Plan JSON for other styles, or select Music Intent."
        )
    plan = MusicPlan(
        **json.loads((ROOT / f"examples/director/{family}.json").read_text())
    )
    plan.source = "preset_fallback"
    intent = plan_intent(command)
    plan.vocal_mode = vocal_mode(command, intent)
    match = re.search(r"(\d{2,3})\s*bpm", text, re.I)
    if match:
        plan.rhythm.bpm = int(match.group(1))
    # Presets cannot safely resolve contradictory instrumentation; never ignore it silently.
    if intent.exclusions:
        raise ValueError(
            "Instrument exclusions require an edited Music Plan; the preset would reintroduce excluded parts. Use Music Intent or edit the plan."
        )
    return MusicPlan.model_validate(plan.model_dump())


def preview(command):
    length = re.search(r"(\d+(?:\.\d+)?)\s*(?:초|seconds?|sec\b)", command.prompt, re.I)
    duration = float(length.group(1)) if length else command.duration
    if not 15 <= duration <= (60 if command.duration > 30 else 30):
        raise ValueError("Public Director generation supports 15–30 seconds.")
    plan = command.music_plan or draft(command)
    mode = (
        ("instrumental" if command.instrumental else "vocal")
        if command.instrumental is not None
        else plan.vocal_mode
    )
    plan = plan.model_copy(update={"vocal_mode": mode})
    parts = [
        plan.style,
        mode,
        plan.rhythm.pattern,
        plan.rhythm.accents_and_space,
        plan.harmony.progression,
        plan.harmony.voicing,
    ]
    parts += [f"{s.instrument}: {s.role_and_interaction}" for s in plan.sessions]
    parts += [f"{e.at_fraction * duration:g}s: {e.action}" for e in plan.events]
    parts += [plan.production.tone, plan.production.dynamics, plan.production.space]
    if plan.exclusions:
        parts += ["Avoid " + ", ".join(plan.exclusions)]
    caption = "; ".join(parts)
    audit = conditioning_budget(
        caption,
        plan.rhythm.bpm,
        plan.rhythm.meter.split("/")[0],
        plan.harmony.key,
        duration,
    )
    if audit["tokens"] > audit["limit"]:
        raise ValueError(
            f"Music Plan compiles to {audit['tokens']} tokens (limit 256 including metadata). Shorten fields before generating; nothing was silently dropped."
        )
    return dict(
        duration=duration,
        music_plan=plan.model_dump(),
        caption=caption,
        conditioning=audit,
        capabilities=CAPABILITIES,
        ready=mode != "unspecified",
        notice="실험용 기획입니다. 화성·변주·공간감은 텍스트 목표이며 실제 트랙 제어가 아닙니다. 독립 앱 초안은 프리셋이므로 세부 요청을 확인하세요.",
    )


def compile_director(command):
    d = preview(command)
    if not d["ready"]:
        raise ValueError("Choose instrumental or vocal before generation.")
    p = MusicPlan(**d["music_plan"])
    return dict(
        action="generate_music",
        original_prompt=command.prompt,
        caption=d["caption"],
        bpm=p.rhythm.bpm,
        timesignature=p.rhythm.meter.split("/")[0],
        keyscale=p.harmony.key,
        duration=d["duration"],
        seed=command.seed,
        instrumental=p.vocal_mode == "instrumental",
        lyrics="[Instrumental]" if p.vocal_mode == "instrumental" else command.lyrics,
        music_plan=p.model_dump(),
        conditioning=d["conditioning"],
        capabilities=CAPABILITIES,
        inference_profile=command.inference_profile,
        planner="director-v1",
    )
