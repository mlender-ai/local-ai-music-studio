"""Screen raw takes conservatively; retain model estimates apart from the stereo original."""

import argparse
from pathlib import Path

import soundfile as sf

from engine.daw.alt_rock import dbfs
from engine.session.render import write_json
from scripts.v4_evaluate import transcriber
from scripts.v6_screen import speech_presence


def screen(raw, stems):
    x, _ = sf.read(raw, dtype="float32")
    estimates = {}
    for model in ("htdemucs", "htdemucs_6s"):
        y, sr = sf.read(stems / model / "vocals.wav", dtype="float32")
        estimates[model] = {
            "relative_rms_db": dbfs(y) - dbfs(x),
            "max_2s_rms_dbfs": max(
                dbfs(y[i : i + 2 * sr]) for i in range(0, len(y), 2 * sr)
            ),
        }
    result = {"estimates": estimates, "no_speech_per_6s": speech_presence(raw)}
    if any(s["relative_rms_db"] > -30 for s in estimates.values()):
        hear = transcriber()
        result["stereo_transcription"] = hear(raw, "")["chunks"]
        result["estimated_voice_transcription"] = hear(
            stems / "htdemucs/vocals.wav", ""
        )["chunks"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for arg in ("raw", "stems", "output"):
        parser.add_argument(arg, type=Path)
    a = parser.parse_args()
    write_json(a.output, screen(a.raw, a.stems))
