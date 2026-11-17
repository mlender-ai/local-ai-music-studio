"""One-off validation helper; waits for this task's download, not an automation."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    "Qwen3-Embedding-0.6B/model.safetensors",
    "acestep-v15-turbo/model.safetensors",
    "vae/diffusion_pytorch_model.safetensors",
]
started = time.monotonic()
while not all((ROOT / ".runtime/models/checkpoints" / f).is_file() for f in required):
    if time.monotonic() - started > 5400:
        raise TimeoutError("Model download did not complete within 90 minutes.")
    time.sleep(5)
os.environ["HF_HUB_DISABLE_XET"] = "1"
subprocess.run([sys.executable, "scripts/download_models.py"], cwd=ROOT, check=True)
subprocess.run(
    [sys.executable, "scripts/validate_generations.py"], cwd=ROOT, check=True
)
