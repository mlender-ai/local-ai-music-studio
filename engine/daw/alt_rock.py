"""Build a portable audio-only REAPER project from the V5 YuE2 performance."""

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from engine.session.render import write_json

from .host import build_in_host, isolated_host
from .qa import levels

RATE = 48000
SECTIONS = (
    ("Intro", 0),
    ("Verse", 4),
    ("Pre-chorus", 12),
    ("Chorus", 16),
    ("Break", 24),
    ("Solo cue", 28),
    ("Final chorus", 36),
    ("Outro", 44),
)
STEMS = {
    name: label
    for name, label in (
        ("vocals", "Vocals · separated estimate"),
        ("drums", "Drums · separated estimate"),
        ("bass", "Bass · separated estimate"),
        ("guitar", "Guitar · separated estimate"),
        ("piano", "Keys · separated estimate"),
        ("other", "Other · separated estimate"),
    )
}
DIRECTIONS = {
    "기타 솔로를 더 날카롭고 공격적으로 만들어줘": {
        "lead_presence": 3.4,
        "lead_db": -12,
    },
    "후렴이 시작되면 기타 공간이 갑자기 넓어지게 해줘": {
        "chorus_wet_db": 1.5,
        "chorus_width": 155,
    },
    "보컬은 더 가까이 들리고 기타는 멀리서 울리는 느낌으로 해줘": {
        "vocal_db": 0.85,
        "plate_db": -26,
        "haze_db": -15,
    },
}


def read(path):
    info = sf.info(path)
    if info.channels != 2 or not 0 < info.duration <= 124:
        raise ValueError(f"Expected bounded stereo audio: {path}")
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    if not np.isfinite(x).all():
        raise ValueError(f"Nonfinite PCM in {path}")
    return x, sr


def dbfs(x):
    return float(10 * np.log10(max(np.mean(x * x, dtype=np.float64), 1e-20)))


