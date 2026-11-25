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
def daw_add_track(name: str, track_type: str = "audio", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Add an audio, stem, or midi track (defaults to safe staged proposal; pass stage_only=False only when authorized)."""
    return daw_mcp.add_track(name, track_type, project_id, expected_revision, stage_only)


@server.tool(name="daw.move_clip", annotations=WRITE)
def daw_move_clip(clip_id: str, timeline_start_beats: float, target_track_id: str | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Move a clip to a new beat position (defaults to safe staged proposal)."""
    return daw_mcp.move_clip(clip_id, timeline_start_beats, target_track_id, project_id, expected_revision, stage_only)


@server.tool(name="daw.split_clip", annotations=WRITE)
def daw_split_clip(clip_id: str, split_beat: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Split an audio or MIDI clip non-destructively (defaults to safe staged proposal)."""
    return daw_mcp.split_clip(clip_id, split_beat, project_id, expected_revision, stage_only)


@server.tool(name="daw.duplicate_clip", annotations=WRITE)
def daw_duplicate_clip(clip_id: str, timeline_start_beats: float | None = None, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Duplicate a clip (defaults to safe staged proposal)."""
    return daw_mcp.duplicate_clip(clip_id, timeline_start_beats, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_gain", annotations=WRITE)
def daw_set_track_gain(track_id: str, gain_db: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Set a track's mixer gain in dB (defaults to safe staged proposal)."""
    return daw_mcp.set_track_gain(track_id, gain_db, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_pan", annotations=WRITE)
def daw_set_track_pan(track_id: str, pan: float, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Set a track's stereo pan (defaults to safe staged proposal)."""
    return daw_mcp.set_track_pan(track_id, pan, project_id, expected_revision, stage_only)


@server.tool(name="daw.set_track_mute", annotations=WRITE)
def daw_set_track_mute(track_id: str, mute: bool, project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Mute or unmute a DAW track (defaults to safe staged proposal)."""
    return daw_mcp.set_track_mute(track_id, mute, project_id, expected_revision, stage_only)


@server.tool(name="daw.edit_midi_notes", annotations=WRITE)
def daw_edit_midi_notes(clip_id: str, operations: list[dict], project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Edit MIDI notes (defaults to safe staged proposal)."""
    return daw_mcp.edit_midi_notes(clip_id, operations, project_id, expected_revision, stage_only)


@server.tool(name="daw.add_section", annotations=WRITE)
def daw_add_section(name: str, start_beats: float, end_beats: float, color: str = "#4a5968", project_id: str | None = None, expected_revision: int | None = None, stage_only: bool = True) -> dict:
    """Add a named section marker (defaults to safe staged proposal)."""
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


# --- AI-Native DAW Phase 03 Composition Engine MCP Tools ---

@server.tool(name="daw.create_composition_plan", annotations=WRITE)
def daw_create_composition_plan(
    instruction: str,
    mode: str | None = None,
    target_instrument: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    use_project_chord_track: bool = False,
    project_id: str | None = None,
    provider_id: str | None = None,
) -> dict:
    """Design a structured CompositionPlan (Identity, Motif, Harmony, Roles, Sections, Reference Binding & Feature Locks) before generating audio/MIDI."""
    return daw_mcp.create_composition_plan(
        instruction,
        mode,
        target_instrument,
        reference_ids,
        selected_influences,
        project_id,
        provider_id,
        feature_locks=feature_locks,
        reference_mode=reference_mode,
        use_project_chord_track=use_project_chord_track,
    )


@server.tool(name="daw.get_composition_plan", annotations=READ)
def daw_get_composition_plan(plan_id: str | None = None, project_id: str | None = None) -> dict:
    """Read a stored CompositionPlan (defaults to the latest plan in the active project)."""
    return daw_mcp.get_composition_plan(plan_id, project_id)


@server.tool(name="daw.generate_music", annotations=WRITE)
def daw_generate_music(
    instruction: str | None = None,
    plan_id: str | None = None,
    reference_ids: list[str] | None = None,
    selected_influences: list[str] | None = None,
    feature_locks: dict[str, str] | None = None,
    reference_mode: str = "reference_compose",
    use_project_chord_track: bool = False,
    engine_choice: str = "auto",
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict:
    """Mode A: Generate a full multi-section arrangement Take with BS.1770-4 loudness, Reference Feature Verification & level-matched preview."""
    return daw_mcp.generate_music(
        instruction,
        plan_id,
        reference_ids,
        selected_influences,
        engine_choice,
        seed,
        sync,
        project_id,
        feature_locks=feature_locks,
        reference_mode=reference_mode,
        use_project_chord_track=use_project_chord_track,
    )


@server.tool(name="daw.generate_instrument", annotations=WRITE)
def daw_generate_instrument(
    instruction: str,
    target_instrument: str = "synth_hook",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict:
    """Mode B: Generate an editable instrument session (MIDI + rendered studio stem WAV)."""
    return daw_mcp.generate_instrument(instruction, target_instrument, reference_ids, seed, sync, project_id)


@server.tool(name="daw.generate_loop", annotations=WRITE)
def daw_generate_loop(
    instruction: str,
    target_instrument: str = "drums",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict:
    """Mode C: Generate a tempo-locked musical loop (drums/bass/keys/guitar/synth_hook) with variation."""
    return daw_mcp.generate_loop(instruction, target_instrument, reference_ids, seed, sync, project_id)


@server.tool(name="daw.generate_midi", annotations=WRITE)
def daw_generate_midi(
    instruction: str,
    target_instrument: str = "synth_hook",
    reference_ids: list[str] | None = None,
    seed: int | None = None,
    sync: bool = True,
    project_id: str | None = None,
) -> dict:
    """Mode C: Generate editable motif-based MIDI notes locked to project key/chords without touching other tracks."""
    return daw_mcp.generate_midi(instruction, target_instrument, reference_ids, seed, sync, project_id)


@server.tool(name="daw.separate_stems", annotations=WRITE)
def daw_separate_stems(asset_id: str, model_name: str = "htdemucs", sync: bool = False, project_id: str | None = None) -> dict:
    """Separate an audio asset into Drums/Bass/Other/Vocals via Demucs (honestly reports unavailable if Demucs is not installed)."""
    return daw_mcp.separate_stems(asset_id, model_name, sync, project_id)


@server.tool(name="daw.list_generation_jobs", annotations=READ)
def daw_list_generation_jobs(project_id: str | None = None) -> dict:
    """List background music generation jobs and their stages/logs."""
    return daw_mcp.list_generation_jobs(project_id)


@server.tool(name="daw.get_generation_status", annotations=READ)
def daw_get_generation_status(job_id: str) -> dict:
    """Poll real-time stage, progress, and logs for a background generation job."""
    return daw_mcp.get_generation_status(job_id)


@server.tool(name="daw.cancel_generation", annotations=WRITE)
def daw_cancel_generation(job_id: str) -> dict:
    """Cancel a queued or running background generation job."""
    return daw_mcp.cancel_generation(job_id)


@server.tool(name="daw.get_generation_result", annotations=READ)
def daw_get_generation_result(take_id: str, project_id: str | None = None) -> dict:
    """Fetch full Take metadata, artifacts, QualityReport, Planned vs Detected sections & provenance."""
    return daw_mcp.get_generation_result(take_id, project_id)


@server.tool(name="daw.preview_generation", annotations=READ)
def daw_preview_generation(take_id: str, project_id: str | None = None) -> dict:
    """Return level-matched (-16 LUFS) preview audio metadata and QualityReport for a Take."""
    return daw_mcp.preview_generation(take_id, project_id)


@server.tool(name="daw.stage_generation_import", annotations=WRITE)
def daw_stage_generation_import(
    take_id: str,
    apply_mode: str = "new_tracks",
    target_track_id: str | None = None,
    start_beats: float | None = None,
    project_id: str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Transactionally apply a Take into the DAW timeline (`new_tracks`, `selected_range`, `new_project`, `keep_take`) with 1-click Undo."""
    return daw_mcp.stage_generation_import(take_id, apply_mode, target_track_id, start_beats, project_id, expected_revision)


@server.tool(name="daw.list_takes", annotations=READ)
def daw_list_takes(project_id: str | None = None) -> dict:
    """List all generated Takes stored in a project."""
    return daw_mcp.list_takes(project_id)


@server.tool(name="daw.select_take", annotations=WRITE)
def daw_select_take(
    take_id: str,
    action: str = "apply",
    apply_mode: str = "new_tracks",
    target_track_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Apply, keep, or reject a generated Take (`action`: apply | keep | reject)."""
    return daw_mcp.select_take(take_id, action, apply_mode, target_track_id, project_id)


@server.tool(name="daw.list_providers", annotations=READ)
def daw_list_providers() -> dict:
    """Inspect honestly detected local/CLI/MCP/API AI Producer providers and active selection."""
    return daw_mcp.list_providers()


@server.tool(name="daw.list_instruments", annotations=READ)
def daw_list_instruments() -> dict:
    """List built-in multi-timbre studio instruments and local music generation engines."""
    return daw_mcp.list_instruments()


@server.tool(name="daw.get_runtime_status", annotations=READ)
def daw_get_runtime_status() -> dict:
    """Inspect Shared Runtime Registry 6-state status across YuE2, ACE-Step, Demucs, Vocal QA models, and Editable MIDI."""
    return daw_mcp.get_runtime_status()


# --- AI-Native DAW Phase 04 Selective Arrangement, Variation & Take Comping MCP Tools ---

@server.tool(name="daw.create_arrangement_edit_plan", annotations=READ)
def daw_create_arrangement_edit_plan(
    instruction: str,
    intensity: str | None = None,
    target_track_id: str | None = None,
    start_beats: float | None = None,
    end_beats: float | None = None,
    project_id: str | None = None,
    provider_id: str | None = None,
) -> dict:
    """Inspect real MIDI/clip context and build a scope-bounded ArrangementEditPlan (with preserved tracks & bars)."""
    return daw_mcp.create_arrangement_edit_plan(
        instruction, intensity, target_track_id, start_beats, end_beats, project_id, provider_id
    )


@server.tool(name="daw.generate_variation", annotations=WRITE)
def daw_generate_variation(
    instruction: str | None = None,
    plan: dict | None = None,
    intensity: str | None = None,
    target_track_id: str | None = None,
    start_beats: float | None = None,
    end_beats: float | None = None,
    seed: int = 42,
    project_id: str | None = None,
) -> dict:
    """Generate a non-destructive selective musical Variation Take (with Solo, In-Context & Original A/B previews) or structural edit."""
    return daw_mcp.generate_variation(
        instruction, plan, intensity, target_track_id, start_beats, end_beats, seed, project_id
    )


@server.tool(name="daw.promote_take_lane", annotations=WRITE)
def daw_promote_take_lane(
    track_id: str,
    lane_id: str,
    start_beats: float | None = None,
    end_beats: float | None = None,
    project_id: str | None = None,
) -> dict:
    """Promote an entire Take Lane or a selective bar sub-range (comping) onto the Track main lane with automatic Original backup."""
    return daw_mcp.promote_take_lane(track_id, lane_id, start_beats, end_beats, project_id)


@server.tool(name="daw.restore_original_take_lane", annotations=WRITE)
def daw_restore_original_take_lane(
    track_id: str,
    lane_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Restore a Track's Original Backup Take Lane onto the main timeline with 1-click Undo."""
    return daw_mcp.restore_original_take_lane(track_id, lane_id, project_id)


@server.tool(name="daw.reverse_audio_clip", annotations=WRITE)
def daw_reverse_audio_clip(
    clip_id: str,
    project_id: str | None = None,
    expected_revision: int | None = None,
) -> dict:
    """Non-destructively reverse an audio clip by creating a new immutable reversed WAV asset while preserving the original."""
    return daw_mcp.reverse_audio_clip(clip_id, project_id, expected_revision)


@server.tool(name="daw.get_music_memory", annotations=READ)
def daw_get_music_memory(project_id: str | None = None) -> dict:
    """Read compact Project Music Memory (genre, key, chords, instrument roles, liked/rejected takes, recent conversation turns)."""
    return daw_mcp.get_music_memory(project_id)


# --- AI-Native DAW Phase 03.2 Advanced Reference Intelligence MCP Tools ---

@server.tool(name="daw.transcribe_reference", annotations=WRITE)
def daw_transcribe_reference(
    reference_id: str | None = None,
    use_demucs: bool = True,
    demucs_model: str = "htdemucs",
    sync: bool = True,
    project_id: str | None = None,
) -> dict:
    """Run precision transcription on a Reference (Demucs 4-stem separation + Basic Pitch ONNX + Drum groove + Sub-bar Chords + Blueprint v2)."""
    return daw_mcp.transcribe_reference(reference_id, use_demucs, demucs_model, sync, project_id)


@server.tool(name="daw.get_chord_track", annotations=READ)
def daw_get_chord_track(project_id: str | None = None) -> dict:
    """Read the project's editable Timeline Chord Track (sub-bar chord symbols, inversions, confidence & lock state)."""
    return daw_mcp.get_chord_track(project_id)


@server.tool(name="daw.set_chord_track", annotations=WRITE)
def daw_set_chord_track(
    chords: list[dict],
    locked: bool | None = None,
    project_id: str | None = None,
    expected_revision: int | None = None,
    stage_only: bool = False,
) -> dict:
    """Replace or lock the project's Timeline Chord Track (recorded with 1-click Undo snapshot)."""
    return daw_mcp.set_chord_track(chords, locked, project_id, expected_revision, stage_only)


@server.tool(name="daw.update_reference_locks", annotations=WRITE)
def daw_update_reference_locks(
    reference_id: str | None = None,
    feature_locks: dict[str, str] | None = None,
    chord_corrections: list[dict] | None = None,
    section_renames: dict[str, str] | None = None,
    project_id: str | None = None,
) -> dict:
    """Update a Reference's 10-feature lock matrix (free/reference/locked) and direct user chord/section corrections."""
    return daw_mcp.update_reference_locks(reference_id, feature_locks, chord_corrections, section_renames, project_id)


@server.tool(name="daw.import_reference_transcription", annotations=WRITE)
def daw_import_reference_transcription(
    reference_id: str | None = None,
    import_chords: bool = True,
    import_drums_midi: bool = False,
    import_bass_midi: bool = False,
    import_melody_midi: bool = False,
    import_stems: bool = False,
    import_sections: bool = False,
    project_id: str | None = None,
) -> dict:
    """Selectively import transcribed Reference Chord Track, Drum/Bass/Melody MIDI, Stems, or Sections into the DAW project."""
    return daw_mcp.import_reference_transcription(
        reference_id,
        import_chords,
        import_drums_midi,
        import_bass_midi,
        import_melody_midi,
        import_stems,
        import_sections,
        project_id,
    )


@server.tool(name="daw.reconstruct_from_reference", annotations=WRITE)
def daw_reconstruct_from_reference(
    reference_id: str | None = None,
    import_stems: bool = False,
    use_quantized_drums: bool = True,
    project_id: str | None = None,
) -> dict:
    """Mode A Reconstruct: rebuild an analyzed Reference as editable MIDI tracks, Chord Track, Arrangement Markers & optional Demucs Stems (1-click Undoable)."""
    return daw_mcp.reconstruct_from_reference(reference_id, import_stems, use_quantized_drums, project_id)


@server.tool(name="daw.get_reference_abc_score", annotations=READ)
def daw_get_reference_abc_score(
    reference_id: str | None = None,
    mode: str = "reference_compose",
    project_id: str | None = None,
) -> dict:
    """Build or read a YuE2-compliant instrumental ABC score (passing check_resting_voice) derived from a transcribed Reference."""
    return daw_mcp.get_reference_abc_score(reference_id, mode, project_id)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
