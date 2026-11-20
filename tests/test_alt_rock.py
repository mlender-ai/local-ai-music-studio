import json

import numpy as np
import pytest
import soundfile as sf

from engine.daw.alt_rock import STEMS, produce, split_report


def test_mix_residual_preserves_unity_gain_reconstruction(tmp_path):
    source = np.random.default_rng(7).normal(0, 0.1, (4800, 2)).astype("float32")
    folders = [tmp_path / name for name in ("htdemucs_6s", "htdemucs")]
    for folder, roles in zip(folders, (STEMS, ("vocals", "drums", "bass", "other"))):
        folder.mkdir()
        for role in roles:
            sf.write(folder / f"{role}.wav", source * 0.1, 48000, subtype="FLOAT")
        (folder / "resources.json").write_text(json.dumps({"total_seconds": 1}))
    audio = tmp_path / "Audio"
    audio.mkdir()
    report = split_report(
        source, folders, [{"name": "Intro", "start": 0, "end": 0.1}], audio
    )
    reconstructed = sum(
        sf.read(path, dtype="float32")[0] for path in audio.glob("*.wav")
    )
    np.testing.assert_allclose(reconstructed, source, atol=2e-7)
    assert (
        report["htdemucs_6s"]["sum_error_vs_mix_db"]
        < report["htdemucs"]["sum_error_vs_mix_db"]
    )


def test_lead_direction_requires_an_audio_excerpt(tmp_path):
    with pytest.raises(ValueError, match="guitar passage"):
        produce(
            tmp_path / "source.wav",
            None,
            tmp_path / "project",
            112,
            -3,
            "기타 솔로를 더 날카롭고 공격적으로 만들어줘",
        )
    assert not (tmp_path / "project").exists()
