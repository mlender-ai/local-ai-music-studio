import json

import pytest

from evaluation.vocal_leakage import TAGS, assess
from scripts.v71_strict import digest, require_preflight


def window(levels, tags=None, asr=None):
    return {
        "start_seconds": 0,
        "end_seconds": 4,
        "rms_dbfs": levels,
        "tags": [
            {tag: score for tag, score in dict.fromkeys(TAGS, 0).items()} | (tags or {})
            for _ in range(3)
        ],
        "asr": asr,
    }


def test_no_detector_evidence_or_no_coverage_is_never_a_pass():
    assert assess([], complete=True)["status"] == "UNCERTAIN"
    assert assess([window([-15, -72, -78])], complete=False)["status"] == "UNCERTAIN"


def test_loud_stem_with_no_corroboration_is_uncertain():
    assert assess([window([-15, -32, -79])], complete=True)["status"] == "UNCERTAIN"


def test_cross_source_ah_and_sustained_humming_are_rejected():
    ah = window(
        [-19, -33, -35],
        asr={"no_speech": [0.44, 0.5, 0.56], "transcripts": ["Ah!", "Ah", "ah."]},
    )
    hum = window([-16, -35, -34], {"Humming": 0.41})
    assert assess([ah], complete=True)["status"] == "REJECT"
    assert assess([hum], complete=True)["status"] == "REJECT"


def test_quiet_stems_and_no_vocal_tags_pass_automated_screen():
    assert assess([window([-15, -75, -68])], complete=True)["status"] == "PASS"


def test_full_run_checks_pass_and_binds_exact_short_audio_and_conditions(tmp_path):
    req = {"duration": 24, "seed": 17}
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(req))
    audio = tmp_path / "original.wav"
    audio.write_bytes(b"unchanged")
    qa = tmp_path / "vocal-leakage.json"
    qa.write_text(
        json.dumps(
            {
                "status": "PASS",
                "seconds": 24,
                "request_sha256": digest(request_path),
                "wav_sha256": digest(audio),
            }
        )
    )
    require_preflight(tmp_path, {**req, "duration": 85})
    with pytest.raises(ValueError):
        require_preflight(tmp_path, {**req, "duration": 85, "seed": 42})
    audio.write_bytes(b"changed")
    with pytest.raises(ValueError):
        require_preflight(tmp_path, {**req, "duration": 85})


def test_uncertain_full_take_cannot_be_exported(tmp_path):
    from scripts.v71_delivery import deliver

    (tmp_path / "original.wav").write_bytes(b"source remains untouched")
    (tmp_path / "strict-result.json").write_text(
        json.dumps({"phase": "full", "selection": "technical_review_ready"})
    )
    (tmp_path / "vocal-leakage.json").write_text(json.dumps({"status": "UNCERTAIN"}))
    output = tmp_path / "delivery"
    with pytest.raises(ValueError):
        deliver(tmp_path, output)
    assert not output.exists()


def test_live_kit_half_time_fold_needs_support_from_the_mix(monkeypatch):
    from scripts import v71_strict

    quality = {
        "waveform": {
            "levels": {"duration_seconds": 70.0, "rms_dbfs": -17},
            "final_100ms_rms_dbfs": -70,
            "rhythm": {"candidates": [{"bpm": 143.2, "strength": 0.29}]},
            "exact_loop_candidates": [],
            "isolated_impulse_count": 0,
        },
        "ending": {"one_second_rms_dbfs": -35, "semantic_eos": True},
        "htdemucs_6s": {
            "drum_rhythm": {"candidates": [{"bpm": 71.8, "strength": 0.41}]}
        },
    }
    monkeypatch.setattr(v71_strict, "inspect", lambda _: quality)
    result = v71_strict.assess_music("take", "highteen-punk-144")
    assert result["selection"] == "technical_review_ready"
    assert result["tempo_evidence"]["confirmed_half_time_relation"]
    quality["waveform"]["rhythm"]["candidates"] = []
    assert (
        v71_strict.assess_music("take", "highteen-punk-144")["selection"]
        == "music_criteria_unmet"
    )
