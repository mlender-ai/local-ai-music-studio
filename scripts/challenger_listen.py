"""Make a common-level listening set for one brief, including optional scored and extended takes."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.daw.qa import levels
from scripts.v4_listen import matched_target


def collect(folders, output):
    tracks = []
    for folder in folders:
        record = json.loads((folder / "experiment.json").read_text())
        if record["status"] != "rendered":
            raise ValueError(f"{folder} has no finished take")
        path = folder / record["original"]
        info = sf.info(path)
        if not (
            info.format == "WAV"
            and info.channels == 2
            and info.samplerate == 48000
            and 0 < info.duration <= 120
        ):
            raise ValueError(f"Unexpected study audio: {path}")
        stats = levels(path)
        tracks.append((folder, record, path, stats))
    ref = tracks[0][1]
    if ref["engine"] != "yue2" or ref.get("input_score"):
        raise ValueError("Supply the approved YuE2 reference first")
    # Only a changed duration cap is permitted for the optional ending experiment.
    for _, record, _, _ in tracks:
        cap_changed = record["brief"]["duration"] != ref["brief"]["duration"]
        if cap_changed and (record["engine"] != "yue2" or record.get("input_score")):
            raise ValueError("Only the YuE2 ending experiment may change the cap")
        if (
            record["genre"] != ref["genre"]
            or record["seed"] != ref["seed"]
            or (record["brief"] | {"duration": None})
            != (ref["brief"] | {"duration": None})
        ):
            raise ValueError("Compare matching briefs and seeds")

    target = matched_target(stats for _, _, _, stats in tracks)
    output.mkdir(parents=True, exist_ok=False)
    report = []
    for i, (folder, record, path, stats) in enumerate(tracks):
        label = record["engine"]
        if i == 0:
            label += "-reference"
        elif record.get("input_score"):
            label += "-score"
        elif record["brief"]["duration"] != ref["brief"]["duration"]:
            label += "-ending"
        name = f"{i + 1}-{label}.wav"
        gain = target - stats["integrated_lufs"]
        with sf.SoundFile(
            output / name, "w", samplerate=48000, channels=2, subtype="PCM_24"
        ) as out:
            for block in sf.blocks(path, blocksize=65536, always_2d=True):
                out.write(block * 10 ** (gain / 20))
        measured = levels(output / name)
        if (
            abs(measured["integrated_lufs"] - target) > 0.15
            or measured["true_peak_dbtp"] > -0.9
        ):
            raise ValueError(f"Listening copy missed loudness or peak target: {name}")
        with sf.SoundFile(path) as audio:
            audio.seek(max(0, audio.frames - audio.samplerate // 10))
            tail_rms = float(10 * np.log10(max(1e-14, np.mean(audio.read() ** 2))))
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report.append(
            dict(
                folder=folder.name,
                source=path.name,
                sha256=digest,
                engine=record["engine"],
                seed=record["seed"],
                brief=record["brief"],
                score=record.get("input_score"),
                seconds=stats["duration_seconds"],
                original_lufs=stats["integrated_lufs"],
                original_dbtp=stats["true_peak_dbtp"],
                original_final_100ms_dbfs=round(tail_rms, 2),
                gain_db=gain,
                wav=name,
                measured_lufs=measured["integrated_lufs"],
                measured_dbtp=measured["true_peak_dbtp"],
                resources=record.get("run") or record["stages"],
            )
        )
    if (
        max(t["measured_lufs"] for t in report)
        - min(t["measured_lufs"] for t in report)
        > 0.2
    ):
        raise ValueError("Measured loudness spread exceeds 0.2 LU")
    (output / "match.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folders", nargs="+", type=Path, help="Approved reference, then challengers"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(args.folders) < 2:
        parser.error("Supply at least one challenger")
    collect(args.folders, args.out)
