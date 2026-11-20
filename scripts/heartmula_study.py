"""Render one local HeartMuLa challenger under the studio worker limits."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import soundfile as sf

from engine.generation.supervisor import run_guarded
from engine.paths import DATA, ROOT, RUNTIME

TAGS = {
    "rock": "korean indie rock,melodic,116 bpm,live drums,electric bass,two answering electric guitars,sparse guitar intro,intimate korean verse,rising chorus,backing harmonies,full band ending",
    "ballad": "korean pop ballad,emotional,72 bpm,intimate korean vocal,felt piano,spacious phrasing,soft bass,brushed drums,widening melodic chorus,gentle resolved ending",
    "jazz": "instrumental,1990s jazz hip hop,soul,90 bpm,laid-back boom bap,swung drums,syncopated electric bass,warm electric piano,jazz harmony,short clean guitar answers,sparse intro,groove,break,return",
}
WEIGHTS = {
    "lm": "mlx-community/HeartMuLa-oss-3B-8bit@7381f061892852cd71b18be01332ce9ef4730911",
    "codec": "mlx-community/HeartCodec-oss-fp16@f36294004e63cf6c66848dbdd43ff6f8ed65dde9",
}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def run(binary, genre, seed):
    brief = json.loads((ROOT / "examples/v4/briefs.json").read_text())[genre]
    folder = DATA / "v4" / f"heartmula-{genre}-{uuid4().hex[:10]}"
    folder.mkdir(parents=True)
    request = dict(
        tags=TAGS[genre], lyrics=brief["lyrics"], duration=brief["duration"], seed=seed
    )
    save(folder / "request.json", request)
    result = dict(
        engine="heartmula",
        genre=genre,
        seed=seed,
        brief=brief,
        request=request,
        weights=WEIGHTS,
        cfg=1.5,
        codec_steps=10,
        codec_guidance=1.25,
        stages={},
    )
    path = folder / "original.wav"
    try:
        score = folder / "score.json"
        for stage, bundle, src, dst in [
            ("compose", "lm", folder / "request.json", score),
            ("render", "codec", score, path),
        ]:
            command = [
                "/usr/bin/env",
                "MLX_ENABLE_TF32=0",
                str(binary.resolve()),
                stage,
                str(RUNTIME / "v41" / bundle),
                str(src),
                str(dst),
            ]
            result["stages"][stage] = run_guarded(command, folder / f"{stage}.log")
        take = json.loads(score.read_text())
        info = sf.info(path)
        if (
            info.samplerate != 48000
            or info.channels != 2
            or info.frames <= 0
            or info.frames != take["frames"] * 3840
            or info.duration > brief["duration"]
        ):
            raise ValueError("Unexpected decoded audio length or format")
        result.update(
            status="rendered",
            original=path.name,
            frames=take["frames"],
            ended_on_end_token=take["endedOnEndToken"],
            duration=info.duration,
        )
    except Exception as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        save(folder / "experiment.json", result)
        print(folder, result["status"], flush=True)
    return folder


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("genres", nargs="+", choices=TAGS)
    cli.add_argument("--binary", required=True, type=Path)
    cli.add_argument("--seed", type=int, default=41)
    args = cli.parse_args()
    if not 0 <= args.seed < 2**64:
        cli.error("--seed must fit an unsigned 64-bit integer")
    for genre in args.genres:
        run(args.binary, genre, args.seed)
