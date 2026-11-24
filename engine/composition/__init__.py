"""Phase 03-C/E: Composition Director, Reference Context Binding, MIDI Composer, Validation & Sample Library."""

from .director import create_composition_plan
from .library import list_library_catalog
from .midi_composer import compose_midi_part, compose_multitrack_parts, notes_to_midi_bytes
from .reference_context import build_reference_binding
from .validation import validate_midi_composition

__all__ = [
    "build_reference_binding",
    "compose_midi_part",
    "compose_multitrack_parts",
    "create_composition_plan",
    "list_library_catalog",
    "notes_to_midi_bytes",
    "validate_midi_composition",
]
