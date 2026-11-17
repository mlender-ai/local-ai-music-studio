"""Serial real A/B test: fixed backend, then three distinct Intent seeds."""

import json
import time
from pathlib import Path
from engine import jobs, store
from engine.schema import Generate, MusicIntent
from agent.command_parser import legacy_generation_plan
from agent.music_intent import FUNK_DISCO

PROMPT = "70년대 후반 80년대 초반 펑키 디스코 팝. 120BPM, 4/4, 싱코페이션 베이스, 뮤트 클린 기타 커팅, 로즈와 브라스, 아날로그 신스. 보컬 없는 30초 음악."
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/fidelity"
OUT.mkdir(parents=True, exist_ok=True)
results = []
originals = {v["id"]: v["path"] for v in store.list_versions()["versions"]}
normal = jobs.generation_plan
for label, seed in [("A", 42), ("B", 42), ("C2", 43), ("C3", 44)]:
    command = Generate(
        prompt=PROMPT,
        seed=seed,
        instrumental=True,
        intent=None
        if label == "A"
        else MusicIntent(**FUNK_DISCO, vocal_mode="instrumental"),
    )
    try:
        if label == "A":
            jobs.generation_plan = legacy_generation_plan
        job = jobs.submit(command, "fidelity-v2-" + label)
    finally:
        jobs.generation_plan = normal
    while job["state"] in ("queued", "running"):
        time.sleep(2)
        job = jobs.status(job["id"])
    results.append(
        dict(
            label=label,
            job=job,
            human_scores={
                k: None
                for k in [
                    "genre",
                    "drum_groove",
                    "bass_rhythm",
                    "guitar_presence",
                    "rhythmic_interlock",
                    "arrangement",
                    "audio_quality",
                ]
            },
        )
    )
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(label, job["state"], flush=True)
    if job["state"] != "succeeded":
        raise RuntimeError(job["error"])
assert all(Path(path).is_file() for path in originals.values())
