"""V7.2 Golden Native Audio Reference Registry & Hybrid Mode Layering (Phase 03.2.1 · GATE 2 / Sections 12–15).

Preserves the exact V7.2 golden native audio lineage (`V7.2_Magnetic_Afterhours_128bpm.wav`, seed 1185,
yue2.cpp commit e646d5228911ae1b81ac2a261115a255848ce85f) and enforces Section 15 (Native Audio Quality Protection):
- Good native audio is ALWAYS imported untouched as `native_audio_original`, NEVER force-reconstructed into flat MIDI.
- Hybrid mode layers editable MIDI / Professional Instrument / FX tracks cleanly alongside the original native audio.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import soundfile as sf

from engine import paths as engine_paths
from engine.composition.director import create_composition_plan
from engine.composition.midi_composer import compose_midi_part
from engine.daw_workspace import commands, proposals, store
from engine.daw_workspace.schema import Clip, MidiNote, make_id

# Validated V7.2 instrumental ABC score (passes strict check_resting_voice: V:Vocal rests only, V:Ins melody)
V72_MAGNETIC_AFTERHOURS_ABC = """X:1
T:Magnetic Afterhours (V7.2 Golden Reference)
M:4/4
L:1/8
Q:1/4=128
K:Fm
% intro
V:Vocal
z8 | z8 | z8 | z8 |
V:Ins
"Fm7"F2 c2 _A2 G2 | "Dbmaj7"_D2 F2 _A2 c2 | "Abmaj7"_A2 c2 _e2 c2 | "Eb6"_E2 G2 _B2 G2 |
% chorus
V:Vocal
z8 | z8 | z8 | z8 |
V:Ins
"Fm7"f2 _e2 c2 _A2 | "Dbmaj7"_d2 c2 _A2 F2 | "Abmaj7"_e2 c2 _A2 c2 | "Eb6"_B2 G2 _E2 G2 |
"""

GOLDEN_NATIVE_REFERENCES: list[dict[str, Any]] = [
    {
        "id": "v72-magnetic-afterhours",
        "title": "V7.2 Magnetic Afterhours (128 BPM · F minor)",
        "genre": "house",
        "bpm": 128.0,
        "key": "F minor",
        "seed": 1185,
        "engine": "yue2-native",
        "sourceBranch": "origin/codex/v7-2-house-hook-first",
        "yue2CppCommit": "e646d5228911ae1b81ac2a261115a255848ce85f",
        "models": ["YuE2-3B-Q8_0.gguf", "YuE2-Vae-F32.gguf"],
        "relativePath": "outputs/daw/library/studio-recordings/V7.2_Magnetic_Afterhours_128bpm.wav",
        "abcScore": V72_MAGNETIC_AFTERHOURS_ABC,
        "descriptionKo": "V7.2 YuE2 Native 골든 레퍼런스 마스터(96초, 128 BPM F minor, 인스트루멘털 검증 완료). 하이브리드 레이어링 및 사운드 벤치마크 기준.",
        "descriptionEn": "V7.2 YuE2 Native golden reference master (96s, 128 BPM F minor, instrumental verified). Benchmark & Hybrid mode base.",
    },
    {
        "id": "v7-jazz-hiphop-90",
        "title": "Jazz Hip-Hop 90 BPM Master",
        "genre": "hiphop",
        "bpm": 90.0,
        "key": "D minor",
        "seed": 42,
        "engine": "yue2-native",
        "sourceBranch": "origin/codex/v7-1-two-genre-instrumental",
        "relativePath": "outputs/daw/library/studio-recordings/Jazz_Hip_Hop_90bpm_Master.wav",
        "descriptionKo": "90 BPM 재즈 힙합 네이티브 오디오 레퍼런스 마스터.",
        "descriptionEn": "90 BPM Jazz Hip-Hop native audio reference master.",
    },
    {
        "id": "v4-yue2-rock-original",
        "title": "V4 YuE2 Indie Rock Original",
        "genre": "rock",
        "bpm": 118.0,
        "key": "A minor",
        "seed": 42,
        "engine": "yue2-native",
        "sourceBranch": "origin/codex/yue2-native-recovery-v7",
        "relativePath": "outputs/daw/library/studio-recordings/V4_YuE2_Rock_Original.wav",
        "descriptionKo": "V4 YuE2 록 네이티브 오디오 오리지널 레퍼런스.",
        "descriptionEn": "V4 YuE2 Rock native audio original reference.",
    },
]

YUE2_RECOVERY_GUIDE: dict[str, Any] = {
    "yue2CppRepo": "https://github.com/d0p3t/yue2.cpp",
    "pinnedCommit": "e646d5228911ae1b81ac2a261115a255848ce85f",
    "requiredBinaries": ["cmake (brew install cmake)", "yue-synth", "yue-plan"],
    "requiredModels": [
        {"name": "YuE2-3B-Q8_0.gguf", "approxSizeGiB": 3.4, "targetPath": ".runtime/v4/models/YuE2-3B-Q8_0.gguf"},
        {"name": "YuE2-Vae-F32.gguf", "approxSizeGiB": 1.1, "targetPath": ".runtime/v4/models/YuE2-Vae-F32.gguf"},
    ],
    "envVars": ["YUE2_BIN", "YUE2_PLAN_BIN", "YUE2_MODEL_PATH", "YUE2_VAE_PATH", "DAW_SHARED_RUNTIME_DIR"],
    "honestyNote": "로컬 디스크에 cmake, yue-synth 바이너리 및 ~4.5 GiB GGUF 가중치가 설치되면 자동으로 YuE2 Native 경로가 활성화됩니다. 미설치 상태에서는 절대 MIDI를 YuE2로 위장하지 않습니다.",
}


def list_golden_references() -> list[dict[str, Any]]:
    """Return golden V7.2/V7/V4 native audio references with live disk availability & duration."""
    out: list[dict[str, Any]] = []
    for item in GOLDEN_NATIVE_REFERENCES:
        abs_p = (engine_paths.ROOT / item["relativePath"]).resolve()
        available = abs_p.is_file()
        duration_sec = None
        sample_rate = None
        if available:
            try:
                info = sf.info(str(abs_p))
                duration_sec = round(float(info.frames) / max(1, int(info.samplerate)), 3)
                sample_rate = int(info.samplerate)
            except Exception:
                pass
        out.append(
            {
                **item,
                "available": available,
                "durationSec": duration_sec,
                "sampleRate": sample_rate,
            }
        )
    return out


def create_hybrid_session(
    project_id: str,
    *,
    golden_reference_id: str | None = None,
    source_asset_id: str | None = None,
    layer_roles: list[str] | None = None,
    instruction: str = "원본 네이티브 오디오를 그대로 보존하면서 어울리는 편집 가능한 MIDI 신스/건반 레이어를 추가해줘",
    bars: int = 8,
) -> dict[str, Any]:
    """Hybrid Production Mode (Section 15): Preserve original Native Audio untouched + layer editable MIDI instruments!

    NEVER replaces or downgrades original native audio with flat MIDI reconstruction.
    """
    proj = store.load_project(project_id)
    proposals.record_undo_snapshot(proj)

    native_asset = None
    ref_bpm = proj.bpm
    ref_key = "F minor"
    ref_genre = "house"
    base_title = "Native Audio Original"

    if golden_reference_id:
        g_item = next((g for g in GOLDEN_NATIVE_REFERENCES if g["id"] == golden_reference_id), None)
        if not g_item:
            raise FileNotFoundError(f"Golden reference not found: {golden_reference_id}")
        abs_p = (engine_paths.ROOT / g_item["relativePath"]).resolve()
        if not abs_p.is_file():
            raise FileNotFoundError(f"Golden reference audio missing on disk: {g_item['relativePath']}")
        raw_bytes = abs_p.read_bytes()
        native_asset, _ = store.import_asset_bytes(
            project_id=project_id,
            filename=abs_p.name,
            raw_bytes=raw_bytes,
            kind_hint="audio",
            source="yue2-v72-golden-native",
            provenance=f"Native Audio Original ({g_item['title']}, {g_item['engine']}) — untouched master",
        )
        ref_bpm = float(g_item["bpm"])
        ref_key = str(g_item["key"])
        ref_genre = str(g_item["genre"])
        base_title = str(g_item["title"])
    elif source_asset_id:
        native_asset = next((a for a in proj.assets if a.id == source_asset_id), None)
        if not native_asset:
            raise FileNotFoundError(f"Audio asset not found: {source_asset_id}")
        base_title = native_asset.name
    else:
        raise ValueError("Either golden_reference_id or source_asset_id is required for Hybrid Mode")

    updated = store.load_project(project_id)
    bpb = updated.timeSignature.beats_per_bar
    if 30.0 <= ref_bpm <= 300.0:
        updated = commands.apply_command(updated, "project.setTempo", {"bpm": ref_bpm})

    # 1. Place untouched Native Audio Original track (Section 15 protection!)
    native_track_id = make_id("trk")
    native_dur_beats = max(bpb, round(native_asset.durationSec / (60.0 / updated.bpm), 2))
    updated = commands.apply_command(
        updated,
        "track.add",
        {
            "id": native_track_id,
            "name": f"{base_title[:28]} (Original)",
            "type": "audio",
            "color": "#6a9999",
            "stemMeta": {
                "assetKind": "native_audio_original",
                "protectedFromMidiOverwrite": True,
                "goldenReferenceId": golden_reference_id,
            },
        },
    )
    updated = commands.apply_command(
        updated,
        "clip.add",
        {
            "trackId": native_track_id,
            "clip": Clip(
                id=make_id("clp"),
                name=f"{base_title[:32]} (Native Audio)",
                type="audio",
                assetId=native_asset.id,
                timelineStartBeats=0.0,
                durationBeats=native_dur_beats,
                sourceOffsetSec=0.0,
                sourceDurationSec=native_asset.durationSec,
            ).model_dump(),
        },
    )

    # 2. Layer editable MIDI tracks cleanly on top (without altering the native audio track!)
    # Enforce Permanent Production Instrument Quality Policy (NEVER auto-select PREVIEW voices!)
    from engine.production.instrument_resolver import resolve_production_instrument

    roles = list(layer_roles or ["synth_hook", "pad"])
    plan = create_composition_plan(
        project=updated,
        instruction=f"{instruction} ({bars}마디, {ref_bpm} BPM, {ref_key}, {ref_genre})",
        mode="full_music",
        production_mode="hybrid",
    )
    layered_track_ids: list[str] = []
    role_meta = {
        "synth_hook": ("Hybrid Synth Layer", "#648ea8", -5.0),
        "pad": ("Hybrid Pad Texture", "#9e7389", -7.5),
        "keys": ("Hybrid Keys Layer", "#b89458", -5.5),
        "bass": ("Hybrid Sub Reinforce", "#867ca8", -6.0),
        "drums": ("Hybrid Top Perc", "#6a997c", -5.0),
        "guitar": ("Hybrid Guitar Layer", "#c2925a", -5.5),
    }

    layer_beats = float(max(4, bars) * bpb)
    for idx, rk in enumerate(roles):
        name, color, gain_db = role_meta.get(rk, (f"Hybrid {rk.title()}", "#648ea8", -6.0))
        resolved_inst = resolve_production_instrument(rk, genre=ref_genre, instruction=instruction)
        inst_ref = str(resolved_inst["instrumentRef"])
        inst_preset = resolved_inst.get("preset")
        notes = compose_midi_part(plan, rk, seed=101 + idx * 13, bpb=bpb, force_active=True)
        tid = make_id("trk")
        updated = commands.apply_command(
            updated,
            "track.add",
            {"id": tid, "name": name, "type": "midi", "instrumentRef": inst_ref, "color": color},
        )
        if inst_preset:
            updated = commands.apply_command(
                updated,
                "track.setInstrument",
                {"trackId": tid, "instrumentRef": inst_ref, "preset": inst_preset},
            )
        updated = commands.apply_command(updated, "track.setGain", {"trackId": tid, "gainDb": gain_db})
        updated = commands.apply_command(
            updated,
            "clip.add",
            {
                "trackId": tid,
                "clip": Clip(
                    id=make_id("clp"),
                    name=f"{name} (MIDI)",
                    type="midi",
                    timelineStartBeats=0.0,
                    durationBeats=layer_beats,
                    notes=[MidiNote(**n) for n in notes],
                ).model_dump(),
            },
        )
        layered_track_ids.append(tid)

    target_len = max(updated.lengthBeats, native_dur_beats, layer_beats)
    if target_len > updated.lengthBeats:
        updated = commands.apply_command(updated, "project.setLength", {"lengthBeats": min(4096.0, math.ceil(target_len / bpb) * bpb)})

    saved = store.save_project(updated, clear_autosave=False)
    return {
        "mode": "hybrid",
        "nativeTrackId": native_track_id,
        "layeredTrackIds": layered_track_ids,
        "nativeAudioPreservedUntouched": True,
        "project": saved.model_dump(),
    }
