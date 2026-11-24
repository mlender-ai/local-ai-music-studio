"""STDIO transport for the verified local engine, without importing model code."""

from mcp.server.fastmcp import FastMCP
from engine import jobs, service, store
from engine.daw_workspace import mcp_tools as daw_mcp
from engine.schema import Generate, Effect

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
        ),
        request_key,
    )


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


# --- AI-Native DAW Phase 02 Agent Bridge MCP Tools ---

@server.tool(name="daw.list_projects", annotations=READ)
def daw_list_projects() -> dict:
    """List local AI-Native DAW projects with revision, BPM, track count, and update time."""
    return daw_mcp.list_projects()


@server.tool(name="daw.get_active_project", annotations=READ)
def daw_get_active_project(session_id: str | None = None) -> dict:
    """Get the currently active DAW project and browser session state."""
    return daw_mcp.get_active_project(session_id)


@server.tool(name="daw.get_project", annotations=READ)
def daw_get_project(project_id: str | None = None) -> dict:
    """Read the full versioned project JSON for a DAW project."""
    return daw_mcp.get_project(project_id)


@server.tool(name="daw.get_selection", annotations=READ)
def daw_get_selection(session_id: str | None = None) -> dict:
    """Read the live Selection Context (track, clips, bar/time range, BPM, revision, active Blueprint)."""
    return daw_mcp.get_selection(session_id)


@server.tool(name="daw.get_tracks", annotations=READ)
def daw_get_tracks(project_id: str | None = None) -> dict:
    """List all tracks in a DAW project with gain, pan, mute, solo, and clip counts."""
    return daw_mcp.get_tracks(project_id)


@server.tool(name="daw.get_clips", annotations=READ)
def daw_get_clips(project_id: str | None = None, track_id: str | None = None) -> dict:
    """List clips in a DAW project, optionally filtered to one track."""
    return daw_mcp.get_clips(project_id, track_id)


@server.tool(name="daw.get_sections", annotations=READ)
def daw_get_sections(project_id: str | None = None) -> dict:
    """List timeline section markers in a DAW project."""
    return daw_mcp.get_sections(project_id)


@server.tool(name="daw.get_midi_notes", annotations=READ)
def daw_get_midi_notes(clip_id: str, project_id: str | None = None) -> dict:
    """Read all MIDI note events (pitch, velocity, startBeat, durationBeats) in a MIDI clip."""
    return daw_mcp.get_midi_notes(clip_id, project_id)


@server.tool(name="daw.get_reference_analysis", annotations=READ)
def daw_get_reference_analysis(reference_id: str | None = None, project_id: str | None = None) -> dict:
    """Read real acoustic analysis results for a project's Reference track."""
    return daw_mcp.get_reference_analysis(reference_id, project_id)


@server.tool(name="daw.get_reference_blueprint", annotations=READ)
def daw_get_reference_blueprint(reference_id: str | None = None, project_id: str | None = None) -> dict:
    """Read the structured ReferenceBlueprint and user-selected musical influences."""
    return daw_mcp.get_reference_blueprint(reference_id, project_id)


@server.tool(name="daw.get_capabilities", annotations=READ)
def daw_get_capabilities() -> dict:
    """Inspect supported vs unsupported DAW commands so agents never fabricate unsupported edits."""
    return daw_mcp.get_capabilities()


