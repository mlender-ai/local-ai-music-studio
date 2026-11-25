"""Phase 05 GATE 4: Professional FX, Sidechain, Routing, Automation & Track Freeze Package."""

from .automation import (
    apply_automated_filter_sweep,
    evaluate_automation_at_beat,
    find_automation_lane,
    sample_automation_curve,
)
from .chain import FX_BY_TYPE, FX_CATALOG, default_fx_slot, list_fx_catalog, process_fx_chain
from .delay_mod import SUBDIVISION_BEATS, apply_chorus, apply_delay, apply_flanger, apply_phaser, apply_saturation, apply_tremolo, compute_delay_ms
from .dynamics import apply_compressor, apply_limiter, apply_noise_gate, apply_sidechain_compressor, apply_transient_shaper
from .eq import DEFAULT_EQ_BANDS, apply_parametric_eq, compute_eq_response_curve
from .freeze import compute_track_render_hash, freeze_track, is_track_freeze_valid, unfreeze_track
from .guitar_amp import AMP_MODELS, CABINET_PROFILES, apply_guitar_amp
from .reverb import REVERB_MODES, apply_reverb

__all__ = [
    "AMP_MODELS",
    "CABINET_PROFILES",
    "DEFAULT_EQ_BANDS",
    "FX_BY_TYPE",
    "FX_CATALOG",
    "REVERB_MODES",
    "SUBDIVISION_BEATS",
    "apply_automated_filter_sweep",
    "apply_chorus",
    "apply_compressor",
    "apply_delay",
    "apply_flanger",
    "apply_guitar_amp",
    "apply_limiter",
    "apply_noise_gate",
    "apply_parametric_eq",
    "apply_phaser",
    "apply_reverb",
    "apply_saturation",
    "apply_sidechain_compressor",
    "apply_transient_shaper",
    "apply_tremolo",
    "compute_delay_ms",
    "compute_eq_response_curve",
    "compute_track_render_hash",
    "default_fx_slot",
    "evaluate_automation_at_beat",
    "find_automation_lane",
    "freeze_track",
    "is_track_freeze_valid",
    "list_fx_catalog",
    "process_fx_chain",
    "sample_automation_curve",
    "unfreeze_track",
]
