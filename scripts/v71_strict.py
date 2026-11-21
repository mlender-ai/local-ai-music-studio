"""Gate long instrumental YuE2 runs on an equivalent short take and screen the full audio."""

import argparse
import hashlib
import json
from pathlib import Path

from engine.paths import DATA, RUNTIME
from evaluation.vocal_leakage import review, score_evidence
from scripts.v4_study import run, yue2_request
from scripts.v71_qa import inspect

GENRES = {"house-techno-128": 128, "highteen-punk-144": 144}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require_preflight(folder, expected):
    request_path = folder / "request.json"
    previous = json.loads(request_path.read_text())
    evidence = json.loads((folder / "vocal-leakage.json").read_text())
    if not 8 <= previous["duration"] <= 30:
        raise ValueError("Use a verified 8–30 second preflight")
    if {**previous, "duration": expected["duration"]} != expected:
        raise ValueError(
            "Full take must reuse the preflight's seed, style, score and settings"
        )
    if (
        evidence["status"] != "PASS"
        or evidence.get("seconds", 0) < 8
        or evidence.get("request_sha256") != digest(request_path)
        or evidence.get("wav_sha256") != digest(folder / "original.wav")
    ):
        raise ValueError("This exact short take needs a passing vocal leakage report")


def assess_music(folder, genre):
    report = {}
    quality = inspect(folder)
    report["technical_music_qa"] = quality
    waveform = quality["waveform"]
    lower, upper = (125, 131) if genre == "house-techno-128" else (140, 148)
    kit = quality["htdemucs_6s"]
    tempo_candidates = kit["drum_rhythm"]["candidates"]
    if genre == "house-techno-128":
        tempo_candidates = kit["drum_kick"]["kick_periods"]
    direct_tempo = next(
        (
            entry
            for entry in tempo_candidates
            if lower <= entry["bpm"] <= upper and entry["strength"] >= 0.15
        ),
        None,
    )
    mix_tempo = next(
        (
            entry
            for entry in waveform["rhythm"]["candidates"]
            if lower <= entry["bpm"] <= upper and entry["strength"] >= 0.15
        ),
        None,
    )
    drum_half_time = next(
        (
            entry
            for entry in tempo_candidates
            if lower <= 2 * entry["bpm"] <= upper and entry["strength"] >= 0.15
        ),
        None,
    )
    half_time = (
        genre == "highteen-punk-144"
        and mix_tempo
        and drum_half_time
        and (abs(mix_tempo["bpm"] - 2 * drum_half_time["bpm"]) <= 2)
    )
    report["tempo_evidence"] = {
        "drum_target": direct_tempo,
        "mix_target": mix_tempo,
        "drum_half_time": drum_half_time,
        "confirmed_half_time_relation": bool(half_time),
    }
    tail_db = waveform["final_100ms_rms_dbfs"]
    quiet_tail = tail_db <= -45 and quality["ending"]["one_second_rms_dbfs"] <= -38
    fading_eos = (
        quality["ending"]["semantic_eos"]
        and tail_db <= waveform["levels"]["rms_dbfs"] - 10
    )
    report["measured_ending_supported"] = quiet_tail or fading_eos
    checks = {
        "duration": 60 <= round(waveform["levels"]["duration_seconds"], 1) <= 90,
        "tempo": bool(direct_tempo or half_time),
        "loop_screen": not waveform["exact_loop_candidates"],
        "impulse_screen": not waveform["isolated_impulse_count"],
    }
    report["technical_checks"] = {**checks, "ending": quiet_tail or fading_eos}
    report["selection"] = (
        "technical_review_ready"
        if all(report["technical_checks"].values())
        else "outro_review_required"
        if all(checks.values())
        else "music_criteria_unmet"
    )
    return report


def produce(
    style,
    score,
    genre,
    seed,
    cap,
    *,
    cot,
    cfg_scale,
    preflight,
    semantic_temperature=None,
):
    brief = {
        "style": style.strip(),
        "lyrics": "",
        "duration": cap,
        "bpm": GENRES[genre],
        "instrumental": True,
    }
    expected = yue2_request(
        brief,
        seed,
        cot=cot,
        score=score,
        cfg_scale=cfg_scale,
        semantic_temperature=semantic_temperature,
    )
    gate = score_evidence(expected, score, RUNTIME / "v6/instrumental")
    if gate["status"] != "PASS":
        raise ValueError(f"Instrumental score gate: {gate['reason']}")
    if preflight:
        if not 60 <= cap <= 90:
            raise ValueError("Full duration cap must be 60–90 seconds")
        require_preflight(preflight, expected)
    elif not 8 <= cap <= 30:
        raise ValueError("Run an 8–30 second preflight before full generation")
    folder = run(
        "yue2",
        genre,
        seed,
        brief,
        score=score,
        cot=cot,
        cfg_scale=cfg_scale,
        semantic_temperature=semantic_temperature,
        output_root=DATA / "v71-hotfix",
    )
    checks = review(folder)
    report = {
        "phase": "full" if preflight else "preflight",
        "preflight": preflight.name if preflight else None,
        "vocal_status": checks["status"],
        "selection": "not_evaluated",
    }
    if preflight and checks["status"] == "PASS":
        report.update(assess_music(folder, genre))
    (folder / "strict-result.json").write_text(json.dumps(report, indent=2) + "\n")
    return folder, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("genre", choices=GENRES)
    parser.add_argument("style", type=Path)
    parser.add_argument("score", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--duration-cap", type=int, default=24)
    parser.add_argument("--cot", choices=("full", "melody"), default="full")
    parser.add_argument("--cfg-scale", type=float)
    parser.add_argument("--semantic-temperature", type=float)
    parser.add_argument("--preflight", type=Path)
    args = parser.parse_args()
    try:
        folder, verdict = produce(
            args.style.read_text(encoding="utf-8"),
            args.score.read_text(encoding="utf-8"),
            args.genre,
            args.seed,
            args.duration_cap,
            cot=args.cot,
            cfg_scale=args.cfg_scale,
            preflight=args.preflight,
            semantic_temperature=args.semantic_temperature,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(folder, verdict["vocal_status"], verdict["selection"], flush=True)
