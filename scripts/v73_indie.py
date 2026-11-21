"""Compile a sparse guitar score and run the guarded YuE2 instrumental path."""

import argparse
import json
from pathlib import Path

from engine.paths import DATA, ROOT
from scripts.v71_strict import produce, replay_stream
from scripts.v72_house import compile_abc, source_prefix

PLAN = ROOT / "examples/v73/strange-afternoon.json"
GENRE = "indie-experimental-rock"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--write-score", type=Path)
    parser.add_argument("--seed", type=int, default=518)
    parser.add_argument("--temperature", type=float, default=0.82)
    parser.add_argument("--cfg-scale", type=float, default=2.4)
    parser.add_argument("--duration-cap", type=int)
    parser.add_argument("--preflight", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--native-prefix", type=Path)
    mode.add_argument("--replay-from", type=Path)
    parser.add_argument("--prefix-seconds", type=float, default=12.0)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    score = compile_abc(plan)
    if args.write_score:
        args.write_score.write_text(score)
        return
    cap = args.duration_cap or (105 if args.preflight else 29)
    source = (
        source_prefix(args.native_prefix, args.prefix_seconds)
        if args.native_prefix
        else None
    )
    tokens = (
        replay_stream(args.replay_from, score, plan["style"], cap)
        if args.replay_from
        else None
    )
    if args.preflight:
        from evaluation.indie_motif import require_motif_preflight

        require_motif_preflight(args.preflight, plan)
    take, verdict = produce(
        plan["style"],
        score,
        GENRE,
        args.seed,
        cap,
        cot="melody",
        cfg_scale=args.cfg_scale,
        preflight=args.preflight,
        semantic_temperature=args.temperature,
        output_root=DATA / "v73-indie",
        duration_range=(60, 110),
        source=source,
        semantic_tokens=tokens,
    )
    if verdict["vocal_status"] == "PASS":
        from evaluation.indie_motif import inspect_take

        inspect_take(take, plan)
    print(take, verdict["vocal_status"], verdict["selection"], flush=True)


if __name__ == "__main__":
    main()
