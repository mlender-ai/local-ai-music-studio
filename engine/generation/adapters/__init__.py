"""Phase 03-D/E Generation Engine Adapters (YuE2, ACE-Step, Demucs, Local Multitrack Composer)."""

from __future__ import annotations

from typing import Any

from .acestep_adapter import probe_acestep
from .local_composer_adapter import execute_local_composition
from .stem_separator import probe_demucs, separate_stems_demucs
from .yue2_adapter import check_resting_voice, probe_yue2, run_yue2_generation


def detect_generation_engines() -> list[dict[str, Any]]:
    """Return honest live availability of every generation & stem-separation engine."""
    yue2 = probe_yue2()
    acestep = probe_acestep()
    demucs = probe_demucs()
    local_comp = {
        "id": "local-multitrack-composer",
        "name": "Local Multitrack & MIDI Composer (6-Voice Studio Synth)",
        "kind": "multitrack-midi-synth",
        "available": True,
        "modes": ["full_music", "instrument_session", "loop_midi"],
        "instrumentalPolicy": "instrumental_strict",
        "honestLabel": "Synthesized Multi-Timbre Multitrack Arrangement (NOT YuE2 neural audio)",
        "statusNoteKo": "즉시 사용 가능: 6종 멀티팀버 악기(드럼/FM 베이스/신스 훅/EP/기타/패드)로 실제 편집 가능한 MIDI+WAV를 생성합니다 (YuE2 신경망 오디오로 위장하지 않음).",
        "statusNoteEn": "Ready offline: composes editable multi-track MIDI & 48 kHz Stereo WAV via 6 built-in studio instruments (explicitly distinct from YuE2 neural audio).",
    }
    return [local_comp, yue2, acestep, demucs]


__all__ = [
    "check_resting_voice",
    "detect_generation_engines",
    "execute_local_composition",
    "probe_acestep",
    "probe_demucs",
    "probe_yue2",
    "run_yue2_generation",
    "separate_stems_demucs",
]
