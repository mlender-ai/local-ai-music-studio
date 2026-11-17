"""Optional conditional experiment; preserves A/B and uses official repaint, not concatenation."""

import json
import time
from engine import jobs
from engine.paths import DATA, ROOT
import sys
import numpy as np
from engine.rendering.audio import read_audio

sys.path.insert(0, str(ROOT))
from engine.schema import Generate
from scripts.compare_arrangement import section_analysis, SCORES

out = DATA / "arrangement"
records = json.loads((out / "results.json").read_text())
b = next(r for r in records if r["label"] == "B")["job"]["result"]
plan = dict(b["metadata"]["plan"])
plan.update(
    caption="Sparse funk disco instrumental intro. Only muted clean electric guitar cutting and light sixteenth-note hi-hat. No kick, no bass, no brass, no synthesizer, no piano in this opening. Quiet, spacious rhythm suggesting the same main guitar motif. Smoothly lead into the existing groove at four seconds; preserve its tempo, key and timbre.",
    task_type="repaint",
    src_audio=b["path"],
    repainting_start=0,
    repainting_end=4,
    source_version_id=b["id"],
)
original = jobs.generation_plan
try:
    jobs.generation_plan = lambda command: plan
    job = jobs.submit(
        Generate(prompt=plan["original_prompt"], instrumental=True, seed=42),
        "arrangement-repaint-v1",
    )
finally:
    jobs.generation_plan = original
while job["state"] in ("queued", "running"):
    time.sleep(2)
    job = jobs.status(job["id"])
record = dict(
    label="C · Repaint intro (experimental)",
    job=job,
    human_scores={k: None for k in SCORES},
)
if job["state"] == "succeeded":
    record["section_analysis"] = section_analysis(job["result"]["path"])
    source, sr = read_audio(b["path"])
    edited, edited_sr = read_audio(job["result"]["path"])
    assert sr == edited_sr and source.shape == edited.shape
    x = source[6 * sr : 26 * sr].astype(np.float64).ravel()
    y = edited[6 * sr : 26 * sr].astype(np.float64).ravel()
    gain = float(x @ y / max(x @ x, 1e-12))
    record["source_context_comparison"] = dict(
        window_seconds=[6, 26],
        best_gain=gain,
        correlation=float(np.corrcoef(x, y)[0, 1]),
        residual_rms=float(np.sqrt(np.mean((y - gain * x) ** 2))),
        source_version=b["id"],
        note="Waveform agreement in a protected-context window; not a listening verdict.",
    )
records = [r for r in records if not r["label"].startswith("C")] + [record]
(out / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
(out / "repaint-result.json").write_text(
    json.dumps(record, ensure_ascii=False, indent=2)
)
print(job["state"], job.get("error"), flush=True)
