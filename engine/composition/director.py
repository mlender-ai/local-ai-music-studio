"""Genre-adaptive Musical Composition Director (Phase 03-C).

Produces a structured CompositionPlan BEFORE any audio or MIDI generation runs:
MusicalIdentity -> SignatureMotif -> Harmony & Groove -> InstrumentRoles
-> Arrangement (genre-adaptive, never fixed 48 bars) -> Variations -> Climax -> GenerationStrategy.
"""

from __future__ import annotations

import re
from typing import Any

from engine.daw_workspace.schema import Project
from engine.providers import build_producer_context, invoke_llm_json

from .reference_context import build_reference_binding
from .schemas import CompositionPlan, PlannedSection

GENRE_PROFILES: dict[str, dict[str, Any]] = {
    "house": {
        "defaultBpm": 126.0,
        "defaultKey": "F minor",
        "scale": "natural_minor",
        "grooveFeel": "four_on_the_floor_groove",
        "swingRatio": 0.54,
        "chords": ["Fm7", "Dbmaj7", "Abmaj7", "Eb6"],
        "motifConcept": "Syncopated 16th-note chord-tone hook with offbeat anticipation and call-and-response tail",
        "motifDegrees": [1, 3, 5, 4, 3, 2, 1, 7],
        "sections": [
            ("INTRO", 4, 0.42, ["drums", "pad"]),
            ("GROOVE", 8, 0.72, ["drums", "bass", "keys"]),
            ("HOOK", 8, 0.90, ["drums", "bass", "keys", "synth_hook"]),
            ("BREAK", 4, 0.48, ["pad", "keys", "synth_hook"]),
            ("CLIMAX", 8, 1.00, ["drums", "bass", "keys", "synth_hook", "pad"]),
            ("OUTRO", 4, 0.38, ["drums", "bass"]),
        ],
    },
    "lofi": {
        "defaultBpm": 84.0,
        "defaultKey": "D minor",
        "scale": "dorian",
        "grooveFeel": "laid_back_swing",
        "swingRatio": 0.60,
        "chords": ["Dm9", "G13", "Cmaj9", "A7"],
        "motifConcept": "Warm Rhodes-style syncopated motif with gentle bluesy 7th/9th upper neighbor tones",
        "motifDegrees": [5, 3, 4, 5, 7, 6, 5, 3],
        "sections": [
            ("INTRO", 4, 0.40, ["keys", "pad"]),
            ("VERSE", 8, 0.68, ["drums", "bass", "keys"]),
            ("HOOK", 8, 0.86, ["drums", "bass", "keys", "guitar"]),
            ("OUTRO", 4, 0.45, ["keys", "pad"]),
        ],
    },
    "synthwave": {
        "defaultBpm": 112.0,
        "defaultKey": "A minor",
        "scale": "natural_minor",
        "grooveFeel": "driving_8th_pulse",
        "swingRatio": 0.50,
        "chords": ["Am", "F", "C", "G"],
        "motifConcept": "Anthemic neon lead hook riding driving 8th-note synth bass arpeggio",
        "motifDegrees": [1, 5, 4, 3, 5, 6, 5, 3],
        "sections": [
            ("INTRO", 4, 0.45, ["pad", "bass"]),
            ("DRIVE", 8, 0.78, ["drums", "bass", "keys"]),
            ("CHORUS", 8, 0.96, ["drums", "bass", "keys", "synth_hook", "pad"]),
            ("BRIDGE", 4, 0.55, ["pad", "synth_hook"]),
            ("FINAL CHORUS", 8, 1.00, ["drums", "bass", "keys", "synth_hook", "pad"]),
        ],
    },
    "hiphop": {
        "defaultBpm": 94.0,
        "defaultKey": "C minor",
        "scale": "natural_minor",
        "grooveFeel": "boom_bap_pocket",
        "swingRatio": 0.58,
        "chords": ["Cm7", "Abmaj7", "Fm7", "G7"],
        "motifConcept": "Minimalist memorable 2-bar melodic loop leaving wide pocket for low-end bounce",
        "motifDegrees": [1, 3, 4, 5, 3, 1, 7, 1],
        "sections": [
            ("INTRO", 4, 0.45, ["keys", "pad"]),
            ("VERSE", 8, 0.76, ["drums", "bass", "keys"]),
            ("HOOK", 8, 0.94, ["drums", "bass", "keys", "synth_hook"]),
            ("OUTRO", 4, 0.42, ["drums", "keys"]),
        ],
    },
    "ambient": {
        "defaultBpm": 76.0,
        "defaultKey": "E minor",
        "scale": "natural_minor",
        "grooveFeel": "floating_rubato",
        "swingRatio": 0.50,
        "chords": ["Em9", "Cmaj7", "Gmaj7", "D6"],
        "motifConcept": "Spacious sparse plucked motif with slow harmonic bloom and wide stereo pads",
        "motifDegrees": [1, 2, 5, 3, 6, 5, 2, 1],
        "sections": [
            ("OPENING", 4, 0.35, ["pad"]),
            ("BLOOM", 8, 0.65, ["pad", "keys", "guitar"]),
            ("CREST", 8, 0.88, ["pad", "keys", "guitar", "bass"]),
            ("FADE", 4, 0.30, ["pad", "keys"]),
        ],
    },
    "pop": {
        "defaultBpm": 118.0,
        "defaultKey": "G major",
        "scale": "major",
        "grooveFeel": "modern_pop_tight",
        "swingRatio": 0.52,
        "chords": ["G", "D", "Em7", "Cadd9"],
        "motifConcept": "Bright pentatonic hook with clear 2-bar question and uplifting 2-bar answer",
        "motifDegrees": [3, 5, 6, 5, 3, 2, 1, 2],
        "sections": [
            ("INTRO", 4, 0.48, ["keys", "guitar"]),
            ("VERSE", 8, 0.70, ["drums", "bass", "guitar"]),
            ("PRE-CHORUS", 4, 0.82, ["drums", "bass", "keys", "pad"]),
            ("CHORUS", 8, 1.00, ["drums", "bass", "keys", "guitar", "synth_hook"]),
            ("OUTRO", 4, 0.45, ["keys", "guitar"]),
        ],
    },
}

