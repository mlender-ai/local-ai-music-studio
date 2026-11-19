"""Bar-level harmony and overlap checks for monophonic bass and comping parts."""

import re
from collections import Counter
from copy import deepcopy

ROOTS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
INTERVALS = {
    "m9": (0, 3, 7, 10, 2),
    "13": (0, 4, 7, 10, 2, 9),
    "maj9": (0, 4, 7, 11, 2),
    "7": (0, 4, 7, 10),
    "m7": (0, 3, 7, 10),
    "6/9": (0, 4, 7, 9, 2),
    "m11": (0, 3, 7, 10, 2, 5),
}
RELEASE = {"bass": 0.036, "keys": 0.21, "guitar": 0.018}

PPQ = 960


def midi_ticks(event, note_index, bpm):
    spread = {"guitar": 0.005, "keys": 0.002}.get(event["voice"], 0)
    start = round((event["step"] / 4 + note_index * spread * bpm / 60) * PPQ)
    end = min(PPQ * 4, start + round(event["length"] * PPQ / 4))
    if not 0 <= start < end <= 4 * PPQ:
        raise ValueError(
            f"Invalid MIDI timing in bar {event['bar']} on {event['track']}"
        )
    return start, end


def chord(symbol):
    m = re.fullmatch(r"([A-G])([b#]?)(maj9|m11|m9|m7|13|7|6/9)", symbol)
    if not m:
        raise ValueError(f"Unsupported session chord: {symbol}")
    root = (ROOTS[m[1]] + {"": 0, "b": -1, "#": 1}[m[2]]) % 12
    return root, {(root + i) % 12 for i in INTERVALS[m[3]]}


def plan_chart(progression, bars):
    symbols = progression.replace("|", " ").split()
    if not symbols or len(symbols) > bars:
        raise ValueError("Empty or oversized chord progression")
    for symbol in symbols:
        chord(symbol)
    return [symbols[i % len(symbols)] for i in range(bars)]


