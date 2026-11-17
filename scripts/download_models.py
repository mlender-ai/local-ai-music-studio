"""Fetch only required weights from the pinned official release, once."""

from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
REVISION = "19671f406d603126926c1b7e2adc169acbcade22"
if __name__ == "__main__":
    snapshot_download(
        "ACE-Step/Ace-Step1.5",
        revision=REVISION,
        local_dir=ROOT / ".runtime/models/checkpoints",
        allow_patterns=[
            "acestep-v15-turbo/*",
            "vae/*",
            "Qwen3-Embedding-0.6B/*",
            "README.md",
            "config.json",
        ],
        max_workers=2,
    )
    print("Official model download complete:", REVISION)
