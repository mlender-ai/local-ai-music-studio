"""Director contract: musical intentions are soft conditioning, never stem controls."""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=180)]


class StrictPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Rhythm(StrictPlan):
    bpm: int = Field(ge=30, le=300)
    meter: Literal["2/4", "3/4", "4/4", "6/8"] = "4/4"
    pattern: Text
    accents_and_space: Text


class Harmony(StrictPlan):
    key: str = Field(pattern=r"^[A-G](#|b)? (major|minor)$")
    progression: Text
    voicing: Text


class SessionPart(StrictPlan):
    instrument: Text
    role_and_interaction: Text


class MusicalEvent(StrictPlan):
    at_fraction: float = Field(ge=0, lt=1)
    action: Text


class Production(StrictPlan):
    tone: Text
    dynamics: Text
    space: Text


class MusicPlan(StrictPlan):
    version: Literal["director-v1"] = "director-v1"
    source: Literal["codex", "user", "preset_fallback"] = "user"
    style: Text
    rhythm: Rhythm
    harmony: Harmony
    sessions: list[SessionPart] = Field(min_length=1, max_length=8)
    events: list[MusicalEvent] = Field(min_length=1, max_length=8)
    production: Production
    exclusions: list[Text] = Field(default_factory=list, max_length=8)
    vocal_mode: Literal["instrumental", "vocal", "unspecified"] = "unspecified"

    @model_validator(mode="after")
    def chronology(self):
        times = [e.at_fraction for e in self.events]
        if times[0] != 0 or times != sorted(set(times)):
            raise ValueError(
                "Events must start at zero and have increasing distinct fractions."
            )
        return self
