"""Strict, serializable commands shared by CLI, MCP and player."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from engine.music_plan import MusicPlan


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ArrangementSection(Strict):
    name: Literal["intro", "groove_entry", "main_groove", "outro"]
    start: float = Field(ge=0, le=30)
    end: float = Field(gt=0, le=30)
    instruments: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=1, max_length=12
    )
    withhold: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=12
    )
    development: str = Field(min_length=1, max_length=400)


class ArrangementPlan(Strict):
    sections: list[ArrangementSection] = Field(min_length=3, max_length=4)
    continuity: str = Field(
        default="Keep one tempo, tonal center, motif and sonic palette; introduce parts without stopping or restarting.",
        max_length=500,
    )
    timing: Literal["approximate_targets"] = "approximate_targets"

    @model_validator(mode="after")
    def timeline(self):
        names = [s.name for s in self.sections]
        if names not in (
            ["intro", "groove_entry", "main_groove"],
            ["intro", "groove_entry", "main_groove", "outro"],
        ):
            raise ValueError(
                "Expected intro → groove_entry → main_groove → optional outro."
            )
        end = 0
        for section in self.sections:
            if abs(section.start - end) > 1e-6 or section.end <= section.start:
                raise ValueError(
                    "Sections must be positive, contiguous and start at zero."
                )
            if set(section.instruments) & set(section.withhold):
                raise ValueError(
                    "An instrument cannot be present and withheld in one section."
                )
            end = section.end
        return self


class MusicIntent(Strict):
    genre: str = Field(default="", max_length=200)
    subgenre: str = Field(default="", max_length=200)
    era: str = Field(default="", max_length=200)
    production_character: str = Field(default="", max_length=400)
    rhythmic_feel: str = Field(default="", max_length=400)
    drum_pattern: str = Field(default="", max_length=400)
    bass_character: str = Field(default="", max_length=400)
    rhythm_guitar: str = Field(default="", max_length=400)
    synth_and_keys: str = Field(default="", max_length=400)
    vocal_character: str = Field(default="", max_length=400)
    arrangement: str = Field(default="", max_length=600)
    arrangement_plan: ArrangementPlan | None = None
    additional_direction: str = Field(default="", max_length=2000)
    bpm: int | None = Field(default=None, ge=30, le=300)
    time_signature: Literal["", "2/4", "3/4", "4/4", "6/8"] = ""
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    vocal_mode: Literal["unspecified", "instrumental", "vocal"] = "unspecified"


class Generate(Strict):
    prompt: str = Field(min_length=3, max_length=2000)
    duration: float = Field(default=30, ge=15, le=30)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    instrumental: bool | None = None
    lyrics: str = Field(default="", max_length=4000)
    intent: MusicIntent | None = None
    music_plan: MusicPlan | None = None
    inference_profile: Literal["turbo_4bit", "turbo_8bit"] = "turbo_4bit"

    @model_validator(mode="after")
    def one_plan(self):
        if self.intent is not None and self.music_plan is not None:
            raise ValueError("Use Music Intent or Music Plan, not both.")
        return self


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