ROLE_CATALOG: dict[str, dict[str, Any]] = {
    "drums": {
        "name": "Drums",
        "trackType": "midi",
        "instrumentRef": "drum-kit-electronic",
        "color": "#6a997c",
        "register": "GM Drum Map (C1–C3)",
        "pan": 0.0,
        "gainDb": -1.0,
    },
    "bass": {
        "name": "Bass",
        "trackType": "midi",
        "instrumentRef": "bass-fm-sub",
        "color": "#867ca8",
        "register": "E1–G2 (MIDI 28–48)",
        "pan": 0.0,
        "gainDb": -1.5,
    },
    "keys": {
        "name": "Keys",
        "trackType": "midi",
        "instrumentRef": "keys-electric-ep",
        "color": "#b89458",
        "register": "C3–C5 (MIDI 48–72)",
        "pan": -0.18,
        "gainDb": -3.5,
    },
    "guitar": {
        "name": "Guitar",
        "trackType": "midi",
        "instrumentRef": "guitar-clean-pluck",
        "color": "#c2925a",
        "register": "E3–E5 (MIDI 52–76)",
        "pan": 0.22,
        "gainDb": -3.5,
    },
    "synth_hook": {
        "name": "Synth Hook",
        "trackType": "midi",
        "instrumentRef": "synth-fm-hook",
        "color": "#648ea8",
        "register": "C4–C6 (MIDI 60–84)",
        "pan": 0.08,
        "gainDb": -2.5,
    },
    "pad": {
        "name": "Warm Pad",
        "trackType": "midi",
        "instrumentRef": "pad-warm-analog",
        "color": "#9e7389",
        "register": "C3–G5 (MIDI 48–79)",
        "pan": -0.08,
        "gainDb": -5.5,
    },
}


