"""Reproducible session bounce from a saved score, mixer and pinned sample bank."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from scipy.signal import welch
from engine.paths import DATA, ROOT
from engine.music_plan import MusicPlan
from engine.rendering.audio import metrics, write_audio
from .bank import BANKS, note
from .score import TRACKS, CHART, SECTIONS, compose
from .mixer import MIX, mix


def write_json(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def specification(plan):
    beat = 60 / plan.rhythm.bpm
    return dict(
        version=1,
        music_plan=plan.model_dump(),
        sample_rate=48000,
        frames=round((56 * beat + 1.0344827586) * 48000),
        mixer=MIX,
        sources={
            k: {a: b for a, b in bank.items() if a != "samples"}
            for k, bank in BANKS.items()
        },
        bank_digest=hashlib.sha256(
            Path(__file__).with_name("banks.json").read_bytes()
        ).hexdigest(),
        events=compose(plan),
        variation_events=compose(plan, True),
        chart=CHART,
        sections=[
            dict(name=name, first=a, last=b, start=(a - 1) * 4 * beat, end=b * 4 * beat)
            for name, a, b in SECTIONS
        ],
    )


def voices_for(spec, events, note_renderer=None):
    if note_renderer is None:
        if spec.get("keyboard_mapping"):
            from engine.daw.instruments import renderer_for

            note_renderer = renderer_for(spec["keyboard_mapping"])
        else:
            note_renderer = note
    sr = spec["sample_rate"]
    frames = spec["frames"]
    step = 15 / spec["music_plan"]["rhythm"]["bpm"]
    voices = {v: np.zeros(frames) for v in spec["mixer"]["levels"]}
    for i, e in enumerate(events):
        if e.get("muted"):
            continue
        duration = e["length"] * step
        rel = {"drums": 0.067, "guitar": 0.018, "keys": 0.21, "bass": 0.036}[e["track"]]
        pitches = e["notes"][::-1] if e["art"] == "up" else e["notes"]
        for j, pitch in enumerate(pitches):
            offset = (
                j * 0.005
                if e["voice"] == "guitar"
                else j * 0.002
                if e["voice"] == "keys"
                else 0
            )
            start = round((((e["bar"] - 1) * 16 + e["step"]) * step + offset) * sr)
            y = note_renderer(
                e["track"],
                e["voice"],
                pitch,
                e["velocity"],
                i + j,
                duration,
                rel,
                sr,
                e["art"] == "slide",
            )
            if e["art"] == "mute":
                y *= np.exp(-np.arange(len(y)) / (0.035 * sr))
            n = min(len(y), frames - start)
            voices[e["voice"]][start : start + n] += y[:n] / len(pitches) ** 0.55
    return voices


def analyze(x, sr):
    report = metrics(x, sr)
    f, p = welch(x, fs=sr, nperseg=4096, axis=0)
    p = p.mean(axis=1)
    for name, lo, hi in [
        ("low_mid_fraction", 180, 500),
        ("presence_fraction", 2000, 6000),
        ("air_fraction", 6000, 16000),
    ]:
        report[name] = float(p[(f >= lo) & (f < hi)].sum() / max(1e-20, p.sum()))
    report["lr_correlation"] = float(np.corrcoef(x.T)[0, 1])
    report["crest_db"] = report["peak_dbfs"] - report["rms_dbfs"]
    report["mono_fold_db"] = float(
        10 * np.log10(np.mean(x.mean(axis=1) ** 2) / np.mean(x**2))
    )
    return report


def bounce(spec, output):
    if output.exists():
        raise ValueError(f"Choose an unused output directory: {output}")
    if (
        spec["version"] != 1
        or spec["sample_rate"] != 48000
        or not 1 <= spec["frames"] <= 48_000 * 120
    ):
        raise ValueError("Unsupported or oversized session.")
    if any(len(spec[key]) > 4096 for key in ("events", "variation_events")):
        raise ValueError("Session event budget exceeded.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if (
        spec["bank_digest"]
        != hashlib.sha256(
            Path(__file__).with_name("banks.json").read_bytes()
        ).hexdigest()
    ):
        raise ValueError("Sample bank changed.")
    if spec.get("keyboard_mapping"):
        from engine.daw.instruments import prepare_keys

        prepare_keys(spec["events"] + spec["variation_events"], spec["keyboard_mapping"])
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "session"
        stage.mkdir()
        sr = spec["sample_rate"]
        reports = {}
        cfg = spec["mixer"]

        def save(filename, x):
            reports[filename] = analyze(x, sr)
            write_audio(stage / filename, x, sr)

        for variant, key in enumerate(("events", "variation_events")):
            voices = voices_for(spec, spec[key])
            dry, wet, master = mix(voices, sr, cfg)
            if not variant:
                for track in TRACKS:
                    save(f"stems/{track}.wav", dry[track])
                    save(f"wet/{track}.wav", wet[track])
                save("dry-mix.wav", sum(dry.values()))
                save("processed-mix.wav", master)
                save("final.wav", master)
            else:
                save("variation-b.wav", master)
            del voices, dry, wet, master
        write_json(stage / "session.json", spec)
        write_json(
            stage / "arrangement.json",
            dict(chart=spec["chart"], sections=spec["sections"]),
        )
        (stage / "qa").mkdir()
        write_json(stage / "qa/audio-analysis.json", reports)
        (stage / "qa/session-report.md").write_text(
            "# Session Engine V1\n\n14 bars at "
            + str(spec["music_plan"]["rhythm"]["bpm"])
            + " BPM. Wet stems include their room return, before master compression. Dry and produced use the same events. Variation uses the same mixer. Listening verdict pending.\n\nElectric piano samples by Greg Sullivan (Wurlitzer EP200), CC BY 3.0, SFZ mapping by kinwie. Samples pitched, enveloped and mixed. See session.json for pinned source repositories.\n"
        )
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--music-plan", type=Path, default=ROOT / "examples/director/soul.json"
    )
    g.add_argument("--session", type=Path)
    parser.add_argument("--out", type=Path, default=DATA / "session-engine")
    args = parser.parse_args()
    spec = (
        json.loads(args.session.read_text())
        if args.session
        else specification(MusicPlan.model_validate_json(args.music_plan.read_text()))
    )
    bounce(spec, args.out.resolve())
    if args.out.resolve() == (DATA / "session-engine").resolve():
        from .catalog import register

        register()


if __name__ == "__main__":
    main()
