"""STDIO transport for the verified local engine, without importing model code."""

from mcp.server.fastmcp import FastMCP
from engine import jobs, service, store
from engine.schema import Generate, Effect, MusicIntent
from engine.music_plan import MusicPlan
from typing import Literal

server = FastMCP("Local AI Music Studio")
READ = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


@server.tool(name="music.generate", annotations=WRITE)
def generate(
    prompt: str,
    duration: float = 30,
    seed: int = 42,
    instrumental: bool | None = None,
    lyrics: str = "",
    request_key: str | None = None,
    intent: MusicIntent | None = None,
    music_plan: MusicPlan | None = None,
    inference_profile: Literal["turbo_4bit", "turbo_8bit"] = "turbo_4bit",
) -> dict:
    """Generate real music offline with ACE-Step. Returns a job ID immediately.

    Duration 15–30s, one model job at a time. Poll music.get_status until
    succeeded/failed. A stable request_key deduplicates retries.
    """
    return jobs.submit(
        Generate(
            prompt=prompt,
            duration=duration,
            seed=seed,
            instrumental=instrumental,
            lyrics=lyrics,
            intent=intent,
            music_plan=music_plan,
            inference_profile=inference_profile,
        ),
        request_key,
    )


@server.tool(name="music.plan", annotations=READ)
def plan(
    prompt: str, instrumental: bool | None = None, intent: MusicIntent | None = None
) -> dict:
    """Preview/edit Music Intent and exact caption; ambiguous vocals require a choice before generation."""
    from agent.music_intent import preview

    return preview(Generate(prompt=prompt, instrumental=instrumental, intent=intent))


@server.tool(name="music.director_plan", annotations=READ)
def director_plan(
    prompt: str,
    duration: float = 30,
    instrumental: bool | None = None,
    music_plan: MusicPlan | None = None,
) -> dict:
    """Validate Codex/user Music Plan JSON, or draft an explicit offline preset.

    Reports exact caption/token budget and soft targets vs actual parameters.
    Pass returned music_plan to music.generate. No LLM download or track mixing.
    """
    from agent.director import preview

    return preview(
        Generate(
            prompt=prompt,
            duration=duration,
            instrumental=instrumental,
            music_plan=music_plan,
        )
    )


@server.tool(name="music.session_lab", annotations=READ)
def session_lab() -> dict:
    """Get playable A/B/C/D, independent stem version IDs, sources, sections and mixer settings."""
    from engine.session.catalog import manifest

    return manifest()


@server.tool(name="music.apply_effect", annotations=WRITE)
def apply_effect(version_id: str, effect: Effect) -> dict:
    """Apply one validated effect to a stored WAV; preserve its original.

    For boosts that exceed full scale, use music.render with a final limiter.
    """
    return service.render(version_id, [effect.model_dump()])


@server.tool(name="music.render", annotations=WRITE)
def render(version_id: str, effects: list[Effect]) -> dict:
    """Render an ordered, validated chain into a new immutable WAV version."""
    return service.render(version_id, [effect.model_dump() for effect in effects])


@server.tool(name="music.compare", annotations=READ)
def compare(original_id: str, modified_id: str) -> dict:
    """Compare sample rate, stereo channels, frames, peaks, clipping and waveform difference."""
    return service.compare_versions(original_id, modified_id)


@server.tool(name="music.get_status", annotations=READ)
def get_status(job_id: str | None = None) -> dict:
    """Get job progress/error/result. Omit job_id for a compact job list."""
    if job_id:
        return jobs.status(job_id)
    state = jobs.status()
    return dict(
        max_concurrent_generations=1,
        jobs=[
            dict(
                id=j["id"],
                state=j["state"],
                error=j["error"],
                version_id=j["result"]["id"] if j["result"] else None,
            )
            for j in state["jobs"]
        ],
    )


@server.tool(name="music.export", annotations=WRITE)
def export(version_id: str, filename: str | None = None) -> dict:
    """Copy a stored version to outputs/exports as WAV; never overwrite or escape the output root."""
    return service.export(version_id, filename)


@server.tool(name="music.produce", annotations=WRITE)
def produce(version_id: str, instruction: str) -> dict:
    """Apply a Korean/English production instruction and return its plan and A/B comparison.

    Supports heavier bass, dreamy reverb, compression and saturation. Melody,
    arrangement, instrument replacement and stem edits return an explicit
    requires_regeneration response, without pretending to change them with EQ.
    """
    return service.produce(version_id, instruction)


@server.tool(name="music.list_versions", annotations=READ)
def list_versions() -> dict:
    """List stored audio versions, parent links, paths, prompts and effect history."""
    return store.list_versions()


@server.tool(name="music.restore", annotations=WRITE)
def restore(version_id: str) -> dict:
    """Select a previous version as current while preserving all other versions."""
    return store.restore(version_id)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
