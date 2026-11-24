"""Honest musical & technical validation for generated MIDI parts (Phase 03-C/F)."""

from __future__ import annotations

from typing import Any

from .midi_composer import parse_key_root_and_scale

ROLE_PITCH_BOUNDS: dict[str, tuple[int, int]] = {
    "drums": (35, 59),
    "bass": (28, 57),
    "keys": (45, 81),
    "guitar": (48, 84),
    "synth_hook": (55, 92),
    "pad": (45, 84),
}


def validate_midi_composition(
    notes: list[dict[str, Any]],
    key_str: str,
    scale_name: str,
    role: str,
    bar_count: int,
    bpb: float = 4.0,
) -> dict[str, Any]:
    """Validate pitch register, key/scale conformity, grid density, and bar-to-bar variation."""
    if not notes:
        return {
            "role": role,
            "noteCount": 0,
            "passed": False,
            "warnings": [f"No MIDI notes generated for role '{role}'."],
        }

    pitches = [int(n["pitch"]) for n in notes]
    vels = [int(n.get("velocity", 100)) for n in notes]
    lo_bound, hi_bound = ROLE_PITCH_BOUNDS.get(role, (24, 108))
    in_bounds = sum(1 for p in pitches if lo_bound <= p <= hi_bound) / len(pitches)

    root_pc, scale_ints = parse_key_root_and_scale(key_str, scale_name)
    scale_pcs = {(root_pc + iv) % 12 for iv in scale_ints}
    if role == "drums":
        scale_fit = 1.0
    else:
        scale_fit = sum(1 for p in pitches if (p % 12) in scale_pcs) / len(pitches)

    # Bar-to-bar variation check (anti-monotony)
    bar_sigs: list[tuple[tuple[int, float], ...]] = []
    for bar in range(max(1, bar_count)):
        b0, b1 = bar * bpb, (bar + 1) * bpb
        sig = tuple(
            sorted(
                (int(n["pitch"]), round(float(n["startBeat"]) - b0, 2))
                for n in notes
                if b0 <= float(n["startBeat"]) < b1
            )
        )
        if sig:
            bar_sigs.append(sig)
    unique_bars = len(set(bar_sigs))
    variation_ratio = round(unique_bars / max(1, len(bar_sigs)), 3)

    warnings: list[str] = []
    if in_bounds < 0.9:
        warnings.append(f"Role '{role}' has {round((1 - in_bounds) * 100)}% notes outside typical register ({lo_bound}–{hi_bound}).")
    if role != "drums" and scale_fit < 0.72:
        warnings.append(f"Role '{role}' scale conformity is {round(scale_fit * 100)}% in {key_str}.")
    if bar_count >= 4 and len(bar_sigs) >= 4 and unique_bars == 1 and role != "pad":
        warnings.append(f"Role '{role}' repeats an identical 1-bar pattern without variation.")

    return {
        "role": role,
        "noteCount": len(notes),
        "pitchMin": min(pitches),
        "pitchMax": max(pitches),
        "registerFitRatio": round(in_bounds, 3),
        "scaleConformityRatio": round(scale_fit, 3),
        "velocityRange": [min(vels), max(vels)],
        "uniqueBarPatterns": unique_bars,
        "activeBars": len(bar_sigs),
        "variationRatio": variation_ratio,
        "passed": len(warnings) == 0,
        "warnings": warnings,
    }
