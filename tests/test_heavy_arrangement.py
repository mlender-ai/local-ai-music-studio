import json
import re

from scripts.heavy.score import OUT, abc, score


def test_shared_heavy_chart_preserves_bar_grid_and_instrumental_input():
    plan = json.loads((OUT / "plan.json").read_text())
    assert plan == json.loads(json.dumps(score()))
    sheet = (OUT / "heavy.abc").read_text()
    assert sheet == abc(plan)
    voice = None
    lengths = {"Vocal": [], "Ins": []}
    for line in sheet.splitlines():
        if line in ("V: Vocal", "V: Ins"):
            voice = line.split()[-1]
        elif line.endswith("|"):
            content = re.sub(r'"[^"]+"', "", line[:-1])
            tokens = re.findall(r"[=_^]?[A-Ga-gzZ][,']*\d*", content)
            assert "".join(tokens) == content.replace("-", "")
            if voice == "Vocal":
                assert all(t[0] in "zZ" for t in tokens)
            lengths[voice].append(
                sum(
                    16 if t == "Z" else int((re.search(r"\d+$", t) or ["1"])[0])
                    for t in tokens
                )
            )
    assert lengths["Ins"] == lengths["Vocal"] == [16] * 48


def test_solo_bridge_return_contract():
    bars = score()["bars"]
    assert all(
        "lead guitar" in b["active_instruments"] and "drums" in b["active_instruments"]
        for b in bars[26:34]
    )
    assert [b["bass_root"] for b in bars[34:38]] == [38, 36, 34, 33]
    assert all(
        b["active_instruments"] == ["drums", "bass"] and not b["fx_cues"]
        for b in bars[34:38]
    )
    assert bars[38]["chord_symbols"] == "D5"
    assert [b["chord_symbols"] for b in bars[42:48]] == [
        "Dm",
        "Gm",
        "A7(b9)",
        "Dm",
        "Dm(add9)",
        "D5",
    ]