def aligned(path, n):
    """Resample an estimate to the mix raster, permitting only rounding at EOF."""
    x, sr = read(path)
    if sr != RATE:
        gcd = math.gcd(sr, RATE)
        x = resample_poly(x, RATE // gcd, sr // gcd, axis=0)
    if abs(len(x) - n) > 4:
        raise ValueError(f"Stem is not time-aligned with the source: {path}")
    return np.pad(x[:n], ((0, max(0, n - len(x))), (0, 0)))


def regions(bpm, duration):
    sheet = [(name, bar * 240 / bpm) for name, bar in SECTIONS]
    return [
        dict(name=name, start=start, end=end)
        for (name, start), (_, end) in zip(sheet, sheet[1:] + [("end", duration)])
    ]


def split_report(source, folders, sections, audio):
    diagnostics = {}
    for folder in folders:
        sources = sorted(folder.glob("*.wav"))
        expected = (
            set(STEMS)
            if folder.name == "htdemucs_6s"
            else {"vocals", "drums", "bass", "other"}
        )
        if {path.stem for path in sources} != expected:
            raise ValueError(f"Unexpected stem inventory: {folder}")
        residual = source.copy()
        stats = {}
        for path in sources:
            x = aligned(path, len(source))
            residual -= x
            stats[path.stem] = {
                "rms_dbfs": dbfs(x),
                "section_dbfs": {
                    part["name"]: dbfs(
                        x[round(part["start"] * RATE) : round(part["end"] * RATE)]
                    )
                    for part in sections
                },
            }
            if folder.name == "htdemucs_6s":
                sf.write(audio / path.name, x, RATE, subtype="FLOAT")
        diagnostics[folder.name] = {
            "sum_error_vs_mix_db": dbfs(residual) - dbfs(source),
            "stems": stats,
            "resources": json.loads((folder / "resources.json").read_text()),
        }
        if folder.name == "htdemucs_6s":
            sf.write(audio / "residual.wav", residual, RATE, subtype="FLOAT")
    return diagnostics


def render(project, args, log):
    subprocess.run(
        [*args, "-renderproject", str(project)],
        check=True,
        timeout=300,
        stdout=log,
        stderr=log,
    )


def produce(source, stems, output, bpm, master_db, direction="", lead=None):
    if not (0 < bpm <= 200 and -12 <= master_db <= 6):
        raise ValueError("Invalid score tempo or master trim")
    revision = direction.strip().rstrip(".!?")
    if revision and revision not in DIRECTIONS:
        raise ValueError("This production accepts the three documented mix directions")
    if revision.startswith("기타 솔로") and not lead:
        raise ValueError("Confirm a guitar passage before requesting lead EQ")
    if revision.startswith("보컬") and not stems:
        raise ValueError("Vocal treatment requires a vocal estimate")
    source_audio, rate = read(source)
    if rate != RATE:
        raise ValueError("Expected the 48 kHz YuE2 output")
    duration = len(source_audio) / RATE
    sections = regions(bpm, duration)
    if any(s["end"] <= s["start"] for s in sections):
        raise ValueError("Source ended before the last planned region")
    if lead and not (stems and 0 <= lead[0] < lead[1] <= duration):
        raise ValueError(
            "Lead focus requires a valid guitar excerpt and separated tracks"
        )

    output.mkdir(parents=True, exist_ok=False)
    audio = output / "Audio"
    audio.mkdir()
    shutil.copyfile(source, output / "YuE2 Original.wav")
    if stems:
        diagnostics = split_report(
            source_audio, [stems / "htdemucs_6s", stems / "htdemucs"], sections, audio
        )
        tracks = STEMS | {"residual": "Residual · original minus estimates"}
    else:
        diagnostics = {}
        shutil.copyfile(source, audio / "stereo.wav")
        tracks = {"stereo": "YuE2 stereo"}
    settings = dict(
        bpm=bpm,
        source_seconds=duration,
        tail=2.0,
        master_db=master_db,
        vocal_db=0.45,
        plate_db=-26,
        haze_db=-18,
        chorus_wet_db=-2,
        chorus_width=110,
        lead_start=0,
        lead_end=0,
        lead_presence=2.1,
        lead_db=-16,
    )
    if lead:
        settings.update(lead_start=lead[0], lead_end=lead[1])
    settings.update(DIRECTIONS.get(revision, {}))
    rows = [f"setting\t{key}\t{value:.10f}" for key, value in settings.items()]
    rows += [f"track\t{key}\t{value}" for key, value in tracks.items()]
    for part in sections:
        rows.append(f"region\t{part['name']}\t{part['start']:.10f}\t{part['end']:.10f}")
    (output / "mix.tsv").write_text("\n".join(rows) + "\n")
    script = output / "build.lua"
    shutil.copyfile(Path(__file__).with_suffix(".lua"), script)
    project = output / "METALLIC DREAM.RPP"
    final = output / "METALLIC DREAM - Final Master.wav"
    replay = output / "reopen"
    with isolated_host() as args, (output / "host.log").open("w") as log:
        host = build_in_host(args, script, log)
        for path in (output / "Dry.RPP", project):
            text = path.read_text().replace(str(audio) + "/", "Audio/")
            path.write_text(text)
            render(path, args, log)
        replay.mkdir()
        (replay / "Audio").symlink_to(audio, target_is_directory=True)
        shutil.copy2(project, replay / project.name)
        render(replay / project.name, args, log)

    dry, rate = read(output / "Dry.wav")
    if rate != RATE or dry.shape != source_audio.shape:
        raise RuntimeError("Dry check changed duration or sample rate")
    master, rate = read(final)
    reopened, _ = read(replay / final.name)
    if rate != RATE or len(master) != len(source_audio) + round(
        settings["tail"] * RATE
    ):
        raise RuntimeError("Master render length mismatch")
    if not np.array_equal(master, reopened):
        raise RuntimeError("REAPER reopen render changed the mix")
    measurements = levels(final, sections)
    if measurements["true_peak_dbtp"] > -1.0 or measurements["clipped_samples"]:
        raise RuntimeError(
            "Master needs more peak headroom; rerender with a lower master trim"
        )
    original = levels(source, sections)
    write_json(
        output / "production.json",
        {
            "host": host.splitlines(),
            "settings": settings,
            "direction": revision or None,
            "sample_rate": RATE,
            "score_regions": sections,
            "dry_error_vs_original_db": dbfs(dry - source_audio) - dbfs(source_audio),
            "reopen_pcm_identical": True,
            "original": original,
            "master": measurements,
            "stem_diagnostics": diagnostics,
            "end_rms_dbfs": {
                "original": dbfs(source_audio[-4800:]),
                "master": dbfs(master[-4800:]),
            },
        },
    )
    return final


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("--stems", type=Path)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--master-db", type=float, default=-3)
    cli.add_argument("--direction", default="")
    cli.add_argument("--lead", nargs=2, type=float, metavar=("START", "END"))
    args = cli.parse_args()
    print(
        produce(
            args.source.resolve(),
            args.stems and args.stems.resolve(),
            args.out.resolve(),
            112,
            args.master_db,
            args.direction,
            args.lead,
        )
    )
