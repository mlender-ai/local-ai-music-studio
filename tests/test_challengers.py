import json

import numpy as np
import pytest
import soundfile as sf

from scripts import heartmula_study, v4_study


def test_yue2_submits_supplied_score(tmp_path, monkeypatch):
    monkeypatch.setattr(v4_study, "DATA", tmp_path)
    score = 'X:1\nM:4/4\nK:C\n"C" C4|]'
    brief = {"style": "jazz", "lyrics": "[Instrumental]", "duration": 4}

    def synth(command, log):
        request = json.loads((log.parent / "request.json").read_text())
        assert request["abc"] == score
        assert request["seed"] == request["lm_seed"] == 41
        (log.parent / "original.wav").touch()
        return {}

    monkeypatch.setattr(v4_study, "run_guarded", synth)
    v4_study.run("yue2", "jazz", 41, brief, score=score)
    result = json.loads(next(tmp_path.rglob("experiment.json")).read_text())
    assert result["input_score"] == score


@pytest.mark.parametrize("short_output", [False, True])
def test_heart_codec_length_checked_before_success(tmp_path, monkeypatch, short_output):
    monkeypatch.setattr(heartmula_study, "DATA", tmp_path)
    stages = []

    def worker(command, log):
        stage = command[-4]
        stages.append(stage)
        if stage == "compose":
            request = json.loads((log.parent / "request.json").read_text())
            assert request["lyrics"] == "[Instrumental]" and request["duration"] == 40
            (log.parent / "score.json").write_text(
                '{"frames": 10, "endedOnEndToken": true}'
            )
        else:
            sf.write(command[-1], np.zeros((3840 if short_output else 38400, 2)), 48000)
        return {"total_seconds": 1}

    monkeypatch.setattr(heartmula_study, "run_guarded", worker)
    if short_output:
        with pytest.raises(ValueError, match="length"):
            heartmula_study.run(tmp_path / "HeartStudy", "jazz", 41)
    else:
        heartmula_study.run(tmp_path / "HeartStudy", "jazz", 41)
    result = json.loads(next(tmp_path.rglob("experiment.json")).read_text())
    assert stages == ["compose", "render"]
    assert result["status"] == ("failed" if short_output else "rendered")
