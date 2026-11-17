import numpy as np
import pytest
import soundfile as sf
from engine.rendering.rhythm import estimate_rhythm
from engine import paths


@pytest.fixture(autouse=True)
def audio_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", tmp_path.resolve())


@pytest.mark.parametrize("bpm", [90, 124, 150])
def test_unconditioned_tempo_does_not_follow_requested_value(tmp_path, bpm):
    # Synthetic metronome fixture only; never presented as generated music.
    sr = 12000
    x = np.zeros(sr * 20)
    click = np.random.default_rng(0).normal(size=120) * np.exp(-np.arange(120) / 20)
    for t in np.arange(0.25, 19.9, 60 / bpm):
        start = round(t * sr)
        x[start : start + len(click)] += click
    path = tmp_path / "test-click.wav"
    sf.write(path, x * 0.15, sr)
    result = estimate_rhythm(path, requested_bpm=73)
    assert any(abs(c["bpm"] - bpm) < 2 for c in result["candidates"])
    if result["estimated_bpm"] is None:
        assert result["assessment"] == "half_double_time_ambiguous"
    else:
        assert abs(result["estimated_bpm"] - bpm) < 2
        assert result["absolute_error_bpm"] > 10


def test_silence_is_not_assigned_a_requested_tempo(tmp_path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(12000 * 15), 12000)
    result = estimate_rhythm(path, requested_bpm=124)
    assert result["estimated_bpm"] is None
    assert result["assessment"] == "uncertain"
