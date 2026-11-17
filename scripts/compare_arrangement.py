"""Single-inference 30s A/B; identical model/seed, no concatenation or post-mastering."""

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
import numpy as np
from engine import jobs, store
from engine.paths import DATA, ROOT, RUNTIME
from engine.rendering.audio import read_audio
from engine.schema import Generate, MusicIntent
from agent.music_intent import FUNK_DISCO
from agent.arrangement import draft_arrangement

PROMPT = "70년대 후반에서 80년대 초반의 펑키 디스코 팝을 만들어줘. 처음에는 뮤트 기타 커팅과 하이햇으로 시작하고, 잠시 후 킥과 싱코페이션 베이스가 합류했으면 좋겠어. 메인에서는 브라스와 신스가 추가되면서 훨씬 풍성하고 신나는 느낌으로 전개해줘. 120BPM, 4/4, 보컬 없는 30초 음악."
SCORES = [
    "intro_clarity",
    "gradual_instrument_entry",
    "main_groove_lift",
    "rhythm_timbre_consistency",
    "natural_transitions",
]


def section_analysis(path):
    audio, sr = read_audio(path)
    rows = []
    for name, start, end in [
        ("intro", 0, 4),
        ("entry", 4, 12),
        ("main", 12, 28),
        ("outro", 28, 30),
    ]:
        x = audio[round(start * sr) : round(end * sr)]
        rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        rows.append(
            dict(
                section=name,
                start=start,
                end=end,
                rms_dbfs=round(20 * np.log10(max(rms, 1e-12)), 3),
                peak=float(np.max(abs(x))),
            )
        )
    boundaries = [
        dict(
            seconds=t, sample_step=float(np.max(abs(audio[t * sr] - audio[t * sr - 1])))
        )
        for t in [4, 12, 28]
    ]
    return dict(
        sections=rows,
        main_minus_intro_db=round(rows[2]["rms_dbfs"] - rows[0]["rms_dbfs"], 3),
        boundary_samples=boundaries,
        note="Target windows only, not detected instrument entry times. RMS and sample steps are not listening scores or proof of seamless joins.",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="v1")
    args = parser.parse_args()
    out = DATA / "arrangement"
    out.mkdir(parents=True, exist_ok=True)
    # Full old-file hashes: neither WAVs nor previous versions may change.
    before = {
        v["id"]: dict(
            path=v["path"],
            sha256=hashlib.sha256(Path(v["path"]).read_bytes()).hexdigest(),
        )
        for v in store.list_versions()["versions"]
    }
    (out / f"preservation-{args.run}.json").write_text(json.dumps(before, indent=2))
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        str(ROOT / ".runtime/models/checkpoints/Qwen3-Embedding-0.6B"),
        local_files_only=True,
    )
    results = []
    for label in ["A", "B"]:
        intent = MusicIntent(**FUNK_DISCO, vocal_mode="instrumental")
        if label == "B":
            intent.arrangement_plan = draft_arrangement(PROMPT, 30)
        command = Generate(
            prompt=PROMPT, intent=intent, instrumental=True, seed=42, duration=30
        )
        job = jobs.submit(command, "arrangement-" + args.run + "-" + label)
        while job["state"] in ("queued", "running"):
            time.sleep(2)
            job = jobs.status(job["id"])
        record = dict(label=label, job=job, human_scores={k: None for k in SCORES})
        if job["state"] == "succeeded":
            record["section_analysis"] = section_analysis(job["result"]["path"])
            log = (RUNTIME / "logs" / f"{job['id']}.log").read_text()
            text = re.search(
                r"text_prompt:\n(.*?)\n\d{4}-\d\d-\d\d .*?={10}", log, re.S
            )
            if text:
                actual = text.group(1)
                tokens = tok.encode(actual)
                record["conditioning"] = dict(
                    text=actual,
                    tokens=len(tokens),
                    limit=256,
                    truncated=len(tokens) > 256,
                    effective_text=tok.decode(tokens[:256]),
                )
        results.append(record)
        (out / f"results-{args.run}.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2)
        )
        (out / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2)
        )
        print(
            label,
            job["state"],
            record.get("conditioning", {}).get("tokens"),
            flush=True,
        )
        if job["state"] != "succeeded":
            raise RuntimeError(job["error"])
    assert all(
        hashlib.sha256(Path(v["path"]).read_bytes()).hexdigest() == v["sha256"]
        for v in before.values()
    )
    print("All pre-existing WAV hashes unchanged.", flush=True)


if __name__ == "__main__":
    main()
