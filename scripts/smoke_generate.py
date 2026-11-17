"""First genuine model inference, before DSP or MCP integration."""

import json
from pathlib import Path
from engine.generation.supervisor import run_worker

root = Path(__file__).resolve().parents[1]
request = dict(
    caption="Dark 1990s trip-hop instrumental, heavy breakbeat drums, deep sub bass, dreamy analog synthesizers, atmospheric, no vocals.",
    bpm=85,
    duration=30,
    seed=42,
    instrumental=True,
    save_dir=str(root / "outputs/originals/test_a"),
    result_path=str(root / ".runtime/test_a_result.json"),
)
if __name__ == "__main__":
    result = run_worker(request, root / ".runtime/logs/test_a.log")
    print(json.dumps(result, indent=2))
