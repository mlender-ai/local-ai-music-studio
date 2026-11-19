"""Validated V1 edits for the instrumental soul chart, returning a new snapshot."""

import re
from copy import deepcopy

from engine.session.score import CHART

ARRANGE = "9~12마디의 기타를 쉬게 하고 베이스를 변주해줘."
CLARIFY = "키보드가 먹먹하니까 악기 소스를 점검하고 더 명료하게 믹싱해줘."


def edit(spec, command):
    result = deepcopy(spec)
    if result["chart"] != CHART:
        raise ValueError("Only the Session Engine V1 soul chart is supported.")
    command = " ".join(command.strip().rstrip(".").split())
    match = re.fullmatch(
        r"(\d+)\s*(?:[~–-]\s*(\d+)마디(?:의|에서)?|마디부터)\s*"
        r"기타(?:를)? (?:쉬게 하고|빼고|뮤트하고) 베이스(?:를)? "
        r"(?:변주해\s*줘|더 리드미컬하게 바꿔\s*줘)",
        command,
    )
    if match:
        first = int(match.group(1))
        last = int(match.group(2) or len(CHART))
        if not 1 <= first <= last <= len(CHART):
            raise ValueError("Bar range is outside the chart.")
        changed = []
        for e in result["events"]:
            if not first <= e["bar"] <= last:
                continue
            before = e.copy()
            if e["track"] == "guitar":
                e["muted"] = True
            elif e["track"] == "bass" and e["step"] in (2.5, 3, 5, 6, 11):
                # Leave downbeats, chord tones and approach notes in place.
                e["step"] += 0.5 if e["bar"] % 2 else -0.5
                e["length"] *= 0.72
                e["velocity"] = min(127, e["velocity"] + 8)
            if e != before:
                changed.append({"before": before, "after": e.copy()})
        if not changed:
            raise ValueError("The region has no eligible guitar or bass events.")
        return result, {
            "command": command,
            "tracks": ["guitar", "bass"],
            "bars": [first, last],
            "changes": changed,
        }
    if re.fullmatch(
        r"(?:키보드|건반)(?:가|이| 소리가) 먹먹(?:하니까|해서|해)[.,]? "
        r"(?:악기 소스를 점검하고 )?(?:조금 |더 )?(?:명료|선명)하게 "
        r"(?:믹싱해|해|만들어)\s*줘",
        command,
    ):
        cfg = result["mixer"]["keys"]
        before = deepcopy(cfg)
        # Reduce the delayed side signal and room return that mask the recorded attack.
        from .instruments import audition

        selected, candidates = audition(spec)
        cfg.update(width=0.24, send=0.09)
        # Only cut the existing keyboard bell when its dry stem is dominated by low mids.
        if candidates[selected]["low_mid_fraction"] > 0.5:
            cfg["chain"][0]["gain_db"] = -4.8
        old_source = result.get("keyboard_mapping", "session-v1")
        result["keyboard_mapping"] = selected
        trim_db = candidates[old_source]["rms_dbfs"] - candidates[selected]["rms_dbfs"]
        result["mixer"]["levels"]["keys"] *= 10 ** (trim_db / 20)
        return result, {
            "command": command,
            "tracks": ["keys"],
            "bars": [1, len(CHART)],
            "same_midi_source_probe": candidates,
            "matched_source_gain_db": trim_db,
            "before": {"mapping": old_source, "mixer": before},
            "after": {"mapping": result["keyboard_mapping"], "mixer": cfg},
        }
    raise ValueError("Unsupported or ambiguous edit. No changes were made.")
