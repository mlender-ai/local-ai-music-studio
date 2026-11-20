"""Render the RUSTED SUNLIGHT arrangement, master and relocated verification copy."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.daw.alt_rock import RATE, aligned, dbfs, read, render
from engine.daw.host import build_in_host, isolated_host
from engine.daw.qa import levels
from engine.paths import ROOT
from engine.session.render import write_json
from scripts.v5_verify import pitch_screen
from scripts.v6_arrange import (
    SECTIONS,
    arrange,
    guitar_answers,
    onset_grid,
    prepare_samples,
)


def produce(source, stems, cues, output):
    config = json.loads(cues.read_text())
    original, rate = read(source)
    if (
        rate != RATE
        or hashlib.sha256(source.read_bytes()).hexdigest() != config["source_sha256"]
    ):
        raise ValueError(
            "Cue sheet requires the exact screened 48 kHz instrumental take"
        )
    duration = len(original) / RATE
    duration_out = duration + config["tail"]
    if not 90 <= duration_out <= 110:
        raise ValueError("Outside the bounded V6 production length")
    output.mkdir(parents=True, exist_ok=False)
    audio = output / "Audio"
    audio.mkdir()
    shutil.copy2(source, audio / "original.wav")
    tracks = {}
    remainder = original.copy()
    for name in ("drums", "bass", "guitar"):
        stem = aligned(stems / "htdemucs_6s" / f"{name}.wav", len(original))
        tracks[name] = stem
        remainder -= stem
        sf.write(audio / f"{name}.wav", stem, RATE, subtype="FLOAT")
    sf.write(audio / "remainder.wav", remainder, RATE, subtype="FLOAT")
    summed = remainder + tracks["guitar"] + tracks["bass"] + tracks["drums"]
    reconstruction = dbfs(summed - original) - dbfs(original)
    beats, bpm, onsets = onset_grid(tracks["drums"], config["pulse_hint_bpm"])
    anchors = config["section_first_beats"]
    if (
        len(anchors) != len(SECTIONS)
        or anchors != sorted(set(anchors))
        or anchors[0] != 0
        or anchors[-1] >= len(beats) - 2
    ):
        raise ValueError("Invalid section cues for this performance")
    sections = []
    for idx, (name, first) in enumerate(zip(SECTIONS, anchors)):
        end_beat = (
            anchors[idx + 1]
            if idx + 1 < len(anchors)
            else int(np.searchsorted(beats, duration))
        )
        sections.append(
            {
                "name": name,
                "first_beat": first,
                "limit_beat": end_beat,
                "start": 0 if idx == 0 else float(beats[first]),
                "end": duration if idx == len(anchors) - 1 else float(beats[end_beat]),
            }
        )
    catalog = prepare_samples(audio)
    events, notes = arrange(beats, sections, audio, tracks["guitar"], tracks["bass"])
    answers = guitar_answers(beats, sections, tracks["guitar"])
    for row in catalog:
        row["placements_seconds"] = [
            round(e["seconds"], 4)
            for e in events
            if e["source"] == Path(row["file"]).stem
        ]
    write_json(output / "sample-manifest.json", catalog)
    write_json(
        output / "events.json",
        {
            "sections": sections,
            "events": events,
            "synth": notes,
            "guitar_answers": answers,
        },
    )
    rows = [
        ["setting", k, v]
        for k, v in {
            "bpm": bpm,
            "duration": duration,
            "tail": config["tail"],
            "trim": config["master_trim_db"],
        }.items()
    ]
    rows += [["region", s["name"], s["start"], s["end"]] for s in sections]
    rows += [
        [
            "item",
            *(e[k] for k in ("source", "seconds", "duration", "db", "pan", "rate")),
        ]
        for e in events
    ]
    rows += [
        ["synth", *(n[k] for k in ("seconds", "end", "midi", "velocity"))]
        for n in notes
    ]
    rows += [
        [
            "guitar",
            *(e[k] for k in ("seconds", "duration", "db", "pan", "rate", "offset")),
        ]
        for e in answers
    ]
    (output / "session.tsv").write_text(
        "".join("\t".join(map(str, row)) + "\n" for row in rows)
    )
    for name in ("rock_fx", "rusted_sunlight"):
        shutil.copyfile(ROOT / f"engine/daw/{name}.lua", output / f"{name}.lua")
    final_name = "RUSTED SUNLIGHT"
    replay = output / "reopen"
    replay.mkdir()
    (replay / "Audio").symlink_to(audio, target_is_directory=True)
    with isolated_host() as args, (output / "host.log").open("w") as log:
        host = build_in_host(args, output / "rusted_sunlight.lua", log)
        for name in ("Arrangement", final_name):
            project = output / f"{name}.RPP"
            project.write_text(project.read_text().replace(str(audio) + "/", "Audio/"))
            render(project, args, log)
        shutil.copy2(project, replay / project.name)
        render(replay / project.name, args, log)
    master = output / f"{final_name}.wav"
    wet, sr = read(master)
    dry, _ = read(output / "Arrangement.wav")
    repeat, _ = read(replay / master.name)
    if (
        sr != RATE
        or not np.array_equal(wet, repeat)
        or abs(len(wet) / RATE - duration_out) > 1 / RATE
    ):
        raise RuntimeError("Render changed on reopening or has incorrect length")
    metrics = levels(master, sections)
    if (
        metrics["true_peak_dbtp"] > -1.0
        or metrics["clipped_samples"]
        or np.array_equal(wet, dry)
    ):
        raise RuntimeError("Peak headroom or processing check failed")
    strong = onsets[(onsets >= beats[anchors[1]]) & (onsets < beats[anchors[-1]])]
    grid_to_onset = [min(abs(strong - t)) for t in beats[anchors[1] : anchors[-1]]]
    lead = sections[5]
    residuals = {
        s["name"]: round(
            dbfs(
                wet[round(s["start"] * RATE) : round(s["end"] * RATE)]
                - dry[round(s["start"] * RATE) : round(s["end"] * RATE)]
            ),
            2,
        )
        for s in sections
    }
    report = {
        "host": host.splitlines(),
        "bpm": bpm,
        "dry_stem_sum_error_relative_db": reconstruction,
        "reference": levels(source, sections),
        "arrangement": levels(output / "Arrangement.wav", sections),
        "master": metrics,
        "section_fx_difference_dbfs": residuals,
        "drum_grid_nearest_transient_median_ms": float(np.median(grid_to_onset) * 1000),
        "guitar_lead_periodicity": pitch_screen(
            tracks["guitar"], lead["start"], lead["end"]
        ),
        "reopen_pcm_identical": True,
        "master_duration_seconds": len(wet) / RATE,
        "stereo_correlation": float(np.corrcoef(wet.T)[0, 1]),
        "tail_first_half_second_dbfs": dbfs(
            wet[len(original) : len(original) + RATE // 2]
        ),
        "tail_last_100ms_dbfs": dbfs(wet[-RATE // 10 :]),
        "foley_events": len(events),
        "synth_answers": len(notes),
    }
    write_json(output / "production.json", report)
    return master


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "stems", "cues", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    print(
        produce(
            *(v.resolve() for v in (args.source, args.stems, args.cues, args.output))
        )
    )
