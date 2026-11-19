"""Sequential model/planner attribution study; no automatic musical verdicts."""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
import numpy as np
from engine import jobs, store
from engine.paths import DATA, ROOT, RUNTIME
from engine.schema import Generate
from agent.command_parser import generation_plan
from agent.director import tokenizer
from engine.rendering.audio import read_audio

BRIEFS = {
    "soul": "부드러운 소울 디스코. 유기적인 드럼과 베이스, 풍성한 세션과 자연스러운 인트로. 116BPM, 4/4, 보컬 없는 음악.",
    "house": "딥 하우스. 반복적인 그루브에 섬세한 변주, 따뜻한 신스, 깊은 공간감. 122BPM, 4/4, 보컬 없는 음악.",
    "ambient": "앰비언트 시네마틱. 유려한 전개와 깊은 레이어, 풍성하고 선명한 공간. 72BPM, 4/4, 보컬 없는 음악.",
}
SCORES = [
    "genre",
    "natural_instruments",
    "groove",
    "session_interaction",
    "development",
    "variation",
    "harmony_melody",
    "mix_space",
    "absence_of_artifacts",
    "overall",
]


def metrics(path):
    x, sr = read_audio(path)
    x = x.astype(np.float64)
    energy = np.sqrt(
        np.mean(x[: len(x) // sr * sr].reshape(-1, sr, x.shape[1]) ** 2, axis=(1, 2))
    )
    db = 20 * np.log10(np.maximum(energy, 1e-12))
    active = db[db > -60]
    mid = (x[:, 0] + x[:, 1]) / 2
    side = (x[:, 0] - x[:, 1]) / 2
    return dict(
        one_second_rms_dbfs=db.round(3).tolist(),
        active_rms_p95_minus_p10_db=float(
            np.percentile(active, 95) - np.percentile(active, 10)
        )
        if len(active)
        else None,
        stereo_correlation=float(np.corrcoef(x.T)[0, 1]),
        side_mid_energy_ratio=float(np.mean(side**2) / max(np.mean(mid**2), 1e-12)),
        silence_seconds_below_minus60=int(sum(db < -60)),
        note="Technical descriptors, not musical scores. Stereo correlation is not spatial quality; RMS variation is not arrangement quality.",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="v1")
    parser.add_argument("--long", action="store_true")
    args = parser.parse_args()
    out = DATA / "producer"
    out.mkdir(parents=True, exist_ok=True)
    preservation = out / f"preservation-{args.run}.json"
    if not preservation.exists():
        preservation.write_text(
            json.dumps(
                {
                    v["path"]: hashlib.sha256(Path(v["path"]).read_bytes()).hexdigest()
                    for v in store.list_versions()["versions"]
                },
                indent=2,
            )
        )
    records = []
    for genre, brief in BRIEFS.items():
        mp = json.loads((ROOT / f"examples/director/{genre}.json").read_text())
        for label in ["A", "B", "C"]:
            command = Generate(
                prompt=brief,
                duration=30,
                seed=42,
                instrumental=True,
                music_plan=None if label == "A" else mp,
                inference_profile="turbo_8bit" if label == "C" else "turbo_4bit",
            )
            plan = generation_plan(command)
            job = jobs.submit(command, f"producer-{args.run}-{genre}-{label}")
            while job["state"] in ("queued", "running"):
                time.sleep(2)
                job = jobs.status(job["id"])
            record = dict(
                genre=genre,
                condition=label,
                job=job,
                human_scores={s: None for s in SCORES},
            )
            if job["state"] == "succeeded":
                record["automatic"] = metrics(job["result"]["path"])
                log = (RUNTIME / "logs" / f"{job['id']}.log").read_text()
                match = re.search(
                    r"text_prompt:\n(.*?)\n\d{4}-\d\d-\d\d .*?={10}", log, re.S
                )
                if match:
                    actual = match.group(1)
                    record["actual_conditioning"] = {
                        "text": actual,
                        "tokens": len(tokenizer().encode(actual)),
                    }
                    if label != "A":
                        assert actual == plan["conditioning"]["text"], (
                            "Preflight/actual text mismatch"
                        )
            records.append(record)
            (out / f"results-{args.run}.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2)
            )
            (out / "results.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2)
            )
            print(genre, label, job["state"], job.get("error"), flush=True)
    # A separate duration experiment, not mixed into same-duration A/B/C.
    if args.long:
        command = Generate(
            prompt=BRIEFS["soul"],
            seed=42,
            instrumental=True,
            music_plan=json.loads((ROOT / "examples/director/soul.json").read_text()),
        )
        # Internal validated experiment only: ordinary Generate remains 15–30 seconds.
        from agent.director import compile_director

        plan = compile_director(command.model_copy(update={"duration": 60}))
        job = jobs.submit_plan(plan, f"producer-{args.run}-soul-60s")
        while job["state"] in ("queued", "running"):
            time.sleep(2)
            job = jobs.status(job["id"])
        record = dict(
            genre="soul-60s",
            condition="D-duration",
            job=job,
            human_scores={s: None for s in SCORES},
        )
        if job["state"] == "succeeded":
            record["automatic"] = metrics(job["result"]["path"])
        records.append(record)
        (out / "results.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2)
        )
        (out / f"results-{args.run}.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2)
        )
        print("60s", job["state"], job.get("error"), flush=True)
    for path, expected in json.loads(preservation.read_text()).items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    print("All pre-existing audio unchanged.", flush=True)


if __name__ == "__main__":
    main()
