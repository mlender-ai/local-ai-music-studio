"""Phase 05 GATE 3: Professional Virtual Instrument Package (SoundFont SF3, Pro Synth, Sampler, Drum Rack, Plugin Scanner)."""

from .articulation import apply_articulation
from .drum_rack import DRUM_RACK_KITS, render_drum_rack_sequence
from .plugin_scanner import scan_host_plugins
from .pro_synth import PRO_SYNTH_PRESETS, render_pro_synth_sequence, resolve_pro_synth_params
from .registry import get_instrument_catalog, list_instruments, render_instrument_preview, render_track_instrument
from .sampler import render_sampler_sequence, slice_audio_by_transients
from .soundfont_engine import SOUNDFONT_INSTRUMENTS, probe_fluidsynth_engine, render_soundfont_sequence
from .synth_engine import INSTRUMENTS, synth_note_for_instrument

__all__ = [
    "DRUM_RACK_KITS",
    "INSTRUMENTS",
    "PRO_SYNTH_PRESETS",
    "SOUNDFONT_INSTRUMENTS",
    "apply_articulation",
    "get_instrument_catalog",
    "list_instruments",
    "probe_fluidsynth_engine",
    "render_drum_rack_sequence",
    "render_instrument_preview",
    "render_pro_synth_sequence",
    "render_sampler_sequence",
    "render_soundfont_sequence",
    "render_track_instrument",
    "resolve_pro_synth_params",
    "scan_host_plugins",
    "slice_audio_by_transients",
    "synth_note_for_instrument",
]
