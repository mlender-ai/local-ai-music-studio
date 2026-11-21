"""Bounded paired generation. Leave every run and its original model WAV intact."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from engine.generation.supervisor import run_guarded, run_worker
from engine.paths import DATA, ROOT, RUNTIME


class ScoreRejected(ValueError):
    """The score was retained for review and must not be sent to synthesis."""


def yue2_request(
    brief, seed, *, cot, score, cfg_scale=None, semantic_temperature=None, source=None,
    semantic_tokens=None,
):
    request = {
        "style": brief["style"],
        "lyrics": brief["lyrics"],
        "duration": brief["duration"],
        "seed": seed,
        "lm_seed": seed,
        "cot": cot,
        "steps": 32,
        "output_format": "wav32",
    }
    if cfg_scale is not None:
        request["cfg_scale"] = cfg_scale
    if semantic_temperature is not None:
        request["semantic_sampling"] = {"temperature": semantic_temperature}
    if score is not None:
        request["abc"] = score
    if source is not None:
        tokens, end_seconds = source
        request.update(source_tokens=tokens, source_start=0.0, source_end=end_seconds)
    if semantic_tokens is not None:
        if source is not None:
            raise ValueError("Replay and native continuation are separate modes")
        request["semantic_tokens"] = semantic_tokens
    return request


def run(
    engine,
    genre,
    seed,
    brief,
    *,
    score=None,
    cot="full",
    output_root=None,
    plan_gate=None,
    cfg_scale=None,
    semantic_temperature=None,
    source=None,
    semantic_tokens=None,
):
    if score is not None and (engine != "yue2" or not score.strip()):
        raise ValueError("Provide a nonempty ABC score for YuE2")
    folder = (output_root or DATA / "v4") / f"{engine}-{genre}-{uuid4().hex[:10]}"
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
            req = yue2_request(
                brief,
                seed,
                cot=cot,
                score=score,
                cfg_scale=cfg_scale,
                semantic_temperature=semantic_temperature,
                source=source,
                semantic_tokens=semantic_tokens,
            )
            if plan_gate is not None and score is None:
                planner_request = folder / "planner-request.json"
                planner_request.write_text(
                    json.dumps(req, ensure_ascii=False, indent=2)
                )
                plan = folder / "planned.abc"
                result["planning"] = run_guarded(
                    [
                        str(base / "yue2cpp/build/yue-plan"),
                        "--model",
                        str(base / "models/YuE2-3B-Q8_0.gguf"),
                        "--request",
                        str(planner_request),
                        "--max-seq",
                        "8192",
                        "--out",
                        str(plan),
                    ],
                    folder / "planner.log",
                )
                score = plan.read_text(encoding="utf-8")
                plan_gate(score)
                result["score_source"] = "native_preflight"
            if score is not None:
                req["abc"] = score
                result["input_score"] = score
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
    except ScoreRejected as exc:
        result.update(status="rejected", error=str(exc))
    except Exception as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        (folder / "experiment.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        print(folder, result["status"], flush=True)
    return folder


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
    ap.add_argument(
        "--score", type=Path, help="Realize this original ABC chart with YuE2."
    )
    ap.add_argument(
        "--duration-cap", type=int, help="Override the YuE2 end-of-song cap (1–120 s)."
    )
    args = ap.parse_args()
    if (args.score or args.duration_cap is not None) and (
        args.engine != "yue2" or len(args.genres) != 1
    ):
        ap.error("--score and --duration-cap require a single YuE2 brief")
    if args.duration_cap is not None and not 1 <= args.duration_cap <= 120:
        ap.error("--duration-cap must be 1–120 seconds")
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
        if args.duration_cap is not None:
            briefs[genre]["duration"] = args.duration_cap
        run(
            args.engine,
            genre,
            args.seed,
            briefs[genre],
            score=args.score.read_text() if args.score else None,
        )
