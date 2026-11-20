"""Generate the original METALLIC DREAM performance with an authored ABC score."""

import argparse
import json

from engine.paths import ROOT

from scripts.v4_study import run


def metallic_dream(seed):
    chart = ROOT / "examples/v5/metallic-dream"
    brief = json.loads(chart.with_suffix(".json").read_text())
    brief["lyrics"] = chart.with_suffix(".txt").read_text()
    run(
        "yue2",
        "metallic-dream",
        seed,
        brief,
        score=chart.with_suffix(".abc").read_text(),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seed", type=int, default=41)
    metallic_dream(cli.parse_args().seed)
