"""Strict, serializable commands shared by CLI, MCP and player."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Generate(Strict):
    prompt: str = Field(min_length=3, max_length=2000)
    duration: float = Field(default=30, ge=15, le=30)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    instrumental: bool | None = None
    lyrics: str = Field(default="", max_length=4000)


class EQ(Strict):
    type: Literal["eq"] = "eq"
    mode: Literal["low_shelf", "high_shelf", "peaking"] = "low_shelf"
    frequency: float = Field(default=120, ge=20, le=20000)
    gain_db: float = Field(default=3, ge=-18, le=18)
    q: float = Field(default=0.707, ge=0.1, le=10)


class Compressor(Strict):
    type: Literal["compressor"] = "compressor"
    threshold_db: float = Field(default=-18, ge=-60, le=0)
    ratio: float = Field(default=3, ge=1, le=20)
    attack_ms: float = Field(default=15, ge=0.1, le=200)
    release_ms: float = Field(default=120, ge=10, le=2000)
    makeup_db: float = Field(default=0, ge=-12, le=12)


class Reverb(Strict):
    type: Literal["reverb"] = "reverb"
    wet: float = Field(default=0.2, ge=0, le=1)
    decay: float = Field(default=2.5, ge=0.1, le=10)
    pre_delay_ms: float = Field(default=25, ge=0, le=250)


class Distortion(Strict):
    type: Literal["distortion"] = "distortion"
    drive_db: float = Field(default=6, ge=0, le=30)
    tone_hz: float = Field(default=6000, ge=100, le=20000)
    output_db: float = Field(default=-6, ge=-30, le=6)


class Limiter(Strict):
    type: Literal["limiter"] = "limiter"
    ceiling_db: float = Field(default=-1, ge=-12, le=-0.1)
    release_ms: float = Field(default=80, ge=10, le=1000)


Effect = Annotated[
    EQ | Compressor | Reverb | Distortion | Limiter, Field(discriminator="type")
]


class Chain(Strict):
    effects: list[Effect] = Field(min_length=1, max_length=12)
