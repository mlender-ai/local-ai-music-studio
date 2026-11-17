"""Admission and resource limits are checked without loading a model."""

import fcntl
import os
import subprocess
import sys
from types import SimpleNamespace
import pytest
from engine import jobs, paths, store
from engine.generation import supervisor
from engine.schema import Generate


@pytest.fixture
def job_space(tmp_path, monkeypatch):
    data = tmp_path / "outputs"
    data.mkdir()
    runtime = tmp_path / "runtime"
    (runtime / "logs").mkdir(parents=True)
    for module in [paths, store, jobs, supervisor]:
        if hasattr(module, "DATA"):
            monkeypatch.setattr(module, "DATA", data)
    for module in [paths, jobs]:
        monkeypatch.setattr(module, "RUNTIME", runtime)
    return data, runtime


def test_idempotency_and_concurrency(job_space, monkeypatch):
    monkeypatch.setattr(
        jobs.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(pid=os.getpid())
    )
    request = Generate(prompt="따뜻한 딥하우스 음악")
    first = jobs.submit(request, "repeat-key")
    again = jobs.submit(request, "repeat-key")
    assert first["id"] == again["id"]
    with pytest.raises(ValueError, match="different request"):
        jobs.submit(Generate(prompt="앰비언트 음악"), "repeat-key")
    with pytest.raises(ValueError, match="busy"):
        jobs.submit(request)


def test_generation_lock_prevents_second_worker(job_space):
    data, runtime = job_space
    with (data / "generation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            supervisor.run_worker({}, runtime / "logs" / "test.log")


@pytest.mark.parametrize("failure", ["timeout", "memory"])
def test_limits_terminate_only_owned_worker(job_space, monkeypatch, failure):
    _, runtime = job_space
    real_popen = subprocess.Popen
    owned = []

    def start(*args, **kwargs):
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(30)"], **kwargs
        )
        owned.append(process)
        return process

    monkeypatch.setattr(supervisor.subprocess, "Popen", start)
    # Avoid replacing subprocess.run's own Popen; pressure check is below failure.
    monkeypatch.setattr(
        supervisor.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=4 * 1024**3),
    )
    monkeypatch.setattr(supervisor, "process_memory", lambda pid: (1024**3, 1024**3))
    options = dict(timeout=-1) if failure == "timeout" else dict(max_memory_gb=0.1)
    with pytest.raises((TimeoutError, RuntimeError)):
        supervisor.run_worker({}, runtime / "logs" / f"{failure}.log", **options)
    assert len(owned) == 1 and owned[0].poll() is not None
