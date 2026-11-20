"""Edit the generated performance against the bar chart, then print the REAPER session."""

import argparse
import itertools
import json
import re
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw.alt_rock import dbfs, render
from engine.daw.host import build_in_host, isolated_host
from engine.daw.qa import levels
from engine.paths import ROOT
from engine.rendering.rhythm import _candidates
from engine.session.render import write_json
from scripts.heavy.band import BAR, RATE, perform
from scripts.heavy.score import OUT, ROOTS, root_name
from scripts.v6_arrange import onset_grid

TRACKS = [
    ("original", "YuE2 original - muted reference", 0, 0),
    ("generated-guitar", "YuE2 guitar estimate - harmonic edits", -4, 0),
    ("generated-drums", "YuE2 kit estimate - grid edits", -5, 0),
    ("left-di", "Recorded guitar samples - left rhythm DI", -17, -0.70),
    ("right-di", "Recorded guitar samples - right rhythm DI", -18, 0.69),
    ("lead-di", "Recorded lead DI - bends and feedback", -20, -0.05),
    ("kit", "Performed kit - accents and toms", -2, 0),
    ("bass", "Performed electric bass", 7, 0),
    ("scratch", "Turntable simulation - guitar cut", -12, -0.17),
    ("metal", "Recorded pipe - two hits", -15, 0.24),
]
CONTROLS = ("Drums", "Bass", "Lead", "Guitars", "Rhythm section")


def harmony_profile(x, sr):
    x = x.mean(axis=1)
    freq, psd = signal.welch(x, sr, nperseg=min(len(x), 8192), nfft=16384)
    peaks = signal.find_peaks(psd)[0]
    peaks = peaks[(freq[peaks] > 65) & (freq[peaks] < 1650)]
    classes = np.rint(69 + 12 * np.log2(freq[peaks] / 440)).astype(int) % 12
    chroma = np.bincount(classes, weights=psd[peaks] ** 0.66, minlength=12)
    return chroma / max(chroma.sum(), 1e-30)


