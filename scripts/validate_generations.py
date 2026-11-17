"""Run three real, distinct model prompts serially; never substitute fixtures."""

import json
import time
from pathlib import Path
from engine import jobs
from engine.schema import Generate

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    (
        "A",
        "90년대 트립합 느낌의 어두운 음악. 85BPM, 묵직한 드럼과 깊은 베이스, 몽환적인 신스. 보컬 없는 30초 음악.",
        42,
    ),
    (
        "B",
        "우주를 떠다니는 듯한 고요한 앰비언트 음악. 천천히 변화하는 패드, 긴 잔향, 드럼 없음.",
        43,
    ),
    (
        "C",
        "따뜻한 딥하우스 음악. 단단한 킥, 반복적인 신스 베이스, 부드러운 코드 진행.",
        44,
    ),
]


def main():
    results = []
    for name, prompt, seed in CASES:
        job = jobs.submit(
            Generate(prompt=prompt, duration=30, seed=seed), f"phase1-test-{name}-v3"
        )
        print(name, job["id"], job["state"], flush=True)
        while job["state"] in ("queued", "running"):
            time.sleep(3)
            job = jobs.status(job["id"])
        results.append(dict(test=name, **job))
        (ROOT / "docs/generation-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2)
        )
        print(name, job["state"], job.get("error"), flush=True)
        if job["state"] != "succeeded":
            raise RuntimeError(
                f"TEST {name} failed. Investigate before continuing: {job['error']}"
            )
    print("All genuine generation cases completed.", flush=True)


if __name__ == "__main__":
    main()
