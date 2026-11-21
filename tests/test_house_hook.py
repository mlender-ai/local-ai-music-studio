import json

import numpy as np
import pytest

from evaluation.house_hook import FRAME_SECONDS, hook_matches, section_analysis
from scripts.v71_strict import digest, require_preflight
from scripts.v72_house import PLAN


def test_hook_finder_distinguishes_ordered_figure_from_held_chord():
    plan = json.loads(PLAN.read_text())
    phrase = plan["hook"]["A"]
    beat = 60 / plan["bpm"]
    chroma = np.zeros((12, 1200))
    for bar, notes in enumerate(phrase):
        for start, length, midi in notes:
            onset = 2 + (bar * 32 + start) * beat / 8
            loc = round(onset / FRAME_SECONDS)
            num = round(length * beat / (8 * FRAME_SECONDS))
            chroma[midi % 12, loc : loc + num] = 1
    assert any(
        hit["supported"] and abs(hit["start_seconds"] - 2) < 0.12
        for hit in hook_matches(chroma, phrase, beat)
    )
    chroma[[5, 8, 0]] = 1
    for pitch in (2, 3, 7, 10):
        chroma[pitch] = 0
    assert not any(hit["supported"] for hit in hook_matches(chroma, phrase, beat))


def test_uniform_kick_and_bass_do_not_count_as_a_drop():
    rate = 20000
    beat = 60 / 128
    envelope = np.zeros(round(60 * rate))
    time = np.arange(round(0.22 * rate)) / rate
    hit = np.sin(2 * np.pi * 54 * time) * np.exp(-17 * time)
    for at in np.arange(0, 59.5, beat):
        begin = round(at * rate)
        envelope[begin : begin + len(hit)] = hit
    drum = np.repeat(envelope[:, None], 2, axis=1)
    flat = section_analysis(drum, drum, drum, rate, beat)
    assert not flat["drop_supported"]
    stripped = drum.copy()
    stripped[23 * rate : 36 * rate] = 0
    contrasted = section_analysis(stripped, stripped, drum, rate, beat)
    assert contrasted["drop_supported"]


def test_semantic_replay_requires_the_same_screened_prefix(tmp_path):
    request = tmp_path / "request.json"
    source = tmp_path / "original.wav"
    tokens = [str(i) for i in range(200)]
    short = {"duration": 8, "semantic_tokens": ",".join(tokens), "seed": 928}
    request.write_text(json.dumps(short))
    source.write_bytes(b"unchanged verification fixture")
    receipt = {
        "status": "PASS",
        "seconds": 8,
        "request_sha256": digest(request),
        "wav_sha256": digest(source),
    }
    (tmp_path / "vocal-leakage.json").write_text(json.dumps(receipt))
    full = {**short, "duration": 96, "semantic_tokens": ",".join([*tokens, "901"])}
    require_preflight(tmp_path, full)
    full["semantic_tokens"] = "200," + full["semantic_tokens"]
    with pytest.raises(ValueError, match="reuse"):
        require_preflight(tmp_path, full)
