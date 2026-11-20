import numpy as np
from scripts.v4_evaluate import character_error, loop_screen


def test_lyrics_score_ignores_section_tags_and_spacing():
    assert character_error("[Verse]\n네가 앉던 의자", "네가앉던 의자!") == 0
    assert character_error("서쪽", "") == 1
    assert character_error("[Instrumental]", "") is None


def test_repetition_screen_finds_copied_audio_under_gain():
    rng = np.random.default_rng(41)
    first, second, third = rng.normal(0, 0.1, (3, 8000))
    assert not loop_screen(np.concatenate([first, second, third, third * 0]), 4000)
    matches = loop_screen(np.concatenate([first, second, first * 0.6]), 4000)
    assert len(matches) == 1 and matches[0]["previous_seconds"] == 0
