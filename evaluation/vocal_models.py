"""Offline adapters for the pinned AudioSet, Whisper and Demucs probes."""

import csv
import hashlib
import os
import sys
import types

from engine.generation.supervisor import run_guarded
from engine.paths import ROOT, RUNTIME

PANN_REVISION = "d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4"
PANN_MD5 = "a419303e1c88aa1b9d2ac3811563d371"
WHISPER_REVISION = "973afd24965f72e36ca33b3055d56a652f456b4d"
STEMS = ("htdemucs", "htdemucs_6s")


def separate(source, target):
    runtime = RUNTIME / "v5"
    command = [
        "/usr/bin/env",
        f"PYTHONPATH={os.pathsep.join(map(str, (ROOT, runtime / 'demucs-mlx', runtime / 'stem-deps312')))}",
        f"DEMUCS_MLX_CACHE_DIR={runtime / 'stem-models'}",
        "DEMUCS_MLX_NO_DOWNLOAD=1",
        sys.executable,
        __file__,
        str(source),
    ]
    for name in STEMS:
        folder = target / name
        folder.mkdir(parents=True, exist_ok=True)
        run_guarded([*command, str(folder), name], folder / "worker.log")
    return [target / name / "vocals.wav" for name in STEMS]


def panns(cache):
    """Use the published checkpoint's feature weights with its upstream MobileNet."""
    import torch
    from torch import nn
    from torch.nn import functional as F

    torch.set_num_threads(2)
    checkpoint = cache / "mobilenet.pth"
    with checkpoint.open("rb") as handle:
        if hashlib.file_digest(handle, "md5").hexdigest() != PANN_MD5:
            raise ValueError("PANNs checkpoint does not match the published checksum")
    weights = torch.load(checkpoint, map_location="cpu", weights_only=True)["model"]

    class Spectrogram(nn.Module):
        def __init__(self, n_fft, hop_length, **_):
            super().__init__()
            self.pad = n_fft // 2
            self.stft = nn.Module()
            self.stft.conv_real = nn.Conv1d(
                1, self.pad + 1, n_fft, stride=hop_length, bias=False
            )
            self.stft.conv_imag = nn.Conv1d(
                1, self.pad + 1, n_fft, stride=hop_length, bias=False
            )

        def forward(self, audio):
            padded = F.pad(audio[:, None], (self.pad, self.pad), mode="reflect")
            power = (
                self.stft.conv_real(padded).square()
                + self.stft.conv_imag(padded).square()
            )
            return power.transpose(1, 2)[:, None]

    class LogmelFilterBank(nn.Module):
        def __init__(self, n_fft, n_mels, **_):
            super().__init__()
            self.melW = nn.Parameter(torch.empty(n_fft // 2 + 1, n_mels))

        def forward(self, power):
            return 10 * torch.log10(torch.clamp(power @ self.melW, min=1e-10))

    class SpecAugmentation(nn.Identity):
        def __init__(self, **_):
            super().__init__()

    # The upstream inference model uses the published STFT and mel tensors as
    # frozen layers. Training-time augmentations are inactive in eval mode.
    from unittest.mock import patch

    modules = {
        "torchlibrosa": types.ModuleType("torchlibrosa"),
        "torchlibrosa.stft": types.SimpleNamespace(
            Spectrogram=Spectrogram, LogmelFilterBank=LogmelFilterBank
        ),
        "torchlibrosa.augmentation": types.SimpleNamespace(
            SpecAugmentation=SpecAugmentation
        ),
    }
    with patch.dict(sys.modules, modules):
        sys.path.insert(0, str(cache))
        try:
            from models import MobileNetV1
        finally:
            sys.path.pop(0)

    model = MobileNetV1(32000, 1024, 320, 64, 50, 14000, 527).eval()
    model.load_state_dict(weights)
    with (cache / "classes.csv").open(newline="", encoding="utf-8") as handle:
        indices = {
            row["display_name"]: int(row["index"]) for row in csv.DictReader(handle)
        }

    def predict(audio, tags):
        with torch.inference_mode():
            scores = model(torch.from_numpy(audio))["clipwise_output"].numpy()
        return [
            {name: round(float(row[indices[name]]), 5) for name in tags}
            for row in scores
        ]

    return predict


def whisper(cache):
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    torch.set_num_threads(2)
    processor = WhisperProcessor.from_pretrained(cache, local_files_only=True)
    model = WhisperForConditionalGeneration.from_pretrained(
        cache, local_files_only=True
    ).eval()
    no_speech = processor.tokenizer.get_vocab()["<|nocaptions|>"]

    def inspect(audio):
        features = processor(
            audio, sampling_rate=16000, return_tensors="pt", return_attention_mask=True
        )
        features_in = features.input_features
        starts = torch.full((len(audio), 1), model.config.decoder_start_token_id)
        with torch.inference_mode():
            encoder = model.get_encoder()(features_in)
            prediction = (
                model(encoder_outputs=encoder, decoder_input_ids=starts)
                .logits[:, 0]
                .softmax(-1)
            )
            tokens = model.generate(
                input_features=features_in,
                attention_mask=features.attention_mask,
                task="transcribe",
                do_sample=False,
                max_new_tokens=32,
            )
        return {
            "no_speech": [round(float(p), 5) for p in prediction[:, no_speech]],
            "transcripts": processor.batch_decode(tokens, skip_special_tokens=True),
        }

    return inspect


if __name__ == "__main__":
    from pathlib import Path

    import mlx.core as mx
    from demucs_mlx.api import Separator

    _, source, target, model_name = sys.argv
    mx.set_cache_limit(256 * 1024**2)
    with Separator(
        model=model_name,
        shifts=0,
        overlap=0.25,
        batch_size=1,
        jobs=0,
        attention_precision="fp32",
        progress=True,
    ) as separator:
        separator.separate(
            Path(source),
            output_dir=Path(target),
            clip="none",
            as_float=True,
            async_write=False,
        )
