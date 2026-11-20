"""Compare harmonic, transient and voice evidence before arranging the new take."""

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw.alt_rock import RATE, aligned, dbfs, read
from engine.paths import RUNTIME
from engine.session.render import write_json
from scripts.v6_arrange import onset_grid


def speech_presence(path):
    """Whisper's first-step no-speech posterior in fixed windows; not a singing detector."""
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    torch.set_num_threads(3)
    directory = RUNTIME / "v4/whisper-small"
    processor = WhisperProcessor.from_pretrained(directory, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(
        directory, local_files_only=True
    ).eval()
    token = processor.tokenizer.get_vocab()["<|nocaptions|>"]
    x, sr = sf.read(path, always_2d=True)
    from math import gcd

    factor = gcd(16000, sr)
    x = signal.resample_poly(x.mean(axis=1), 16000 // factor, sr // factor)
    rows = []
    with torch.inference_mode():
        for idx in range(0, len(x), 16000 * 6):
            chunk = x[idx : idx + 16000 * 6]
            features = processor(
                chunk, sampling_rate=16000, return_tensors="pt"
            ).input_features
            ids = torch.tensor([[model.config.decoder_start_token_id]])
            probs = (
                model(input_features=features, decoder_input_ids=ids)
                .logits[0, 0]
                .softmax(0)
            )
            rows.append(
                {"seconds": idx / 16000, "no_speech": round(probs[token].item(), 4)}
            )
    return rows


def screen(source, stems):
    mix, _ = read(source)
    stem = {
        name: aligned(stems / "htdemucs_6s" / (name + ".wav"), len(mix))
        for name in ("vocals", "drums", "bass", "guitar")
    }
    alt = aligned(stems / "htdemucs/vocals.wav", len(mix))
    beats, bpm, _ = onset_grid(stem["drums"], 104)
    rows = []
    for i in range(0, len(beats) - 4, 4):
        a, b = [np.clip(round(t * RATE), 0, len(mix)) for t in (beats[i], beats[i + 4])]
        if b <= a:
            continue
        rows.append(
            dict(
                beat=i,
                start=round(float(beats[i]), 3),
                mix=round(dbfs(mix[a:b]), 2),
                **{n: round(dbfs(x[a:b]), 2) for n, x in stem.items()},
                vocals_four=round(dbfs(alt[a:b]), 2),
            )
        )
    return {
        "duration": len(mix) / RATE,
        "bpm": bpm,
        "bars": rows,
        "six_source_voice_vs_mix_db": dbfs(stem["vocals"]) - dbfs(mix),
        "four_source_voice_vs_mix_db": dbfs(alt) - dbfs(mix),
        "original_no_speech": speech_presence(source),
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "stems", "report"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    write_json(args.report, screen(args.source, args.stems))