def edits(source, folder, plan):
    guitar, rate = sf.read(folder / "guitar.wav", dtype="float32", always_2d=True)
    drums, sr = sf.read(folder / "drums.wav", dtype="float32", always_2d=True)
    assert sr == rate and len(guitar) == len(drums)
    if abs(sf.info(source).duration - len(drums) / sr) > 0.005:
        raise ValueError("Stem and source lengths disagree")
    mono = (
        signal.resample_poly(drums.mean(axis=1), 40, 147)
        if sr == 44100
        else signal.resample_poly(drums.mean(axis=1), 1, 4)
    )
    _, _, spectrum = signal.stft(mono, 12000, nperseg=512, noverlap=392)
    candidates = _candidates(np.maximum(0, np.diff(abs(spectrum), axis=1)).sum(axis=0))
    strong = [
        c["bpm"]
        for c in candidates
        if c["strength"] >= max(0.1, candidates[0]["strength"] * 0.82)
    ]
    bpm = (
        min(strong, key=lambda value: abs(value - plan["bpm"]))
        if strong
        else (candidates[0]["bpm"] if candidates else plan["bpm"])
    )
    # A syncopated take can put dotted notes above the quarter note. Use the chart
    # only when its pulse is independently present and another measured peak corroborates it.
    quarter = next(
        (
            c
            for c in candidates
            if abs(c["bpm"] / plan["bpm"] - 1) < 0.025 and c["strength"] >= 0.1
        ),
        None,
    )
    if quarter and any(
        abs(c["bpm"] / quarter["bpm"] - ratio) < 0.02
        for c in candidates
        for ratio in (2 / 3, 4 / 3, 0.5, 2)
    ):
        bpm = quarter["bpm"]
    if bpm < 80:
        bpm *= 2
    if bpm > 152:
        bpm /= 2
    aligned = signal.resample_poly(drums, 160, 147, axis=0) if sr == 44100 else drums
    assert sr in (44100, RATE)
    beats, measured, _ = onset_grid(aligned, bpm)
    # Determine the most likely first downbeat from bass-drum energy on alternating beats.
    low = signal.sosfilt(signal.butter(3, 115, fs=sr, output="sos"), drums.mean(axis=1))
    phases = []
    for k in range(4):
        powers = [
            np.mean(low[int(t * sr) : int(t * sr) + round(0.09 * sr)] ** 2)
            for t in beats[k::4]
            if 0 <= t < len(low) / sr - 0.10
        ]
        phases.append(np.mean(powers) if powers else 0)
    phase = int(np.argmax(phases)) if max(phases) > 1.35 * phases[0] else 0
    windows = []
    for i in range(phase, len(beats) - 4, 4):
        a, b = max(0.0, beats[i]), beats[i + 4]
        if b > len(guitar) / sr:
            break
        sl = slice(round(a * sr), round(b * sr))
        windows.append(
            {
                "index": len(windows),
                "offset": float(a),
                "span": float(b - a),
                "guitar": dbfs(guitar[sl]),
                "drums": dbfs(drums[sl]),
                "chroma": harmony_profile(guitar[sl], sr),
            }
        )
    if len(windows) < 8:
        raise ValueError("Too few complete performance bars")
    decisions = []
    prev = -2
    last_drum = -2
    for b in plan["bars"]:
        n = b["bar"]
        ch = b["chord_symbols"]
        root = ROOTS[root_name(ch)] % 12
        if 35 <= n <= 38:
            continue
        target = round((n - 1) * (len(windows) - 1) / 47)
        if n > 2 and n < 48 and n != 24:
            close = [w for w in windows if abs(w["index"] - target) <= 6]
            w = max(
                close,
                key=lambda w: (
                    min(w["drums"], -20)
                    - 1.2 * abs(w["index"] - target)
                    + 2.5 * (w["index"] == last_drum + 1)
                    - 2.0 * (w["index"] == last_drum)
                ),
            )
            if w["drums"] > -39:
                last_drum = w["index"]
                decisions.append(
                    {
                        "lane": "generated-drums",
                        "bar": n,
                        "source_bar": w["index"] + 1,
                        "offset": w["offset"],
                        "rate": w["span"] / BAR,
                        "pitch": 0,
                        "db": -5 if n in (23, 25, 26) else -1,
                    }
                )
        if n in (2, 14, 24, 26, 34, 38, 45):
            continue
        allowed = (
            [0, 7]
            if "5" in ch or ch == "Dped"
            else [0, 4, 7, 10]
            if "A7" in ch
            else [0, 3, 7]
            if "m" in ch
            else [0, 4, 7]
        )
        pcs = [(root + k) % 12 for k in allowed]

        def match(w, shift, pcs=pcs, root=root):
            c = np.roll(w["chroma"], shift)
            return float(c[pcs].sum()), float(c[root])

        options = []
        for w in windows:
            if w["guitar"] < -39:
                continue
            for shift in (-2, -1, 0, 1, 2):
                fit, rootmass = match(w, shift)
                rank = (
                    fit
                    + 0.16 * rootmass
                    - 0.035 * abs(shift)
                    - 0.006 * abs(w["index"] - target)
                    + 0.13 * (w["index"] == prev + 1)
                )
                options.append((rank, w["index"], shift, fit))
        if not options:
            continue
        _, idx, shift, fit = max(options)
        w = windows[idx]
        if fit < 0.54:
            continue
        prev = idx
        decisions.append(
            {
                "lane": "generated-guitar",
                "bar": n,
                "source_bar": idx + 1,
                "offset": w["offset"],
                "rate": w["span"] / BAR,
                "pitch": shift,
                "chord_energy_share": fit,
                "db": -8
                if 27 <= n <= 34
                else -2
                if 15 <= n <= 22 or 39 <= n <= 46
                else -5,
            }
        )
    return decisions, {
        "pulse_bpm": measured,
        "initial_grid_candidate_bpm": bpm,
        "downbeat_phase": phase,
        "complete_bars": len(windows),
        "unconstrained_pulse": candidates,
    }