def validate(spec):
    chart = spec["chart"]
    step_sec = 15 / spec["music_plan"]["rhythm"]["bpm"]
    expected = plan_chart(spec["music_plan"]["harmony"]["progression"], len(chart))
    issues = []
    bars = []
    tones = []
    last_keys = []
    for event in spec["events"]:
        if not event.get("muted") and not 1 <= event["bar"] <= len(chart):
            raise ValueError(f"Event outside score: {event}")
    ordered = sorted(
        enumerate(spec["events"]), key=lambda item: (item[1]["bar"], item[1]["step"])
    )
    for bar, symbol in enumerate(chart, 1):
        root, pcs = chord(symbol)
        events = [(i, e) for i, e in ordered if e["bar"] == bar and not e.get("muted")]
        row = {
            "bar": bar,
            "chord": symbol,
            "plan": expected[bar - 1],
            "pitch_classes": sorted(pcs),
            "notes": {},
            "bass_approaches": [],
            "densities": dict(Counter(e["track"] for _, e in events)),
        }
        bars.append(row)

        def issue(kind, track, notes, t, *, bar=bar, **more):
            issues.append(
                dict(
                    kind=kind,
                    bar=bar,
                    track=track,
                    notes=notes,
                    seconds=round(t, 5),
                    **more,
                )
            )

        if expected[bar - 1] != symbol:
            issue("plan_chart_disagreement", "harmony", [], (bar - 1) * 16 * step_sec)
        for i, e in events:
            track = e["track"]
            if track == "drums" or e["voice"] == "chuck":
                continue
            pitches = e["notes"]
            row["notes"].setdefault(track, []).append(
                {"step": e["step"], "notes": pitches, "length": e["length"]}
            )
            if (
                track == "keys"
                and last_keys
                and "incoming_voice_motion_semitones" not in row
                and bar > 1
            ):
                row["incoming_voice_motion_semitones"] = [
                    min(abs(p - q) for q in last_keys) for p in pitches
                ]
            if track == "keys":
                last_keys = pitches
            for j, p in enumerate(pitches[::-1] if e["art"] == "up" else pitches):
                start_tick, end_tick = midi_ticks(
                    e, j, spec["music_plan"]["rhythm"]["bpm"]
                )
                onset = ((bar - 1) * 16 + start_tick * 4 / PPQ) * step_sec
                off = ((bar - 1) * 16 + end_tick * 4 / PPQ) * step_sec
                tones.append((onset, off, off + RELEASE[track], track, p, i, bar))
                if track == "bass" and p % 12 in pcs:
                    row.setdefault("bass_functions", []).append(
                        {
                            "step": e["step"],
                            "note": p,
                            "root": p % 12 == root,
                            "interval": (p - root) % 12,
                        }
                    )
                if p % 12 in pcs and not (track == "bass" and e["step"] >= 14):
                    continue
                following = next(
                    (
                        n
                        for _, n in ordered
                        if n["track"] == track
                        and not n.get("muted")
                        and (n["bar"], n["step"]) > (bar, e["step"])
                    ),
                    None,
                )
                resolves = (
                    following
                    and 0 < abs(following["notes"][0] - p) <= 2
                    and following["notes"][0] % 12
                    in chord(chart[following["bar"] - 1])[1]
                )
                if (
                    track == "bass"
                    and resolves
                    and (following["bar"] - bar) * 16 + following["step"] - e["step"]
                    <= 2
                    and e["length"] <= 1.5
                    and min(e["step"] % 4, 4 - e["step"] % 4) > 0.45
                ):
                    row["bass_approaches"].append(
                        {"note": p, "to": following["notes"][0], "step": e["step"]}
                    )
                elif p % 12 in pcs:
                    continue
                elif (
                    track == "keys"
                    and symbol.endswith("7")
                    and (p - root) % 12 == 5
                    and following
                    and any(
                        q == p - 1 or q % 12 == (root + 4) % 12
                        for q in following["notes"]
                    )
                ):
                    row.setdefault("suspensions", []).append(p)
                else:
                    issue(
                        "nonchord_tone",
                        track,
                        [p],
                        onset,
                        event=i,
                        strong=min(e["step"] % 4, 4 - e["step"] % 4) <= 0.45,
                        duration=round(off - onset, 4),
                    )
    active = []
    overlaps = []
    for item in sorted(tones):
        t, off, tail, tr, p, i, bar = item
        active = [old for old in active if old[2] > t]
        for a, ao, at, atr, q, j, abar in active:
            if p == q and tr == atr and min(ao, off) - t > 0.04:
                kind = "duplicate_note"
            elif atr == tr == "bass" and min(ao, off) - t > 0.035:
                kind = "overlapping_bass"
            elif abs(p - q) == 1 and min(ao, off) - t >= 0.12:
                kind = "sustained_semitone"
            elif p == q and tr != atr and min(ao, off) - t >= 0.06:
                kind = "register_doubling"
            elif abar != bar and abs(p - q) <= 1:
                kind = "boundary_release"
            else:
                continue
            entry = {
                "kind": kind,
                "bar": bar,
                "track": f"{atr}/{tr}",
                "notes": [q, p],
                "seconds": round(t, 5),
                "overlap_seconds": round(max(0, min(ao, off) - t), 5),
                "with_release_seconds": round(min(at, tail) - t, 5),
                "events": [j, i],
            }
            if kind == "boundary_release" and min(ao, off) <= t:
                overlaps.append(entry)
            else:
                issues.append(entry)
        active.append(item)
    return {
        "passed": not issues,
        "issues": issues,
        "release_observations": overlaps,
        "bars": bars,
    }


def repair_soul(spec):
    """Keep the published intro/cadence; make their actual chord symbols explicit."""
    from .score import CHART, CHORDS, GUITAR_REPLY

    if spec["chart"] != CHART or spec["music_plan"]["harmony"]["key"] != "D minor":
        raise ValueError("The legacy repair requires the original soul chart")
    fixed = deepcopy(spec)
    fixed["music_plan"]["harmony"]["progression"] = " ".join(spec["chart"])
    for key in ("events", "variation_events"):
        events = fixed[key]
        for e in events:
            symbol = spec["chart"][e["bar"] - 1]
            if e["track"] == "keys" and e["notes"] == [57, 60, 64, 65]:
                e["notes"] = [53, 57, 60, 64]  # F3 below E4, retains b3 and 9
            authored_shapes = [shape[-3:] for shape in CHORDS[symbol][1:]]
            if symbol == "Dm9":
                authored_shapes.append([60, 64, 65])
            if e["voice"] == "guitar" and e["notes"] in authored_shapes:
                # Short upper-register answers retain a common tone with the next chord.
                e["notes"] = [GUITAR_REPLY[symbol]]
            if (
                e["track"] == "keys"
                and e["bar"] == len(spec["chart"])
                and e["step"] == 9
                and any(
                    other["bar"] == e["bar"]
                    and other["step"] == e["step"]
                    and other["track"] == "keys"
                    and other["notes"] == e["notes"]
                    and other["length"] > e["length"]
                    and not other.get("muted")
                    for other in events
                )
            ):
                e["muted"] = True
    return fixed
