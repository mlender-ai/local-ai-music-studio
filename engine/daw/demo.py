"""Produce immutable reference, region-edit and source-edit versions of the soul session."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from engine.paths import DATA
from engine.rendering.audio import write_audio
from engine.session.bank import CACHE, select_sample
from engine.session.mixer import mix
from engine.session.render import voices_for, write_json

from . import edits, instruments, project, qa


def render_version(spec, change, folder):
    voices = voices_for(spec, spec["events"])
    dry, wet, master = mix(voices, spec["sample_rate"], spec["mixer"])
    audio = {
        "dry": sum(dry.values()),
        "premaster": sum(wet.values()),
        "session-preview": master,
        "keys-dry": dry["keys"],
        "keys-wet": wet["keys"],
    }
    if change and "bass" in change["tracks"]:
        for track in ("bass", "guitar"):
            audio[track + "-dry"] = dry[track]
    for label, x in audio.items():
        write_audio(folder / (label + ".wav"), x, spec["sample_rate"])
    write_json(folder / "session.json", spec)
    if change:
        write_json(folder / "edit.json", change)


def prepare(source, output):
    if output.exists() or not output.resolve().is_relative_to(DATA):
        raise ValueError("Choose an unused directory under MUSIC_DATA_DIR")
    output.parent.mkdir(parents=True, exist_ok=True)
    base = json.loads((source / "session.json").read_text())
    arranged, change_one = edits.edit(base, edits.ARRANGE)
    clarified, change_two = edits.edit(arranged, edits.CLARIFY)
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "session"
        stage.mkdir()
        reports = {}
        # The V1 take selector uses the original event index. Muting preserves it.
        for name, spec, change in (
            ("01-reference", base, None),
            ("02-region", arranged, change_one),
            ("03-keys", clarified, change_two),
        ):
            folder = stage / name
            folder.mkdir()
            render_version(spec, change, folder)
            reports[name] = {
                "project": project.export(spec, folder),
                "sources": qa.sources(spec),
                "audio": {
                    f.name: qa.levels(f, spec["sections"])
                    for f in sorted(folder.glob("*.wav"))
                },
            }
        reference = stage / "01-reference"
        reference_audio, sr = sf.read(reference / "session-preview.wav")
        legacy, _ = sf.read(source / "processed-mix.wav")
        if not np.array_equal(reference_audio, legacy):
            raise RuntimeError(
                "Reference no longer reproduces the original processed mix"
            )
        start, end = [round(n * 240 / 116 * sr) for n in (8, 12)]
        regional = {}
        for track in ("guitar", "bass"):
            old, _ = sf.read(source / "stems" / (track + ".wav"))
            new, _ = sf.read(stage / "02-region" / (track + "-dry.wav"))
            diff = new - old
            regional[track] = {
                "before_max": float(np.max(abs(diff[:start]))),
                "inside_rms": float(np.sqrt(np.mean(diff[start:end] ** 2))),
                "after_max": float(np.max(abs(diff[end:]))),
                "edited_track_inside_rms": float(np.sqrt(np.mean(new[start:end] ** 2))),
            }
        legacy_analysis = {
            p.name: qa.levels(p, base["sections"])
            for p in [
                source / "dry-mix.wav",
                source / "variation-b.wav",
                source / "processed-mix.wav",
                source / "final.wav",
            ]
        }
        checks = {
            "region_boundaries_frames": [start, end],
            "region_stem_difference": regional,
            "original_final_equals_processed": legacy_analysis["final.wav"][
                "pcm_sha256"
            ]
            == legacy_analysis["processed-mix.wav"]["pcm_sha256"],
            "reference_matches_original": True,
        }
        if regional["guitar"]["edited_track_inside_rms"] != 0 or any(
            m["before_max"] or m["after_max"] or not m["inside_rms"]
            for m in regional.values()
        ):
            raise RuntimeError(f"Unexpected out-of-region change: {regional}")
        write_json(
            stage / "qa.json",
            {
                "backend": "Session Engine preview",
                "versions": reports,
                "originals": legacy_analysis,
                "checks": checks,
            },
        )
        raw = stage / "raw"
        raw.mkdir()
        for track in ("drums", "bass", "guitar", "keys"):
            e = next(
                e
                for e in clarified["events"]
                if e["track"] == track and not e.get("muted")
            )
            p = e["notes"][0]
            if track == "keys" and clarified.get("keyboard_mapping"):
                *_, source_path, digest = instruments.key_region(
                    p, e["velocity"], clarified["keyboard_mapping"]
                )
            else:
                *_, source_path, digest = select_sample(
                    track, e["voice"], p, e["velocity"], clarified["events"].index(e)
                )
            samples, rate = sf.read(CACHE / digest, always_2d=True)
            sf.write(raw / (track + ".wav"), samples, rate, subtype="FLOAT")
            write_json(
                raw / (track + ".json"),
                {
                    "original": source_path,
                    "blob": digest,
                    "author": base["sources"][track]["author"],
                    "license": base["sources"][track]["license"],
                },
            )
        write_json(stage / "credits.json", base["sources"])
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DATA / "session-engine")
    parser.add_argument("--out", type=Path, default=DATA / "daw-session")
    args = parser.parse_args()
    prepare(args.source.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
