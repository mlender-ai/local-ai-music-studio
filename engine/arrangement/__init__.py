"""Phase 04: Selective Arrangement, Musical Variation, Audio Seam Validation, Take Comping & Project Music Memory."""

from .audio_ops import create_reversed_clip_asset, render_contextual_preview_pair, validate_audio_seam
from .memory import ensure_music_memory, record_conversation_turn, resolve_contextual_reference, update_project_music_memory
from .midi_variation import execute_arrangement_edit_plan, generate_variation_take
from .scope import ArrangementEditPlan, EditScope, create_arrangement_edit_plan, extract_midi_notes_in_range
from .take_lanes import promote_take_lane, rename_take_lane, restore_original_lane

__all__ = [
    "ArrangementEditPlan",
    "EditScope",
    "create_arrangement_edit_plan",
    "create_reversed_clip_asset",
    "ensure_music_memory",
    "execute_arrangement_edit_plan",
    "extract_midi_notes_in_range",
    "generate_variation_take",
    "promote_take_lane",
    "record_conversation_turn",
    "rename_take_lane",
    "render_contextual_preview_pair",
    "resolve_contextual_reference",
    "restore_original_lane",
    "update_project_music_memory",
    "validate_audio_seam",
]
