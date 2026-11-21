"""Check a rendered instrumental rock take for the guitar motif and band changes."""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from evaluation.house_hook import band, db, hook_matches, pitch_classes
from scripts.v71_strict import digest


def melody_evidence(audio, rate, plan, bpm):
    chroma = pitch_classes(audio.mean(axis=1), rate)
    evidence = {}
    for name in ("A", "A_prime", "B", "final", "fragment"):
        hits = hook_matches(chroma, plan["hook"][name], 60 / bpm)
        # Compare each candidate with pitch-transposed and reversed controls.
        strongest = sorted(
            hits,
            key=lambda hit: (
                hit["supported"],
                hit["note_strength"] + hit["above_decoy"],
            ),
            reverse=True,
        )
        evidence[name] = {
            "supported": [hit for hit in hits if hit["supported"]],
            "best": strongest[:4],
        }
    return evidence


def band_sections(stems, rate, seconds_per_bar):
    """Describe two-bar rolling windows. Locations are inferred from sound."""
    span = 2 * seconds_per_bar
    length = len(stems["drums"]) / rate
    cymbals = band(stems["drums"], rate, 3400, 9500)
    mid = band(stems["guitar"], rate, 240, 2300)
    width = stems["guitar"][:, 0] - stems["guitar"][:, 1]
    sources = {**stems, "cymbals": cymbals, "guitar_mid": mid, "guitar_side": width}
    rows = []
    for at in np.arange(0, length - span + 0.01, seconds_per_bar):
        start, end = round(at * rate), round((at + span) * rate)
        rows.append(
            {
                "start_seconds": round(float(at), 3),
                "end_seconds": round(float(at + span), 3),
                **{
                    f"{name}_dbfs": db(np.sqrt(np.mean(audio[start:end] ** 2)))
                    for name, audio in sources.items()
                },
            }
        )
    if length < 40:
        return {"two_bar_windows": rows}
    mid_lulls = [
        row
        for row in rows
        if 0.30 * length <= row["start_seconds"] < 0.66 * length
        and row["guitar_dbfs"] > -48
    ]
    if not mid_lulls:
        return {"two_bar_windows": rows, "interlude_supported": False}
    lull = min(mid_lulls, key=lambda row: row["drums_dbfs"] - row["guitar_dbfs"])
    before = [
        row
        for row in rows
        if 4 <= row["start_seconds"] and row["end_seconds"] <= lull["start_seconds"]
    ]
    after = [
        row
        for row in rows
        if row["start_seconds"] >= lull["end_seconds"]
        and row["end_seconds"] <= length - seconds_per_bar
    ]
    if not before or not after:
        return {"two_bar_windows": rows, "interlude_supported": False}
    active = max(before, key=lambda row: row["drums_dbfs"] + row["bass_dbfs"])
    climax = max(
        after,
        key=lambda row: (
            row["drums_dbfs"] + row["cymbals_dbfs"] + row["guitar_mid_dbfs"]
        ),
    )
    build = [row for row in after if row["start_seconds"] < climax["start_seconds"]]
    return {
        "two_bar_windows": rows,
        "opening": rows[0],
        "early_band": active,
        "interlude": lull,
        "build": build,
        "climax": climax,
        "interlude_supported": bool(active["drums_dbfs"] - lull["drums_dbfs"] >= 6),
        "climax_drums_vs_interlude_db": round(
            climax["drums_dbfs"] - lull["drums_dbfs"], 2
        ),
        "climax_cymbals_vs_early_db": round(
            climax["cymbals_dbfs"] - active["cymbals_dbfs"], 2
        ),
    }


def inspect_take(take, plan):
    original = take / "original.wav"
    receipt = json.loads((take / "vocal-leakage.json").read_text())
    source_sha = digest(original)
    diagnostics = take / "diagnostics"
    if (
        receipt["status"] != "PASS"
        or receipt["wav_sha256"] != source_sha
        or (diagnostics / "source.sha256").read_text().strip() != source_sha
    ):
        raise ValueError("Motif analysis requires the exact vocal-screened original")
    stems = {}
    root = diagnostics / "htdemucs_6s"
    rates = set()
    for stem in ("guitar", "other", "drums", "bass"):
        data, rate = sf.read(root / f"{stem}.wav", dtype="float32", always_2d=True)
        rates.add(rate)
        stems[stem] = data
    if (
        len(rates) != 1
        or len({data.shape for data in stems.values()}) != 1
        or data.shape[1] != 2
    ):
        raise ValueError("Band analysis requires aligned stereo separation estimates")
    strict = json.loads((take / "strict-result.json").read_text())
    evidence = strict.get("tempo_evidence", {})
    tempo = (
        evidence.get("drum_target")
        or evidence.get("common_period")
        or evidence.get("mix_target")
        or {}
    )
    bpm = tempo.get("bpm", plan["bpm"])
    matrices = {
        "guitar_estimate": melody_evidence(stems["guitar"], rate, plan, bpm),
        "guitar_plus_other": melody_evidence(
            stems["guitar"] + stems["other"], rate, plan, bpm
        ),
    }
    arrangement = band_sections(stems, rate, 240 / bpm)
    result = {
        "original_sha256": source_sha,
        "analysis_grid_bpm": bpm,
        "melody_matches": matrices,
        "arrangement": arrangement,
        "scope": "Separation estimates and pitch-class matches. Evocative sound, guitar technique and exact octave require listening.",
    }
    if "climax" in arrangement:
        start = arrangement["climax"]["start_seconds"]
        origin = arrangement["interlude"]["start_seconds"]
        repeat = {
            hit["start_seconds"]
            for source in matrices.values()
            for hit in source["A"]["supported"]
        }
        result["motif_return"] = {
            "before_interlude": sorted(at for at in repeat if at + 480 / bpm <= origin),
            "near_climax": sorted(
                at for at in repeat if start - 240 / bpm <= at < start + 960 / bpm
            ),
        }
    (take / "motif-qa.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def require_motif_preflight(take, plan):
    sources = inspect_take(take, plan)["melody_matches"]
    span = 480 / plan["bpm"]
    if not any(
        abs(a["start_seconds"] - b["start_seconds"]) >= span
        for source in sources.values()
        for a in source["A"]["supported"]
        for b in source["A"]["supported"]
        + source["A_prime"]["supported"]
        + source["B"]["supported"]
    ):
        raise ValueError("The preflight needs the guitar motif in two distinct moments")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("take", type=Path)
    cli.add_argument("plan", type=Path)
    args = cli.parse_args()
    print(
        json.dumps(inspect_take(args.take, json.loads(args.plan.read_text())), indent=2)
    )
