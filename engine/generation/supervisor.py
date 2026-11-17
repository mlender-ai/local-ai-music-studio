"""Bounded subprocess execution; only children created here are ever stopped."""

import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from engine.paths import DATA
from engine.generation.resources import process_memory

GiB = 1024**3


def run_worker(
    request: dict, log_path: Path, timeout: float = 900, max_memory_gb: float = 10
):
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / "generation.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another local model worker is already running."
            ) from exc
        return _run_locked(request, log_path, timeout, max_memory_gb, lock.fileno())


def _run_locked(request, log_path, timeout, max_memory_gb, lock_fd):
    root = Path(__file__).resolve().parents[2]
    request_path = log_path.with_suffix(".request.json")
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2))
    if psutil.virtual_memory().available < 1.5 * GiB:
        raise RuntimeError(
            "Insufficient available RAM (requires at least 1.5 GiB before launch)."
        )
    if psutil.disk_usage(root).free < 2 * GiB:
        raise RuntimeError("Insufficient disk space (requires 2 GiB).")
    peak, footprint_peak, low_since = 0, 0, None
    started = time.monotonic()
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "engine.generation.worker", str(request_path)],
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(lock_fd,),
        )
        try:
            while process.poll() is None:
                try:
                    rss, footprint = process_memory(process.pid)
                except psutil.NoSuchProcess:
                    break
                peak = max(peak, rss)
                footprint_peak = max(footprint_peak, footprint)
                if footprint > max_memory_gb * GiB:
                    raise RuntimeError(
                        f"Generation stopped: child memory footprint exceeded {max_memory_gb} GiB."
                    )
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Generation exceeded {timeout} seconds.")
                available = psutil.virtual_memory().available
                if available < 600 * 1024**2:
                    low_since = low_since or time.monotonic()
                    if time.monotonic() - low_since > 5:
                        raise RuntimeError(
                            "Generation stopped: system available memory below 600 MiB for 5s."
                        )
                else:
                    low_since = None
                if sys.platform == "darwin":
                    pressure = subprocess.run(
                        [
                            "/usr/sbin/sysctl",
                            "-n",
                            "kern.memorystatus_vm_pressure_level",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if pressure.stdout.strip() == "4":
                        raise RuntimeError(
                            "Generation stopped: macOS critical memory pressure."
                        )
                time.sleep(0.5)
            if process.wait() != 0:
                tail = log_path.read_text(errors="replace")[-4000:]
                raise RuntimeError(f"ACE-Step worker failed; see {log_path}\n{tail}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    result = json.loads(Path(request["result_path"]).read_text())
    result["peak_rss_gib"] = round(peak / GiB, 3)
    result["peak_footprint_gib"] = round(footprint_peak / GiB, 3)
    result["total_seconds"] = round(time.monotonic() - started, 3)
    return result
