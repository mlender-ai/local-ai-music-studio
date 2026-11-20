"""Read-only waveform measurements and optional independent Korean transcription."""

import argparse
import hashlib
import json
import math
import re
from itertools import groupby
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import uniform_filter1d

from engine.daw.qa import levels
from engine.paths import RUNTIME
from engine.rendering.audio import read_audio
from engine.rendering.rhythm import estimate_rhythm


def loop_screen(mono, sr):
    """Search earlier audio for near-identical 2 s waveforms, ignoring overall gain."""
    gcd = math.gcd(sr, 4000)
    pcm = signal.resample_poly(mono, 4000 // gcd, sr // gcd)
    n = 8000
    energy = np.r_[0.0, np.cumsum(pcm**2)]
    matches = []
    for at in range(2 * n, len(pcm) - n + 1, n):
        clip = pcm[at : at + n]
        if np.mean(clip**2) < 1e-6:
            continue
        previous = pcm[:at]
        power = energy[n : at + 1] - energy[: at - n + 1]
        corr = signal.correlate(previous, clip, mode="valid", method="fft") / np.sqrt(
            np.maximum(power * np.dot(clip, clip), 1e-12)
        )
        best = int(np.argmax(corr))
        if corr[best] > 0.985:
            matches.append(
                dict(
                    seconds=at / 4000,
                    previous_seconds=best / 4000,
                    similarity=round(float(corr[best]), 4),
                )
            )
    return matches


def waveform(path, brief):
    x, sr = read_audio(path)
    info = sf.info(path)
    if info.format not in ("WAV", "WAVEX") or x.shape[1] != 2:
        raise ValueError("Expected a stereo WAV")
    stats = levels(path)
    hop = sr // 10
    blocks = x[: len(x) // hop * hop].reshape(-1, hop, 2)
    quiet = np.mean(blocks**2, axis=(1, 2)) < 1e-6
    d = np.diff(x, axis=0)
    local = np.sqrt(
        np.maximum(0, uniform_filter1d(d * d, axis=0, size=round(0.006 * sr)))
    )
    spikes = (d[1:] * d[:-1] < 0) & (
        np.minimum(abs(d[1:]), abs(d[:-1])) > np.maximum(0.04, 9 * local[:-1])
    )
    return dict(
        levels=stats,
        subtype=info.subtype,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        max_silence_seconds=max(
            (sum(1 for _ in group) / 10 for silent, group in groupby(quiet) if silent),
            default=0,
        ),
        isolated_impulse_count=int(np.any(spikes, axis=1).sum()),
        exact_loop_candidates=loop_screen(x.mean(axis=1), sr),
        quarters_rms_dbfs=[
            round(float(10 * np.log10(max(np.mean(part**2), 1e-14))), 2)
            for part in np.array_split(x, 4)
        ],
        final_100ms_rms_dbfs=round(
            float(10 * np.log10(max(np.mean(x[-hop:] ** 2), 1e-14))), 2
        ),
        rhythm=estimate_rhythm(path, brief["bpm"]),
    )


def character_error(reference, heard):
    def normalize(s):
        return re.sub(r"[^가-힣a-z0-9]", "", re.sub(r"\[[^\]]*\]", "", s).lower())

    a, b = normalize(reference), normalize(heard)
    prev = list(range(len(b) + 1))
    for i, c in enumerate(a, 1):
        row = [i]
        for j, d in enumerate(b, 1):
            row.append(min(row[-1] + 1, prev[j] + 1, prev[j - 1] + (c != d)))
        prev = row
    return round(prev[-1] / len(a), 3) if a else None


def transcriber():
    import torch
    from transformers import WhisperProcessor, WhisperForConditionalGeneration

    torch.set_num_threads(3)
    model_dir = RUNTIME / "v4/whisper-small"
    proc = WhisperProcessor.from_pretrained(model_dir, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(
        model_dir, local_files_only=True
    ).eval()

    def hear(path, lyrics):
        x, sr = sf.read(path, always_2d=True)
        gcd = math.gcd(sr, 16000)
        x = signal.resample_poly(x.mean(axis=1), 16000 // gcd, sr // gcd)
        chunks = []
        with torch.inference_mode():
            for i in range(0, len(x), 30 * 16000):
                chunk = x[i : i + 30 * 16000]
                if len(chunk) < 0.5 * 16000:
                    continue
                features = proc(
                    chunk,
                    sampling_rate=16000,
                    return_tensors="pt",
                    return_attention_mask=True,
                )
                ids = model.generate(
                    input_features=features.input_features,
                    attention_mask=features.attention_mask,
                    language="ko",
                    task="transcribe",
                    do_sample=False,
                    max_new_tokens=180,
                )
                chunks.append(
                    proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
                )
        return dict(
            model="openai/whisper-small@973afd24965f72e36ca33b3055d56a652f456b4d",
            language="ko",
            chunks=chunks,
            character_error_rate=character_error(lyrics, " ".join(chunks)),
        )

    return hear


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("--asr", action="store_true")
    args = ap.parse_args()
    hear = transcriber() if args.asr else None
    for folder in args.folders:
        folder = folder.resolve()
        d = json.loads((folder / "experiment.json").read_text())
        if d["status"] != "rendered":
            continue
        path = folder / d["original"]
        qa = waveform(path, d["brief"])
        if hear:
            qa["asr"] = hear(path, d["brief"]["lyrics"])
        (folder / "qa.json").write_text(json.dumps(qa, indent=2, ensure_ascii=False))
        print(folder.name, qa["levels"]["integrated_lufs"], flush=True)
