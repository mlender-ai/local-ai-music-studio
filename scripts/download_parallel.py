"""Resume official weight downloads with bounded range requests and SHA-256.

Use if Hugging Face Xet fails. Never combines overlapping downloads, and
never publishes a weight file before verifying its official LFS digest.
"""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".runtime/models/checkpoints"
REPO = "ACE-Step/Ace-Step1.5"
REV = "19671f406d603126926c1b7e2adc169acbcade22"
PREFIXES = ("acestep-v15-turbo/", "vae/", "Qwen3-Embedding-0.6B/")


def download_file(item):
    name = item["path"]
    size = item["size"]
    expected = item["lfs"]["oid"]
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise RuntimeError(f"Existing weight checksum mismatch: {name}")
        print("VERIFIED existing", name, flush=True)
        return
    partial = target.with_suffix(".partial")
    ledger = target.with_suffix(".ranges.json")
    if not partial.exists():
        old = list(
            (DEST / ".cache/huggingface/download" / Path(name).parent).glob(
                f"*.{expected}.incomplete"
            )
        )
        if old:
            old[0].rename(partial)
    prefix = partial.stat().st_size if partial.exists() else 0
    if ledger.exists():
        saved = json.loads(ledger.read_text())
        prefix = saved["prefix"]
        complete = saved["complete"]
    else:
        complete = []
    fd = os.open(partial, os.O_RDWR | os.O_CREAT, 0o600)

    def part(start):
        end = min(start + 32 * 1024**2, size) - 1
        if os.environ.get("MUSIC_DOWNLOAD_MIRROR") == "modelscope":
            url = f"https://www.modelscope.cn/models/{REPO}/resolve/master/{name}?range_start={start}"
        else:
            url = f"https://huggingface.co/{REPO}/resolve/{REV}/{name}?download=true&range_start={start}"
        for attempt in range(8):
            try:
                response = requests.get(
                    url,
                    headers={"Range": f"bytes={start}-{end}"},
                    stream=True,
                    timeout=(20, 90),
                )
                response.raise_for_status()
                if (
                    response.status_code != 206
                    or response.headers.get("Content-Range")
                    != f"bytes {start}-{end}/{size}"
                ):
                    raise RuntimeError("Server did not honor the exact byte range")
                offset = start
                for block in response.iter_content(1024**2):
                    if offset + len(block) > end + 1:
                        raise RuntimeError("Oversized response")
                    os.pwrite(fd, block, offset)
                    offset += len(block)
                if offset != end + 1:
                    raise RuntimeError("Incomplete range")
                return start
            except Exception:
                if attempt == 7:
                    raise
                time.sleep(min(5 * (attempt + 1), 30))

    def save_ledger():
        temporary = ledger.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(prefix=prefix, complete=complete)))
        temporary.replace(ledger)

    errors = []
    try:
        save_ledger()
        ranges = [n for n in range(prefix, size, 32 * 1024**2) if n not in complete]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            for future in concurrent.futures.as_completed(
                [pool.submit(part, n) for n in ranges]
            ):
                try:
                    complete.append(future.result())
                except Exception as error:
                    errors.append(str(error))
                    print(
                        "Range failed; other completed ranges will be retained:",
                        error,
                        flush=True,
                    )
                    continue
                save_ledger()
                downloaded = prefix + sum(
                    min(32 * 1024**2, size - start) for start in complete
                )
                print(
                    name,
                    f"{downloaded / 1024**2:.0f}/{size / 1024**2:.0f} MiB",
                    flush=True,
                )
    finally:
        os.close(fd)
    if errors:
        raise RuntimeError(f"{len(errors)} ranges failed; rerun to resume: {errors[0]}")
    with partial.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError(f"SHA-256 mismatch: {name}")
    partial.rename(target)
    ledger.unlink()
    print("VERIFIED", name, digest, flush=True)


if __name__ == "__main__":
    response = requests.get(
        f"https://huggingface.co/api/models/{REPO}/tree/{REV}?recursive=true",
        timeout=30,
    )
    response.raise_for_status()
    for item in response.json():
        if item["path"].startswith(PREFIXES) and item.get("lfs"):
            download_file(item)
