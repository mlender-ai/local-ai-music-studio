"""Measure V7.1 originals and optional separation diagnostics without editing audio."""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from engine.rendering.rhythm import _candidates, estimate_pcm_rhythm
from scripts.v4_evaluate import waveform
from scripts.v7_native import ScoreRejected, check_resting_voice


def rms_db(audio):
    return float(10 * np.log10(max(1e-15, np.mean(audio**2))))


def drum_pulses(drums, sr):
    """Describe estimated kit periodicity and the kick-band support on its own beat grid."""
    _, time, spectrum = signal.stft(
        drums.mean(axis=1), fs=sr, nperseg=sr // 25, noverlap=3 * sr // 100
    )
    frequencies = np.fft.rfftfreq(sr // 25, 1 / sr)
    kick_energy = (
        np.abs(spectrum[(frequencies >= 30) & (frequencies <= 125)]) ** 2
    ).sum(axis=0)
    attack = np.maximum(np.diff(kick_energy, prepend=0), 0)
    candidates = _candidates(attack)
    burst = signal.find_peaks(
        attack, distance=10, prominence=np.percentile(attack, 95) * 0.35
    )[0]
    grids = []
    for candidate in candidates:
        if candidate["strength"] < 0.12 or not len(burst):
            continue
        period = 60 / candidate["bpm"]
        phase = np.angle(np.sum(attack * np.exp(2j * np.pi * time / period)))
        start = (phase * period / (2 * np.pi)) % period
        beats = np.arange(start + period, time[-1] - period, period)
        if not len(beats):
            continue
        indices = np.rint(beats * 100).astype(int)
        kick_near = np.min(abs(indices[:, None] - burst), axis=1) <= 5
        groups = kick_near[: len(beats) // 4 * 4].reshape(-1, 4)
        grids.append(
            {
                "bpm": candidate["bpm"],
                "beat_count": len(beats),
                "beat_fraction_with_kick_band_attack_within_50ms": float(
                    kick_near.mean()
                ),
                "four_beat_groups": len(groups),
                "four_beat_groups_with_attack_at_every_beat": int(
                    groups.all(axis=1).sum()
                ),
            }
        )
    return {"kick_periods": candidates, "grids": grids}


def inspect(folder):
    record = json.loads((folder / "experiment.json").read_text())
    planned = folder / "plan.abc"
    if not planned.exists():
        planned = folder / "planned.abc"
    abc = planned.read_text(encoding="utf-8")
    tempo = re.search(r"(?m)^Q:1/4\s*=\s*(\d+)", abc)
    try:
        check_resting_voice(abc)
        score_screen = "resting_vocal_lane"
    except ScoreRejected as exc:
        score_screen = str(exc)
    output = {
        "attempt": record,
        "score_bpm": int(tempo[1]) if tempo else None,
        "score_screen": score_screen,
    }
    if record["status"] != "rendered":
        return output
    original = folder / record["original"]
    audio, sr = sf.read(original, always_2d=True, dtype="float32")
    output["waveform"] = waveform(original, record["brief"])
    log = (folder / "worker.log").read_text()
    output["ending"] = {
        "semantic_eos": "Semantic song 0: end token" in log,
        "one_second_rms_dbfs": rms_db(audio[-sr:]),
    }
    for model in ("htdemucs", "htdemucs_6s"):
        stems = folder / "diagnostics" / model
        if not stems.exists():
            continue
        voice, voice_rate = sf.read(stems / "vocals.wav", dtype="float32")
        track, rate = sf.read(stems / "drums.wav", always_2d=True, dtype="float32")
        output[model] = {
            "vocal_minus_mix_rms_db": rms_db(voice) - rms_db(audio),
            "vocal_windows": [
                {
                    "start": at,
                    "vocal_dbfs": rms_db(
                        voice[at * voice_rate : (at + 2) * voice_rate]
                    ),
                    "mix_dbfs": rms_db(audio[at * sr : (at + 2) * sr]),
                }
                for at in range(0, int(len(audio) / sr), 2)
            ],
            "drum_rhythm": estimate_pcm_rhythm(track, rate, record["brief"]["bpm"]),
            "drum_kick": drum_pulses(track, rate),
        }
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("take", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.take), ensure_ascii=False, indent=2))