def build(source, stems, output, trim, tracking=None):
    source = source.resolve()
    output = output.resolve()
    stems = stems.resolve()
    plan = json.loads((OUT / "plan.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    a = output / "Audio"
    if tracking:
        shutil.copytree(tracking / "Audio", a)
        shutil.copyfile(tracking / "events.json", output / "events.json")
    else:
        perform(plan, output)
    shutil.copy2(source, a / "original.wav")
    for name in ("drums", "guitar"):
        shutil.copy2(stems / (name + ".wav"), a / ("generated-" + name + ".wav"))
    decisions, grid = edits(source, stems, plan)
    write_json(output / "edits.json", {"grid": grid, "edits": decisions})
    rows = [["trim", trim], *[["track", *row] for row in TRACKS]]

    def item(key, pos, length, offset, rate=1, pitch=0, db=0, edge=0.002):
        rows.append(["item", key, key, pos, length, offset, rate, pitch, db, edge])

    item("original", 0, sf.info(source).duration, 0)
    for section, bars in itertools.groupby(plan["bars"], key=lambda b: b["section"]):
        group = list(bars)
        rows.append(["region", section, group[0]["bar"], group[-1]["bar"]])
    ev = json.loads((output / "events.json").read_text())
    for b in plan["bars"]:
        n = b["bar"]
        pos = (n - 1) * BAR
        rows.append(["bar", n, b["chord_symbols"]])
        for lane, *_ in TRACKS[3:]:
            if any(e["lane"] == lane and e["bar"] == n for e in ev):
                item(lane, pos, BAR + (1.5 if n == 48 else 0), pos, edge=0.0008)
    for d in decisions:
        n = d["bar"]
        span = BAR - (0.09 if n in (14, 34) else 0)
        item(
            d["lane"],
            (n - 1) * BAR,
            span,
            d["offset"],
            d["rate"],
            d["pitch"],
            d["db"],
            0.025 if d["lane"].endswith("guitar") else 0.006,
        )
    (output / "layout.tsv").write_text(
        "".join("\t".join(map(str, row)) + "\n" for row in rows)
    )
    for name in ("rock_fx", "iron_return"):
        shutil.copyfile(ROOT / f"engine/daw/{name}.lua", output / f"{name}.lua")
    with isolated_host() as args, (output / "host.log").open("w") as log:
        build_in_host(args, output / "iron_return.lua", log)
        calibration = output / "Headroom.RPP"
        base = (output / "Iron Return.RPP").read_text().replace(str(a) + "/", "Audio/")
        calibration.write_text(
            base.replace('RENDER_PATTERN "Iron Return"', 'RENDER_PATTERN "Headroom"')
        )
        render(calibration, args, log)
        meter = levels(output / "Headroom.wav")
        if meter["clipped_samples"]:
            raise ValueError("Calibration clipped; reduce initial trim")
        adjustment = min(
            -1.6 - meter["true_peak_dbtp"], -14.5 - meter["integrated_lufs"]
        )
        gain = 10 ** ((trim + adjustment) / 20)
        write_json(
            output / "gain.json",
            {
                "measured_true_peak": meter["true_peak_dbtp"],
                "measured_lufs": meter["integrated_lufs"],
                "initial_trim_db": trim,
                "final_trim_db": trim + adjustment,
            },
        )
        for name in ("Iron Return", *CONTROLS):
            rpp = output / (name + ".RPP")
            text = rpp.read_text().replace(str(a) + "/", "Audio/")
            text, count = re.subn(
                r"(?m)^(  MASTER_VOLUME )[^ ]+", lambda m: m[1] + str(gain), text
            )
            if count != 1:
                raise ValueError("Expected one master gain")
            rpp.write_text(text)
            render(rpp, args, log)
        moved = output / "reopened"
        moved.mkdir()
        (moved / "Audio").symlink_to(a, target_is_directory=True)
        rpp = output / "Iron Return.RPP"
        shutil.copyfile(rpp, moved / rpp.name)
        render(moved / rpp.name, args, log)
    return output


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for k in ("source", "stems", "out"):
        cli.add_argument(k, type=Path)
    cli.add_argument("--trim", type=float, default=-18)
    cli.add_argument("--tracking", type=Path)
    args = cli.parse_args()
    print(build(args.source, args.stems, args.out, args.trim, args.tracking))
