"""Backend protocol keeps inference isolated from producer and transports."""

import os
from pydantic import Field
from typing import Literal
from engine.schema import Strict
from typing import Protocol
from engine.paths import DATA, RUNTIME
from engine.generation.supervisor import run_worker


class RuntimeSettings(Strict):
    device: Literal["mps", "cpu"] = "mps"
    mlx: bool = True
    timeout: float = Field(default=900, ge=30, le=3600)
    max_memory_gb: float = Field(default=10, ge=2, le=16)

    @classmethod
    def from_environment(cls):
        return cls(
            device=os.environ.get("MUSIC_DEVICE", "mps"),
            mlx=os.environ.get("MUSIC_MLX_DIT", "1") == "1",
            timeout=os.environ.get("MUSIC_GENERATION_TIMEOUT", "900"),
            max_memory_gb=os.environ.get("MUSIC_MAX_MEMORY_GB", "10"),
        )


class GenerationBackend(Protocol):
    def generate(self, plan: dict, job_id: str) -> dict: ...


class ACEStepBackend:
    def generate(self, plan, job_id):
        directory = DATA / "originals" / job_id
        directory.mkdir(parents=True, exist_ok=False)
        request = {
            k: v for k, v in plan.items() if k not in ("action", "original_prompt")
        }
        settings = RuntimeSettings.from_environment()
        if plan.get("inference_profile") == "turbo_8bit" and not settings.mlx:
            raise ValueError("turbo_8bit requires the MLX decoder.")
        request.update(
            save_dir=str(directory),
            result_path=str(RUNTIME / f"{job_id}.result.json"),
            device=settings.device,
            mlx=settings.mlx,
        )
        return run_worker(
            request,
            RUNTIME / "logs" / f"{job_id}.log",
            timeout=settings.timeout,
            max_memory_gb=settings.max_memory_gb,
        )
