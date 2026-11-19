"""Render a new validated Music Plan or repair a copy of the legacy soul snapshot."""

import argparse
import json
from pathlib import Path

from engine.music_plan import MusicPlan
from engine.session.bank import install
from engine.session.harmony import repair_soul, validate
from engine.session.render import specification, write_json

from .host import render
from .instruments import prepare_keys
from .session_qa import diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", type=Path)
    source.add_argument("--repair-soul", type=Path, metavar="SESSION_JSON")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("Choose a new output directory")
    if args.repair_soul:
        original = json.loads(args.repair_soul.read_text())
        spec = repair_soul(original)
    else:
        spec = specification(MusicPlan.model_validate_json(args.plan.read_text()))
    report = validate(spec)
    out.mkdir(parents=True)
    write_json(out / "harmony.json", report)
    if args.repair_soul:
        write_json(out / "before.json", validate(original))
    if not report["passed"]:
        parser.exit(1, f"Review MIDI before rendering: {out / 'harmony.json'}\n")
    install()
    if spec.get("keyboard_mapping"):
        prepare_keys(spec["events"], spec["keyboard_mapping"])
    write_json(out / "session.json", spec)
    job = render(out)
    write_json(job / "diagnostics.json", diagnostics(spec, job))
    print(job)


if __name__ == "__main__":
    main()
