"""Pack an editable, single-download REAPER project and verify its decoded render."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import soundfile as sf

from engine.daw.alt_rock import render
from engine.daw.host import isolated_host
from scripts.heavy.score import OUT


def package(session, target):
    session = session.resolve()
    media = session / "Audio"
    original_project = (session / "Iron Return.RPP").read_text()
    source_pattern = r'(<SOURCE )WAVE(\s+FILE ")Audio/([\w-]+)\.wav"'
    keys = {m[2] for m in re.findall(source_pattern, original_project)}
    assert keys == {p.stem for p in media.glob("*.wav")}
    with TemporaryDirectory(dir=session.parent) as temp:
        root = Path(temp)
        audio = root / "Audio"
        audio.mkdir()
        for key in sorted(keys):
            original = key == "original"
            name = key + (".mp3" if original else ".wv")
            codec = (
                ["-af", "volume=-4dB", "-c:a", "libmp3lame", "-b:a", "256k"]
                if original
                else ["-c:a", "wavpack", "-sample_fmt", "fltp"]
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-i",
                    str(media / (key + ".wav")),
                    *codec,
                    str(audio / name),
                ],
                check=True,
            )

        def relink(m):
            if m[3] == "original":
                return m[1] + "MP3" + m[2] + 'Audio/original.mp3" 1'
            return m[1] + "WAVPACK" + m[2] + "Audio/" + m[3] + '.wv"'

        project = root / "Iron Return.RPP"
        project.write_text(
            re.sub(source_pattern, relink, original_project).replace(
                "YuE2 original - muted reference",
                "YuE2 MP3 reference - muted (-4 dB proxy)",
            )
        )
        # The reference is muted. All active audio should produce identical output samples.
        with isolated_host() as args, (root / "host.log").open("w") as log:
            render(project, args, log)
        a, rate = sf.read(session / "Iron Return.wav", dtype="int32")
        b, other = sf.read(root / "Iron Return.wav", dtype="int32")
        if rate != other or not np.array_equal(a, b):
            raise ValueError("Portable media did not reproduce the 24-bit master")
        with ZipFile(target, "x", compression=ZIP_DEFLATED, compresslevel=1) as z:
            for path in [project, *sorted(audio.glob("*.wv")), *audio.glob("*.mp3")]:
                z.write(path, path.relative_to(root))
            for name in ("events.json", "edits.json", "fx.tsv", "qa.json", "gain.json"):
                z.write(session / name, name)
            for name in ("heavy.abc", "plan.json", "recordings.json"):
                z.write(OUT / name, name)
            z.writestr(
                "MEDIA.txt",
                "Muted reference is a -4 dB MP3 proxy. Original float WAV is distributed beside this ZIP. All active media are lossless. Open Iron Return.RPP in REAPER with stock JSFX and amp models.\n",
            )
        with ZipFile(target) as z:
            if z.testzip():
                raise ValueError("ZIP checksum error")
    return {"portable_reopen_pcm_identical": True, "zip_bytes": target.stat().st_size}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("session", type=Path)
    cli.add_argument("target", type=Path)
    args = cli.parse_args()
    print(json.dumps(package(args.session, args.target)))
