"""Generate an instrumental YuE2 stereo take from a music brief, with native scoring."""

import argparse
from pathlib import Path

from engine.paths import DATA
from scripts.v4_study import run


def generate(direction: str, seed: int, duration: int):
    direction = direction.strip()
    if not direction or not 1 <= duration <= 120 or not 0 <= seed < 2**63:
        raise ValueError("Provide a brief, a 1–120 s duration cap and a 63-bit seed")
    return run(
        "yue2",
        "instrumental-rock",
        seed,
        {
            "style": f"Instrumental guitar rock. {direction}",
            "lyrics": "",
            "duration": duration,
        },
        output_root=DATA / "v7",
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("brief", type=Path, help="UTF-8 production brief")
    cli.add_argument("--seed", type=int, required=True)
    cli.add_argument("--duration-cap", type=int, default=120)
    args = cli.parse_args()
    try:
        generate(args.brief.read_text(encoding="utf-8"), args.seed, args.duration_cap)
    except ValueError as exc:
        cli.error(str(exc))


if __name__ == "__main__":
    main()
