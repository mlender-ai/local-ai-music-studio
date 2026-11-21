import json

import numpy as np
import soundfile as sf

from evaluation.indie_motif import band_sections
from scripts.v71_strict import digest
from scripts.v73_finish import add_reverse_guitar


def test_interlude_uses_band_withdrawal_and_late_reentry():
    rate = 20000
    t = np.arange(rate * 72) / rate
    kit = np.sin(2 * np.pi * 90 * t) + 0.3 * np.sin(2 * np.pi * 5200 * t)
    guitar = 0.17 * np.sin(2 * np.pi * 392 * t)
    bass = 0.17 * np.sin(2 * np.pi * 98 * t)
    envelope = np.where((t >= 28) & (t < 38), 0.01, 0.12)
    envelope[(t >= 56) & (t < 62)] = 0.39
    stems = {
        name: np.column_stack((audio, audio))
        for name, audio in {
            "drums": kit * envelope,
            "guitar": guitar,
            "bass": bass,
        }.items()
    }

    result = band_sections(stems, rate, 2.4)
    assert result["interlude_supported"]
    assert 28 <= result["interlude"]["start_seconds"] < 35
    assert 55 <= result["climax"]["start_seconds"] < 61

    stems["drums"] = np.column_stack((kit, kit)) * 0.12
    assert not band_sections(stems, rate, 2.4)["interlude_supported"]


def test_reverse_treatment_preserves_timeline_outside_the_interlude(tmp_path):
    rate = 24000
    t = np.arange(12 * rate) / rate
    note = 0.11 * np.sin(2 * np.pi * 392 * t)
    audio = np.column_stack((note, note))
    original = tmp_path / "original.wav"
    sf.write(original, audio, rate, subtype="FLOAT")
    source_sha = digest(original)
    diagnostics = tmp_path / "diagnostics"
    guitar = diagnostics / "htdemucs_6s/guitar.wav"
    guitar.parent.mkdir(parents=True)
    sf.write(guitar, audio, rate, subtype="FLOAT")
    (diagnostics / "source.sha256").write_text(source_sha + "\n")
    (tmp_path / "motif-qa.json").write_text(
        json.dumps(
            {
                "original_sha256": source_sha,
                "arrangement": {
                    "interlude_supported": True,
                    "interlude": {"start_seconds": 6, "end_seconds": 9},
                },
            }
        )
    )
    output, report = add_reverse_guitar(tmp_path, audio, rate, 1.0, 6.5, 1.25)
    effect = report["effects"][0]
    onset = round(6.5 * rate)
    ending = onset + effect["frames_in_edit"]
    np.testing.assert_array_equal(audio[:onset], output[:onset])
    np.testing.assert_array_equal(audio[ending:], output[ending:])
    assert np.max(np.abs(output[onset:ending] - audio[onset:ending])) > 0.005
