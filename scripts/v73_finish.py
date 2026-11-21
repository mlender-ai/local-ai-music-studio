"""Automate one band withdrawal and recovery over the intact native stereo take."""

import argparse
import json
import math
import shutil
from itertools import pairwise
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from evaluation.house_hook import band, db
from scripts.v71_strict import digest


def add_reverse_guitar(
    take, audio, rate, source_time, placement, length, *, interlude=None
):
    report = json.loads((take / "motif-qa.json").read_text())
    diagnostics = take / "diagnostics"
    source_sha = digest(take / "original.wav")
    if (
        report["original_sha256"] != source_sha
        or (diagnostics / "source.sha256").read_text().strip() != source_sha
        or (interlude is None and not report["arrangement"].get("interlude_supported"))
    ):
        raise ValueError(
            "The guitar treatment needs a measured interlude in this source"
        )
    interlude = report["arrangement"]["interlude"] if interlude is None else interlude
    if not (
        interlude["start_seconds"] <= placement
        and placement + length <= interlude["end_seconds"]
        and 0.6 <= length <= 1.8
        and 0 <= source_time < interlude["start_seconds"]
    ):
        raise ValueError(
            "Place a short earlier guitar excerpt entirely within the interlude"
        )

    stem = diagnostics / "htdemucs_6s/guitar.wav"
    with sf.SoundFile(stem) as reader:
        source_rate = reader.samplerate
        reader.seek(round(source_time * source_rate))
        clip = reader.read(round(length * source_rate), always_2d=True)
    divisor = math.gcd(rate, source_rate)
    effect = band(clip[::-1], source_rate, 240, 6200)
    effect = resample_poly(effect, rate // divisor, source_rate // divisor, axis=0)
    start = round(placement * rate)
    bed = audio[start : start + len(effect)]
    if bed.shape != effect.shape:
        raise ValueError("The guitar edit would leave the rendered stereo timeline")
    edge = round(rate * 0.08)
    fade = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, edge))
    effect[:edge] *= fade[:, None]
    effect[-edge:] *= fade[::-1, None]
    effect_rms = np.sqrt(np.mean(effect**2))
    if effect_rms <= 0.001:
        raise ValueError("The source excerpt lacks an audible guitar track")
    relative_db = -12.5
    effect *= np.sqrt(np.mean(bed**2)) * 10 ** (relative_db / 20) / effect_rms
    output = audio.copy()
    output[start : start + len(effect)] += effect
    return output, {
        "effects": [
            {
                "type": "reverse_guitar_swell",
                "source": "Original's Demucs guitar estimate",
                "source_sha256": digest(stem),
                "source_start_seconds": source_time,
                "placement_seconds": placement,
                "duration_seconds": len(effect) / rate,
                "bandpass_hz": [240, 6200],
                "edge_fade_ms": 80,
                "effect_rms_dbfs_before_master_gain": db(np.sqrt(np.mean(effect**2))),
                "effect_to_local_mix_rms_db": relative_db,
                "frames_in_edit": len(effect),
            }
        ]
    }


def apply_gain_lane(audio, stem, rate, points):
    edges = [round(seconds * rate) for seconds, _ in points]
    if (
        len(edges) < 2
        or not 0 <= edges[0] < edges[-1] <= len(audio)
        or not all(a < b for a, b in pairwise(edges))
        or not all(0 <= level <= 1 for _, level in points)
        or points[0][1] != 1
        or points[-1][1] != 1
    ):
        raise ValueError("Use bounded, ordered attenuation with neutral edges")
    track, source_rate = sf.read(stem, dtype="float32", always_2d=True)
    divisor = math.gcd(rate, source_rate)
    track = resample_poly(track, rate // divisor, source_rate // divisor, axis=0)
    if abs(len(track) - len(audio)) > 4 or track.shape[1] != audio.shape[1]:
        raise ValueError("Automation needs aligned native separation estimates")
    if len(track) < len(audio):
        track = np.pad(track, ((0, len(audio) - len(track)), (0, 0)))
    for (start, end), ((_, a), (_, b)) in zip(pairwise(edges), pairwise(points)):
        position = np.arange(end - start) / (end - start)
        gain = a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * position))
        audio[start:end] += (gain - 1)[:, None] * track[start:end]


def produce_mix(take, out, plan):
    raw = take / "original.wav"
    receipt = json.loads((take / "vocal-leakage.json").read_text())
    source_sha = digest(raw)
    if receipt["status"] != "PASS" or receipt["wav_sha256"] != source_sha:
        raise ValueError("Production requires a full vocal-screened original")
    assessment = json.loads((take / "strict-result.json").read_text())
    if assessment["phase"] != "full" or not all(
        assessment["technical_checks"][field]
        for field in ("duration", "tempo", "impulse_screen")
    ):
        raise ValueError(
            "The native take lacks verified audio, timing or transient integrity"
        )
    analysis = json.loads((take / "motif-qa.json").read_text())
    if not all(analysis["motif_return"].values()):
        raise ValueError("Use a take with the genuine motif both early and late")
    stems = take / "diagnostics/htdemucs_6s"
    if (stems.parent / "source.sha256").read_text().strip() != source_sha:
        raise ValueError("Production stems do not match the original")
    audio, rate = sf.read(raw, always_2d=True)
    for name in ("drums", "bass"):
        apply_gain_lane(
            audio, stems / f"{name}.wav", rate, plan["gain_automation"][name]
        )
    reverse = plan["reverse_guitar"]
    audio, details = add_reverse_guitar(
        take,
        audio,
        rate,
        reverse["source_start_seconds"],
        reverse["placement_seconds"],
        reverse["duration_seconds"],
        interlude=plan["interlude"],
    )
    out.mkdir(parents=True)
    sf.write(out / "original.wav", audio, rate, subtype="FLOAT")
    for name in ("request.json", "plan.abc", "experiment.json", "worker.log"):
        shutil.copyfile(take / name, out / name)
    manifest = {
        "native_sha256": source_sha,
        "produced_sha256": digest(out / "original.wav"),
        "frames": len(audio),
        "gain_automation": plan["gain_automation"],
        **details,
    }
    (out / "production.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return out


def verify_mix(folder, composition):
    from evaluation.indie_motif import inspect_take
    from evaluation.vocal_leakage import review
    from scripts.v71_strict import assess_music

    voice = review(folder)
    result = {
        "phase": "full",
        "vocal_status": voice["status"],
        "source": "produced native stereo with intact timeline",
        "selection": "not_evaluated",
    }
    if voice["status"] == "PASS":
        result.update(assess_music(folder, "indie-experimental-rock", (60, 110)))
    (folder / "strict-result.json").write_text(json.dumps(result, indent=2) + "\n")
    if voice["status"] == "PASS":
        inspect_take(folder, composition)
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("take", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("plan", type=Path)
    cli.add_argument(
        "--composition",
        type=Path,
        help="Screen the produced mix against this score plan",
    )
    args = cli.parse_args()
    out = produce_mix(args.take, args.output, json.loads(args.plan.read_text()))
    if args.composition:
        report = verify_mix(out, json.loads(args.composition.read_text()))
        print(out, report["vocal_status"], report["selection"])
    else:
        print(out)
