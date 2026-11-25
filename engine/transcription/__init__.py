"""Phase 03.2: Advanced Reference Intelligence — Real Music Transcription, Chord Track & Blueprint v2."""

from .basic_pitch_transcriber import extract_melody_topline, transcribe_audio_basic_pitch
from .chord_tracker import extract_chord_timeline, parse_chord_metadata
from .drum_transcriber import transcribe_drum_groove
from .pipeline import (
    DEFAULT_FEATURE_LOCKS,
    FEATURE_LOCK_SPECS,
    build_reference_blueprint_v2,
    reconstruct_reference_to_project,
    transcribe_reference_audio,
    validate_feature_locks_for_engine,
)
from .sheetsage_adapter import build_yue2_abc_from_reference, probe_sheetsage2

__all__ = [
    "DEFAULT_FEATURE_LOCKS",
    "FEATURE_LOCK_SPECS",
    "build_reference_blueprint_v2",
    "build_yue2_abc_from_reference",
    "extract_chord_timeline",
    "extract_melody_topline",
    "parse_chord_metadata",
    "probe_sheetsage2",
    "reconstruct_reference_to_project",
    "transcribe_audio_basic_pitch",
    "transcribe_drum_groove",
    "transcribe_reference_audio",
    "validate_feature_locks_for_engine",
]
