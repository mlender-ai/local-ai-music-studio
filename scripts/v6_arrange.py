"""Place recorded Foley and harmonic answers against the actual drum and band audio."""

import hashlib
import json
import math

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import gaussian_filter1d

from engine.daw.alt_rock import RATE
from engine.paths import ROOT

FOLEY = ROOT / "examples/v6/foley"
SECTIONS = (
    "Opening",
    "Groove A",
    "Development",
    "First explosion",
    "Mechanical break",
    "Lead guitar",
    "Final expansion",
    "Resolution",
)


def prepare_samples(audio):
    catalog = json.loads((FOLEY / "sources.json").read_text())
    for source in catalog:
        path = FOLEY / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Sample hash mismatch: {path}")
        x, sr = sf.read(path, always_2d=True)
        source.update(decoded_rate=sr, decoded_seconds=len(x) / sr)
        gcd = math.gcd(sr, RATE)
        x = signal.resample_poly(x.mean(axis=1), RATE // gcd, sr // gcd)
        name = path.stem
        if name == "motor":
            # Wind the motor up backwards into the section downbeat.
            x = x[round(1.1 * RATE) : round(2.9 * RATE)][::-1].copy()
            x = signal.sosfilt(
                signal.butter(3, [550, 3100], "bandpass", fs=RATE, output="sos"), x
            )
            x *= np.linspace(0.02, 1, len(x)) ** 1.4
            attack, release = 0.045, 0.09
            source["processing"] = (
                "1.1–2.9 s reversed, 550–3100 Hz band-pass, rising envelope"
            )
        else:
            peak = np.max(abs(x))
            onset = np.flatnonzero(abs(x) > peak * 0.035)[0]
            x = x[max(0, onset - 24) :][
                : round((0.43 if name == "pipe" else 0.16) * RATE)
            ]
            x = signal.sosfilt(
                signal.butter(
                    2, 240 if name == "pipe" else 600, "highpass", fs=RATE, output="sos"
                ),
                x,
            )
            attack, release = 0.0006, 0.018
            source["processing"] = (
                "onset trim, high-pass, edge fades, item-level pitch, gain and pan"
            )
        x[: round(attack * RATE)] *= np.linspace(0, 1, round(attack * RATE))
        x[-round(release * RATE) :] *= np.linspace(1, 0, round(release * RATE))
        target = audio / (name + ".wav")
        sf.write(target, x * 0.85 / max(abs(x)), RATE, subtype="PCM_24")
        source.update(
            processed=target.name,
            processed_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        )
    return catalog


def onset_grid(drums, expected_bpm):
    """Fit beat period then track local phase using only the drum transients."""
    mono = signal.resample_poly(drums.mean(axis=1), 1, 4)
    rate = RATE // 4
    _, times, spec = signal.stft(mono, rate, nperseg=384, noverlap=324, boundary=None)
    flux = np.maximum(np.diff(abs(spec), axis=1), 0).sum(axis=0)
    envelope = gaussian_filter1d(flux, 1.4)
    # STFT frame centers lead a transient in this positive-difference detector.
    times = times[1:] + 0.008
    peak_ids, _ = signal.find_peaks(envelope, distance=18, prominence=0.0015)
    peaks, weights = times[peak_ids], envelope[peak_ids]
    tempi = np.arange(expected_bpm * 0.87, expected_bpm * 1.13, 0.03)

    def pulse_strength(bpm):
        return abs(np.sum(weights * np.exp(2j * np.pi * peaks * bpm / 60)))

    bpm = max(tempi, key=pulse_strength)
    period = 60 / bpm
    phase = (
        np.angle(np.sum(weights * np.exp(2j * np.pi * peaks / period)))
        / (2 * np.pi)
        * period
    )
    phase %= period
    if phase > period * 0.72:
        phase -= period
    count = math.ceil((len(drums) / RATE - phase) / period) + 2
    nominal = phase + np.arange(count) * period
    beats = nominal.copy()
    for idx, pos in enumerate(nominal):
        dist = peaks - pos
        residual = (dist + period / 2) % period - period / 2
        weight = weights * np.exp(-((dist / 2.8) ** 2)) * (abs(residual) < 0.095)
        if weight.sum() > 0.03:
            beats[idx] += np.average(residual, weights=weight)
    return beats, float(bpm), peaks


def harmonic_note(guitar, bass, start, length, target):
    """Choose the nearest register of a strong pitch class in the sounding harmony."""
    start = max(0, round(start * RATE))
    end = min(len(guitar), start + round(length * RATE))
    chroma = np.zeros(12)
    for data, weight in ((guitar, 1), (bass, 0.65)):
        x = data[start:end].mean(axis=1)
        freq, power = signal.welch(x, RATE, nperseg=min(8192, len(x)), nfft=16384)
        peaks, _ = signal.find_peaks(power)
        peaks = peaks[(freq[peaks] > 65) & (freq[peaks] < 1600)]
        pc = np.rint(69 + 12 * np.log2(freq[peaks] / 440)).astype(int) % 12
        votes = np.bincount(pc, weights=power[peaks] ** 0.7, minlength=12)
        chroma += weight * votes / (votes.sum() + 1e-24)
    candidates = [
        n
        for n in range(target - 7, target + 8)
        if chroma[n % 12] >= 0.48 * chroma.max()
    ]
    note = max(candidates, key=lambda n: chroma[n % 12] / (1 + 0.17 * abs(n - target)))
    return note, round(float(chroma[note % 12] / max(chroma.max(), 1e-16)), 3)


def arrange(beats, regions, audio, guitar, bass):
    events, notes = [], []
    lengths = {
        k: sf.info(audio / f"{k}.wav").duration for k in ("pipe", "key", "motor")
    }

    def clock(beat):
        return max(0.0, float(np.interp(beat, np.arange(len(beats)), beats)))

    def hit(name, beat, db, pan, rate=1.0, arrive=False):
        duration = lengths[name] / rate
        pos = clock(beat) - (duration if arrive else 0)
        if pos >= 0 and pos + duration <= regions[-1]["end"]:
            events.append(
                {
                    "source": name,
                    "beat": beat,
                    "seconds": pos,
                    "duration": duration,
                    "db": db,
                    "pan": pan,
                    "rate": rate,
                    "align": "end" if arrive else "attack",
                }
            )

    for region in regions:
        a, b = region["first_beat"], region["limit_beat"]
        name = region["name"]
        for k, down in enumerate(range(a, b - 3, 4)):
            if name == "Opening":
                if k in (0, 2):
                    hit("pipe", down + 0.5, -13, -0.42)
            elif name in ("Groove A", "Development", "Final expansion"):
                for j, offset in enumerate(
                    ((0.75, 2.5), (1.5,), (0.75, 3.25), (2.5, 3.5))[k % 4]
                ):
                    hit(
                        "pipe",
                        down + offset,
                        (-14 if name == "Final expansion" else -16) - 2 * j,
                        -0.38 if k % 2 == 0 else 0.3,
                        1 if j == 0 else 1.12,
                    )
            elif name == "First explosion" and k in (3, 7):
                hit("key", down + 2.75, -15, 0.36)
                hit("pipe", down + 3.5, -13, -0.28, 0.84)
            elif name == "Mechanical break":
                for j, offset in enumerate(
                    ((0, 1.5, 3.25), (0.5, 2.5), (0, 2.75, 3.5))[k % 3]
                ):
                    hit(
                        "pipe",
                        down + offset,
                        -4.5 - 2 * j,
                        -0.35 + 0.22 * j,
                        (1, 0.84, 1.12)[j],
                    )
            elif name == "Lead guitar" and k % 2 == 1:
                hit("key", down + 3.5, -19, 0.36)
            elif name == "Resolution" and k == 0:
                hit("pipe", down + 2, -15, -0.2, 0.84)
            if name in ("Development", "Final expansion") and k % 2 == 0:
                pos = clock(down + 2.5)
                end = clock(down + 3.75)
                note, support = harmonic_note(
                    guitar, bass, pos, end - pos, 76 if k % 4 == 0 else 71
                )
                notes.append(
                    {
                        "seconds": pos,
                        "end": end,
                        "midi": note,
                        "velocity": 71 if k % 4 == 0 else 57,
                        "pitch_class_relative_support": support,
                    }
                )
        if name in ("Development", "Mechanical break"):
            # Three eighth notes per accent; meets 4/4 again every three bars.
            for j, beat in enumerate(np.arange(a + 0.5, b - 0.25, 1.5)):
                hit(
                    "key",
                    float(beat),
                    (-7 if name == "Mechanical break" else -18) - (j % 2) * 3,
                    0.42 if j % 3 else -0.18,
                    0.92 if j % 3 else 1.08,
                )
        if name in ("First explosion", "Mechanical break", "Lead guitar", "Resolution"):
            hit(
                "motor",
                a,
                -16 if name == "Mechanical break" else -21,
                0.25,
                arrive=True,
            )
    return events, notes


def guitar_answers(beats, sections, guitar):
    """Echo the opening performance at tape speed into gaps in the exposed lead."""
    opening_end = sections[1]["first_beat"]
    lead = sections[5]["first_beat"]

    def profile(start, seconds):
        segment = guitar[round(start * RATE) : round((start + seconds) * RATE)].mean(
            axis=1
        )
        freq, psd = signal.welch(segment, RATE, nperseg=8192)
        peaks = signal.find_peaks(psd)[0]
        peaks = peaks[(freq[peaks] > 85) & (freq[peaks] < 1800)]
        pc = np.round(69 + 12 * np.log2(freq[peaks] / 440)).astype(int) % 12
        chroma = np.bincount(pc, weights=np.sqrt(psd[peaks]), minlength=12)
        return chroma / max(np.linalg.norm(chroma), 1e-12)

    answers = []
    for k, (beat, length, speed) in enumerate(
        ((2.5, 0.75, 1.0), (7, 1, 2.0), (14, 1.5, 2.0), (20, 2, 1.0))
    ):
        pos = float(np.interp(lead + beat, np.arange(len(beats)), beats))
        duration = length * float(np.median(np.diff(beats)))
        target = profile(pos, duration)
        candidates = [max(0.0, float(t)) for t in beats[: opening_end - 3]]
        scores = [float(target @ profile(t, duration * speed)) for t in candidates]
        best = int(np.argmax(scores))
        if scores[best] >= 0.58:
            answers.append(
                {
                    "seconds": pos,
                    "duration": duration,
                    "offset": candidates[best],
                    "rate": speed,
                    "db": (-5, -4, -5, -7)[k],
                    "pan": (-0.32, 0.25, -0.25, 0.18)[k],
                    "chroma_similarity": round(scores[best], 3),
                }
            )
    return answers
