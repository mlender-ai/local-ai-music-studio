"""Make two gain-only listening copies from measured originals in the same study."""

import argparse
import json
from pathlib import Path

import soundfile as sf

from engine.daw.qa import levels
from engine.rendering.audio import read_audio


def compare(folders, output):
    rows = []
    for folder in folders:
        run = json.loads((folder / "experiment.json").read_text())
        qa = json.loads((folder / "qa.json").read_text())
        if run["status"] != "rendered":
            raise ValueError("A comparison needs two rendered originals")
        rows.append((folder, run, qa["levels"]))
    if (
        rows[0][1]["brief"] != rows[1][1]["brief"]
        or rows[0][1]["seed"] != rows[1][1]["seed"]
    ):
        raise ValueError("Use two takes of the same brief and seed")
    # Preserve headroom for intersample peaks. Never boost the quieter take.
    target = min(
        -18.0,
        *(s["integrated_lufs"] - max(0, s["true_peak_dbtp"] + 1) for _, _, s in rows),
    )
    output.mkdir(parents=True, exist_ok=False)
    report = []
    for index, (folder, run, stats) in enumerate(rows, 1):
        gain = target - stats["integrated_lufs"]
        x, sr = read_audio(folder / run["original"])
        name = f"{index}-{run['engine']}.wav"
        sf.write(output / name, x * 10 ** (gain / 20), sr, subtype="PCM_24")
        measured = levels(output / name)
        report.append(
            dict(
                source_folder=folder.name,
                source=run["original"],
                wav=name,
                gain_db=gain,
                target_lufs=target,
                measured_lufs=measured["integrated_lufs"],
                true_peak_dbtp=measured["true_peak_dbtp"],
            )
        )
    (output / "match.json").write_text(json.dumps(report, indent=2))
    if abs(report[0]["measured_lufs"] - report[1]["measured_lufs"]) > 0.2:
        raise ValueError("Measured pair differs by more than 0.2 LU")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folders", nargs=2, type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    print(compare([f.resolve() for f in args.folders], args.out.resolve()))
