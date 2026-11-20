"""Validate the chart, isolation renders, melody and hard bridge boundary."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from engine.daw.alt_rock import dbfs
from engine.daw.qa import levels
from engine.session.render import write_json
from scripts.heavy.band import BAR, RATE
from scripts.heavy.score import OUT, ROOTS, abc, root_name


def validate(plan, events):
    bars = plan["bars"]
    assert [b["bar"] for b in bars] == list(range(1, 49))
    assert abc(plan) == (OUT / "heavy.abc").read_text()
    roots = []
    resolutions = []
    tensions = []
    kick_locks = {}
    for b in bars:
        n = b["bar"]
        ch = b["chord_symbols"]
        r = ROOTS[root_name(ch)] % 12
        bass = [e for e in events if e["lane"] == "bass" and e["bar"] == n]
        assert bass[0]["midi"] % 12 == (2 if n == 24 else r)
        roots.append(bass[0]["midi"])
        lead = [e for e in events if e["lane"] == "lead-di" and e["bar"] == n]
        pitches = (
            [0, 7]
            if "5" in ch
            else [0, 4, 7, 10, 1]
            if "A7" in ch
            else [0, 3, 7, 2]
            if "m" in ch
            else [0, 4, 7]
        )
        for e in lead:
            if (e["midi"] - r) % 12 not in pitches:
                if e["length"] > 0.6:
                    raise ValueError(f"Sustained unplanned lead tone in bar {n}")
                tensions.append([n, e["midi"], round(e["length"], 3)])
            assert e["midi"] % 12 != 1 or "A7" in ch
            # Inspect overlap with an actual rhythm or bass event, in the same register.
            for comp in events:
                if comp["bar"] != n or comp["lane"] not in (
                    "left-di",
                    "right-di",
                    "bass",
                ):
                    continue
                overlap = min(
                    e["seconds"] + e["length"], comp["seconds"] + comp["length"]
                ) - max(e["seconds"], comp["seconds"])
                if abs(e["midi"] - comp["midi"]) == 1 and overlap > 0.4:
                    raise ValueError(
                        f"Long semitone cluster at bar {n}, {e['seconds']:.3f}"
                    )
        if n in (2, 6, 14, 26, 34, 38, 45):
            nxt = next(e for e in events if e["bar"] == n + 1 and e["lane"] == "bass")
            assert nxt["midi"] - bass[-1]["midi"] == 1
            resolutions.append([n, bass[-1]["midi"], nxt["midi"]])
        guitar = [e for e in events if e["lane"] == "left-di" and e["bar"] == n]
        if n in range(35, 39):
            assert not guitar and not lead
        kicks = {
            round(e["step"])
            for e in events
            if e["bar"] == n and e.get("voice") == "kick"
        }
        if 3 <= n <= 22 or 27 <= n <= 34 or 39 <= n <= 46:
            attacks = {round(e["step"]) for e in guitar}
            kick_locks[n] = sorted(kicks & attacks)
            if not kick_locks[n]:
                raise ValueError(f"No common guitar/kick accent at bar {n}")
        if ch.endswith("5"):
            assert all((e["midi"] - r) % 12 in (0, 7) for e in guitar)
    return {
        "bass_first_notes": roots,
        "semitone_resolutions": resolutions,
        "short_lead_tensions": tensions,
        "verified_bars": 48,
        "common_kick_and_guitar_accents_sixteenths": kick_locks,
        "long_same_register_semitones": 0,
    }


def bass_pitch(x, at, length):
    y = x[round((at + 0.04) * RATE) : round((at + length - 0.015) * RATE)].mean(axis=1)
    y = signal.resample_poly(y, 1, 8)
    f, p = signal.periodogram(y, 6000, window="hann", nfft=32768)
    ids = np.flatnonzero((f >= 29) & (f < 170))
    peaks = signal.find_peaks(p[ids])[0]
    if not len(peaks):
        return None
    strong = peaks[p[ids[peaks]] > p[ids[peaks]].max() * 0.14]
    return round(float(69 + 12 * np.log2(f[ids[strong[0]]] / 440)), 2)


def lead_bends(audio, events):
    """Compare early and held pitch near the written guitar fundamental in the actual solo print."""
    rows = []
    for e in events:
        if (
            e["lane"] != "lead-di"
            or not 27 <= e["bar"] <= 34
            or e["art"] not in ("bend", "feedback")
        ):
            continue
        target = 440 * 2 ** ((e["midi"] - 69) / 12)
        observed = []
        for offset in (0.014, 0.28):
            start = round((e["seconds"] + offset) * RATE)
            excerpt = audio[start : start + round(0.05 * RATE)].mean(axis=1)
            f, power = signal.periodogram(excerpt, RATE, window="hann", nfft=32768)
            band = np.flatnonzero((f >= target * 0.77) & (f <= target * 1.09))
            fundamental = f[band[np.argmax(power[band])]]
            observed.append(round(float(69 + 12 * np.log2(fundamental / 440)), 2))
        if abs(observed[1] - e["midi"]) > 0.65 or observed[1] - observed[0] < 0.8:
            raise ValueError(f"Unresolved lead bend at bar {e['bar']}: {observed}")
        rows.append(
            {"bar": e["bar"], "target": e["midi"], "early_and_sustained_midi": observed}
        )
    return rows


def verify(folder):
    plan = json.loads((OUT / "plan.json").read_text())
    events = json.loads((folder / "events.json").read_text())
    chart = validate(plan, events)

    def read(name):
        x, s = sf.read(folder / (name + ".wav"), dtype="float32", always_2d=True)
        assert s == RATE and x.shape[1] == 2 and np.isfinite(x).all()
        return x

    master = read("Iron Return")
    assert len(master) == round((48 * BAR + 1.65) * RATE)
    reopened = read("reopened/Iron Return")
    if not np.array_equal(master, reopened):
        raise ValueError("Reopen render differs")
    duo = read("Rhythm section")
    guitar = read("Guitars")
    window = slice(round(34 * BAR * RATE), round(38 * BAR * RATE))
    bridge_diff = float(np.max(np.abs(master[window] - duo[window])))
    if bridge_diff > 2e-5 or abs(guitar[window]).max() > 2e-5:
        raise ValueError(f"Guitar or return in bridge: {bridge_diff}")
    levels_by_bar = {}
    for name in ("Drums", "Bass", "Lead", "Guitars", "Iron Return"):
        x = read(name)
        levels_by_bar[name] = [
            round(dbfs(x[round(n * BAR * RATE) : round((n + 1) * BAR * RATE)]), 2)
            for n in range(48)
        ]
    for name in ("Drums", "Bass", "Lead"):
        if min(levels_by_bar[name][26:34]) < -42:
            raise ValueError(f"Missing solo part: {name}")
    if levels_by_bar["Guitars"][38] < -38:
        raise ValueError("Missing re-entry")
    bass = read("Bass")
    pitch_checks = []
    for n in (2, 6, 14, 26, 34, 35, 36, 37, 38, 39, 45, 46):
        row = [e for e in events if e["lane"] == "bass" and e["bar"] == n]
        e = row[-1] if n in (2, 6, 14, 26, 34, 45) else row[0]
        pitch_checks.append(
            {
                "bar": n,
                "expected": e["midi"],
                "observed": bass_pitch(bass, e["seconds"], e["length"]),
            }
        )
    for q in pitch_checks:
        if (
            q["observed"] is None
            or abs((q["observed"] - q["expected"] + 6) % 12 - 6) > 0.65
        ):
            raise ValueError(f"Rendered bass pitch: {q}")
    regions = [
        {
            "name": b["section"],
            "start": (b["bar"] - 1) * BAR,
            "end": (
                b["bar"] - 1 + sum(i["section"] == b["section"] for i in plan["bars"])
            )
            * BAR,
        }
        for b in plan["bars"]
        if b["bar"] == 1 or plan["bars"][b["bar"] - 2]["section"] != b["section"]
    ]
    metrics = levels(folder / "Iron Return.wav", regions)
    if metrics["clipped_samples"] or metrics["true_peak_dbtp"] > -1:
        raise ValueError(f"Headroom {metrics['true_peak_dbtp']}")
    edge = []
    for n in (14, 22, 26, 34, 38, 46):
        i = round(n * BAR * RATE)
        edge.append(
            {
                "after_bar": n,
                "boundary_sample_jump": float(max(abs(master[i] - master[i - 1]))),
                "local_peak_slope": float(
                    abs(np.diff(master[i - 480 : i + 480], axis=0)).max()
                ),
            }
        )
    q = {
        "chart": chart,
        "master": metrics,
        "reopen_pcm_identical": True,
        "bridge_max_master_minus_duo": bridge_diff,
        "bridge_guitar_peak": float(abs(guitar[window]).max()),
        "per_bar_dbfs": levels_by_bar,
        "rendered_bass_notes": pitch_checks,
        "rendered_solo_bends": lead_bends(read("Lead"), events),
        "transition_samples": edge,
        "sha256": hashlib.sha256((folder / "Iron Return.wav").read_bytes()).hexdigest(),
    }
    write_json(folder / "qa.json", q)
    return q


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("folder", type=Path)
    verify(cli.parse_args().folder)
