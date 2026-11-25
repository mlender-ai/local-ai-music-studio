"""Subprocess runner for Demucs (`htdemucs` / `htdemucs_6s`) using soundfile + Apple Silicon MPS.

Runs inside `run_cancellable_guarded()` so true SIGTERM -> SIGKILL process-group cancellation,
10 GiB RSS guard, and Apple Silicon unified memory cleanup work cleanly without requiring FFmpeg.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model
from scipy.signal import resample_poly


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Demucs stem separation via soundfile + MPS/CPU.")
    parser.add_argument("--input", required=True, help="Input readable WAV/FLAC/OGG path")
    parser.add_argument("--out-dir", required=True, help="Directory to write <stem>.wav files")
    parser.add_argument("--model", default="htdemucs", help="Demucs model name (htdemucs or htdemucs_6s)")
    parser.add_argument("--max-duration-sec", type=float, default=300.0, help="Safety bound for memory")
    args = parser.parse_args()

    in_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    info = sf.info(str(in_path))
    if info.frames <= 0 or info.samplerate <= 0:
        raise ValueError(f"Empty or unreadable audio file: {in_path}")

    max_frames = int(min(info.frames, args.max_duration_sec * info.samplerate))
    data, sr = sf.read(str(in_path), frames=max_frames, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)

    model = get_model(args.model)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    model.eval()

    target_sr = int(model.samplerate)
    if sr != target_sr:
        g = math.gcd(int(sr), target_sr)
        data = np.stack(
            [resample_poly(data[:, ch], target_sr // g, int(sr) // g) for ch in range(2)],
            axis=1,
        ).astype(np.float32)

    wav_tensor = torch.from_numpy(data.T.copy()).unsqueeze(0).to(device)
    with torch.no_grad():
        separated = apply_model(
            model,
            wav_tensor,
            shifts=0,
            split=True,
            overlap=0.25,
            progress=False,
        )[0].cpu().numpy()

    meta_stems = []
    for idx, stem_name in enumerate(model.sources):
        stem_stereo = np.clip(separated[idx].T, -1.0, 1.0).astype(np.float32)
        out_wav = out_dir / f"{stem_name}.wav"
        tmp_wav = out_dir / f".{stem_name}.tmp.wav"
        sf.write(str(tmp_wav), stem_stereo, target_sr, subtype="PCM_24")
        tmp_wav.replace(out_wav)
        rms = float(np.sqrt(np.mean(stem_stereo * stem_stereo))) if len(stem_stereo) else 0.0
        meta_stems.append(
            {
                "role": stem_name,
                "filename": out_wav.name,
                "sampleRate": target_sr,
                "durationSec": round(len(stem_stereo) / target_sr, 3),
                "rmsDbfs": round(20.0 * math.log10(max(rms, 1e-9)), 2),
            }
        )

    manifest = {
        "model": args.model,
        "device": device,
        "sampleRate": target_sr,
        "sources": list(model.sources),
        "stems": meta_stems,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Release MPS unified memory promptly
    del wav_tensor, separated, model
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()


if __name__ == "__main__":
    main()
