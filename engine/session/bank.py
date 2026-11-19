"""Subset of pinned PCM recordings, selected by key, velocity and take."""

import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import numpy as np
import soundfile as sf
from engine.paths import RUNTIME

BANKS = json.loads(Path(__file__).with_name("banks.json").read_text())
CACHE = RUNTIME / "session-samples"


def fetch(task):
    bank, path, digest = task
    target = CACHE / digest

    def verified(data):
        return (
            hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            == digest
        )

    if target.exists() and verified(target.read_bytes()):
        return
    url = f"https://raw.githubusercontent.com/{bank['repo']}/{bank['revision']}/{quote(path)}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if not verified(data):
        raise ValueError(f"Sample checksum mismatch: {path}")
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(dir=CACHE, delete=False) as tmp:
        tmp.write(data)
    Path(tmp.name).replace(target)


def install():
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(6) as workers:
        list(
            workers.map(
                fetch,
                ((b, row[-2], row[-1]) for b in BANKS.values() for row in b["samples"]),
            )
        )


@lru_cache(maxsize=100)
def pcm(digest):
    x, sr = sf.read(CACHE / digest, always_2d=True, dtype="float32")
    x = x.mean(axis=1)
    # Compensate differing microphone gains. Velocity and source layer retain dynamics.
    return x / max(0.005, float(np.max(abs(x)))), sr


def select_sample(track, voice, pitch, velocity, take):
    rows = [r for r in BANKS[track]["samples"] if r[0] == voice]
    layers = sorted({r[2] for r in rows})
    layer = layers[min(len(layers) - 1, int(velocity / 128 * len(layers)))]
    selected = min(
        (r for r in rows if r[2] == layer),
        key=lambda r: (abs(r[1] - pitch), r[3] != (1 + take % 2)),
    )
    return selected


def note(track, voice, pitch, velocity, take, duration, release, sr, slide=False):
    selected = select_sample(track, voice, pitch, velocity, take)
    data, rate = pcm(selected[-1])
    speed = rate / sr * 2 ** ((pitch - selected[1]) / 12)
    t = np.arange(round((duration + release) * sr)) / sr
    pos = t * sr * speed
    if slide:
        pos = np.cumsum(speed * 2 ** (-np.maximum(0, 1 - t / 0.055) * 2 / 12)) - speed
        pos = np.maximum(0, pos)
    y = np.interp(pos, np.arange(len(data)), data, right=0)
    envelope = np.clip(1 - (t - duration) / release, 0, 1) ** 2
    return y * envelope * np.minimum(t / 0.0007, 1) * (velocity / 127) ** 1.35


if __name__ == "__main__":
    install()
