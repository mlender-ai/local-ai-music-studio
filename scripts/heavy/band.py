"""Perform the score with recorded strings and drums; keep DI and discrete events."""

import json

import numpy as np
import soundfile as sf
from scipy import signal

from engine.paths import ROOT
from engine.session.bank import BANKS, fetch, note, pcm, select_sample
from engine.session.render import write_json
from scripts.heavy.score import BPM, OUT, root_name

RATE = 48000
STEP = 60 / BPM / 4
BAR = 16 * STEP
LOW = {"D": 26, "Bb": 34, "C": 36, "A": 33, "F": 29, "G": 31, "Eb": 27}
STRING = {"D": 38, "Bb": 46, "C": 48, "A": 45, "F": 41, "G": 43, "Eb": 39}
EXTRA = json.loads((OUT / "recordings.json").read_text())


def source(voice, pitch, take):
    return min(
        (x for x in EXTRA if x["voice"] == voice and x["take"] == take),
        key=lambda x: abs(x["key"] - pitch),
    )


def string_note(pitch, seconds, take, art):
    row = source("guitar", pitch, take)
    x, sr = pcm(row["blob"])
    t = np.arange(round(seconds * RATE)) / RATE
    bend = np.zeros_like(t)
    if art in ("bend", "feedback"):
        bend -= 2 * np.clip(1 - t / 0.20, 0, 1) ** 1.3
        bend += 0.19 * np.minimum(1, t / 0.36) * np.sin(2 * np.pi * 5.6 * t)
    speed = sr / RATE * 2 ** ((pitch - row["key"] + bend) / 12)
    y = np.interp(np.cumsum(speed) - speed[0], np.arange(len(x)), x, right=0)
    if art == "chug":
        y = signal.sosfilt(signal.butter(2, 1950, fs=RATE, output="sos"), y) * np.exp(
            -t * 12
        )
    return y * np.minimum(1, t / 0.0014) * np.minimum(
        1, (seconds - t) / min(0.04, seconds * 0.2)
    ), row["blob"]


