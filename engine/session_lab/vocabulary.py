"""Instrument Performance Vocabulary & Empirical Engine Capability Matrix (Phase 05.2 · Sections 5, 6, 8).

Connects musical performance vocabulary directly to:
- Verified engine capabilities (`VERIFIED | PARTIALLY_SUPPORTED | EXPERIMENTAL | UNSUPPORTED | FAILED`)
- Generation Strategies A–E
- Real instrument presets, articulations, and subtle musical FX chains.
Unsupported techniques are NEVER marked as implemented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine import paths as engine_paths

CAPABILITY_STATES = ("VERIFIED", "PARTIALLY_SUPPORTED", "EXPERIMENTAL", "UNSUPPORTED", "FAILED")

GENERATION_STRATEGIES: dict[str, dict[str, str]] = {
    "strategy_a_native_audio": {
        "id": "strategy_a_native_audio",
        "label": "Strategy A · Native Instrument-focused Audio (YuE2)",
        "descriptionKo": "YuE2가 해당 악기 단독 오디오를 누출 없이 생성할 수 있음이 실증된 경우 우선 사용.",
    },
    "strategy_b_native_stem": {
        "id": "strategy_b_native_stem",
        "label": "Strategy B · Native Audio + Stem Extraction (YuE2 + Demucs)",
        "descriptionKo": "YuE2 네이티브 오디오 생성 후 Demucs로 분리 가능한 스템(drums/bass)을 추출. 추출 스템임을 명시하며 혼합 other 스템을 단독 기타/피아노로 위장하지 않음.",
    },
    "strategy_c_pro_instrument": {
        "id": "strategy_c_pro_instrument",
        "label": "Strategy C · Professional Instrument Performance (SF3 / Drum Rack / Pro Synth)",
        "descriptionKo": "검증된 프로 가상악기와 연주 지능(보이싱·그루브·아티큘레이션·피치벤드)으로 독립 편집·화성 정렬·제로 누출 레이어를 생성.",
    },
    "strategy_d_sample": {
        "id": "strategy_d_sample",
        "label": "Strategy D · Sample-based Session (Sampler / Library)",
        "descriptionKo": "사용 권한이 확인된 스튜디오 루프·원샷 샘플과 Sampler를 활용.",
    },
    "strategy_e_hybrid": {
        "id": "strategy_e_hybrid",
        "label": "Strategy E · Hybrid (Native Audio + Extracted Stems + Pro Instruments)",
        "descriptionKo": "네이티브 오디오·추출 스템·프로 가상악기 레이어를 음악적 역할에 따라 결합.",
    },
}

# Canonical Instrument Performance Vocabulary (Section 8) linked to real support & rendering metadata
PERFORMANCE_VOCABULARY: dict[str, dict[str, dict[str, Any]]] = {
    "guitar": {
        "funk_riff": {
            "label": "Funk Guitar Riff / Comping",
            "aliases": ["riff", "funk", "funk_comping", "palm_mute", "chord_stab", "펑키", "펑크", "리프", "뮤트"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-guitar-clean",
            "preset": "muted_funk",
            "articulation": "palm_mute",
            "subtleFx": [
                {"type": "guitar_amp", "preset": "clean", "parameters": {"outputGainDb": 6.0}},
                {"type": "parametric_eq", "preset": "low_mid_clean"},
            ],
            "sendRoomDb": -13.0,
        },
        "clean_melodic": {
            "label": "Clean Melodic Guitar / Arpeggio",
            "aliases": ["arpeggio", "single_note_phrase", "clean", "strumming", "call_and_response", "클린", "아르페지오", "프레이즈"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-guitar-clean",
            "preset": "jazz_hollow",
            "articulation": "strum_down",
            "subtleFx": [
                {"type": "guitar_amp", "preset": "clean", "parameters": {"outputGainDb": 7.5}},
                {"type": "delay", "preset": "dotted_eighth", "wetDry": 0.16},
            ],
            "sendRoomDb": -10.5,
        },
        "solo": {
            "label": "Expressive Guitar Solo (Bend / Slide / Legato)",
            "aliases": ["guitar_solo", "bend", "slide", "legato", "vibrato", "솔로", "기타 솔로"],
            "supportStatus": "PARTIALLY_SUPPORTED",
            "supportNoteKo": "MIDI pitchBendSemitones 기반 벤드·슬라이드와 프레이즈 아크는 실지원되나, 실제 기타리스트의 미세 비브라토·피킹 뉘앙스는 SF3 한계가 있어 사용자 청취 평가 필요.",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-guitar-clean",
            "preset": "clean_strat",
            "articulation": "natural",
            "subtleFx": [
                {"type": "guitar_amp", "preset": "clean", "parameters": {"outputGainDb": 8.5, "drive": 0.28}},
                {"type": "delay", "preset": "dotted_eighth", "wetDry": 0.18},
            ],
            "sendRoomDb": -9.5,
        },
        "vibrato_authentic_finger": {
            "label": "Authentic Finger Vibrato / Pinch Harmonics",
            "aliases": ["pinch_harmonic"],
            "supportStatus": "UNSUPPORTED",
            "supportNoteKo": "현재 SF3 사운드폰트 기반 기타 엔진에서는 실제 손가락 비브라토·하모닉스 연주를 지원하지 않습니다.",
            "recommendedStrategy": "strategy_e_hybrid",
        },
    },
    "keys": {
        "neo_soul_comping": {
            "label": "Neo Soul Rootless Chord Comping",
            "aliases": ["chord_comping", "jazz_voicing", "rootless_voicing", "syncopated_chords", "passing_chord", "walking_harmony", "컴핑", "보이싱", "재지", "로즈", "neo soul", "네오소울"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-ep-rhodes",
            "preset": "jazz_warm_ep",
            "articulation": "warm_roll",
            "subtleFx": [
                {"type": "chorus", "preset": "juno_wide", "wetDry": 0.18},
                {"type": "parametric_eq", "preset": "low_mid_clean"},
            ],
            "sendRoomDb": -12.0,
        },
        "piano_melody": {
            "label": "Piano / Rhodes Melodic Phrase & Counter Melody",
            "aliases": ["melodic_phrase", "arpeggio", "counter_melody", "피아노 멜로디", "멜로디"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-piano-grand",
            "preset": "warm_felt",
            "articulation": "warm_roll",
            "subtleFx": [{"type": "parametric_eq", "preset": "low_mid_clean"}],
            "sendRoomDb": -11.0,
        },
        "piano_solo": {
            "label": "Improvised Jazz / Neo Soul Piano Solo",
            "aliases": ["improvised_solo", "solo", "피아노 솔로", "건반 솔로"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-ep-rhodes",
            "preset": "rhodes_tine",
            "articulation": "natural",
            "subtleFx": [
                {"type": "chorus", "preset": "juno_wide", "wetDry": 0.15},
                {"type": "delay", "preset": "dotted_eighth", "wetDry": 0.14},
            ],
            "sendRoomDb": -10.5,
        },
    },
    "bass": {
        "pocket_groove": {
            "label": "Fingerstyle Pocket Bass",
            "aliases": ["fingerstyle_groove", "pocket_groove", "muted_notes", "포켓", "그루브"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-bass-electric",
            "preset": "fingered",
            "articulation": "legato",
            "subtleFx": [
                {"type": "parametric_eq", "preset": "bass_focus"},
                {"type": "compressor", "preset": "gentle_glue"},
            ],
            "sendRoomDb": None,
        },
        "syncopated_riff": {
            "label": "Syncopated & Octave Bass Riff",
            "aliases": ["syncopation", "octave_riff", "slide", "passing_notes", "리프", "옥타브", "싱코페이션"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-bass-electric",
            "preset": "fingered",
            "articulation": "slide",
            "subtleFx": [
                {"type": "parametric_eq", "preset": "bass_focus"},
                {"type": "compressor", "preset": "gentle_glue"},
            ],
            "sendRoomDb": None,
        },
        "melodic_bassline": {
            "label": "Melodic & Walking Bassline",
            "aliases": ["walking_bass", "melodic_bassline", "멜로딕 베이스", "워킹"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "sf-bass-electric",
            "preset": "fretless",
            "articulation": "slide",
            "subtleFx": [
                {"type": "parametric_eq", "preset": "bass_focus"},
                {"type": "compressor", "preset": "gentle_glue"},
            ],
            "sendRoomDb": -20.0,
        },
    },
    "drums": {
        "pocket_groove": {
            "label": "R&B Laid-back Pocket Groove",
            "aliases": ["pocket_groove", "swing", "laid_back_groove", "ghost_notes", "dynamic_accent", "포켓", "레이백", "드럼", "r&b"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "boombap-vintage",
            "articulation": "natural",
            "subtleFx": [
                {"type": "compressor", "preset": "gentle_glue"},
                {"type": "saturation", "preset": "warm_tape"},
            ],
            "sendRoomDb": -16.0,
        },
        "syncopated_hiphop": {
            "label": "Syncopated Hip-hop / Breakbeat Groove",
            "aliases": ["breakbeat", "shuffle", "groove_variation", "double_time", "half_time", "힙합", "싱코페이션", "변주"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "boombap-vintage",
            "articulation": "flam_accents",
            "subtleFx": [
                {"type": "compressor", "preset": "gentle_glue"},
                {"type": "saturation", "preset": "warm_tape"},
            ],
            "sendRoomDb": -15.5,
        },
        "drum_fill_transition": {
            "label": "Drum Fill & Section Transition",
            "aliases": ["fill", "drum_fill", "필인", "필", "전환"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "boombap-vintage",
            "articulation": "flam_accents",
            "subtleFx": [{"type": "compressor", "preset": "gentle_glue"}],
            "sendRoomDb": -15.0,
        },
    },
    "percussion": {
        "subtle_layer": {
            "label": "Subtle Shaker / Rim / Conga Layer",
            "aliases": ["shaker", "rim", "tambourine", "subtle", "셰이커", "잔잔"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "percussion-latin-studio",
            "articulation": "natural",
            "subtleFx": [{"type": "parametric_eq", "preset": "low_mid_clean"}],
            "sendRoomDb": -13.5,
        },
        "syncopated_riff": {
            "label": "Syncopated Conga / Bongo / Cross-rhythm Riff",
            "aliases": ["conga", "bongo", "syncopation", "polyrhythm", "cross_rhythm", "rhythmic_response", "콩가", "봉고", "독특", "리프"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "percussion-latin-studio",
            "articulation": "natural",
            "subtleFx": [{"type": "parametric_eq", "preset": "low_mid_clean"}],
            "sendRoomDb": -12.5,
        },
        "percussion_break": {
            "label": "Percussion Solo / Break",
            "aliases": ["solo", "break", "브레이크", "퍼커션 솔로"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-drum-rack",
            "preset": "percussion-latin-studio",
            "articulation": "natural",
            "subtleFx": [{"type": "parametric_eq", "preset": "low_mid_clean"}],
            "sendRoomDb": -12.0,
        },
    },
    "synth": {
        "lead_solo": {
            "label": "Expressive Synth Lead / Hook / Solo",
            "aliases": ["lead", "hook", "solo", "counter_melody", "modulated_phrase", "신스", "리드", "훅"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-synth-analog",
            "preset": "warm-analog-pluck",
            "articulation": "legato",
            "subtleFx": [{"type": "delay", "preset": "dotted_eighth", "wetDry": 0.18}],
            "sendRoomDb": -11.0,
        },
        "textural_pad": {
            "label": "Warm Analog Textural Layer / Chord Stab",
            "aliases": ["chord_stab", "arpeggio", "textural_layer", "패드", "텍스처"],
            "supportStatus": "VERIFIED",
            "recommendedStrategy": "strategy_c_pro_instrument",
            "instrumentRef": "pro-synth-analog",
            "preset": "wide-analog-pad",
            "articulation": "natural",
            "subtleFx": [{"type": "parametric_eq", "preset": "low_mid_clean"}],
            "sendRoomDb": -10.0,
        },
    },
}


def resolve_performance_spec(instrument: str, performance_type: str | None = None, instruction: str = "") -> tuple[str, dict[str, Any]]:
    """Resolve canonical (performanceKey, spec) for an instrument & natural-language request."""
    inst_key = instrument.lower().strip()
    if inst_key in ("piano", "rhodes", "ep", "keyboard"):
        inst_key = "keys"
    elif inst_key in ("synth_hook", "pad", "lead"):
        inst_key = "synth"
    fam = PERFORMANCE_VOCABULARY.get(inst_key) or PERFORMANCE_VOCABULARY["keys"]
    if performance_type and performance_type in fam:
        return performance_type, fam[performance_type]

    low = f"{performance_type or ''} {instruction}".lower()
    for pk, spec in fam.items():
        if spec.get("supportStatus") == "UNSUPPORTED":
            continue
        if pk in low or any(al in low for al in spec.get("aliases", [])):
            return pk, spec
    first_key = next(k for k, v in fam.items() if v.get("supportStatus") != "UNSUPPORTED")
    return first_key, fam[first_key]


def get_instrument_capability_matrix() -> dict[str, Any]:
    """Return honest empirical YuE2 + Demucs + Pro Instrument capability matrix (Section 5 & 6).

    Reads real GATE 0 probe evidence from `outputs/daw/phase052_gate0_audit/gate0_audit_results.json`
    when available so status claims are strictly evidence-backed.
    """
    audit_path = engine_paths.DATA / "daw" / "phase052_gate0_audit" / "gate0_audit_results.json"
    audit_data: dict[str, Any] = {}
    if audit_path.is_file():
        try:
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
        except Exception:
            audit_data = {}

    yue_drums_status = (audit_data.get("yue2_solo_drums") or {}).get("capabilityStatus", "EXPERIMENTAL")
    yue_guitar_status = (audit_data.get("yue2_solo_guitar") or {}).get("capabilityStatus", "EXPERIMENTAL")

    return {
        "schemaVersion": 1,
        "empiricalAuditPresent": bool(audit_data),
        "empiricalAuditPath": str(audit_path) if audit_path.is_file() else None,
        "yue2InstrumentFocused": {
            "full_band_instrumental": {
                "status": "VERIFIED",
                "noteKo": "YuE2 Native Audio + 공식 compile_score.py는 완성형 다악기 인스트루멘털 생성에 최적화되어 있음 (Phase 05.1 검증 완료).",
            },
            "solo_drums": {
                "status": yue_drums_status,
                "empirical": audit_data.get("yue2_solo_drums"),
                "noteKo": (
                    "단독 드럼 프롬프트에서도 베이스/화성 누출이 발생할 수 있으므로, 순수 독립 드럼이 필요하면 "
                    "Strategy B(Demucs drums 스템 추출) 또는 Strategy C(Pro Drum Rack SF3)를 사용합니다."
                ),
            },
            "solo_guitar": {
                "status": yue_guitar_status,
                "empirical": audit_data.get("yue2_solo_guitar"),
                "noteKo": (
                    "YuE2는 전체 밴드 맥락으로 생성하는 경향이 강하며, Demucs other 스템은 기타·건반이 혼합되므로 "
                    "혼합 오디오를 독립 기타로 위장하지 않고 정확한 화성·리듬 독립 레이어는 Strategy C(Pro SF3 Guitar + Amp/IR)를 사용합니다."
                ),
            },
            "solo_bass": {
                "status": "PARTIALLY_SUPPORTED",
                "noteKo": "YuE2 생성 후 Demucs bass 스템 추출(Strategy B)은 가능하나 정확한 코드·킥 동기화는 Strategy C(sf-bass-electric)가 우세합니다.",
            },
            "solo_piano": {
                "status": "PARTIALLY_SUPPORTED",
                "noteKo": "Demucs 4스템은 피아노와 기타를 other로 묶어 분리하므로 독립 피아노/로즈 레이어는 Strategy C(sf-ep-rhodes / sf-piano-grand)를 우선합니다.",
            },
            "accompaniment_free_overdub": {
                "status": "UNSUPPORTED",
                "noteKo": "현재 YuE2 런타임은 기존 다트랙 세션 오디오를 청취하며 새 단독 악기만 오버더빙하는 inpainting을 지원하지 않습니다.",
            },
        },
        "strategies": GENERATION_STRATEGIES,
        "vocabulary": PERFORMANCE_VOCABULARY,
    }
