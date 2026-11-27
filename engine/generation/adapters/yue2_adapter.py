"""YuE2 Native Adapter aligned 1:1 with V7.2 `scripts/v4_study.py`, `scripts/v7_native.py` & Official Music Agent Skill (Phase 05.1).

Verified against `origin/codex/v7-2-house-hook-first` and local `.runtime/v6/instrumental/`:
- Real CLI flags:
  - Planner: `yue-plan --model YuE2-3B-Q8_0.gguf --request planner-request.json --max-seq 8192 --out planned.abc`
  - Synth:   `yue-synth --model YuE2-3B-Q8_0.gguf --vae YuE2-Vae-F32.gguf --request request.json --max-seq 8192 --out original.wav --score plan.abc --tokens semantic_tokens.csv`
- Compiles official YuE2 resting-voice instrumental ABC scores (`v6/instrumental/compile_score.py` when present,
  with strict YuE2 15-quality chord normalizer and clean built-in fallback).
- Supports CoT (`full`/`melody`/`off`), `cfg_scale`, `semantic_sampling.temperature`, `abc` score conditioning,
  `source_tokens` continuation, and `semantic_tokens` resynthesis.
- Wires strict `check_resting_voice()` directly into pre-synthesis execution gate.
- Vocal leakage screening uses strict 3-state verdict (`PASS`, `REJECT`, `UNCERTAIN`) and NEVER falsely returns
  `PASS` on neural audio without actually executing Demucs isolated vocal stem screening!
- Runs under `run_cancellable_guarded()` (true process-group SIGTERM/SIGKILL cancellation + 10 GiB RAM guard).
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.composition.schemas import CompositionPlan
from engine.generation.process_guard import run_cancellable_guarded
from engine.runtime import get_runtime_registry, record_engine_verification

ALLOWED_YUE2_SECTIONS = frozenset(
    (
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "interlude",
        "bridge",
        "instrumental",
        "outro",
    )
)

# Official YuE2 ABC chord qualities from `.runtime/v6/instrumental/abc_tools.py`
YUE2_LEGAL_QUALITIES = frozenset(
    ("", "m", "dim", "aug", "7", "maj7", "m7", "dim7", "m7b5", "sus4", "sus2", "6", "m6", "7sus4", "m(maj7)")
)

_KEY_TO_ABC_TOKEN = {
    "C major": "C",
    "G major": "G",
    "D major": "D",
    "A major": "A",
    "E major": "E",
    "F major": "F",
    "Bb major": "Bb",
    "Eb major": "Eb",
    "A minor": "Am",
    "E minor": "Em",
    "D minor": "Dm",
    "G minor": "Gm",
    "C minor": "Cm",
    "F minor": "Fm",
    "Bb minor": "Bbm",
    "B minor": "Bm",
    "F# minor": "F#m",
    "C# minor": "C#m",
}

_ROOT_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

_SCALES = {
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "major": [0, 2, 4, 5, 7, 9, 11],
}


def probe_yue2() -> dict[str, Any]:
    reg = get_runtime_registry()
    return next(e for e in reg["engines"] if e["id"] == "yue2-native")


def normalize_chord_for_yue2(chord: str) -> str:
    """Normalize extended jazz/neo-soul chords (Dm9, G13, Cmaj9, A7(b9), Cadd9) to official YuE2 ABC qualities."""
    raw = str(chord or "").strip()
    if not raw or raw in ("N/C", "uncertain"):
        return "Dm7"
    # Strip slash bass for base normalization, re-attach if clean pitch
    slash_bass = ""
    if "/" in raw:
        base_part, bass_part = raw.split("/", 1)
        if re.fullmatch(r"[A-G][#b]?", bass_part.strip()):
            slash_bass = "/" + bass_part.strip()
        raw = base_part.strip()

    m = re.match(r"^([A-G][#b]?)(.*)$", raw)
    if not m:
        return "Dm7"
    root, qual = m.group(1), m.group(2).strip()
    if qual in YUE2_LEGAL_QUALITIES:
        return f"{root}{qual}{slash_bass}"

    ql = qual.lower()
    if "m(maj7)" in ql or "mmaj7" in ql:
        mapped = "m(maj7)"
    elif "m7b5" in ql or "ø" in ql:
        mapped = "m7b5"
    elif "dim7" in ql:
        mapped = "dim7"
    elif "dim" in ql:
        mapped = "dim"
    elif "aug" in ql or "+" in ql:
        mapped = "aug"
    elif "7sus4" in ql or "9sus4" in ql or "13sus4" in ql:
        mapped = "7sus4"
    elif "sus4" in ql:
        mapped = "sus4"
    elif "sus2" in ql:
        mapped = "sus2"
    elif "maj9" in ql or "maj11" in ql or "maj13" in ql or "maj7" in ql:
        mapped = "maj7"
    elif ql.startswith(("m9", "m11", "m13", "min9", "min7", "m7")):
        mapped = "m7"
    elif ql.startswith(("m6", "min6")):
        mapped = "m6"
    elif ql.startswith(("m", "min")):
        mapped = "m"
    elif "add9" in ql or "add11" in ql:
        mapped = ""
    elif any(k in ql for k in ("13", "11", "9", "7", "alt", "b9", "#9", "#11", "b13")):
        mapped = "7"
    elif "6" in ql:
        mapped = "6"
    else:
        mapped = ""
    return f"{root}{mapped}{slash_bass}"


def _normalize_abc_section(raw_label: str) -> str:
    low = str(raw_label or "").strip().lower()
    for allowed in ("intro", "pre-chorus", "chorus", "verse", "bridge", "interlude", "outro", "instrumental"):
        if allowed in low:
            return allowed
    if "hook" in low or "climax" in low:
        return "chorus"
    if "break" in low:
        return "bridge"
    if "groove" in low or "drive" in low or "bloom" in low:
        return "verse"
    return "instrumental"


def _key_to_abc(key_str: str) -> str:
    cleaned = str(key_str or "D minor").strip()
    if cleaned in _KEY_TO_ABC_TOKEN:
        return _KEY_TO_ABC_TOKEN[cleaned]
    parts = cleaned.split()
    if not parts:
        return "Dm"
    root = parts[0]
    mode = parts[1].lower() if len(parts) > 1 else "minor"
    return f"{root}m" if mode.startswith("min") else root


def _load_official_compile_score():
    """Dynamically load official `.runtime/v6/instrumental/compile_score.py` if present on this host."""
    reg = get_runtime_registry()
    v6_dir_str = (reg.get("vocalQaModels") or {}).get("officialAbcValidatorPath")
    if not v6_dir_str:
        return None
    v6_dir = Path(v6_dir_str)
    script = v6_dir / "compile_score.py"
    if not script.is_file():
        return None
    try:
        if str(v6_dir) not in sys.path:
            sys.path.insert(0, str(v6_dir))
        spec = importlib.util.spec_from_file_location("yue2_official_compile_score", str(script))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    except Exception:
        return None
    return None


def compile_instrumental_abc_for_plan(
    plan: CompositionPlan,
    *,
    cot: str = "melody",
) -> dict[str, Any]:
    """Compile an official YuE2 resting-voice instrumental ABC score for `plan`.

    - Uses `.runtime/v6/instrumental/compile_score.py` when present (identical to V7.2 Magnetic Afterhours).
    - Keeps `V:Vocal` strictly resting (`Z4|` / `z8`) and places a musical monophonic motif on `V:Ins`.
    - Normalizes extended chord symbols (`Dm9 -> Dm7`, `G13 -> G7`, `Cmaj9 -> Cmaj7`) when `cot == "full"`.
    """
    ident = plan.musicalIdentity or {}
    hg = plan.harmonyAndGroove or {}
    bpm = int(round(float(ident.get("tempoBpm") or 90.0)))
    key_str = str(hg.get("key") or ident.get("key") or "D minor")
    scale_name = str(hg.get("scale") or ident.get("scale") or "dorian")
    abc_key = _key_to_abc(key_str)
    duration_sec = float(ident.get("durationSec") or 22.0)
    bar_sec = 4.0 * (60.0 / max(45.0, float(bpm)))
    # Target bar count aligned to duration (minimum 4 bars, multiple of 4 for clean musical phrases)
    est_bars = max(4, min(32, int(round(duration_sec / bar_sec))))
    bars = max(4, ((est_bars + 3) // 4) * 4)

    # Extract root MIDI pitch around octave 4 (60..71)
    root_name = key_str.split()[0] if key_str.split() else "D"
    root_pc = _ROOT_SEMITONES.get(root_name, 2)
    root_midi = 60 + root_pc  # e.g., D4 = 62, F4 = 65
    scale_ints = _SCALES.get(scale_name, _SCALES["natural_minor"])

    raw_degrees = list((plan.signatureMotif or {}).get("scaleDegrees") or [5, 3, 4, 5, 7, 6, 5, 3])
    chords_raw = list(hg.get("chordProgression") or ["Dm9", "G13", "Cmaj9", "A7"])
    chords_norm = [normalize_chord_for_yue2(c) for c in chords_raw] or ["Dm7", "G7", "Cmaj7", "A7"]

    def _deg_to_midi(deg: int, oct_shift: int = 0) -> int:
        idx = (max(1, int(deg)) - 1) % len(scale_ints)
        return max(52, min(84, root_midi + scale_ints[idx] + oct_shift * 12))

    # Build exact event payload for official `.runtime/v6/instrumental/compile_score.py`:
    # - `bars`: [{"meter": "4/4", "key": abc_key, "section": sec_label}, ...]
    # - `notes`: [[onset_int_or_frac_str, dur_int_or_frac_str, midi_int], ...] (NO floats!)
    # - `chords`: [[onset_int_or_frac_str, yue2_legal_symbol], ...] (only for cot == "full")
    from fractions import Fraction

    def _frac_token(val: Fraction) -> int | str:
        return int(val) if val.denominator == 1 else f"{val.numerator}/{val.denominator}"

    bars_payload: list[dict[str, Any]] = []
    notes_payload: list[list[Any]] = []
    chords_payload: list[list[Any]] = []
    sections_payload: list[dict[str, Any]] = []
    sec_names_cycle = ["intro", "verse", "chorus", "interlude", "bridge", "chorus", "outro"]
    planned_secs = list(plan.arrangement or [])

    for blk_idx, blk_start in enumerate(range(0, bars, 4)):
        blk_bars = min(4, bars - blk_start)
        if blk_idx < len(planned_secs):
            sec_label = _normalize_abc_section(planned_secs[blk_idx].name)
        else:
            sec_label = sec_names_cycle[blk_idx % len(sec_names_cycle)]

        sec_notes_fallback: list[dict[str, Any]] = []
        sec_chords_fallback: list[dict[str, Any]] = []
        oct_lift = 1 if (sec_label == "chorus" and blk_idx >= 1) else 0

        for b_off in range(blk_bars):
            global_bar = blk_start + b_off
            bars_payload.append({"meter": "4/4", "key": abc_key, "section": sec_label})
            global_beat0 = Fraction(global_bar * 4, 1)
            local_beat0 = float(b_off * 4)

            if cot == "full":
                ch_sym = chords_norm[global_bar % len(chords_norm)]
                chords_payload.append([_frac_token(global_beat0), ch_sym])
                sec_chords_fallback.append({"onset": local_beat0, "symbol": ch_sym})

            d0 = raw_degrees[(b_off * 2) % len(raw_degrees)]
            d1 = raw_degrees[(b_off * 2 + 1) % len(raw_degrees)]
            d2 = raw_degrees[(b_off * 2 + 2) % len(raw_degrees)]
            d3 = raw_degrees[(b_off * 2 + 3) % len(raw_degrees)]

            if b_off % 2 == 0:
                # Bar 1 / 3: laid-back syncopated phrase starting at beat 1.5
                bar_ev = [
                    (Fraction(3, 2), Fraction(1, 2), _deg_to_midi(d0, oct_lift)),
                    (Fraction(2, 1), Fraction(1, 2), _deg_to_midi(d1, oct_lift)),
                    (Fraction(5, 2), Fraction(1, 1), _deg_to_midi(d2, oct_lift)),
                    (Fraction(7, 2), Fraction(1, 2), _deg_to_midi(d3, oct_lift)),
                ]
            else:
                # Bar 2 / 4: expressive answer phrase resolving with breathing space
                bar_ev = [
                    (Fraction(1, 1), Fraction(1, 1), _deg_to_midi(d1, oct_lift)),
                    (Fraction(2, 1), Fraction(1, 2), _deg_to_midi(d2, oct_lift)),
                    (Fraction(5, 2), Fraction(1, 1), _deg_to_midi(d0, oct_lift)),
                ]

            for rel_on, rel_dur, pitch in bar_ev:
                notes_payload.append([_frac_token(global_beat0 + rel_on), _frac_token(rel_dur), int(pitch)])
                sec_notes_fallback.append({"onset": local_beat0 + float(rel_on), "duration": float(rel_dur), "midi": int(pitch)})

        sec_entry: dict[str, Any] = {
            "label": sec_label,
            "bars": blk_bars,
            "notes": sec_notes_fallback,
        }
        if cot == "full":
            sec_entry["chords"] = sec_chords_fallback
        sections_payload.append(sec_entry)

    compile_mod = _load_official_compile_score()
    if compile_mod is not None:
        official_input: dict[str, Any] = {
            "bpm": int(bpm),
            "key": abc_key,
            "bars": bars_payload,
            "notes": notes_payload,
        }
        if cot == "full" and chords_payload:
            official_input["chords"] = chords_payload
        try:
            compiled_out = compile_mod.compile_events(official_input)
            abc_text = compiled_out[0] if isinstance(compiled_out, tuple) else str(compiled_out)
            official_check = compiled_out[1] if isinstance(compiled_out, tuple) and len(compiled_out) > 1 else {}
            ok, issues = check_resting_voice(abc_text)
            if ok:
                return {
                    "abc": abc_text,
                    "validInstrumentalYuE2": True,
                    "validationIssues": [],
                    "officialCheck": official_check,
                    "source": "official_v6_compile_score",
                    "cot": cot,
                    "bars": bars,
                    "normalizedChords": chords_norm,
                }
        except Exception:
            pass

    # Clean built-in fallback strictly conforming to check_resting_voice()
    pitch_names = ["C", "^C", "D", "^D", "E", "F", "^F", "G", "^G", "A", "^A", "B"]

    def _m2a(p: int) -> str:
        pc = p % 12
        octv = (p // 12) - 1
        nm = pitch_names[pc]
        if octv == 4:
            return nm
        if octv == 5:
            return nm.lower()
        if octv > 5:
            return nm.lower() + ("'" * (octv - 5))
        return nm + ("," * (4 - octv))

    lines = ["X:1", "T:", "M:4/4", "L:1/8", f"Q:1/4={bpm}", "V:Vocal", "V:Ins", f"K:{abc_key}"]
    for sec in sections_payload:
        lines.append(f"% {sec['label']}")
        lines.append("V:Vocal")
        lines.append(" | ".join(["z8"] * int(sec["bars"])) + " |")
        lines.append("V:Ins")
        ins_bars: list[str] = []
        for b_off in range(int(sec["bars"])):
            b_notes = [n for n in sec["notes"] if b_off * 4 <= n["onset"] < (b_off + 1) * 4]
            toks: list[str] = []
            if cot == "full":
                ch = next((c["symbol"] for c in sec.get("chords", []) if int(c["onset"] // 4) == b_off), chords_norm[b_off % len(chords_norm)])
                toks.append(f'"{ch}"')
            cur = 0
            for n in b_notes:
                nu = int(round((n["onset"] - b_off * 4) * 2))
                if nu > cur:
                    toks.append(f"z{nu - cur}")
                    cur = nu
                du = max(1, min(8 - cur, int(round(n["duration"] * 2))))
                toks.append(f"{_m2a(int(n['midi']))}{du if du > 1 else ''}")
                cur += du
            if cur < 8:
                toks.append(f"z{8 - cur}")
            ins_bars.append(" ".join(toks))
        lines.append(" | ".join(ins_bars) + " |")
    abc_text = "\n".join(lines) + "\n"
    ok, issues = check_resting_voice(abc_text)
    return {
        "abc": abc_text,
        "validInstrumentalYuE2": ok,
        "validationIssues": issues,
        "source": "builtin_resting_voice_abc_compiler",
        "cot": cot,
        "bars": bars,
        "normalizedChords": chords_norm,
    }


def check_resting_voice(abc_text: str) -> tuple[bool, list[str]]:
    """Exact strict instrumental ABC gate matching `scripts/v7_native.py`:
    - Only allowed section comments (`% intro`, `% verse`, `% chorus`, etc.)
    - Only `V:Vocal` and `V:Ins` voices (no extra voices)
    - Zero `w:`/`W:` lyrics and zero inline `[V:...]`/`[w:...]` voice/lyric switches
    - `V:Vocal` must contain ONLY rests (`z`/`Z`), barlines, chord quotes, and whitespace
    - `V:Ins` must contain sounding pitch notes (`A-Ga-g`)
    """
    issues: list[str] = []
    if not abc_text or not abc_text.strip():
        return False, ["ABC score is empty."]

    lane = ""
    lanes: set[str] = set()
    instrumental_notes = False

    for raw_line in abc_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%"):
            sec = line[1:].strip().lower()
            if sec and sec not in ALLOWED_YUE2_SECTIONS:
                issues.append(f"Unsupported ABC section marker: '{line}'")
            continue
        if line.startswith("V:"):
            parts = line[2:].strip().split(maxsplit=1)
            lane = parts[0] if parts else ""
            if lane not in {"Vocal", "Ins"}:
                issues.append(f"Unsupported ABC voice '{lane}' (only Vocal and Ins allowed).")
            else:
                lanes.add(lane)
            continue
        if re.match(r"^[wW]:", line):
            issues.append("Sung lyric directive (w:/W:) is forbidden in instrumental-only mode.")
            continue
        if re.match(r"^[XTMLQK]:", line):
            continue

        music = re.sub(r'"[^"]*"', "", line)
        if re.search(r"\[\s*[VwW]:", music):
            issues.append("Inline voice or lyric directive ([V:]/[w:]) is forbidden.")
            continue
        if lane == "Vocal":
            if not re.fullmatch(r"(?:[zZxX]\d*|[|:\[\]\s/().>-])+", music):
                issues.append(f"V:Vocal contains non-rest pitch material: '{music[:32]}'")
        elif lane == "Ins":
            if re.search(r"[A-Ga-g]", music):
                instrumental_notes = True

    if lanes != {"Vocal", "Ins"}:
        issues.append(f"Score must declare both V:Vocal and V:Ins lanes (found: {sorted(lanes)}).")
    if not instrumental_notes:
        issues.append("V:Ins contains no sounding instrumental pitch notes.")

    return len(issues) == 0, issues


def build_yue2_request_from_plan(
    plan: CompositionPlan,
    seed: int = 42,
    *,
    cot: str = "melody",
    abc_score: str | None = None,
    cfg_scale: float | None = 2.4,
    semantic_temperature: float | None = 0.80,
    source_tokens: tuple[str, float] | None = None,
    semantic_tokens: str | None = None,
    auto_compile_instrumental_abc: bool = True,
) -> dict[str, Any]:
    """Build exact V7.2-compatible YuE2 request JSON from a CompositionPlan (with Official ABC, Reference Blueprint & Taste conditioning)."""
    ident = plan.musicalIdentity
    hg = plan.harmonyAndGroove or {}
    genre_key = str(ident.get("genre", "rnb_neosoul"))
    genre_style_map = {
        "rnb_neosoul": "sophisticated late-night alternative R&B, neo-soul, jazzy instrumental hip-hop",
        "hiphop": "warm jazzy instrumental hip-hop, laid-back boom-bap pocket",
        "indie_rock": "warm modern indie rock band instrumental, shimmering electric guitars and live acoustic drums",
        "house": "hypnotic late-night progressive deep house instrumental",
        "lofi": "warm jazzy lo-fi instrumental with dusty vinyl feel",
        "synthwave": "atmospheric analog synthwave instrumental",
        "ambient": "spacious cinematic ambient instrumental",
        "pop": "modern refined instrumental pop",
    }
    genre_desc = genre_style_map.get(genre_key, genre_key.replace("_", " "))
    mood = str(ident.get("mood", "warm, refined, late-night, relaxed yet groovy"))
    bpm = int(round(float(ident.get("tempoBpm", 90.0))))
    key = str(ident.get("key", "D minor"))
    instrumental = bool(ident.get("instrumentalOnly", True))
    duration = int(min(120, max(15, round(float(ident.get("durationSec") or 22.0)))))

    motif_desc = str(plan.signatureMotif.get("concept") or "")
    chords_hint = " to ".join(str(c) for c in (hg.get("chordProgression") or [])[:4])
    groove_feel = str(hg.get("grooveFeel") or "natural pocket groove").replace("_", " ")

    if genre_key == "rnb_neosoul":
        ensemble_desc = (
            "Warm Fender Rhodes electric piano playing rich jazz-soul 9th and 13th chords with subtle stereo tremolo, "
            "deep round finger electric bass locking tightly into the pocket, laid-back dusty acoustic drum kit with crisp rimshot, "
            "soft swung hi-hats and natural room air, and tasteful restrained clean hollow-body electric guitar phrases"
        )
    else:
        role_names = ", ".join(r.get("name", r.get("role", "")) for r in plan.instrumentRoles)
        ensemble_desc = f"Natural studio ensemble with {role_names}" if role_names else "Natural organic studio ensemble"

    style_parts = [
        f"Instrumental, {bpm} BPM, {genre_desc}, {ident.get('timeSignature', '4/4')}, {key}" if instrumental else f"{bpm} BPM, {genre_desc}, {ident.get('timeSignature', '4/4')}, {key}",
        ensemble_desc,
        f"Mood: {mood}, groove: {groove_feel}",
    ]
    if chords_hint:
        style_parts.append(f"Harmonic movement around {chords_hint}")
    if motif_desc:
        style_parts.append(motif_desc)

    # Reflect Reference Blueprint v3 sound/spatial descriptors when bound
    ref_applied = plan.referenceBinding.appliedFeatures or {}
    ref_sound = ref_applied.get("referenceSoundProfile") or {}
    if isinstance(ref_sound, dict) and ref_sound.get("toneSummary"):
        style_parts.append(f"Reference tonal feel: {ref_sound['toneSummary']}")
    if ref_applied.get("spectralCentroidTargetHz"):
        c_hz = float(ref_applied["spectralCentroidTargetHz"])
        tone_hint = "warm mellow highs" if c_hz < 1300 else ("balanced studio clarity" if c_hz < 2200 else "crisp airy highs")
        style_parts.append(tone_hint)

    style_parts.append("Balanced clear studio analog mix, crisp presence, realistic organic human timing, natural room space")
    if instrumental:
        style_parts.append("Acoustic and electric instruments only, no voice, no vocals, no humming, no choirs, no vocal samples")
    style = ". ".join(p.strip().rstrip(".") for p in style_parts if p and p.strip()) + "."

    abc_source = "user_abc" if abc_score else None
    if abc_score is None:
        abc_meta = ref_applied.get("abcScore")
        if isinstance(abc_meta, dict) and abc_meta.get("validInstrumentalYuE2") and abc_meta.get("abc"):
            abc_score = str(abc_meta["abc"])
            abc_source = "reference_blueprint_abc"

    if abc_score is None and instrumental and auto_compile_instrumental_abc and cot != "off":
        # Prefer official `.runtime/v6/instrumental/compile_score.py` when present;
        # otherwise allow `yue-plan` preflight gate in `run_yue2_generation` to plan & validate ABC.
        if _load_official_compile_score() is not None:
            compiled = compile_instrumental_abc_for_plan(plan, cot=cot)
            if compiled.get("validInstrumentalYuE2") and compiled.get("abc"):
                abc_score = str(compiled["abc"])
                abc_source = str(compiled.get("source") or "official_v6_compile_score")

    if abc_score is not None and instrumental:
        ok, issues = check_resting_voice(abc_score)
        if not ok:
            raise ValueError(f"Instrumental ABC gate rejected score: {'; '.join(issues)}")

    req: dict[str, Any] = {
        "style": style,
        "lyrics": "",
        "duration": duration,
        "seed": int(seed),
        "lm_seed": int(seed),
        "cot": cot if cot in ("full", "melody", "off") else "melody",
        "steps": 32,
        "output_format": "wav32",
    }
    if cfg_scale is not None:
        req["cfg_scale"] = float(cfg_scale)
    if semantic_temperature is not None:
        req["semantic_sampling"] = {"temperature": float(semantic_temperature)}
    if abc_score is not None:
        req["abc"] = abc_score
    if source_tokens is not None:
        toks, end_sec = source_tokens
        req["source_tokens"] = toks
        req["source_start"] = 0.0
        req["source_end"] = float(end_sec)
    if semantic_tokens is not None:
        if source_tokens is not None:
            raise ValueError("Replay (`semantic_tokens`) and continuation (`source_tokens`) are separate modes")
        req["semantic_tokens"] = semantic_tokens
    if abc_source:
        req["_metaAbcSource"] = abc_source
    return req


def screen_vocal_leakage(
    audio: np.ndarray,
    sr: int,
    *,
    source_kind: str = "neural_audio",  # "neural_audio" | "deterministic_midi_synth"
    vocals_stem_audio: np.ndarray | None = None,
    vocals_stem_sr: int | None = None,
    audio_path: Path | None = None,
    use_demucs: bool = False,
) -> dict[str, Any]:
    """Honest 3-state vocal-leakage screen (`PASS`, `REJECT`, `UNCERTAIN`) per Phase 03.1 & Phase 05.1.

    Honesty invariant:
    - NEVER claims `PASS` on neural audio without ACTUALLY executing Demucs isolated vocal stem screening!
    - Merely having PANNs/Whisper files on disk without executing them MUST return `UNCERTAIN`, not `PASS`.
    - Deterministic non-vocal synth / SoundFont output returns `PASS` (`deterministic_non_vocal_synth`).
    """
    if len(audio) < max(1, sr // 4):
        return {
            "checked": True,
            "status": "UNCERTAIN",
            "suspectedVocal": False,
            "method": "dsp_window_screen",
            "autoApprovedInstrumental": False,
            "note": "Audio too short for vocal screening.",
        }

    stereo = audio if audio.ndim == 2 and audio.shape[1] >= 2 else np.stack([audio, audio], axis=1)
    mid = 0.5 * (stereo[:, 0].astype(np.float64) + stereo[:, 1].astype(np.float64))
    side = 0.5 * (stereo[:, 0].astype(np.float64) - stereo[:, 1].astype(np.float64))

    demucs_vocal_arr = vocals_stem_audio
    demucs_vocal_sr = vocals_stem_sr or sr
    if demucs_vocal_arr is None and use_demucs and audio_path is not None and audio_path.is_file():
        try:
            from engine.generation.adapters.stem_separator import probe_demucs, separate_stems_demucs

            if probe_demucs().get("available"):
                stems = separate_stems_demucs(audio_path, audio_path.parent / "vocal_qa_stems", use_cache=True)
                v_item = next((s for s in stems if s.get("role") == "vocals"), None)
                if v_item and Path(v_item["wavPath"]).is_file():
                    demucs_vocal_arr, demucs_vocal_sr = sf.read(str(v_item["wavPath"]), dtype="float32", always_2d=True)
        except Exception:
            demucs_vocal_arr = None

    win_len = min(len(mid), 4 * sr)
    hop = max(sr, 2 * sr)
    starts = list(range(0, max(1, len(mid) - win_len + 1), hop)) or [0]

    flagged_windows: list[dict[str, Any]] = []
    max_center_ratio = 0.0
    max_mod_score = 0.0

    for st in starts:
        seg_m = mid[st : st + win_len]
        seg_s = side[st : st + win_len]
        nperseg = min(4096, len(seg_m))
        f, p_m = signal.welch(seg_m, fs=sr, nperseg=nperseg)
        _, p_s = signal.welch(seg_s, fs=sr, nperseg=nperseg)
        tot = float(np.sum(p_m + p_s)) + 1e-18
        v_mask = (f >= 300.0) & (f <= 3400.0)
        mid_v = float(np.sum(p_m[v_mask]))
        side_v = float(np.sum(p_s[v_mask]))
        center_ratio = mid_v / tot
        center_dom = mid_v / (mid_v + side_v + 1e-18)
        max_center_ratio = max(max_center_ratio, center_ratio)

        mod_score = 0.0
        if len(seg_m) >= sr:
            try:
                sos = signal.butter(2, [320.0, 3200.0], btype="bandpass", fs=sr, output="sos")
                vb = signal.sosfilt(sos, seg_m)
                env = np.abs(vb)
                dec = max(1, sr // 100)
                env_ds = env[::dec]
                env_ds = env_ds - np.mean(env_ds)
                ef, ep = signal.welch(env_ds, fs=sr / dec, nperseg=min(256, len(env_ds)))
                e_tot = float(np.sum(ep)) + 1e-18
                syll_e = float(np.sum(ep[(ef >= 3.0) & (ef <= 8.5)]))
                mod_score = syll_e / e_tot
                max_mod_score = max(max_mod_score, mod_score)
            except Exception:
                pass

        if center_ratio > 0.68 and center_dom > 0.90 and mod_score > 0.28:
            flagged_windows.append(
                {
                    "startSec": round(st / sr, 2),
                    "endSec": round((st + len(seg_m)) / sr, 2),
                    "centerVocalRatio": round(center_ratio, 3),
                    "syllabicModulation": round(mod_score, 3),
                }
            )

    if source_kind == "deterministic_midi_synth":
        return {
            "checked": True,
            "status": "PASS",
            "suspectedVocal": False,
            "autoApprovedInstrumental": True,
            "method": "deterministic_non_vocal_synth",
            "windowsChecked": len(starts),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": [],
            "note": "비보컬 결정론적 악기/사운드폰트 합성 출력(보컬 모델 미사용)입니다.",
        }

    # Genuine Demucs-isolated vocal stem multi-window screening!
    if demucs_vocal_arr is not None and len(demucs_vocal_arr) >= max(1, demucs_vocal_sr // 4):
        v_mono = demucs_vocal_arr.mean(axis=1).astype(np.float64) if demucs_vocal_arr.ndim == 2 else demucs_vocal_arr.astype(np.float64)
        mix_rms_all = float(np.sqrt(np.mean(mid * mid))) + 1e-9
        v_win = min(len(v_mono), 4 * demucs_vocal_sr)
        v_hop = max(demucs_vocal_sr, 2 * demucs_vocal_sr)
        v_starts = list(range(0, max(1, len(v_mono) - v_win + 1), v_hop)) or [0]
        max_v_db = -120.0
        max_v_ratio = 0.0
        demucs_flagged: list[dict[str, Any]] = []
        for vst in v_starts:
            vseg = v_mono[vst : vst + v_win]
            v_rms = float(np.sqrt(np.mean(vseg * vseg)))
            v_db = 20.0 * float(np.log10(max(v_rms, 1e-9)))
            v_ratio = v_rms / mix_rms_all
            max_v_db = max(max_v_db, v_db)
            max_v_ratio = max(max_v_ratio, v_ratio)
            # V7.2 principle: "Stem energy alone cannot establish vocals" (melodic EP/guitar/synth often bleeds into htdemucs vocals).
            # Require corroborated syllabic modulation on the vocal stem OR extreme dominance to REJECT; otherwise UNCERTAIN!
            v_mod = 0.0
            if len(vseg) >= demucs_vocal_sr:
                try:
                    vsos = signal.butter(2, [320.0, 3200.0], btype="bandpass", fs=demucs_vocal_sr, output="sos")
                    vbp = signal.sosfilt(vsos, vseg)
                    venv = np.abs(vbp)
                    vdec = max(1, demucs_vocal_sr // 100)
                    venv_ds = venv[::vdec] - np.mean(venv[::vdec])
                    vef, vep = signal.welch(venv_ds, fs=demucs_vocal_sr / vdec, nperseg=min(256, len(venv_ds)))
                    v_mod = float(np.sum(vep[(vef >= 3.0) & (vef <= 8.5)])) / (float(np.sum(vep)) + 1e-18)
                except Exception:
                    pass
            if (v_db > -22.0 and v_ratio > 0.35 and v_mod > 0.22) or (v_db > -26.0 and v_ratio > 0.20 and v_mod > 0.30):
                demucs_flagged.append(
                    {
                        "startSec": round(vst / demucs_vocal_sr, 2),
                        "endSec": round((vst + len(vseg)) / demucs_vocal_sr, 2),
                        "vocalStemRmsDbfs": round(v_db, 2),
                        "vocalToMixRatio": round(v_ratio, 3),
                        "vocalStemSyllabicMod": round(v_mod, 3),
                    }
                )
        if demucs_flagged or flagged_windows:
            return {
                "checked": True,
                "status": "REJECT",
                "suspectedVocal": True,
                "autoApprovedInstrumental": False,
                "method": "demucs_isolated_vocal_stem_screen",
                "windowsChecked": len(v_starts),
                "maxVocalStemRmsDbfs": round(max_v_db, 2),
                "maxVocalToMixRatio": round(max_v_ratio, 3),
                "vocalBandCenterRatio": round(max_center_ratio, 3),
                "syllabicModulationPeak": round(max_mod_score, 3),
                "flaggedWindows": demucs_flagged or flagged_windows,
                "note": f"Demucs 분리 보컬 스템에서 유의미한 보컬/허밍 에너지 감지(최대 {max_v_db:.1f} dBFS) — 무보컬 승인 거부(REJECT).",
            }
        if max_v_db < -38.0 and max_v_ratio < 0.06:
            return {
                "checked": True,
                "status": "PASS",
                "suspectedVocal": False,
                "autoApprovedInstrumental": True,
                "method": "demucs_isolated_vocal_stem_screen",
                "windowsChecked": len(v_starts),
                "maxVocalStemRmsDbfs": round(max_v_db, 2),
                "maxVocalToMixRatio": round(max_v_ratio, 3),
                "vocalBandCenterRatio": round(max_center_ratio, 3),
                "syllabicModulationPeak": round(max_mod_score, 3),
                "flaggedWindows": [],
                "note": f"Demucs 분리 보컬 스템 전 구간 정숙 확인(최대 {max_v_db:.1f} dBFS, 비율 {max_v_ratio:.3f}) — 무보컬 통과(PASS).",
            }
        return {
            "checked": True,
            "status": "UNCERTAIN",
            "suspectedVocal": False,
            "autoApprovedInstrumental": False,
            "method": "demucs_isolated_vocal_stem_screen",
            "windowsChecked": len(v_starts),
            "maxVocalStemRmsDbfs": round(max_v_db, 2),
            "maxVocalToMixRatio": round(max_v_ratio, 3),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": [],
            "note": f"Demucs 보컬 스템 경계 에너지(최대 {max_v_db:.1f} dBFS, 비율 {max_v_ratio:.3f}) — 수동 청취 확인 필요(UNCERTAIN).",
        }

    if flagged_windows:
        return {
            "checked": True,
            "status": "REJECT",
            "suspectedVocal": True,
            "autoApprovedInstrumental": False,
            "method": "dsp_formant_modulation_screen",
            "windowsChecked": len(starts),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": flagged_windows,
            "note": f"보컬 대역 집중 및 음절 변조 의심 구간 {len(flagged_windows)}개 감지 — 무보컬 자동 승인 거부(REJECT).",
        }

    # Honest anti-fabrication: DSP alone WITHOUT running Demucs vocal isolation NEVER auto-approves neural audio!
    return {
        "checked": True,
        "status": "UNCERTAIN",
        "suspectedVocal": False,
        "autoApprovedInstrumental": False,
        "method": "dsp_only_without_demucs_run",
        "windowsChecked": len(starts),
        "vocalBandCenterRatio": round(max_center_ratio, 3),
        "syllabicModulationPeak": round(max_mod_score, 3),
        "flaggedWindows": [],
        "note": "DSP 1차 검사에서 명백한 보컬은 미감지이나, Demucs 보컬 스템 분리가 미실행되어 UNCERTAIN(수동 청취 확인 필요)으로 분류합니다.",
    }


def run_yue2_generation(
    plan: CompositionPlan,
    out_wav: Path,
    *,
    seed: int = 42,
    cot: str = "melody",
    abc_score: str | None = None,
    cfg_scale: float | None = 2.4,
    semantic_temperature: float | None = 0.80,
    source_tokens: tuple[str, float] | None = None,
    semantic_tokens: str | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: float = 480.0,
    use_demucs_vocal_qa: bool = False,
) -> dict[str, Any]:
    """Execute real native YuE2 (`compile_score.py` resting-voice ABC + `yue-synth` Metal + `--tokens` + Demucs vocal QA)."""
    info = probe_yue2()
    if not info["available"]:
        raise RuntimeError(info["statusNoteEn"])

    synth_bin = Path(info["binaryPath"])
    backbone = Path(info["modelPath"])
    vae = Path(info["vaePath"])
    plan_bin = Path(info["plannerBinaryPath"]) if info.get("plannerBinaryPath") else None

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    req_payload = build_yue2_request_from_plan(
        plan,
        seed=seed,
        cot=cot,
        abc_score=abc_score,
        cfg_scale=cfg_scale,
        semantic_temperature=semantic_temperature,
        source_tokens=source_tokens,
        semantic_tokens=semantic_tokens,
        auto_compile_instrumental_abc=True,
    )
    score_source = str(req_payload.pop("_metaAbcSource", "user_abc" if abc_score else "model_inline"))

    # If still no ABC score and planner exists in instrumental mode, run preflight yue-plan gate
    instrumental = bool(plan.musicalIdentity.get("instrumentalOnly", True))
    if instrumental and "abc" not in req_payload and plan_bin and plan_bin.is_file() and req_payload["cot"] != "off":
        planner_req_path = out_wav.parent / "planner-request.json"
        planner_req_path.write_text(json.dumps(req_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        planned_abc_path = out_wav.parent / "planned.abc"
        run_cancellable_guarded(
            [
                str(plan_bin),
                "--model",
                str(backbone),
                "--request",
                str(planner_req_path),
                "--max-seq",
                "8192",
                "--out",
                str(planned_abc_path),
            ],
            out_wav.parent / "planner.log",
            cancel_event=cancel_event,
            timeout_sec=180.0,
        )
        planned_text = planned_abc_path.read_text(encoding="utf-8")
        ok, issues = check_resting_voice(planned_text)
        if not ok:
            raise ValueError(f"YuE2 native preflight ABC rejected (vocal notes detected): {'; '.join(issues)}")
        req_payload["abc"] = planned_text
        score_source = "native_preflight_verified"

    req_path = out_wav.parent / "request.json"
    req_path.write_text(json.dumps(req_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    plan_out_path = out_wav.parent / "plan.abc"
    tokens_out_path = out_wav.parent / "semantic_tokens.csv"

    cmd = [
        str(synth_bin),
        "--model",
        str(backbone),
        "--vae",
        str(vae),
        "--request",
        str(req_path),
        "--max-seq",
        "8192",
        "--out",
        str(out_wav),
        "--score",
        str(plan_out_path),
        "--tokens",
        str(tokens_out_path),
    ]
    run_meta = run_cancellable_guarded(
        cmd,
        out_wav.parent / "yue2.log",
        cancel_event=cancel_event,
        timeout_sec=timeout_sec,
    )
    if not out_wav.is_file():
        record_engine_verification("yue2-native", False, error="yue-synth finished without producing output WAV")
        raise RuntimeError("YuE2 binary finished without creating output WAV")

    audio, sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
    dur_sec = round(len(audio) / max(1, sr), 3)
    # Run genuine Demucs isolated vocal stem QA on short clips when requested & available
    should_run_demucs_qa = bool(use_demucs_vocal_qa and instrumental and dur_sec <= 45.0)
    vocal_check = screen_vocal_leakage(
        audio,
        sr,
        source_kind="neural_audio",
        audio_path=out_wav,
        use_demucs=should_run_demucs_qa,
    )
    record_engine_verification(
        "yue2-native",
        True,
        wav_path=str(out_wav),
        details={
            "durationSec": dur_sec,
            "peakRssGiB": run_meta["peakRssGiB"],
            "scoreSource": score_source,
            "vocalScreeningStatus": vocal_check.get("status"),
        },
    )
    return {
        "engine": "yue2-native",
        "modelVersion": str(info.get("modelVersion") or "YuE2-3B-Q8_0 + YuE2-Vae-F32"),
        "wavPath": str(out_wav),
        "sampleRate": sr,
        "durationSec": dur_sec,
        "scoreSource": score_source,
        "planAbcPath": str(plan_out_path) if plan_out_path.is_file() else None,
        "semanticTokensPath": str(tokens_out_path) if tokens_out_path.is_file() else None,
        "vocalScreening": vocal_check,
        "request": req_payload,
        "runMeta": run_meta,
    }
