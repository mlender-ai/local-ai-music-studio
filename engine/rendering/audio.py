"""Validate real PCM, quantify differences, and keep originals immutable."""

import numpy as np
import soundfile as sf
from scipy.signal import welch
from engine.paths import audio_path


def read_audio(path):
    path = audio_path(path)
    info = sf.info(path)
    if (
        info.frames < 1
        or info.duration > 120
        or info.channels not in (1, 2)
        or not 8000 <= info.samplerate <= 192000
    ):
        raise ValueError(
            "Only nonempty mono/stereo WAV up to 120 seconds and 192 kHz is supported."
        )
    if info.frames * info.channels > 6_000_000:
        raise ValueError("Audio is too large for bounded DSP processing.")
    x, sr = sf.read(path, always_2d=True, dtype="float64")
    if not np.isfinite(x).all():
        raise ValueError("Audio contains NaN or infinity.")
    return x, sr


def metrics(x, sr):
    mono = x.mean(axis=1)
    freq, power = welch(mono, sr, nperseg=min(8192, len(mono)))
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x * x)))
    return dict(
        sample_rate=sr,
        channels=x.shape[1],
        frames=len(x),
        duration_seconds=len(x) / sr,
        peak=peak,
        peak_dbfs=float(20 * np.log10(max(peak, 1e-12))),
        rms=rms,
        rms_dbfs=float(20 * np.log10(max(rms, 1e-12))),
        clipped_samples=int(np.count_nonzero(np.abs(x) >= 1)),
        finite=bool(np.isfinite(x).all()),
        low_band_power=float(power[(freq >= 20) & (freq < 200)].sum()),
        high_band_power=float(power[freq >= 5000].sum()),
    )


def analyze(path):
    x, sr = read_audio(path)
    return dict(path=str(audio_path(path)), **metrics(x, sr))


def compare(a, b):
    x, sr = read_audio(a)
    y, yr = read_audio(b)
    result = dict(
        original=metrics(x, sr),
        modified=metrics(y, yr),
        original_path=str(audio_path(a)),
        modified_path=str(audio_path(b)),
        same_format=sr == yr and x.shape == y.shape,
    )
    if result["same_format"]:
        result.update(
            difference_rms=float(np.sqrt(np.mean((x - y) ** 2))),
            changed_samples=int(np.count_nonzero(np.abs(x - y) > 1e-7)),
            identical=bool(np.array_equal(x, y)),
        )
    return result


def write_audio(path, x, sr):
    path = audio_path(path, must_exist=False)
    if path.exists():
        raise ValueError("Refusing to overwrite an existing audio version.")
    if not np.isfinite(x).all() or np.max(np.abs(x)) > 1:
        raise ValueError("Output is non-finite or exceeds full scale. Add a limiter.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create also prevents concurrent writers from overwriting a file.
    with path.open("xb") as stream:
        sf.write(stream, x, sr, format="WAV", subtype="PCM_24")
    return str(path)
