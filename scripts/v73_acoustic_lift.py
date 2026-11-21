"""Add an electric response from recorded samples to an acoustic-led take."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.dsp.chain import process
from engine.session.bank import BANKS, note, select_sample
from evaluation.house_hook import band, db
from scripts.v71_strict import digest
from scripts.v73_finish import verify_mix


def electric_response(take, out, part):
    source = take / "original.wav"
    source_sha = digest(source)
    vocal = json.loads((take / "vocal-leakage.json").read_text())
    timbre = json.loads((take / "guitar-timbre.json").read_text())
    verdict = json.loads((take / "strict-result.json").read_text())
    if (
        verdict["phase"] != "full"
        or vocal["status"] != "PASS"
        or vocal["wav_sha256"] != source_sha
        or timbre["source_sha256"] != source_sha
        or not all(x["acoustic_opening_supported"] for x in timbre["sections"].values())
    ):
        raise ValueError(
            "Use a fully screened take with an acoustically supported opening"
        )
    dry, rate = sf.read(source, always_2d=True, dtype="float32")
    beat = 60 / part["bpm"]
    length = round((part["beats"] * beat + 1.1) * rate)
    start = round(part["start_seconds"] * rate)
    if not 0.58 * len(dry) <= start <= len(dry) - length:
        raise ValueError("Place the short response within the second half of the take")

    mono = np.zeros(length, dtype="float32")
    samples = []
    for counter, (onset, beats, midi, velocity) in enumerate(part["notes"]):
        at = round(onset * beat * rate)
        audio = note(
            "guitar", "guitar", midi, velocity, counter, beats * beat, 0.13, rate
        )
        region = mono[at : at + len(audio)]
        if at < 0 or len(region) != len(audio):
            raise ValueError("Electric note exceeds the bounded response")
        region += audio
        sample = select_sample("guitar", "guitar", midi, velocity, counter)
        samples.append(
            {"pitch": midi, "asset": sample[-2], "git_blob_sha1": sample[-1]}
        )

    fade = np.minimum(np.arange(length) / (0.055 * rate), 1.0)
    mono *= fade
    mono = band(mono, rate, 105, 6500)
    stereo = np.column_stack((mono * 0.89, mono))
    chain = [
        {"type": "distortion", "drive_db": 5.5, "tone_hz": 5200, "output_db": -2.0},
        {"type": "reverb", "wet": 0.13, "pre_delay_ms": 20, "decay": 0.46},
    ]
    lead = process(stereo, rate, chain)
    release = round(rate * 0.16)
    lead[-release:] *= np.linspace(1, 0, release)[:, None]
    bed = dry[start : start + len(lead)]
    gain = (
        np.sqrt(np.mean(bed**2))
        * 10 ** (-4.5 / 20)
        / max(np.sqrt(np.mean(lead**2)), 1e-8)
    )
    lead *= gain
    mix = dry.copy()
    mix[start : start + len(lead)] += lead
    out.mkdir(parents=True)
    sf.write(out / "original.wav", mix, rate, subtype="FLOAT")
    sf.write(out / "electric-response.wav", lead, rate, subtype="FLOAT")
    for name in ("request.json", "plan.abc", "experiment.json", "worker.log"):
        shutil.copyfile(take / name, out / name)
    source_bank = BANKS["guitar"]
    manifest = {
        "native_sha256": source_sha,
        "arranged_sha256": digest(out / "original.wav"),
        "start_seconds": start / rate,
        "length_seconds": len(lead) / rate,
        "source": {
            key: source_bank[key] for key in ("repo", "revision", "license", "author")
        },
        "lead_rms_dbfs": db(np.sqrt(np.mean(lead**2))),
        "lead_to_bed_rms_db": -4.5,
        "effects": chain,
        "notes": part["notes"],
        "recordings": samples,
    }
    (out / "electric-response.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("take", "output", "part", "composition"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    out = electric_response(args.take, args.output, json.loads(args.part.read_text()))
    report = verify_mix(out, json.loads(args.composition.read_text()))
    print(out, report["vocal_status"], report["selection"])