def perform(plan, out):
    a = out / "Audio"
    a.mkdir(parents=True, exist_ok=False)
    for row in EXTRA:
        fetch((BANKS[row["bank"]], row["path"], row["blob"]))
    duration = 48 * BAR + 1.65
    lanes = {
        k: np.zeros(round(duration * RATE), dtype="float32")
        for k in ("left-di", "right-di", "lead-di", "bass", "kit", "metal", "scratch")
    }
    events = []

    def put(lane, bar, step, wave, gain, **meta):
        idx = round(((bar - 1) * 16 + step) * STEP * RATE)
        count = min(len(wave), len(lanes[lane]) - idx)
        lanes[lane][idx : idx + count] += gain * wave[:count]
        events.append(
            dict(
                lane=lane,
                bar=bar,
                step=step,
                seconds=idx / RATE,
                length=count / RATE,
                gain=gain,
                **meta,
            )
        )

    for b in plan["bars"]:
        n = b["bar"]
        ch = b["chord_symbols"]
        root = root_name(ch)
        bridge = 35 <= n <= 38
        solo = 27 <= n <= 34
        big = 15 <= n <= 22 or 39 <= n <= 46
        power = "5" in ch or ch == "Dped"
        # Two performances use separate round robins, pick order, note lengths and gaps.
        for side, lane in enumerate(("left-di", "right-di")):
            hits = list(b["rhythmic_accents"])
            if side and hits and (big or 3 <= n <= 10):
                hits = (
                    sorted({*hits[:-1], max(hits[-2] + 1, hits[-1] - 1)})
                    if len(hits) > 2
                    else hits
                )
            for j, s in enumerate(hits):
                p = STRING[root]
                if n == 2 and s < 8:
                    intervals = [0, 7, 17]
                elif "A7" in ch and s >= 8:
                    intervals = [0, 10, 16]
                elif (big or solo) and j == 0 and ch in ("Dm", "Gm"):
                    intervals = [0, 7, 15]
                elif not power and j == 0 and n in (4, 6, 8, 9, 11, 12):
                    intervals = [0, 7, 15 if "m" in ch else 16]
                else:
                    intervals = [0, 7]
                limit = (hits[j + 1] if j + 1 < len(hits) else 16) - s
                opened = (big and j == 0) or n in (1, 2, 47, 48) or (solo and j == 0)
                length = min(
                    limit - 0.14,
                    (6.7 if not side else 5.9)
                    if opened
                    else (1.12 if j % 2 == 0 else 0.80),
                )
                if n == 48:
                    length = 15.8
                if n == 1 and j == 0:
                    intervals = [0, 7, 14]
                if n == 47 and j == 0:
                    intervals = [0, 7, 15, 26]
                if n == 48:
                    intervals = [0, 7, 12]
                if side and opened:
                    intervals = [7, 12] if power else intervals[1:] + [12]
                for k, interval in enumerate(intervals):
                    delay = (0.004 + side * 0.002) * k / STEP + 0.018 * side
                    dur = length * STEP
                    y, blob = string_note(
                        p + interval, dur, side + 1, "open" if opened else "chug"
                    )
                    put(
                        lane,
                        n,
                        s + delay,
                        y,
                        0.48 * (0.88**k),
                        midi=p + interval,
                        art="open" if opened else "chug",
                        blob=blob,
                    )
        bass = LOW[root] if not bridge else b["bass_root"]
        bh = [0, 6, 9, 13] if bridge else [0, 5, 8, 14] if n % 2 else [0, 3, 8, 11, 14]
        if n in (1, 23, 24, 47, 48):
            bh = {1: [0], 23: [0, 10], 24: [0, 12], 47: [0, 8], 48: [0]}[n]
        if n == 34:
            bh = [0, 6, 10, 12]
        for j, s in enumerate(bh):
            p = bass
            if n == 24:
                p = 26 if s == 0 else 27
            elif n == 39 and j == 0:
                p = 38
            elif j == len(bh) - 1 and ("A7" in ch or n == 38):
                p = 25 if n in (2, 6, 14, 26, 45) else 37
            elif j > 0 and j == len(bh) - 1 and (n % 3 == 0 or bridge):
                p = bass + 7
            elif j == 2 and (n >= 39 or n in (28, 32, 36)):
                p = bass + 12
            length = min(
                (bh[j + 1] if j + 1 < len(bh) else 16) - s - 0.18,
                5.4 if j == 0 or bridge else 2.5,
            )
            if n == 48:
                length = 12
            vel = 113 if j == 0 else 88 if j % 2 else 101
            y = note("bass", "bass", p, vel, n + j, length * STEP, 0.017, RATE)
            put(
                "bass",
                n,
                s,
                y,
                0.61,
                midi=p,
                art="picked",
                blob=select_sample("bass", "bass", p, vel, n + j)[-1],
            )
        if solo or n in (14, 26, 45, 46, 47):
            for j, (s, p, l) in enumerate(b["lead_motif"]):
                art = (
                    "feedback" if n >= 31 and l >= 6 else "bend" if l >= 6 else "picked"
                )
                y, blob = string_note(
                    p, l * STEP * (0.96 if l > 2 else 0.82), 1 + j % 2, art
                )
                put("lead-di", n, s, y, 0.8, midi=p, art=art, blob=blob)

        def hit(s, voice, vel, n=n):
            if n in (14, 34) and s >= 15:
                return
            take = (n + int(s)) % 2 + 1
            if voice in ("htom", "ltom", "crash"):
                row = source(voice, 0, take)
                x, sr = pcm(row["blob"])
                time = (
                    np.arange(round((1.45 if voice == "crash" else 0.57) * RATE)) / RATE
                )
                y = (
                    np.interp(time * sr, np.arange(len(x)), x, right=0)
                    * np.minimum(1, (time[-1] - time) / 0.07)
                    * (vel / 127) ** 1.4
                )
                blob = row["blob"]
            else:
                span = {"snare": 0.34, "kick": 0.35, "hat": 0.12, "openhat": 0.4}[voice]
                y = note("drums", voice, 0, vel, take, span, 0.032, RATE)
                blob = select_sample("drums", voice, 0, vel, take)[-1]
            gain = {
                "kick": 0.85,
                "snare": 0.71,
                "hat": 0.16,
                "openhat": 0.22,
                "htom": 0.61,
                "ltom": 0.66,
                "crash": 0.39,
            }[voice]
            put("kit", n, s, y, gain, voice=voice, velocity=vel, blob=blob)

        if n < 3:
            if n == 2:
                hit(12, "ltom", 94)
                hit(14, "snare", 103)
        elif n == 48:
            hit(0, "kick", 119)
            hit(0, "crash", 107)
        else:
            kicks = (
                [[0, 6, 11], [0, 3, 10, 14], [0, 7, 10], [0, 6, 9]][n - 35]
                if bridge
                else [0, 10]
                if 23 <= n <= 26
                else sorted(
                    set(
                        [0, 8]
                        + b["rhythmic_accents"][:2]
                        + ([14] if n % 3 == 1 else [])
                    )
                )
            )
            for j, s in enumerate(kicks):
                hit(s, "kick", 121 if j == 0 or big else 103)
            for s in [8] if bridge or 23 <= n <= 26 else [4, 12]:
                hit(s, "snare", 121 if big or solo or bridge else 110)
            if n % 4 == 1 or n == 37:
                hit(7, "snare", 57)
            for j, s in enumerate(range(0, 16, 4 if bridge or 23 <= n <= 26 else 2)):
                hit(
                    s,
                    "openhat" if (big or solo) and (j % 4 == 3) else "hat",
                    93 if j % 2 == 0 else 67,
                )
            if n in (3, 15, 19, 27, 31, 39, 43, 46):
                hit(0, "crash", 117)
            if b["fills"]:
                seq = (
                    ("htom", "htom", "ltom", "snare")
                    if n not in (10, 14)
                    else ("snare", "snare", "htom", "snare")
                )
                for j, voice in enumerate(seq):
                    hit(12 + j, voice, 76 + 12 * j)
    # One short gesture cut into a virtual platter. Read-head reversals + fader cuts act on a new guitar attack.
    grain, _ = string_note(57, 0.95, 2, "open")
    for n, s, beats, style in ((1, 5, 1.15, 0), (23, 3, 1.5, 1), (26, 6, 0.95, 2)):
        t = np.arange(round(beats * 4 * STEP * RATE)) / RATE
        u = t / t[-1]
        knots = [0, 0.21, 0.39, 0.58, 0.76, 1]
        travel = (
            [0.065, 0.31, 0.11, 0.26, 0.08, 0.17],
            [0.05, 0.41, 0.10, 0.32, 0.14, 0.36],
            [0.08, 0.30, 0.06, 0.21, 0.09, 0.17],
        )[style]
        pos = np.interp(u, knots, travel)
        cut = np.interp(
            u,
            [0, 0.02, 0.20, 0.22, 0.26, 0.28, 0.48, 0.50, 0.53, 0.55, 0.93, 1],
            [0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0],
        )
        y = (
            signal.sosfilt(
                signal.butter(2, [550, 4800], "bandpass", fs=RATE, output="sos"),
                np.interp(pos * RATE, np.arange(len(grain)), grain),
            )
            * cut
        )
        put(
            "scratch",
            n,
            s,
            y,
            0.6 / max(abs(y)),
            art="platter + crossfader",
            positions=travel,
        )
    x, sr = sf.read(ROOT / "examples/v6/foley/pipe.mp3", always_2d=True)
    x = x.mean(axis=1)[: round(sr * 0.37)]
    x *= np.minimum(1, np.arange(len(x))[::-1] / (0.025 * sr))
    for n, s in ((1, 12), (24, 12)):
        put("metal", n, s, x, 0.46 / max(abs(x)), art="CC0 pipe hit")
    # Gate the dominant chord in two short cuts before the first wall of guitars.
    for lane in ("left-di", "right-di", "lead-di"):
        for point in (13.25, 13.75):
            i = round((13 * 16 + point) * STEP * RATE)
            end = i + round(0.032 * RATE)
            wave = lanes[lane]
            wave[i - 96 : i] *= np.linspace(1, 0, 96)
            wave[i:end] = 0
            wave[end : end + 96] *= np.linspace(0, 1, 96)
    # Kill direct feeds before the 15 and 35 downbeats; this includes any drum sample ring.
    for n in (14, 34):
        end = round(n * BAR * RATE)
        cut = round((n * BAR - STEP * 0.60) * RATE)
        for y in lanes.values():
            y[cut - 240 : cut] *= np.linspace(1, 0, 240)
            y[cut:end] = 0
    for name, x in lanes.items():
        sf.write(a / (name + ".wav"), x, RATE, subtype="FLOAT")
    write_json(out / "events.json", events)
    return events
