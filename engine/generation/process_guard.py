"""Real subprocess.Popen process-group cancellation, shared cross-process lock & 10 GiB Memory Guard (Phase 03.1 · Section 16).

Fixes the Phase 03 `subprocess.run()` cancellation flaw:
- Spawns child process in its own process group (`start_new_session=True`)
- Acquires cross-process exclusive lock (`fcntl.flock`) so multiple agents never run heavy models simultaneously
- Polls every 0.25s for user `cancel_event`, Apple Silicon 10 GiB RSS/footprint limit, and macOS critical memory pressure
- On cancel or memory violation, sends SIGTERM -> waits 2s -> SIGKILL to the ENTIRE process group (`os.killpg`)
  and verifies the process has terminated before releasing the lock.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psutil

from engine import paths as engine_paths

GiB = 1024**3
DEFAULT_MEMORY_LIMIT_BYTES = 10 * GiB


class GenerationCancelledError(RuntimeError):
    """Raised when a running external model subprocess was terminated via cancellation."""


def _generation_lock_path() -> Path:
    d = engine_paths.DATA / "daw"
    d.mkdir(parents=True, exist_ok=True)
    return d / ".model_execution.lock"


@contextmanager
def shared_model_execution_lock(cancel_event: threading.Event | None = None, timeout_sec: float = 600.0):
    """Cross-process exclusive lock preventing two agents from exhausting Apple Silicon 16 GiB RAM."""
    lock_file = _generation_lock_path()
    deadline = time.monotonic() + timeout_sec
    with lock_file.open("a+") as fh:
        acquired = False
        while not acquired:
            if cancel_event and cancel_event.is_set():
                raise GenerationCancelledError("Cancelled while waiting for shared model execution lock")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for another active music model run to finish")
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _terminate_process_group(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=2.0)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        pass


def _process_tree_rss(pid: int) -> int:
    try:
        p = psutil.Process(pid)
        total = p.memory_info().rss
        for child in p.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                continue
        return total
    except psutil.Error:
        return 0


def run_cancellable_guarded(
    command: list[str],
    log_path: Path,
    *,
    cancel_event: threading.Event | None = None,
    timeout_sec: float = 600.0,
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Execute a heavy external binary/script under shared lock, memory guard, and true SIGTERM/SIGKILL cancellation."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    peak_rss = 0
    last_pressure_check = 0.0

    with shared_model_execution_lock(cancel_event=cancel_event):
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelledError("Generation cancelled before subprocess start")

        with log_path.open("w", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                command,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(cwd) if cwd else None,
                start_new_session=True,
            )
            try:
                while proc.poll() is None:
                    if cancel_event and cancel_event.is_set():
                        _terminate_process_group(proc)
                        raise GenerationCancelledError("Generation process terminated cleanly by user cancel")

                    elapsed = time.monotonic() - started
                    if elapsed > timeout_sec:
                        _terminate_process_group(proc)
                        raise TimeoutError(f"Model subprocess exceeded timeout ({timeout_sec:.0f}s)")

                    rss = _process_tree_rss(proc.pid)
                    if rss > peak_rss:
                        peak_rss = rss
                    if memory_limit_bytes > 0 and rss > memory_limit_bytes:
                        _terminate_process_group(proc)
                        raise RuntimeError(
                            f"Generation stopped: process RSS ({rss / GiB:.2f} GiB) exceeded {memory_limit_bytes / GiB:.1f} GiB safety guard."
                        )

                    if sys.platform == "darwin" and (time.monotonic() - last_pressure_check) >= 2.0:
                        last_pressure_check = time.monotonic()
                        try:
                            pr = subprocess.run(
                                ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                                capture_output=True,
                                text=True,
                                timeout=1.0,
                                check=False,
                            )
                            if pr.stdout.strip() == "4":
                                _terminate_process_group(proc)
                                raise RuntimeError("Generation stopped: macOS critical memory pressure.")
                        except Exception:
                            pass

                    time.sleep(0.15)

                rc = proc.wait()
            finally:
                if proc.poll() is None:
                    _terminate_process_group(proc)

    if cancel_event and cancel_event.is_set():
        raise GenerationCancelledError("Generation cancelled before completion")

    if rc != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"Model subprocess exited with code {rc}. Log tail:\n{tail}")

    return {
        "returncode": rc,
        "peakRssGiB": round(peak_rss / GiB, 3),
        "elapsedSec": round(time.monotonic() - started, 3),
        "logPath": str(log_path),
    }