@server.tool(name="daw.add_track", annotations=WRITE)
def daw_add_track(name: str, track_type: str = "audio", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Add an audio, stem, or midi track to the DAW project."""
    return daw_mcp.add_track(name, track_type, project_id, expected_revision, stage_only)


@server.tool(name="daw.move_clip", annotations=WRITE)
def daw_move_clip(clip_id: str, timeline_start_beats: float, target_track_id: str | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Move a clip to a new beat position (and optional compatible track)."""
    return daw_mcp.move_clip(clip_id, timeline_start_beats, target_track_id, project_id, expected_revision, stage_only)


@server.tool(name="daw.split_clip", annotations=WRITE)
def daw_split_clip(clip_id: str, split_beat: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Split an audio or MIDI clip non-destructively at a timeline beat position."""
    return daw_mcp.split_clip(clip_id, split_beat, project_id, expected_revision, stage_only)


@server.tool(name="daw.duplicate_clip", annotations=WRITE)
def daw_duplicate_clip(clip_id: str, timeline_start_beats: float | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Duplicate a clip immediately after itself or at a specified beat."""
    return daw_mcp.duplicate_clip(clip_id, timeline_start_beats, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_gain", annotations=WRITE)
def daw_set_track_gain(track_id: str, gain_db: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Set a track's mixer gain in dB (-60 to +6 dB)."""
    return daw_mcp.set_track_gain(track_id, gain_db, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_pan", annotations=WRITE)
def daw_set_track_pan(track_id: str, pan: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Set a track's stereo pan (-1.0 hard left to +1.0 hard right)."""
    return daw_mcp.set_track_pan(track_id, pan, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_mute", annotations=WRITE)
def daw_set_track_mute(track_id: str, mute: bool, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Mute or unmute a DAW track."""
    return daw_mcp.set_track_mute(track_id, mute, project_id, expected_revision, stage_only)


@server.tool(name="daw.edit_midi_notes", annotations=WRITE)
def daw_edit_midi_notes(clip_id: str, operations: list[dict], project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Apply validated midi.addNote / moveNote / resizeNote / setVelocity / deleteNote operations."""
    return daw_mcp.edit_midi_notes(clip_id, operations, project_id, expected_revision, stage_only)


@server.tool(name="daw.add_section", annotations=WRITE)
def daw_add_section(name: str, start_beats: float, end_beats: float, color: str = "#4a5968", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = False) -> dict:
    """Add a named section marker to the arrangement timeline."""
    return daw_mcp.add_section(name, start_beats, end_beats, color, project_id, expected_revision, stage_only)


@server.tool(name="daw.preview_changes", annotations=WRITE)
def daw_preview_changes(summary: str, operations: list[dict], project_id: str | None = None, base_revision: int | None = None) -> dict:
    """Stage revision-checked edits as a pending ChangeProposal for user preview & approval in the DAW UI."""
    return daw_mcp.preview_changes(summary, operations, project_id, base_revision)


@server.tool(name="daw.apply_changes", annotations=WRITE)
def daw_apply_changes(proposal_id: str, project_id: str | None = None) -> dict:
    """Apply a staged pending ChangeProposal atomically (recording Undo snapshot & bumping revision)."""
    return daw_mcp.apply_changes(proposal_id, project_id)


@server.tool(name="daw.reject_changes", annotations=WRITE)
def daw_reject_changes(proposal_id: str, project_id: str | None = None) -> dict:
    """Reject a pending ChangeProposal without modifying the project."""
    return daw_mcp.reject_changes(proposal_id, project_id)


@server.tool(name="daw.undo", annotations=WRITE)
def daw_undo(project_id: str | None = None) -> dict:
    """Undo the last applied agent/server project mutation."""
    return daw_mcp.undo(project_id)


@server.tool(name="daw.redo", annotations=WRITE)
def daw_redo(project_id: str | None = None) -> dict:
    """Redo the last undone agent/server project mutation."""
    return daw_mcp.redo(project_id)


@server.tool(name="daw.analyze_reference", annotations=WRITE)
def daw_analyze_reference(reference_id: str | None = None, project_id: str | None = None, sync: bool = True) -> dict:
    """Run real acoustic analysis on a Reference track and generate its ReferenceBlueprint."""
    return daw_mcp.analyze_reference(reference_id, project_id, sync)


@server.tool(name="daw.get_analysis_status", annotations=READ)
def daw_get_analysis_status(job_id: str) -> dict:
    """Poll progress/status of an async Reference analysis job."""
    return daw_mcp.get_analysis_status(job_id)


@server.tool(name="daw.compare_audio", annotations=READ)
def daw_compare_audio(reference_id: str, target_kind: str = "project_mix", target_id: str | None = None, project_id: str | None = None) -> dict:
    """Compare a Reference against the current project mix or an audio asset using normalized acoustic metrics."""
    return daw_mcp.compare_audio(reference_id, target_kind, target_id, project_id)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
