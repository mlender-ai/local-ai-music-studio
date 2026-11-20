"""Measure new layers and moving returns with two isolated control renders."""

import argparse
import itertools
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import welch

from engine.daw.alt_rock import RATE, dbfs, read, render
from engine.daw.host import isolated_host
from engine.session.render import write_json
from scripts.v6_arrange import onset_grid


def performance(project, sections):
    """Compare the pattern of sixteenth-note energies between adjacent bars."""
    audio = project / "Audio"
    drums, _ = read(audio / "drums.wav")
    bass, _ = read(audio / "bass.wav")
    beats, _, _ = onset_grid(drums, 104)
    report = {}
    for name, x in (("drums", drums), ("bass", bass)):
        patterns = {}
        for section in sections:
            bars = []
            for start in range(section["first_beat"], section["limit_beat"] - 3, 4):
                ticks = np.interp(
                    start + np.arange(17) / 4, np.arange(len(beats)), beats
                )
                idx = np.clip(np.rint(ticks * RATE).astype(int), 0, len(x))
                if min(np.diff(idx)) <= 0 or dbfs(x[idx[0] : idx[-1]]) < -48:
                    continue
                rms = np.array([dbfs(x[i:j]) for i, j in itertools.pairwise(idx)])
                bars.append(rms - rms.mean())
            if len(bars) > 1:
                patterns[section["name"]] = round(
                    float(np.mean(abs(np.diff(bars, axis=0)))), 2
                )
        report[name + "_mean_adjacent_bar_accent_difference_db"] = patterns
    samples = {}
    for name in ("pipe", "key", "motor"):
        x, sr = sf.read(audio / (name + ".wav"))
        freq, power = welch(x, sr, nperseg=min(len(x), 4096))
        energy = np.cumsum(x * x)
        samples[name] = {
            "dominant_bin_hz": round(float(freq[np.argmax(power)]), 1),
            "time_to_90_percent_energy_ms": round(
                float(np.searchsorted(energy, energy[-1] * 0.9) / sr * 1000), 1
            ),
        }
    report["processed_samples"] = samples
    return report


def controls(project, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "Audio").symlink_to(project / "Audio", target_is_directory=True)
    original = (project / "RUSTED SUNLIGHT.RPP").read_text()
    parts = re.split(r"(?=^  <TRACK\b)", original, flags=re.MULTILINE)
    sections = json.loads((project / "events.json").read_text())["sections"]
    master, _ = read(project / "RUSTED SUNLIGHT.wav")
    result = {}
    with isolated_host() as args, (output / "controls.log").open("w") as log:
        for name in ("without-additions", "fixed-returns"):
            chunks = []
            changed = []
            for part in parts:
                match = re.search(r'^    NAME "([^"]+)"$', part, re.MULTILINE)
                track = match[1] if match else ""
                if name == "without-additions" and track.startswith(
                    ("Foley ·", "Guitar answers ·", "Solar glass ·")
                ):
                    part, count = re.subn(
                        r"^    MUTESOLO 0 ",
                        "    MUTESOLO 1 ",
                        part,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    assert count == 1
                    changed.append(track)
                if name == "fixed-returns" and track.startswith(
                    (
                        "Room ·",
                        "Shoegaze ·",
                        "Metallic space ·",
                        "Delay ·",
                        "Transition ·",
                    )
                ):
                    # Retain the opening return gain at every automation point.
                    initial = re.search(r"^      PT 0 ([.\d]+) ", part, re.MULTILINE)[1]
                    part = re.sub(
                        r"^(      PT [\d.]+) [\d.]+ ",
                        rf"\g<1> {initial} ",
                        part,
                        flags=re.MULTILINE,
                    )
                    changed.append(track)
                chunks.append(part)
            assert len(changed) == 5
            rpp = output / f"{name}.RPP"
            rpp.write_text(
                "".join(chunks).replace(
                    'RENDER_PATTERN "RUSTED SUNLIGHT"', f'RENDER_PATTERN "{name}"'
                )
            )
            render(rpp, args, log)
            control, _ = read(output / f"{name}.wav")
            delta = master - control
            if np.max(abs(delta)) < 0.001:
                raise RuntimeError(f"Control failed to change the mix: {name}")
            result[name] = {
                "changed_tracks": changed,
                "section_delta_dbfs": {
                    s["name"]: round(
                        dbfs(delta[round(s["start"] * RATE) : round(s["end"] * RATE)]),
                        2,
                    )
                    for s in sections
                },
            }
    result["performance"] = performance(project, sections)
    write_json(output / "control-results.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("project", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    controls(args.project.resolve(), args.output.resolve())
