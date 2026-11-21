"""Find evidence of one scored hook and of changes in the rendered rhythm section."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

from scripts.v71_strict import digest

FRAME_SECONDS = 0.01
PITCHES = np.arange(53, 93)


def pitch_classes(audio, sample_rate):
    target_rate = 16000
    divisor = math.gcd(sample_rate, target_rate)
    audio = signal.resample_poly(audio, target_rate // divisor, sample_rate // divisor)
    frequencies, _, spectra = signal.stft(
        audio,
        fs=target_rate,
        nperseg=2048,
        noverlap=2048 - round(FRAME_SECONDS * target_rate),
        nfft=8192,
    )
    magnitude = abs(spectra)
    background = ndimage.uniform_filter1d(magnitude, 19, axis=0)
    relative = np.maximum(0, np.log1p(magnitude / np.maximum(background, 1e-7)) - 0.65)
    relative *= np.minimum(1, magnitude / max(float(np.max(magnitude)) * 0.025, 1e-7))
    hz = 440 * 2 ** ((PITCHES - 69) / 12)
    fundamental, octave, octave_fifth = (
        relative[np.rint(hz * harmonic / frequencies[1]).astype(int)]
        for harmonic in (1, 2, 3)
    )
    strength = fundamental * (0.65 + 0.22 * octave + 0.13 * octave_fifth)
    chroma = np.stack([strength[PITCHES % 12 == k].max(axis=0) for k in range(12)])
    return chroma / np.maximum(chroma.max(axis=0), 0.18)


def hook_matches(chroma, phrase, beat_seconds):
    """Scan time offsets; compare note strength against reversed and shifted pitches."""
    ticks = beat_seconds / 8
    events = [
        (32 * bar + start, length, midi % 12)
        for bar, notes in enumerate(phrase)
        for start, length, midi in notes
    ]
    offsets = [
        round((start + min(length * 0.40, 2)) * ticks / FRAME_SECONDS)
        for start, length, _ in events
    ]
    usable = chroma.shape[1] - round(len(phrase) * 4 * beat_seconds / FRAME_SECONDS)
    if usable <= 0:
        return []
    centered = ndimage.maximum_filter1d(chroma, size=11, axis=1)
    slices = np.stack([centered[:, start : start + usable] for start in offsets])
    pitches = np.array([pitch for _, _, pitch in events])
    positions = np.arange(len(pitches))
    notes = slices[positions, pitches]
    absolute = notes.mean(axis=0)
    alternate = np.stack(
        [
            slices[positions, (pitches + shift) % 12].mean(axis=0)
            for shift in range(1, 12)
        ]
    )
    scrambled = slices[positions, pitches[::-1]].mean(axis=0)
    contrast = absolute - np.maximum(alternate.max(axis=0), scrambled)
    rank = (slices > notes[:, None, :] + 1e-8).sum(axis=1)
    evidence = absolute + np.maximum(0, contrast)
    peaks, _ = signal.find_peaks(np.r_[-1.0, evidence, -1.0], distance=125)
    return [
        {
            "start_seconds": round(at * FRAME_SECONDS, 3),
            "note_strength": round(float(absolute[at]), 3),
            "above_decoy": round(float(contrast[at]), 3),
            "notes_in_top_three": int(
                ((rank[:, at] < 3) & (notes[:, at] >= 0.25)).sum()
            ),
            "notes_total": len(pitches),
            "supported": bool(
                absolute[at] >= 0.61
                and contrast[at] >= 0.08
                and ((rank[:, at] < 3) & (notes[:, at] >= 0.25)).sum()
                >= math.ceil(len(pitches) * 0.75)
            ),
        }
        for at in peaks - 1
    ]


def band(audio, sample_rate, low, high):
    return signal.sosfilt(
        signal.butter(3, (low, high), fs=sample_rate, btype="band", output="sos"),
        audio,
        axis=0,
    )


def db(rms):
    return round(float(20 * np.log10(max(1e-6, rms))), 2)


def section_analysis(drums, bass, synth, qa_rate, beat_seconds):
    kick = band(drums, qa_rate, 32, 125)
    sub = band(bass, qa_rate, 35, 160)
    high = band(drums, qa_rate, 3300, 9000)
    channels = [
        kick,
        sub,
        high,
        synth,
        synth[:, 0] - synth[:, 1],
        synth[:, 0] + synth[:, 1],
    ]
    tick = round(qa_rate * FRAME_SECONDS)
    frames = len(kick) // tick
    power = np.array(
        [
            np.mean(track[: frames * tick].reshape(frames, tick, -1) ** 2, axis=(1, 2))
            for track in channels
        ]
    )
    kick_attack = np.maximum(0, np.diff(power[0] ** 0.5, prepend=0))
    active_kicks, _ = signal.find_peaks(
        kick_attack, distance=14, prominence=float(np.percentile(kick_attack, 97)) * 0.4
    )
    attack_times = active_kicks * FRAME_SECONDS
    if len(active_kicks) < 8:
        return {"drop_supported": False, "reason": "insufficient kick events"}
    period_frames = beat_seconds / FRAME_SECONDS
    phase = np.angle(
        np.sum(kick_attack * np.exp(2j * np.pi * np.arange(frames) / period_frames))
    )
    offset = (phase * beat_seconds / (2 * np.pi)) % beat_seconds
    beats = np.arange(offset, frames * FRAME_SECONDS, beat_seconds)
    near = np.min(abs(beats[:, None] - attack_times), axis=1) <= 0.065
    sums = np.c_[np.zeros(len(channels)), np.cumsum(power, axis=1, dtype=np.float64)]

    def summary(start, end):
        lo, hi = np.rint(np.asarray([start, end]) / FRAME_SECONDS).astype(int)
        mask = (beats >= start) & (beats < end)
        means = np.maximum(0, (sums[:, hi] - sums[:, lo]) / (hi - lo))
        return {
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "kick_rms_dbfs": db(np.sqrt(means[0])),
            "bass_rms_dbfs": db(np.sqrt(means[1])),
            "high_percussion_rms_dbfs": db(np.sqrt(means[2])),
            "synth_estimate_rms_dbfs": db(np.sqrt(means[3])),
            "synth_side_mid_db": db(np.sqrt(means[4] / max(1e-12, means[5]))),
            "kick_beat_coverage": round(float(near[mask].mean()), 3)
            if mask.any()
            else 0,
        }

    bar = 4 * beat_seconds
    duration = frames * FRAME_SECONDS
    opportunities = []
    for at in np.arange(0.47 * duration, duration - 3.5 * bar, beat_seconds):
        for build_bars in (1, 2, 3, 4):
            break_end = at - build_bars * bar
            if break_end < 7 * bar:
                continue
            before = summary(break_end - 3 * bar, break_end)
            build = summary(break_end, at)
            drop = summary(at, at + 3.5 * bar)
            kick_gain = drop["kick_rms_dbfs"] - before["kick_rms_dbfs"]
            bass_gain = drop["bass_rms_dbfs"] - before["bass_rms_dbfs"]
            contrast = drop["kick_beat_coverage"] - before["kick_beat_coverage"]
            score = min(kick_gain, 25) + min(bass_gain, 20) + contrast * 20
            opportunities.append(
                (score, before, build, drop, kick_gain, bass_gain, contrast)
            )
    if not opportunities:
        return {
            "drop_supported": False,
            "reason": "audio too short for a late-drop comparison",
        }
    _, before, build, drop, kick_gain, bass_gain, contrast = max(
        opportunities, key=lambda row: row[0]
    )
    lo, hi = [
        round(drop[key] / FRAME_SECONDS) for key in ("start_seconds", "end_seconds")
    ]
    simultaneous = np.corrcoef(np.sqrt(power[0:2, lo:hi]))[0, 1]
    return {
        "intro": summary(0, bar),
        "early_groove": summary(4 * bar, 8 * bar),
        "breakdown_estimate": before,
        "build_estimate": build,
        "drop_estimate": drop,
        "outro": summary(duration - 2 * bar, duration),
        "break_to_drop_kick_db": round(kick_gain, 2),
        "break_to_drop_bass_db": round(bass_gain, 2),
        "build_percussion_vs_break_db": round(
            build["high_percussion_rms_dbfs"] - before["high_percussion_rms_dbfs"], 2
        ),
        "drop_percussion_vs_build_db": round(
            drop["high_percussion_rms_dbfs"] - build["high_percussion_rms_dbfs"], 2
        ),
        "drop_kick_bass_envelope_correlation": round(float(simultaneous), 3)
        if np.isfinite(simultaneous)
        else None,
        "drop_supported": bool(
            kick_gain >= 6
            and bass_gain >= 4
            and contrast >= 0.35
            and drop["kick_beat_coverage"] >= 0.70
        ),
    }


def inspect_hook(take, plan, *, reference=False):
    source = take / "original.wav"
    voice = json.loads((take / "vocal-leakage.json").read_text())
    source_sha = digest(source)
    if voice["status"] != "PASS" or source_sha != voice["wav_sha256"]:
        raise ValueError("Listening analysis requires the exact vocal-screened source")
    diagnostics = take / "diagnostics"
    if (diagnostics / "source.sha256").read_text().strip() != source_sha:
        raise ValueError("Analysis stems do not match the original")
    stems = diagnostics / "htdemucs_6s"
    other, rate = sf.read(stems / "other.wav", dtype="float32", always_2d=True)
    chroma = pitch_classes(other.mean(axis=1), rate)
    strict = take / "strict-result.json"
    tempo = (
        json.loads(strict.read_text()).get("tempo_evidence", {})
        if strict.is_file()
        else {}
    )
    measured_kick = tempo.get("drum_target")
    bpm = measured_kick["bpm"] if measured_kick else plan["bpm"]
    beat = 60 / bpm
    summary = {}
    for label in ("A", "A_prime", "B", "final", "fragment"):
        candidates = hook_matches(chroma, plan["hook"][label], beat)
        best = sorted(
            candidates,
            key=lambda hit: (
                hit["supported"],
                hit["note_strength"] + max(0, hit["above_decoy"]),
            ),
            reverse=True,
        )
        summary[label] = {
            "supported": [hit for hit in candidates if hit["supported"]],
            "best": best[:4],
        }
    evidence = {
        "original_sha256": source_sha,
        "melody_matches": summary,
        "analysis_grid_bpm": bpm,
        "scope": "Pitch-class motif screening of a separated accompaniment estimate; octave and perception unchecked.",
    }
    if len(other) / rate > 40:
        drums, drum_rate = sf.read(stems / "drums.wav", dtype="float32", always_2d=True)
        bass, bass_rate = sf.read(stems / "bass.wav", dtype="float32", always_2d=True)
        if (
            rate != drum_rate
            or rate != bass_rate
            or len(drums) != len(other)
            or len(bass) != len(other)
        ):
            raise ValueError(
                "Arrangement analysis needs time-aligned separation estimates"
            )
        arrangement = section_analysis(drums, bass, other, rate, beat)
        evidence["arrangement"] = arrangement
        if "drop_estimate" in arrangement:
            drop_start = arrangement["drop_estimate"]["start_seconds"]
            break_start = arrangement["breakdown_estimate"]["start_seconds"]
            bar = 4 * beat
            starts = [entry["start_seconds"] for entry in summary["A"]["supported"]]
            evidence["hook_return"] = {
                "early_A_seconds": [at for at in starts if at + 2 * bar <= break_start],
                "breakdown_A_seconds": [
                    at
                    for at in starts
                    if break_start
                    <= at
                    < arrangement["breakdown_estimate"]["end_seconds"]
                ],
                "drop_A_seconds": [
                    at
                    for at in starts
                    if drop_start - beat <= at < drop_start + 8 * bar
                ],
                "breakdown_fragment_seconds": [
                    hit["start_seconds"]
                    for hit in summary["fragment"]["supported"]
                    if break_start
                    <= hit["start_seconds"]
                    < arrangement["breakdown_estimate"]["end_seconds"]
                ],
            }
    if not reference:
        (take / "hook-qa.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("take", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--reference", action="store_true")
    args = parser.parse_args()
    result = inspect_hook(
        args.take, json.loads(args.plan.read_text()), reference=args.reference
    )
    print(json.dumps(result, indent=2))
