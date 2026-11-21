"""Export screened audio with playback headroom and, when needed, a worked ending."""

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


def deliver(take, out, *, outro_fade=0.0):
    verdict = json.loads((take / "strict-result.json").read_text())
    voice = json.loads((take / "vocal-leakage.json").read_text())
    source = take / "original.wav"
    original_sha = digest(source)
    checks = verdict.get("technical_checks", {})
    handled_ending = (
        0 < outro_fade <= 8
        and verdict["selection"] == "outro_review_required"
        and all(
            checks.get(field)
            for field in ("duration", "tempo", "loop_screen", "impulse_screen")
        )
        and checks.get("ending") is False
    )
    ready = (
        outro_fade == 0 and verdict["selection"] == "technical_review_ready"
    ) or handled_ending
    if (
        verdict["phase"] != "full"
        or not ready
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
    if handled_ending:
        samples = round(outro_fade * rate)
        fade = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, samples))
        scaled[-samples:] *= fade[:, None]
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

        tail_rms = float(
            10 * np.log10(max(1e-14, np.mean(decoded[-rate // 10 :] ** 2)))
        )
        if handled_ending and tail_rms > -45:
            raise ValueError("The playback outro did not reach a quiet tail")

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
                    "outro_fade_seconds": outro_fade,
                    "playback_last_100ms_rms_dbfs": tail_rms,
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
    cli.add_argument("--outro-fade", type=float, default=0.0)
    args = cli.parse_args()
    print(deliver(args.take, args.output, outro_fade=args.outro_fade))