def _detect_genre(text: str, ref_bpm: float | None = None) -> str:
    low = text.lower()
    if any(k in low for k in ("house", "하우스", "deep house", "딥하우스", "tech house", "클럽", "club", "edm", "dance", "댄스")):
        return "house"
    if any(k in low for k in ("lofi", "lo-fi", "로파이", "칠합", "chill", "재즈", "jazz", "카페")):
        return "lofi"
    if any(k in low for k in ("synthwave", "신스웨이브", "레트로", "retro", "80s", "네온", "cyber")):
        return "synthwave"
    if any(k in low for k in ("hiphop", "hip-hop", "힙합", "트랩", "trap", "붐뱁", "boom bap", "랩")):
        return "hiphop"
    if any(k in low for k in ("ambient", "앰비언트", "시네마틱", "cinematic", "몽환", "명상", "ost", "사운드트랙")):
        return "ambient"
    if any(k in low for k in ("pop", "팝", "알앤비", "r&b", "rnb", "인디", "indie", "밝은", "신나는")):
        return "pop"
    if ref_bpm:
        if 118 <= ref_bpm <= 134:
            return "house"
        if 75 <= ref_bpm <= 96:
            return "lofi"
        if 96 < ref_bpm < 118:
            return "synthwave"
    return "house"


def _detect_mode_and_instrument(
    text: str,
    explicit_mode: str | None = None,
    explicit_instrument: str | None = None,
) -> tuple[str, str | None]:
    low = text.lower()
    target_inst = explicit_instrument
    if not target_inst:
        if any(k in low for k in ("신스 훅", "신스훅", "synth hook", "리드", "lead", "멜로디", "melody", "훅", "hook", "신스", "synth")):
            target_inst = "synth_hook"
        elif any(k in low for k in ("드럼", "drum", "비트", "beat", "퍼커션", "리듬")):
            target_inst = "drums"
        elif any(k in low for k in ("베이스", "bass", "서브")):
            target_inst = "bass"
        elif any(k in low for k in ("피아노", "건반", "키보드", "코드", "piano", "keys", "chord", "rhodes", "ep")):
            target_inst = "keys"
        elif any(k in low for k in ("기타", "guitar", "아르페지오", "플럭")):
            target_inst = "guitar"
        elif any(k in low for k in ("패드", "pad", "텍스처", "스트링")):
            target_inst = "pad"

    if explicit_mode in ("full_music", "instrument_session", "loop_midi"):
        return explicit_mode, target_inst

    # Infer mode cleanly from natural language
    if any(k in low for k in ("midi", "미디", "루프", "loop", "4마디", "8마디", "패턴", "훅을 만들어", "훅 만들어", "멜로디 만들어", "라인 만들어", "세션")):
        if any(k in low for k in ("풀 트랙", "완곡", "전체 곡", "full track", "full song", "한 곡")):
            return "full_music", None
        if any(k in low for k in ("midi", "미디", "루프", "loop", "훅", "hook", "패턴", "4마디")):
            return "loop_midi", target_inst or "synth_hook"
        return "instrument_session", target_inst or "synth_hook"

    if target_inst and any(k in low for k in ("유지해", "추가해", "만들어줘", "넣어줘", "preserve", "keep", "add")):
        if not any(k in low for k in ("풀", "전체", "완곡", "트랙을 만들어", "곡을 만들어", "full")):
            return "loop_midi", target_inst

    return "full_music", None


def _extract_bpm(text: str) -> float | None:
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*bpm", text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 45.0 <= val <= 220.0:
            return round(val, 1)
    return None


