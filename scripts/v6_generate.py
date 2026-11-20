"""Render the instrumental score under the shared YuE2 resource guard."""

import argparse
import json

from engine.paths import DATA, ROOT
from scripts.v4_study import run


def generate(seed):
    chart = ROOT / "examples/v6/rusted-sunlight"
    brief = json.loads(chart.with_suffix(".json").read_text())
    run(
        "yue2",
        "rusted-sunlight",
        seed,
        brief,
        score=chart.with_suffix(".abc").read_text(),
        output_root=DATA / "v6",
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seed", type=int, default=73)
    generate(cli.parse_args().seed)
