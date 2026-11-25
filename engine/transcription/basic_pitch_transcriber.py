"""Real Spotify Basic Pitch (ONNX Runtime, Apache-2.0) polyphonic audio-to-MIDI transcriber.

Runs natively on Apple Silicon arm64 + Python 3.12 with <350 MB RSS and ZERO TensorFlow / FFmpeg requirement.
Preserves BOTH raw unquantized timing AND beat-grid-quantized timing, amplitude velocity, confidence,
and pitch-bend contour summary.
"""

from __future__ import annotations

import logging
import threading
import warnings
from pathlib import Path
from typing import Any

import numpy as np

from engine.daw_workspace.schema import make_id
from engine.runtime import record_engine_verification

_model_lock = threading.Lock()
_cached_model: Any = None
_cached_onnx_path: Path | None = None


def _get_basic_pitch_model():
    global _cached_model, _cached_onnx_path
    with _model_lock:
        if _cached_model is not None:
            return _cached_model, _cached_onnx_path
        import basic_pitch
        from basic_pitch.inference import Model

        onnx_candidates = list(Path(basic_pitch.__file__).parent.rglob("*.onnx"))
        if not onnx_candidates:
            raise RuntimeError("Basic Pitch ONNX model (`nmp.onnx`) not found in basic_pitch package")
        _cached_onnx_path = onnx_candidates[0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logging.getLogger("root").setLevel(logging.ERROR)
            _cached_model = Model(_cached_onnx_path)
        return _cached_model, _cached_onnx_path


def _snap(val: float, grid: float = 0.25) -> float:
    return round(max(0.0, round(val / grid) * grid), 4)


def transcribe_audio_basic_pitch(
    audio_path: Path,
    *,
    bpm: float = 120.0,
    beat_offset_sec: float = 0.0,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.32,
    minimum_note_length_ms: float = 95.0,
    minimum_frequency_hz: float | None = None,
    maximum_frequency_hz: float | None = None,
    melodia_trick: bool = True,
    monophonic: bool = False,
    max_notes: int = 800,
) -> dict[str, Any]:
    """Run real Basic Pitch ONNX inference on an audio WAV/FLAC file and return structured MIDI events."""
    from basic_pitch.inference import predict

    model, onnx_path = _get_basic_pitch_model()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, _, raw_events = predict(
            str(audio_path),
            model,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=minimum_note_length_ms,
            minimum_frequency=minimum_frequency_hz,
            maximum_frequency=maximum_frequency_hz,
            multiple_pitch_bends=False,
            melodia_trick=melodia_trick,
        )

    sec_per_beat = 60.0 / max(30.0, float(bpm))
    parsed: list[dict[str, Any]] = []
    for ev in raw_events:
        start_s = float(ev[0])
        end_s = float(ev[1])
        pitch = int(ev[2])
        amp = float(ev[3])
        bends = list(ev[4]) if len(ev) > 4 and ev[4] is not None else []
        if end_s <= start_s + 0.02:
            continue
        raw_beat = max(0.0, (start_s - beat_offset_sec) / sec_per_beat)
        raw_dur = max(0.0625, (end_s - start_s) / sec_per_beat)
        q_beat = _snap(raw_beat, 0.25)
        q_dur = max(0.25, _snap(raw_dur, 0.25))
        vel = max(24, min(124, int(round(32 + amp * 92))))
        conf = round(float(np.clip(amp, 0.05, 0.99)), 3)
        # Pitch bend contour summary (Basic Pitch bins are 1/3 semitone = ~33.3 cents each)
        bend_cents = 0.0
        if bends:
            arr = np.array(bends, dtype=np.float64)
            bend_cents = round(float(np.mean(arr) * (100.0 / 3.0)), 1)

        parsed.append(
            {
                "id": make_id("note"),
                "pitch": max(0, min(127, pitch)),
                "velocity": vel,
                "onsetSec": round(start_s, 4),
                "offsetSec": round(end_s, 4),
                "startBeat": round(raw_beat, 4),
                "durationBeats": round(raw_dur, 4),
                "quantizedStartBeat": q_beat,
                "quantizedDurationBeats": q_dur,
                "microtimingOffsetMs": round((raw_beat - q_beat) * sec_per_beat * 1000.0, 2),
                "confidence": conf,
                "pitchBendCents": bend_cents,
            }
        )

    parsed.sort(key=lambda x: (x["startBeat"], -x["confidence"], x["pitch"]))

    # Optional monophonic cleanup (for Bass stem — keep strongest note at overlapping onsets)
    if monophonic and parsed:
        mono_clean: list[dict[str, Any]] = []
        for n in parsed:
            if mono_clean and abs(n["startBeat"] - mono_clean[-1]["startBeat"]) < 0.12:
                if n["confidence"] > mono_clean[-1]["confidence"]:
                    mono_clean[-1] = n
                continue
            if mono_clean and mono_clean[-1]["startBeat"] + mono_clean[-1]["durationBeats"] > n["startBeat"]:
                mono_clean[-1]["durationBeats"] = round(max(0.08, n["startBeat"] - mono_clean[-1]["startBeat"]), 4)
            mono_clean.append(n)
        parsed = mono_clean

    if len(parsed) > max_notes:
        parsed = parsed[:max_notes]

    pitches = [n["pitch"] for n in parsed]
    mean_conf = round(float(np.mean([n["confidence"] for n in parsed])), 3) if parsed else 0.0
    record_engine_verification(
        "basic-pitch-onnx",
        True,
        wav_path=str(audio_path),
        details={"model": onnx_path.name if onnx_path else "nmp.onnx", "noteCount": len(parsed)},
    )
    return {
        "model": "spotify-basic-pitch-onnx",
        "license": "Apache-2.0",
        "noteCount": len(parsed),
        "pitchMin": min(pitches) if pitches else None,
        "pitchMax": max(pitches) if pitches else None,
        "meanConfidence": mean_conf,
        "notes": parsed,
    }


def extract_melody_topline(notes: list[dict[str, Any]], min_pitch: int = 55) -> list[dict[str, Any]]:
    """Extract the salient monophonic upper-voice lead melody line from polyphonic notes."""
    high_notes = [n for n in notes if int(n["pitch"]) >= min_pitch and float(n.get("confidence", 0.5)) >= 0.35]
    if not high_notes:
        return []
    high_notes.sort(key=lambda x: (float(x["startBeat"]), -int(x["pitch"])))

    topline: list[dict[str, Any]] = []
    for n in high_notes:
        if not topline:
            topline.append(dict(n))
            continue
        prev = topline[-1]
        # Simultaneous chord stack -> keep the highest salient pitch (top melody line)
        if abs(float(n["startBeat"]) - float(prev["startBeat"])) < 0.18:
            if int(n["pitch"]) > int(prev["pitch"]):
                topline[-1] = dict(n)
            continue
        # Clip previous sustained note slightly before next melody onset for clean monophonic phrasing
        if float(prev["startBeat"]) + float(prev["durationBeats"]) > float(n["startBeat"]):
            prev["durationBeats"] = round(max(0.08, float(n["startBeat"]) - float(prev["startBeat"])), 4)
        topline.append(dict(n))
    return topline
