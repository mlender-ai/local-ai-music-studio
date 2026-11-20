"""Run the bundled ReaScript against a fresh copy of a validated score snapshot."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from engine.dsp.chain import process
from engine.paths import DATA, RUNTIME
from engine.rendering.audio import write_audio
from engine.session.render import write_json

from . import project, qa
from .portable import make_portable


def executable():
    for app in (
        RUNTIME / "REAPER.app",
        Path("/Applications/REAPER.app"),
        Path.home() / "Applications/REAPER.app",
    ):
        binpath = app / "Contents/MacOS/REAPER"
        if binpath.is_file() and os.access(binpath, os.X_OK):
            return binpath
    return None


@contextmanager
def isolated_host():
    binary = executable()
    if not binary:
        raise RuntimeError(
            "Official REAPER.app was not found. No host render was started."
        )
    profile = RUNTIME / "reaper-render-profile"
    profile.mkdir(parents=True, exist_ok=True)
    with (profile / "render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = profile / "reaper.ini"
        if not config.exists():
            # REAPER's own macOS system-device defaults. Leave hardware rate
            # and buffer size unchanged and retain the profile between jobs.
            config.write_text(
                "[REAPER]\ncoreaudioindevnew=<default>\ncoreaudiooutdevnew=<default>\n"
                "coreaudiobs=512\ncoreaudiobsuse=0\ncoreaudiosrate=48000\n"
                "coreaudiosrateuse=0\ncoreaudioignorereset=0\ncoreaudioignprojsr=0\n"
            )
        yield [str(binary), "-newinst", "-nosplash", "-cfgfile", str(config)]


def build_in_host(args, script, log):
    host = subprocess.Popen([*args, str(script)], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 120
        status = script.parent / "host-status.txt"
        while not status.exists():
            if host.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(
                    f"REAPER did not finish the build. See {script.parent}"
                )
            time.sleep(0.25)
        message = status.read_text()
        if not message.startswith("BUILT\n"):
            raise RuntimeError(message)
        return message
    finally:
        if host.poll() is None:
            host.terminate()
            try:
                host.wait(timeout=10)
            except subprocess.TimeoutExpired:
                host.kill()
                host.wait()


def render(snapshot):
    with isolated_host() as args:
        return _render(snapshot, args)


def _render(snapshot, args):
    spec = json.loads((snapshot / "session.json").read_text())
    job = snapshot / ("host-" + uuid4().hex)
    job.mkdir()
    layout = project.export(spec, job)
    with (job / "host.log").open("w") as log:
        message = build_in_host(args, job / "build.lua", log)
        for name in ("Dry.RPP", "Studio.RPP"):
            make_portable(job / name, layout["sampler_zones"])
        replay = job / "replay"
        replay.mkdir()
        shutil.copy2(job / "Studio.RPP", replay / "Studio.RPP")
        (replay / "Samples").symlink_to(job / "Samples", target_is_directory=True)
        for rpp in (job / "Dry.RPP", job / "Studio.RPP", replay / "Studio.RPP"):
            subprocess.run(
                [*args, "-renderproject", str(rpp)],
                check=True,
                timeout=300,
                stdout=log,
                stderr=log,
            )

    def read_render(path):
        x, rate = sf.read(path, always_2d=True)
        if (
            sf.info(path).subtype != "PCM_24"
            or rate != spec["sample_rate"]
            or x.shape != (spec["frames"], 2)
            or not np.isfinite(x).all()
        ):
            raise RuntimeError(f"Invalid or misaligned REAPER render: {path.name}")
        if np.any(x <= -1) or np.any(x >= 1 - 2**-23):
            raise RuntimeError(f"24-bit PCM reached a sample rail: {path.name}")
        return x, rate

    path = job / "reaper-mixed.wav"
    x, rate = read_render(path)
    if np.max(abs(x)) < 1e-5:
        raise RuntimeError("REAPER returned a silent mix")
    replay_audio, _ = read_render(replay / path.name)
    if not np.array_equal(replay_audio, x):
        raise RuntimeError(f"Mix changed when reopening Studio.RPP: {job}")
    dry_path = job / "dry-Master.wav"
    dry, _ = read_render(dry_path)
    stems = np.zeros_like(dry)
    for lane in project.LANES:
        stem, _ = read_render(job / f"dry-{lane}.wav")
        if np.max(abs(stem)) < 1e-6 and any(
            e["voice"] == lane and not e.get("muted") for e in spec["events"]
        ):
            raise RuntimeError(f"Silent active sampler lane: {lane}")
        stems += stem
    stem_error = float(np.max(abs(stems - dry)))
    if stem_error > 2e-6:
        raise RuntimeError(f"Dry stems do not sum to the dry mix: {stem_error}")
    final = job / "master.wav"
    in_host = "host_master_gain_db" in spec["mixer"]
    if in_host:
        shutil.copyfile(path, final)
    else:
        write_audio(final, process(x, rate, spec["mixer"]["master"]), rate)
    mixed, master = (
        qa.levels(path, spec["sections"]),
        qa.levels(final, spec["sections"]),
    )
    write_json(
        job / "render.json",
        {
            "host": message.splitlines(),
            "layout": layout,
            "reopen_pcm_identical": True,
            "dry_stem_sum_max_abs": stem_error,
            "dry": qa.levels(dry_path, spec["sections"]),
            "mix": mixed,
            "master": master,
            "master_chain": spec["mixer"]["master"],
            "master_location": "Studio.RPP" if in_host else "offline DSP",
            "applied": in_host or mixed["pcm_sha256"] != master["pcm_sha256"],
        },
    )
    return job


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    folder = parser.parse_args().snapshot.resolve()
    if not folder.is_relative_to(DATA):
        parser.error("Choose a generated snapshot under MUSIC_DATA_DIR")
    try:
        print(render(folder))
    except RuntimeError as exc:
        parser.exit(1, f"{exc}\n")
