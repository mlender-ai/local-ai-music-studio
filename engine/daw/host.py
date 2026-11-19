"""Run the bundled ReaScript against a fresh copy of a validated score snapshot."""

import argparse
import json
import os
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


def render(snapshot):
    binary = executable()
    if not binary:
        raise RuntimeError(
            "Official REAPER.app was not found. No host render was started."
        )
    spec = json.loads((snapshot / "session.json").read_text())
    job = snapshot / ("host-" + uuid4().hex)
    job.mkdir()
    project.export(spec, job)
    config = job / "reaper.ini"
    config.write_text("[REAPER]\n")
    args = [str(binary), "-newinst", "-nosplash", "-cfgfile", str(config)]
    with (job / "host.log").open("w") as log:
        host = subprocess.Popen([*args, str(job / "build.lua")], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 120
            status = job / "host-status.txt"
            while not status.exists():
                if host.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"REAPER did not finish the build. See {job}")
                time.sleep(0.25)
            message = status.read_text()
            if not message.startswith("BUILT\n"):
                raise RuntimeError(message)
        finally:
            # This instance is dedicated to the job. User-open instances are independent.
            if host.poll() is None:
                host.terminate()
                try:
                    host.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait()
        subprocess.run(
            [*args, "-renderproject", str(job / "Studio.RPP")],
            check=True,
            timeout=300,
            stdout=log,
            stderr=log,
        )
    path = job / "reaper-mixed.wav"
    x, rate = sf.read(path, always_2d=True)
    if (
        rate != spec["sample_rate"]
        or x.shape != (spec["frames"], 2)
        or not np.isfinite(x).all()
        or np.max(abs(x)) < 1e-5
    ):
        raise RuntimeError("REAPER returned a silent, invalid or misaligned mix")
    final = job / "master.wav"
    write_audio(final, process(x, rate, spec["mixer"]["master"]), rate)
    mixed, master = (
        qa.levels(path, spec["sections"]),
        qa.levels(final, spec["sections"]),
    )
    write_json(
        job / "render.json",
        {
            "host": message.splitlines(),
            "mix": mixed,
            "master": master,
            "master_chain": spec["mixer"]["master"],
            "applied": mixed["pcm_sha256"] != master["pcm_sha256"],
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
