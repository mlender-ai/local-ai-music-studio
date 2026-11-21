"""Compile the Magnetic Afterhours melody guide and run guarded YuE2 generation."""

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

from engine.paths import DATA, ROOT, RUNTIME
from scripts.v71_strict import YUE_SEMANTIC_HZ, digest, produce

PLAN = ROOT / "examples/v72/magnetic-afterhours.json"


def compile_abc(plan):
    unit = Fraction(4, plan["subdivisions_per_bar"])
    bars, notes = [], []
    for section in plan["sections"]:
        for first, variant in section["placements"]:
            phrase = plan["hook"][variant]
            if not 1 <= first <= section["bars"] + 1 - len(phrase):
                raise ValueError(f"Hook leaves its section: {section['name']}")
            for index, bar in enumerate(phrase, start=len(bars) + first - 1):
                for start, length, pitch in bar:
                    if start < 0 or start + length > plan["subdivisions_per_bar"]:
                        raise ValueError(f"Hook note leaves bar {index + 1}")
                    notes.append(
                        [str(index * 4 + start * unit), str(length * unit), pitch]
                    )
        bars.extend(
            [{"section": section["abc"], "meter": plan["time_signature"]}]
            * section["bars"]
        )
    # The official compiler uses abc_tools for note timing and its roundtrip.
    sys.path.insert(0, str(RUNTIME / "v6/instrumental"))
    try:
        from compile_score import compile_events

        text, _ = compile_events(
            {"key": plan["key"], "bpm": plan["bpm"], "bars": bars, "notes": notes}
        )
    except ImportError as error:
        raise ValueError(
            "Install the official YuE2 Instrumental tools first"
        ) from error
    finally:
        sys.path.pop(0)
    return text


def require_hook_preflight(take, plan):
    from evaluation.house_hook import inspect_hook

    matches = inspect_hook(take, plan)["melody_matches"]
    phrase_seconds = len(plan["hook"]["A"]) * 4 * 60 / plan["bpm"]
    if not any(
        abs(a["start_seconds"] - variant["start_seconds"]) >= phrase_seconds
        for a in matches["A"]["supported"]
        for variant in matches["A_prime"]["supported"] + matches["B"]["supported"]
    ):
        raise ValueError(
            "Preflight needs separate audio evidence for A and a related variant"
        )


def source_prefix(take, seconds):
    evidence = json.loads((take / "vocal-leakage.json").read_text())
    if (
        evidence["status"] != "PASS"
        or evidence["wav_sha256"] != digest(take / "original.wav")
        or not 8 <= seconds < evidence["seconds"]
    ):
        raise ValueError("Select a bounded prefix from a passed instrumental take")
    sidecar = json.loads((take / "original.json").read_text())
    tokens = sidecar["semantic_tokens"]
    if len(tokens.split(",")) / YUE_SEMANTIC_HZ < seconds:
        raise ValueError("YuE2 semantic prefix is shorter than the requested section")
    return tokens, seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--write-score", type=Path)
    parser.add_argument("--seed", type=int, default=518)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--cfg-scale", type=float, default=2.4)
    parser.add_argument("--duration-cap", type=int)
    parser.add_argument("--preflight", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--native-prefix", type=Path)
    mode.add_argument("--replay-from", type=Path)
    parser.add_argument("--prefix-seconds", type=float, default=14.4)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    score = compile_abc(plan)
    if args.write_score:
        args.write_score.write_text(score)
        return
    if args.preflight:
        require_hook_preflight(args.preflight, plan)
    source = (
        source_prefix(args.native_prefix, args.prefix_seconds)
        if args.native_prefix
        else None
    )
    cap = args.duration_cap or (105 if args.preflight else 28)
    semantic_tokens = None
    if args.replay_from:
        stored = json.loads((args.replay_from / "original.json").read_text())
        original_request = json.loads((args.replay_from / "request.json").read_text())
        if (
            original_request.get("abc") != score
            or original_request["style"] != plan["style"]
        ):
            raise ValueError("Replay must retain the original conditions and hook")
        semantic_tokens = ",".join(
            stored["semantic_tokens"].split(",")[: cap * YUE_SEMANTIC_HZ]
        )
    take, verdict = produce(
        plan["style"],
        score,
        "house-techno-128",
        args.seed,
        cap,
        cot="melody",
        cfg_scale=args.cfg_scale,
        preflight=args.preflight,
        semantic_temperature=args.temperature,
        output_root=DATA / "v72-house",
        duration_range=(60, 105),
        source=source,
        semantic_tokens=semantic_tokens,
    )
    if verdict["vocal_status"] == "PASS":
        from evaluation.house_hook import inspect_hook

        inspect_hook(take, plan)
    print(take, verdict["vocal_status"], verdict["selection"], flush=True)


if __name__ == "__main__":
    main()
