"""Render isolated notes through the project's real RS5K and Python paths."""

import argparse
import json
import math
from copy import deepcopy
from pathlib import Path

import soundfile as sf

from engine.session.bank import CACHE, note, select_sample
from engine.session.render import write_json
from engine.session.tuning import pitch

from .host import render
from .instruments import key_region, renderer_for


def selected(spec):
    mapping = spec.get("keyboard_mapping")
    rows = {}
    for i, event in enumerate(spec["events"]):
        track = event["track"]
        if track == "drums" or event["voice"] == "chuck" or event.get("muted"):
            continue
        notes = event["notes"][::-1] if event["art"] == "up" else event["notes"]
        for j, midi in enumerate(notes):
            velocity = event["velocity"]
            if track == "keys" and mapping:
                root, cents, _, source, digest = key_region(midi, velocity, mapping)
            else:
                _, root, _, _, source, digest = select_sample(
                    track, track, midi, velocity, i + j
                )
                cents = 0
            rows.setdefault(
                (track, midi, digest),
                {
                    "track": track,
                    "midi": midi,
                    "velocity": velocity,
                    "parity": (i + j) % 2,
                    "root": root,
                    "sfz_cents": cents,
                    "source": source,
                    "digest": digest,
                },
            )
    return list(rows.values())


def measure(snapshot):
    spec = json.loads((snapshot / "session.json").read_text())
    rows = selected(spec)
    fixture = deepcopy(spec)
    events = []
    slot_counts = {}
    # Separate tracks are measured from their individual host stems. Preserve
    # original event index parity for the bank's alternating recorded takes.
    for row in rows:
        t = row["track"]
        slot = slot_counts.get(t, 0)
        slot_counts[t] = slot + 1
        event = {
            "track": t,
            "voice": t,
            "notes": [row["midi"]],
            "velocity": row["velocity"],
            "bar": 1 + slot // 3,
            "step": (slot % 3) * 5.25,
            "length": 4.2,
            "art": "normal",
        }
        if len(events) % 2 != row["parity"]:
            events.append(dict(event, muted=True))
        events.append(event)
        row["offset"] = ((event["bar"] - 1) * 16 + event["step"]) / 6
    bars = math.ceil(max(slot_counts.values()) / 3)
    fixture["music_plan"]["rhythm"]["bpm"] = 90
    fixture.update(
        chart=["Fmaj9"] * bars,
        events=events,
        variation_events=[],
        frames=round((bars * 8 / 3 + 0.5) * 48000),
        sections=[
            {
                "name": "Calibration",
                "first": 1,
                "last": bars,
                "start": 0,
                "end": bars * 8 / 3,
            }
        ],
    )
    folder = snapshot / "pitch-probe"
    folder.mkdir(exist_ok=True)
    write_json(folder / "session.json", fixture)
    job = render(folder.resolve())
    stems = {t: sf.read(job / f"dry-{t}.wav")[0] for t in slot_counts}
    play = (
        renderer_for(spec["keyboard_mapping"]) if spec.get("keyboard_mapping") else note
    )
    for row in rows:
        t = row["track"]
        midi = row["midi"]
        x, sr = sf.read(CACHE / row["digest"])
        sample = pitch(x, sr)
        offset = round(row["offset"] * 48000)
        host = pitch(stems[t][offset : offset + 33600], 48000)
        preview = pitch(
            play(t, t, midi, row["velocity"], row["parity"], 0.7, 0.036, 48000, False),
            48000,
        )

        def cents(value, target):
            return (
                None
                if value is None or target is None
                else round(100 * (value - target), 2)
            )

        row.update(
            source_root_deviation_cents=cents(sample, row["root"]),
            python_deviation_cents=cents(preview, midi),
            reaper_deviation_cents=cents(host, midi),
            backend_difference_cents=cents(host, preview),
        )
    passed = all(
        all(
            r[k] is not None and abs(r[k]) <= limit
            for k, limit in [
                ("python_deviation_cents", 30),
                ("reaper_deviation_cents", 30),
                ("backend_difference_cents", 12),
            ]
        )
        for r in rows
    )
    result = {
        "passed": passed,
        "rows": rows,
        "probe_job": job.name,
        "concert_a_hz": 440,
        "absolute_tolerance_cents": 30,
        "backend_tolerance_cents": 12,
    }
    write_json(snapshot / "tuning.json", result)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", type=Path)
    result = measure(ap.parse_args().snapshot)
    print(len(result["rows"]), "pitched zones; passed:", result["passed"])
