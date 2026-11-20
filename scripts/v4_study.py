"""Bounded paired generation. Leave every run and its original model WAV intact."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from engine.generation.supervisor import run_guarded, run_worker
from engine.paths import DATA, ROOT, RUNTIME


def run(engine, genre, seed, brief):
    folder = DATA / "v4" / f"{engine}-{genre}-{uuid4().hex[:10]}"
    folder.mkdir(parents=True)
    result = dict(engine=engine, genre=genre, seed=seed, brief=brief)
    log = folder / "worker.log"
    try:
        if engine == "turbo":
            req = dict(
                caption=brief["style"],
                lyrics=brief["lyrics"],
                instrumental=brief["lyrics"] == "[Instrumental]",
                bpm=brief["bpm"],
                timesignature="4",
                duration=brief["duration"],
                seed=seed,
                mlx=True,
                device="mps",
                save_dir=str(folder),
                result_path=str(folder / "worker.json"),
            )
            record = run_worker(req, log)
            path = Path(record.pop("path"))
        else:
            base = RUNTIME / "v4"
            binary = base / "yue2cpp/build/yue-synth"
            req = dict(
                style=brief["style"],
                lyrics=brief["lyrics"],
                duration=brief["duration"],
                seed=seed,
                lm_seed=seed,
                cot="full",
                steps=32,
                output_format="wav32",
            )
            request = folder / "request.json"
            request.write_text(json.dumps(req, ensure_ascii=False, indent=2))
            path = folder / "original.wav"
            cmd = [
                str(binary),
                "--model",
                str(base / "models/YuE2-3B-Q8_0.gguf"),
                "--vae",
                str(base / "models/YuE2-Vae-F32.gguf"),
                "--request",
                str(request),
                "--max-seq",
                "8192",
                "--out",
                str(path),
                "--score",
                str(folder / "plan.abc"),
            ]
            record = run_guarded(cmd, log)
        if not path.is_file():
            raise RuntimeError("Missing model output")
        result.update(status="rendered", original=path.name, run=record)
    except Exception as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        (folder / "experiment.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        print(folder, result["status"], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engine", choices=["turbo", "yue2"])
    ap.add_argument("genres", nargs="+", choices=["rock", "ballad", "jazz"])
    ap.add_argument(
        "--prompt", help="Override the selected brief with your own musical direction."
    )
    ap.add_argument(
        "--lyrics-file", type=Path, help="Original lyrics for a custom brief."
    )
    ap.add_argument(
        "--instrumental", action="store_true", help="Use an instrumental custom brief."
    )
    ap.add_argument("--seed", type=int, default=41)
    args = ap.parse_args()
    briefs = json.loads((ROOT / "examples/v4/briefs.json").read_text())
    if args.prompt:
        if len(args.genres) != 1 or (bool(args.lyrics_file) == args.instrumental):
            ap.error(
                "Use one tempo/duration preset and either --lyrics-file or --instrumental with --prompt"
            )
        lyrics = (
            args.lyrics_file.read_text().strip()
            if args.lyrics_file
            else "[Instrumental]"
        )
        if not lyrics or len(lyrics) > 4000:
            ap.error("Provide 1–4000 lyric characters")
        briefs[args.genres[0]].update(
            prompt=args.prompt, style=args.prompt, lyrics=lyrics
        )
    elif args.lyrics_file or args.instrumental:
        ap.error("Use --prompt for a custom brief")
    for genre in args.genres:
        run(args.engine, genre, args.seed, briefs[genre])
