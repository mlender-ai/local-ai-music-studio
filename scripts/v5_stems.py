"""Run the optional, pinned Demucs MLX separator under the generation guard."""

import argparse
import os
import sys
from pathlib import Path

from engine.generation.supervisor import run_guarded
from engine.paths import RUNTIME
from engine.session.render import write_json

MODELS = ("htdemucs_6s", "htdemucs")


def separate(source, output):
    runtime = RUNTIME / "v5"
    code = runtime / "demucs-mlx"
    deps = runtime / "stem-deps312"
    output.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        target = output / model
        target.mkdir()
        command = [
            "/usr/bin/env",
            f"PYTHONPATH={os.pathsep.join(map(str, (code, deps)))}",
            f"DEMUCS_MLX_CACHE_DIR={runtime / 'stem-models'}",
            "DEMUCS_MLX_NO_DOWNLOAD=1",
            sys.executable,
            "-m",
            "scripts.v5_stems",
            str(source),
            str(target),
            "--worker",
            model,
        ]
        write_json(
            target / "resources.json", run_guarded(command, target / "worker.log")
        )


def worker(source, output, model):
    from demucs_mlx.api import Separator
    import mlx.core as mx

    mx.set_cache_limit(256 * 1024**2)
    with Separator(
        model=model,
        shifts=0,
        overlap=0.25,
        batch_size=1,
        jobs=0,
        attention_precision="fp32",
        progress=True,
    ) as separator:
        separator.separate(
            source, output_dir=output, clip="none", as_float=True, async_write=False
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--worker", choices=MODELS)
    args = cli.parse_args()
    if args.worker:
        worker(args.source, args.output, args.worker)
    else:
        separate(args.source.resolve(), args.output.resolve())
