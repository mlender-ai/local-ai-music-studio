"""One durable model job at a time, including independent CLI/MCP processes."""

import json
import os
import subprocess
import sys
import time
import uuid
import psutil
from agent.command_parser import generation_plan
from engine.schema import Generate
from engine.paths import ROOT, RUNTIME, initialize
from engine.store import database, get_job, update_job, add_version
from engine.rendering.audio import analyze
from engine.rendering.rhythm import estimate_rhythm
from engine.generation.backend import ACEStepBackend


def recover_jobs():
    with database() as db:
        rows = db.execute(
            "SELECT id,pid,created FROM jobs WHERE state IN ('queued','running')"
        ).fetchall()
        for row in rows:
            if time.time() - row["created"] < 15:
                continue
            pid = row["pid"]
            alive = False
            try:
                process = psutil.Process(pid) if pid else None
                alive = bool(
                    process
                    and process.is_running()
                    and process.status() != psutil.STATUS_ZOMBIE
                    and abs(process.create_time() - row["created"]) < 30
                )
            except psutil.Error:
                pass
            if not alive:
                db.execute(
                    "UPDATE jobs SET state='failed',error=?,updated=? WHERE id=?",
                    ("Job runner exited before completion.", time.time(), row["id"]),
                )


def submit(command: Generate, request_key: str | None = None):
    plan = generation_plan(command)
    recover_jobs()
    if request_key and (not 1 <= len(request_key) <= 128):
        raise ValueError("request_key must be 1–128 characters.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if request_key:
            old = db.execute(
                "SELECT id,request FROM jobs WHERE request_key=?", (request_key,)
            ).fetchone()
            if old:
                previous = json.loads(old["request"])
                comparable = (
                    "original_prompt",
                    "duration",
                    "seed",
                    "instrumental",
                    "lyrics",
                )
                same = previous == plan or (
                    "planner" not in previous
                    and all(previous.get(k) == plan.get(k) for k in comparable)
                    and command.intent is None
                )
                if not same:
                    raise ValueError(
                        "request_key already belongs to a different request."
                    )
                existing_id = old["id"]
                return get_job(existing_id)
        active = db.execute(
            "SELECT id FROM jobs WHERE state IN ('queued','running')"
        ).fetchone()
        if active:
            raise ValueError(f"Generation busy; active job: {active[0]}")
        job_id = uuid.uuid4().hex
        now = time.time()
        db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                "queued",
                now,
                now,
                None,
                request_key,
                json.dumps(plan, ensure_ascii=False),
                None,
                None,
            ),
        )
    try:
        with (RUNTIME / "logs" / f"{job_id}.runner.log").open("w") as log:
            child = subprocess.Popen(
                [sys.executable, "-m", "engine.jobs", job_id],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        update_job(job_id, pid=child.pid)
    except Exception as exc:
        update_job(job_id, state="failed", error=str(exc))
        raise
    return get_job(job_id)


def run(job_id):
    initialize()
    try:
        update_job(job_id, state="running", pid=os.getpid())
        job = get_job(job_id)
        output = ACEStepBackend().generate(job["request"], job_id)
        analysis = analyze(output["path"])
        if analysis["rms"] < 1e-5 or analysis["clipped_samples"]:
            raise ValueError("Model output is silent or clipped; generation rejected.")
        if abs(analysis["duration_seconds"] - job["request"]["duration"]) > 0.1:
            raise ValueError("Model duration differs from request by more than 100 ms.")
        # Report rhythmic evidence separately from file validity. Never pass a
        # genre/tempo quality verdict merely because a WAV was produced.
        rhythm = estimate_rhythm(output["path"], job["request"].get("bpm"))
        version = add_version(
            output["path"],
            dict(
                kind="generation",
                plan=job["request"],
                generation=output,
                analysis=analysis,
                rhythm=rhythm,
                quality_review="needs_listening",
            ),
        )
        update_job(
            job_id, state="succeeded", result=json.dumps(version, ensure_ascii=False)
        )
    except Exception as exc:
        update_job(job_id, state="failed", error=f"{type(exc).__name__}: {exc}")


def status(job_id=None):
    recover_jobs()
    if job_id:
        return get_job(job_id)
    with database() as db:
        rows = db.execute(
            "SELECT id FROM jobs ORDER BY created DESC LIMIT 20"
        ).fetchall()
    return dict(max_concurrent_generations=1, jobs=[get_job(r[0]) for r in rows])


if __name__ == "__main__":
    run(sys.argv[1])
