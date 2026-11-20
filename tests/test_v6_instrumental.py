import json
import re
from collections import defaultdict

from engine.paths import ROOT


def test_original_chart_has_only_instrumental_notes_and_complete_bars():
    base = ROOT / "examples/v6/rusted-sunlight"
    assert json.loads(base.with_suffix(".json").read_text())["lyrics"] == ""
    voice = None
    bars = defaultdict(list)
    for line in base.with_suffix(".abc").read_text().splitlines():
        if line in ("V: Vocal", "V: Ins"):
            voice = line.split()[1]
        elif line.endswith("|") and voice:
            for bar in line.rstrip("|").split("|"):
                notes = re.sub(r'"[^"]+"|[\s-]', "", bar)
                tokens = re.findall(r"[=_^]?[A-Ga-gz][,']*\d*", notes)
                assert "".join(tokens) == notes
                assert (
                    sum(
                        int(re.search(r"\d+$", t)[0]) if t[-1].isdigit() else 1
                        for t in tokens
                    )
                    == 16
                )
                if voice == "Vocal":
                    assert all(t.startswith("z") for t in tokens)
                bars[voice].append(notes)
    assert len(bars["Vocal"]) == len(bars["Ins"]) == 44
    assert len(set(bars["Ins"])) > 32
