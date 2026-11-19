"""Compare the three sequential REAPER bounces at the actual edit boundaries."""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.daw.controller import DEMO, verified_host
from engine.daw.project import LANES
from engine.daw.qa import levels
from engine.paths import DATA
from engine.session.render import write_json


def compare(root):
    jobs = [verified_host(root / version) for version in DEMO]
    if not all(jobs):
        raise ValueError("Render all three DAW versions first")
    spec = json.loads((root / DEMO[0] / "session.json").read_text())
    first, last = json.loads((root / DEMO[1] / "edit.json").read_text())["bars"]
    sr = spec["sample_rate"]
    frames_per_bar = 240 * sr / spec["music_plan"]["rhythm"]["bpm"]
    start, end = round((first - 1) * frames_per_bar), round(last * frames_per_bar)
    result = {"bars": [first, last], "seconds": [start / sr, end / sr], "lanes": {}}
    for lane in LANES:
        a, b, c = (sf.read(job / f"dry-{lane}.wav", always_2d=True)[0] for job in jobs)
        if lane in ("guitar", "chuck", "bass"):
            if not np.array_equal(a[:start], b[:start]) or not np.array_equal(
                a[end:], b[end:]
            ):
                raise ValueError(f"Unexpected edit outside selected region: {lane}")
            inside = float(np.sqrt(np.mean((b[start:end] - a[start:end]) ** 2)))
            if inside == 0 or lane != "bass" and b[start:end].any():
                raise ValueError(f"Expected bar edit missing on {lane}")
        elif not np.array_equal(a, b):
            raise ValueError(f"Unrequested arrangement edit on {lane}")
        if (lane == "keys") == np.array_equal(b, c):
            raise ValueError(f"Unexpected keyboard edit result for {lane}")
        result["lanes"][lane] = {
            "arrangement_changed_frames": int(np.any(a != b, axis=1).sum()),
            "keyboard_edit_changed_frames": int(np.any(c != b, axis=1).sum()),
        }
    result["keys_dry"] = {
        name: levels(job / "dry-keys.wav") for name, job in zip(DEMO, jobs, strict=True)
    }
    result["versions"] = {
        name: json.loads((job / "render.json").read_text())
        for name, job in zip(DEMO, jobs, strict=True)
    }
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--root", type=Path, default=DATA / "daw-session")
    root = cli.parse_args().root
    write_json(root / "reaper-comparison.json", compare(root))
