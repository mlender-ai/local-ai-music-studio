"""Export a technically verified take with only playback headroom adjustment."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from engine.daw.qa import levels
from scripts.v71_strict import digest


def deliver(take, out):
    verdict = json.loads((take / "strict-result.json").read_text())
    voice = json.loads((take / "vocal-leakage.json").read_text())
    source = take / "original.wav"
    original_sha = digest(source)
    if (
        verdict["phase"] != "full"
        or verdict["selection"] != "technical_review_ready"
        or voice["status"] != "PASS"
        or original_sha != voice["wav_sha256"]
        or original_sha != verdict["technical_music_qa"]["waveform"]["sha256"]
        or digest(take / "request.json") != voice["request_sha256"]
    ):
        raise ValueError("Deliver only a full take whose source passed both reviews")
    if out.exists():
        raise FileExistsError(out)

    raw = verdict["technical_music_qa"]["waveform"]["levels"]
    gain = min(0.0, round(-1.6 - raw["true_peak_dbtp"], 2))
    audio, rate = sf.read(source, always_2d=True)
    scaled = audio * 10 ** (gain / 20)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as temporary:
        pack = Path(temporary) / "take"
        pack.mkdir()
        wav, mp3 = pack / "final.wav", pack / "final.mp3"
        sf.write(wav, scaled, rate, subtype="PCM_24")
        decoded, sample_rate = sf.read(wav, always_2d=True)
        error = float(np.max(np.abs(decoded - scaled)))
        if sample_rate != rate or error > 2**-23:
            raise ValueError("Lossless playback copy differs beyond PCM24 quantization")
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(wav),
                "-c:a",
                "libmp3lame",
                "-b:a",
                "320k",
                str(mp3),
            ],
            check=True,
        )
        copies = {}
        for file in (wav, mp3):
            quality = levels(file)
            if (
                quality["frames"] != len(audio)
                or quality["channels"] != 2
                or quality["clipped_samples"]
                or quality["true_peak_dbtp"] > -1
            ):
                raise ValueError(
                    f"Playback file failed format or headroom check: {file.name}"
                )
            copies[file.name] = {"sha256": digest(file), "levels": quality}

        for item, name in [
            (source, "original.wav"),
            (take / "request.json", "request.json"),
            (take / "experiment.json", "generation.json"),
            (take / "plan.abc", "generated-plan.abc"),
            (take / "vocal-leakage.json", "vocal-leakage.json"),
            (take / "strict-result.json", "quality.json"),
        ]:
            shutil.copyfile(item, pack / name)
        (pack / "delivery.json").write_text(
            json.dumps(
                {
                    "original_sha256": original_sha,
                    "playback_gain_db": gain,
                    "pcm24_max_rounding_error": error,
                    "copies": copies,
                    "human_listening": "unverified",
                },
                indent=2,
            )
            + "\n"
        )
        pack.rename(out)
    return out


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("take", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    print(deliver(args.take, args.output))