def _extract_bars(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*(?:마디|bars?)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 128:
            return val
    return None


def _extract_key(text: str) -> str | None:
    m = re.search(r"\b([A-G][#b]?)\s*(minor|major|min|maj|m)\b", text, re.IGNORECASE)
    if m:
        root = m.group(1).upper()
        if len(root) == 2 and root[1] == "B":
            root = root[0] + "b"
        mode_raw = m.group(2).lower()
        mode = "minor" if mode_raw in ("minor", "min", "m") else "major"
        return f"{root} {mode}"
    return None


def _extract_mood(text: str, genre: str) -> str:
    low = text.lower()
    moods = []
    if any(k in low for k in ("어두운", "다크", "dark", "밤", "심야", "미드나잇", "night", "afterhours")):
        moods.append("late-night / moody")
    if any(k in low for k in ("에너지", "신나는", "강렬", "energetic", "driving", "club", "업리프팅")):
        moods.append("energetic / driving")
    if any(k in low for k in ("따뜻", "감성", "warm", "chill", "편안", "몽환", "dreamy")):
        moods.append("warm / atmospheric")
    if any(k in low for k in ("그루브", "그루비", "groovy", "펑키", "funky", "바운스")):
        moods.append("groovy / tight pocket")
    if not moods:
        return "focused / club-ready" if genre == "house" else "expressive / balanced"
    return ", ".join(moods)


def _chords_for_key(key_str: str, default_chords: list[str]) -> list[str]:
    """Transpose genre chord progression into requested/reference key."""
    parts = key_str.strip().split()
    if len(parts) < 2:
        return list(default_chords)
    root, mode = parts[0], parts[1].lower()
    note_map = {
        "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
        "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
        "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
    }
    names_flat = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    names_sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    r_idx = note_map.get(root)
    if r_idx is None:
        return list(default_chords)
    use_flat = root in ("F", "Bb", "Eb", "Ab", "Db", "Gb", "C", "G") and mode == "minor"
    names = names_flat if use_flat else names_sharp
    if mode == "minor":
        # i7 - VI(maj7) - III(maj7) - VII6 (classic modern minor progression)
        return [
            f"{names[r_idx]}m7",
            f"{names[(r_idx + 8) % 12]}maj7",
            f"{names[(r_idx + 3) % 12]}maj7",
            f"{names[(r_idx + 10) % 12]}6",
        ]
    # I - V - vi7 - IVmaj7
    return [
        f"{names[r_idx]}",
        f"{names[(r_idx + 7) % 12]}",
        f"{names[(r_idx + 9) % 12]}m7",
        f"{names[(r_idx + 5) % 12]}maj7",
    ]


def create_composition_plan(
    project: Project,
    instruction: str,
    mode: str | None = None,
    target_instrument: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    selection: dict[str, Any] | None = None,
    provider_id: str | None = None,
    engine_preference: str = "auto",
) -> CompositionPlan:
    """Create a complete, traceable, genre-adaptive CompositionPlan before generation."""
    binding = build_reference_binding(project, reference_ids=reference_ids, explicit_influences=selected_influences)
    ref_bpm = binding.appliedFeatures.get("tempoBpm")
    ref_key = binding.appliedFeatures.get("key")

    genre = _detect_genre(instruction, ref_bpm=ref_bpm)
    profile = GENRE_PROFILES[genre]
    resolved_mode, resolved_inst = _detect_mode_and_instrument(
        instruction, explicit_mode=mode, explicit_instrument=target_instrument
    )

    prompt_bpm = _extract_bpm(instruction)
    bpm = prompt_bpm or ref_bpm or (project.bpm if resolved_mode != "full_music" else profile["defaultBpm"])
    bpm = round(float(bpm), 1)

    prompt_key = _extract_key(instruction)
    key = prompt_key or ref_key or profile["defaultKey"]
    scale = "major" if "major" in key.lower() else profile["scale"]

    # Chord progression: respect reference chords if bass_movement/mood_energy/harmony selected and valid
    ref_chords = binding.appliedFeatures.get("referenceChords") or []
    valid_ref_chords = [c for c in ref_chords if c and c != "N/C"]
    if len(valid_ref_chords) >= 2 and any(k in binding.selectedInfluences for k in ("bass_movement", "mood_energy", "harmony_mood")):
        chords = valid_ref_chords[:4]
        while len(chords) < 4:
            chords.append(chords[len(chords) % len(valid_ref_chords)])
    else:
        chords = _chords_for_key(key, profile["chords"])

    bpb = project.timeSignature.beats_per_bar
    prompt_bars = _extract_bars(instruction)

    # Determine section arrangement (NEVER hardcoded 48 bars!)
    planned_sections: list[PlannedSection] = []
    if resolved_mode in ("loop_midi", "instrument_session"):
        bars = prompt_bars or (4 if resolved_mode == "loop_midi" else 8)
        role_key = resolved_inst or "synth_hook"
        if bars <= 4:
            planned_sections.append(
                PlannedSection(
                    name="HOOK LOOP" if role_key == "synth_hook" else f"{role_key.upper()} LOOP",
                    startBar=1,
                    endBar=bars,
                    bars=bars,
                    energy=0.82,
                    activeRoles=[role_key],
                    transitionNote="Motif A (bars 1–2) -> Variation A'/Resolution (bars 3–4)",
                    source="planned",
                )
            )
        else:
            half = bars // 2
            planned_sections.append(
                PlannedSection(
                    name="PHRASE A",
                    startBar=1,
                    endBar=half,
                    bars=half,
                    energy=0.72,
                    activeRoles=[role_key],
                    transitionNote="Establish primary melodic/rhythmic motif",
                    source="planned",
                )
            )
            planned_sections.append(
                PlannedSection(
                    name="PHRASE B (VARIATION)",
                    startBar=half + 1,
                    endBar=bars,
                    bars=bars - half,
                    energy=0.90,
                    activeRoles=[role_key],
                    transitionNote="Develop motif with harmonic lift and cadence turnaround",
                    source="planned",
                )
            )
        total_bars = bars
        active_role_keys = [role_key]
    else:
        # Full Music: honor prompt bars or reference arrangement arc or genre-native section structure!
        ref_arc = binding.appliedFeatures.get("arrangementArc")
        if ref_arc and len(ref_arc) >= 3 and not prompt_bars:
            cur_bar = 1
            for idx, rs in enumerate(ref_arc[:6]):
                rel_e = float(rs.get("relativeEnergy", 0.65))
                sec_bars = 4 if (idx == 0 or idx == len(ref_arc[:6]) - 1 or rel_e < 0.55) else 8
                roles = ["drums", "pad"] if rel_e < 0.50 else (
                    ["drums", "bass", "keys"] if rel_e < 0.78 else ["drums", "bass", "keys", "synth_hook", "pad"]
                )
                planned_sections.append(
                    PlannedSection(
                        name=str(rs.get("label", f"SECTION {idx + 1}")).upper(),
                        startBar=cur_bar,
                        endBar=cur_bar + sec_bars - 1,
                        bars=sec_bars,
                        energy=round(min(1.0, max(0.25, rel_e)), 2),
                        activeRoles=roles,
                        transitionNote=f"Aligned to reference section energy ({rel_e:.2f})",
                        source="planned",
                    )
                )
                cur_bar += sec_bars
            total_bars = cur_bar - 1
        elif prompt_bars:
            # Build proportional arrangement matching requested bar count
            if prompt_bars <= 8:
                planned_sections = [
                    PlannedSection(name="GROOVE", startBar=1, endBar=prompt_bars, bars=prompt_bars, energy=0.85, activeRoles=["drums", "bass", "keys", "synth_hook"], source="planned")
                ]
            else:
                intro_b = max(2, prompt_bars // 6)
                outro_b = max(2, prompt_bars // 6)
                mid_b = prompt_bars - intro_b - outro_b
                g_b = max(4, mid_b // 2)
                c_b = max(2, mid_b - g_b)
                planned_sections = [
                    PlannedSection(name="INTRO", startBar=1, endBar=intro_b, bars=intro_b, energy=0.45, activeRoles=["drums", "pad"], source="planned"),
                    PlannedSection(name="GROOVE", startBar=intro_b + 1, endBar=intro_b + g_b, bars=g_b, energy=0.78, activeRoles=["drums", "bass", "keys"], source="planned"),
                    PlannedSection(name="CLIMAX", startBar=intro_b + g_b + 1, endBar=intro_b + g_b + c_b, bars=c_b, energy=0.98, activeRoles=["drums", "bass", "keys", "synth_hook", "pad"], source="planned"),
                    PlannedSection(name="OUTRO", startBar=prompt_bars - outro_b + 1, endBar=prompt_bars, bars=outro_b, energy=0.40, activeRoles=["drums", "bass"], source="planned"),
                ]
            total_bars = prompt_bars
        else:
            cur_bar = 1
            for sec_name, sec_bars, sec_energy, sec_roles in profile["sections"]:
                planned_sections.append(
                    PlannedSection(
                        name=sec_name,
                        startBar=cur_bar,
                        endBar=cur_bar + sec_bars - 1,
                        bars=sec_bars,
                        energy=sec_energy,
                        activeRoles=list(sec_roles),
                        transitionNote="Dynamic density shift and turnaround fill at section boundary",
                        source="planned",
                    )
                )
                cur_bar += sec_bars
            total_bars = cur_bar - 1

        # Collect ordered unique roles used across planned sections
        seen_roles: list[str] = []
        for s in planned_sections:
            for r in s.activeRoles:
                if r not in seen_roles:
                    seen_roles.append(r)
        active_role_keys = seen_roles

    instrument_roles = []
    for rk in active_role_keys:
        meta = ROLE_CATALOG.get(rk, ROLE_CATALOG["synth_hook"])
        instrument_roles.append(
            {
                "role": rk,
                "name": meta["name"],
                "trackType": meta["trackType"],
                "instrumentRef": meta["instrumentRef"],
                "color": meta["color"],
                "register": meta["register"],
                "pan": meta["pan"],
                "gainDb": meta["gainDb"],
                "activeSections": [s.name for s in planned_sections if rk in s.activeRoles],
            }
        )

    # Check if user explicitly asked to preserve existing drums/bass or target current selection
    low_inst = instruction.lower()
    preserve_existing = any(k in low_inst for k in ("유지", "보존", "그대로", "preserve", "keep")) or resolved_mode != "full_music"
    vocal_requested = any(k in low_inst for k in ("보컬", "가사", "노래", "vocal", "lyrics", "sing"))
    instrumental_only = not vocal_requested

    climax_sec = max(planned_sections, key=lambda s: s.energy)
    duration_sec = round(total_bars * bpb * (60.0 / bpm), 2)

    # Optional LLM enrichment ONLY when local Ollama or user-configured API is genuinely active
    ctx = build_producer_context(project, selection=selection)
    llm_note_patch, prov_meta = invoke_llm_json(
        system_prompt=(
            "You are an AI Music Producer inside a DAW. Return compact JSON with keys "
            "`title`, `motifConcept`, `variationTips` (array of 2 concise strings) matching the requested genre/key/BPM."
        ),
        user_prompt=f"Instruction: {instruction}\nGenre: {genre}, BPM: {bpm}, Key: {key}, Mode: {resolved_mode}\nContext: {ctx['project']}",
        provider_id=provider_id,
    )

    title_base = (
        str(llm_note_patch.get("title")).strip()
        if isinstance(llm_note_patch, dict) and llm_note_patch.get("title")
        else (
            f"{key} {genre.title()} {resolved_inst.replace('_', ' ').title() if resolved_inst else 'Arrangement'}"
        )
    )
    motif_concept = (
        str(llm_note_patch.get("motifConcept")).strip()
        if isinstance(llm_note_patch, dict) and llm_note_patch.get("motifConcept")
        else profile["motifConcept"]
    )

    variations = [
        "Motif A (Bars 1–2) -> Motif A' rhythmic/register lift (Bars 3–4) to prevent loop monotony",
        "Turnaround percussion fill & passing-tone bass pickup entering every new section",
        "Dynamic contrast between Break/Verse texture and full-band Climax",
    ]
    if isinstance(llm_note_patch, dict) and isinstance(llm_note_patch.get("variationTips"), list):
        extra_tips = [str(x).strip() for x in llm_note_patch["variationTips"] if str(x).strip()][:2]
        if extra_tips:
            variations = extra_tips + variations[:1]

    # Resolve bar range from selection if loop/instrument mode
    sel_bar_range = ctx.get("selection", {}).get("barRange")
    start_beats = float(sel_bar_range["startBeats"]) if (sel_bar_range and resolved_mode != "full_music") else 0.0

    # Determine actual engine label honestly
    actual_engine = (
        "midi-composer-v3"
        if resolved_mode in ("loop_midi", "instrument_session")
        else ("local-multitrack-composer" if engine_preference in ("auto", "local-multitrack-composer") else engine_preference)
    )

    summary_ko = (
        f"[{resolved_mode}] {title_base} · {bpm} BPM · {key} · {total_bars}마디({duration_sec:.1f}초) · "
        f"악기: {', '.join(r['name'] for r in instrument_roles)}"
        + (f" · 레퍼런스 반영: {', '.join(binding.selectedInfluences)}" if binding.referenceIds else "")
    )
    summary_en = (
        f"[{resolved_mode}] {title_base} · {bpm} BPM · {key} · {total_bars} bars ({duration_sec:.1f}s) · "
        f"Roles: {', '.join(r['name'] for r in instrument_roles)}"
    )

    return CompositionPlan(
        projectId=project.id,
        instruction=instruction.strip(),
        mode=resolved_mode,  # type: ignore[arg-type]
        musicalIdentity={
            "title": title_base,
            "genre": genre,
            "mood": _extract_mood(instruction, genre),
            "tempoBpm": bpm,
            "timeSignature": f"{project.timeSignature.numerator}/{project.timeSignature.denominator}",
            "key": key,
            "scale": scale,
            "barCount": total_bars,
            "durationSec": duration_sec,
            "instrumentalOnly": instrumental_only,
        },
        signatureMotif={
            "concept": motif_concept,
            "scaleDegrees": list(profile["motifDegrees"]),
            "callAndResponse": True,
            "variationRule": "A -> A' (rhythmic variation) -> B (contrast lift) -> Return",
        },
        harmonyAndGroove={
            "key": key,
            "scale": scale,
            "chordProgression": chords,
            "chordsPerBar": 1,
            "grooveFeel": binding.appliedFeatures.get("grooveFeel") or profile["grooveFeel"],
            "swingRatio": float(binding.appliedFeatures.get("swingRatio") or profile["swingRatio"]),
        },
        instrumentRoles=instrument_roles,
        arrangement=planned_sections,
        variations=variations,
        climax={
            "sectionName": climax_sec.name,
            "startBar": climax_sec.startBar,
            "endBar": climax_sec.endBar,
            "energy": climax_sec.energy,
            "strategy": "Full multi-instrument layering with motif octave lift and turnaround fill",
        },
        generationStrategy={
            "mode": resolved_mode,
            "preferredEngine": engine_preference,
            "actualEngine": actual_engine,
            "targetInstrument": resolved_inst,
            "targetTrackId": ctx.get("selection", {}).get("selectedTrackId") if resolved_mode != "full_music" else None,
            "preserveExistingTracks": preserve_existing,
            "startBeats": start_beats,
            "durationBeats": total_bars * bpb,
        },
        referenceBinding=binding,
        providerProvenance=prov_meta,
        summaryKo=summary_ko,
        summaryEn=summary_en,
    )
