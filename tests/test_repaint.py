import numpy as np
import pytest
import soundfile as sf
from engine import paths
from engine.generation.worker import conditional_parameters


def test_repaint_boundaries_and_default_path(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", tmp_path.resolve())
    path = tmp_path / "source.wav"
    sf.write(path, np.zeros((12000 * 15, 2)), 12000)
    request = dict(
        task_type="repaint",
        src_audio=str(path),
        repainting_start=0,
        repainting_end=4,
        duration=15,
    )
    assert conditional_parameters({}) == {}
    assert conditional_parameters(request)["chunk_mask_mode"] == "explicit"
    for updates in [
        dict(repainting_start=-1),
        dict(repainting_end=16),
        dict(repainting_end=float("nan")),
        dict(duration=30),
        dict(src_audio="/tmp/escape.wav"),
        dict(task_type="cover"),
    ]:
        with pytest.raises((ValueError, OSError)):
            conditional_parameters(dict(request, **updates))
