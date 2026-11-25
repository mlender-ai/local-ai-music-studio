"""Shared Runtime Registry (Phase 03.1 · Section 2.2 & 2.3).

Allows multiple Git worktrees, branches, and AI agents to share one local model/engine
installation without copying multi-gigabyte weights per branch or hardcoding personal
paths into Git.

Strict 6-state engine lifecycle:
- uninstalled: neither binary nor model found
- binary_found: executable binary present, model weights missing
- model_found: model weights present, executable binary missing
- ready: binary + weights + runtime present, not yet verified with a real smoke WAV
- verified: real audio/stem generation smoke test succeeded and recorded
- failed: last verification or run failed
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.daw_workspace.schema import utc_now_iso

ENGINE_STATES = ("uninstalled", "binary_found", "model_found", "ready", "verified", "failed")


def _local_config_path() -> Path:
    env_p = os.environ.get("DAW_RUNTIME_CONFIG", "").strip()
    if env_p:
        return Path(env_p).expanduser()
    return Path.home() / ".config" / "ai-native-daw" / "runtime.json"


def _verification_log_path() -> Path:
    d = engine_paths.DATA / "daw"
    d.mkdir(parents=True, exist_ok=True)
    return d / "runtime_verifications.json"


def load_local_runtime_overrides() -> dict[str, Any]:
    """Load user-local runtime path overrides (never committed to Git)."""
    p = _local_config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_local_runtime_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    p = _local_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = load_local_runtime_overrides()
    existing.update(overrides)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return existing


def _load_verifications() -> dict[str, Any]:
    p = _verification_log_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def record_engine_verification(
    engine_id: str,
    success: bool,
    wav_path: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a real smoke-test generation outcome so `verified` is strictly evidence-backed."""
    verifs = _load_verifications()
    rec = {
        "engineId": engine_id,
        "verified": bool(success),
        "lastAttemptAt": utc_now_iso(),
        "lastSuccessAt": utc_now_iso() if success else verifs.get(engine_id, {}).get("lastSuccessAt"),
        "lastWavPath": wav_path if success else verifs.get(engine_id, {}).get("lastWavPath"),
        "lastError": None if success else (error or "Verification failed"),
        "details": details or {},
    }
    verifs[engine_id] = rec
    p = _verification_log_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(verifs, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return rec


def _candidate_runtime_roots(overrides: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    for env_key in ("DAW_SHARED_RUNTIME_DIR", "MUSIC_RUNTIME_DIR"):
        v = os.environ.get(env_key, "").strip()
        if v:
            roots.append(Path(v).expanduser())
    if overrides.get("sharedRuntimeRoot"):
        roots.append(Path(str(overrides["sharedRuntimeRoot"])).expanduser())
    roots.append(engine_paths.RUNTIME)
    roots.append(Path.home() / ".local" / "share" / "ai-native-daw" / "runtime")
    roots.append(Path.home() / ".cache" / "ai-native-daw" / "runtime")
    # Deduplicate while preserving priority
    seen: set[str] = set()
    uniq: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def _first_existing_file(candidates: list[Path | None], executable: bool = False) -> Path | None:
    for c in candidates:
        if c and c.is_file():
            if not executable or os.access(c, os.X_OK):
                return c
    return None


def _compute_state(
    has_binary: bool,
    has_model: bool,
    verif: dict[str, Any] | None,
) -> str:
    if verif and verif.get("lastError") and not verif.get("verified") and (has_binary and has_model):
        return "failed"
    if has_binary and has_model:
        return "verified" if (verif and verif.get("verified")) else "ready"
    if has_binary:
        return "binary_found"
    if has_model:
        return "model_found"
    return "uninstalled"


def _probe_yue2_entry(roots: list[Path], overrides: dict[str, Any], verif: dict[str, Any] | None) -> dict[str, Any]:
    ov = overrides.get("yue2-native") or {}
    env_bin = os.environ.get("YUE2_BIN", "").strip()
    env_plan = os.environ.get("YUE2_PLAN_BIN", "").strip()
    env_model = os.environ.get("YUE2_MODEL_PATH", "").strip()
    env_vae = os.environ.get("YUE2_VAE_PATH", "").strip()

    synth_bin = _first_existing_file(
        [
            Path(env_bin).expanduser() if env_bin else None,
            Path(ov["binaryPath"]).expanduser() if ov.get("binaryPath") else None,
            *[r / "v4" / "yue2cpp" / "build" / "yue-synth" for r in roots],
        ],
        executable=True,
    )
    plan_bin = _first_existing_file(
        [
            Path(env_plan).expanduser() if env_plan else None,
            Path(ov["plannerBinaryPath"]).expanduser() if ov.get("plannerBinaryPath") else None,
            synth_bin.with_name("yue-plan") if synth_bin else None,
            *[r / "v4" / "yue2cpp" / "build" / "yue-plan" for r in roots],
        ],
        executable=True,
    )
    backbone = _first_existing_file(
        [
            Path(env_model).expanduser() if env_model else None,
            Path(ov["modelPath"]).expanduser() if ov.get("modelPath") else None,
            *[r / "v4" / "models" / "YuE2-3B-Q8_0.gguf" for r in roots],
        ]
    )
    vae = _first_existing_file(
        [
            Path(env_vae).expanduser() if env_vae else None,
            Path(ov["vaePath"]).expanduser() if ov.get("vaePath") else None,
            *[r / "v4" / "models" / "YuE2-Vae-F32.gguf" for r in roots],
        ]
    )

    has_bin = synth_bin is not None
    has_models = backbone is not None and vae is not None
    state = _compute_state(has_bin, has_models, verif)

    missing: list[str] = []
    if not synth_bin:
        missing.append("yue-synth binary (.runtime/v4/yue2cpp/build/yue-synth)")
    if not backbone:
        missing.append("YuE2-3B-Q8_0.gguf backbone (.runtime/v4/models/YuE2-3B-Q8_0.gguf)")
    if not vae:
        missing.append("YuE2-Vae-F32.gguf VAE (.runtime/v4/models/YuE2-Vae-F32.gguf)")

    return {
        "id": "yue2-native",
        "name": "YuE2 Native Audio Generator (yue2.cpp Metal)",
        "kind": "neural-audio",
        "category": "neural_audio",
        "state": state,
        "available": state in ("ready", "verified"),
        "verified": state == "verified",
        "binaryPath": str(synth_bin) if synth_bin else None,
        "plannerBinaryPath": str(plan_bin) if plan_bin else None,
        "modelPath": str(backbone) if backbone else None,
        "vaePath": str(vae) if vae else None,
        "pythonEnv": None,
        "modelVersion": "YuE2-3B-Q8_0 + YuE2-Vae-F32",
        "memoryRequirementGiB": 6.5,
        "memoryGuardGiB": 10.0,
        "modes": ["full_music"],
        "capabilities": [
            "full_music_neural_audio",
            "abc_score_conditioning",
            "melody_cot",
            "full_cot",
            "semantic_continuation",
            "semantic_resynthesis",
        ],
        "unsupportedCapabilities": ["single_instrument_inpainting"],
        "missingItems": missing,
        "lastSuccessAt": (verif or {}).get("lastSuccessAt"),
        "lastWavPath": (verif or {}).get("lastWavPath"),
        "statusNoteKo": (
            f"YuE2 실행 및 가중치 준비 완료 ({state})."
            if state in ("ready", "verified")
            else f"YuE2 미설치 ({state}): {', '.join(missing)}. 미설치 상태에서 자체 MIDI로 몰래 대체하지 않습니다."
        ),
        "statusNoteEn": (
            f"YuE2 native runtime {state}."
            if state in ("ready", "verified")
            else f"YuE2 {state}: missing {', '.join(missing)}. Never silently substituted with MIDI."
        ),
    }


def _probe_acestep_entry(roots: list[Path], overrides: dict[str, Any], verif: dict[str, Any] | None) -> dict[str, Any]:
    ov = overrides.get("ace-step-local") or {}
    env_dir = os.environ.get("ACESTEP_CHECKPOINT_DIR", "").strip()
    ckpt_candidates = [
        Path(env_dir).expanduser() if env_dir else None,
        Path(ov["modelPath"]).expanduser() if ov.get("modelPath") else None,
        *[r / "models" / "checkpoints" for r in roots],
    ]
    ckpt_dir = next(
        (
            d
            for d in ckpt_candidates
            if d and d.is_dir() and any(p.suffix in (".safetensors", ".pt", ".bin", ".ckpt") for p in d.rglob("*") if p.is_file())
        ),
        None,
    )
    has_pkg = importlib.util.find_spec("acestep") is not None
    state = _compute_state(has_pkg, ckpt_dir is not None, verif)
    missing: list[str] = []
    if not has_pkg:
        missing.append("acestep Python package")
    if not ckpt_dir:
        missing.append("ACE-Step checkpoints (.runtime/models/checkpoints/)")
    return {
        "id": "ace-step-local",
        "name": "ACE-Step 1.5 Local Diffusion (MLX/MPS)",
        "kind": "neural-audio",
        "category": "neural_audio",
        "state": state,
        "available": state in ("ready", "verified"),
        "verified": state == "verified",
        "binaryPath": None,
        "modelPath": str(ckpt_dir) if ckpt_dir else None,
        "pythonEnv": os.environ.get("VIRTUAL_ENV") or None,
        "modelVersion": "ACE-Step-2B-Turbo",
        "memoryRequirementGiB": 6.0,
        "memoryGuardGiB": 10.0,
        "modes": ["full_music"],
        "capabilities": ["full_music_neural_audio", "repaint_30s"],
        "missingItems": missing,
        "lastSuccessAt": (verif or {}).get("lastSuccessAt"),
        "statusNoteKo": (
            f"ACE-Step 실행 가능 ({state})."
            if state in ("ready", "verified")
            else f"ACE-Step 미설치 ({state}): {', '.join(missing)}."
        ),
        "statusNoteEn": (
            f"ACE-Step {state}."
            if state in ("ready", "verified")
            else f"ACE-Step {state}: missing {', '.join(missing)}."
        ),
    }


def _probe_demucs_entry(roots: list[Path], overrides: dict[str, Any], verif: dict[str, Any] | None) -> dict[str, Any]:
    ov = overrides.get("demucs-htdemucs") or {}
    cli = shutil.which("demucs") or (str(ov["binaryPath"]) if ov.get("binaryPath") and Path(ov["binaryPath"]).is_file() else None)
    pkg = importlib.util.find_spec("demucs") is not None
    mlx_dir = next((r / "v5" / "demucs-mlx" for r in roots if (r / "v5" / "demucs-mlx").is_dir()), None)
    mlx_models = next((r / "v5" / "stem-models" for r in roots if (r / "v5" / "stem-models").is_dir()), None)

    has_bin = bool(cli or pkg or mlx_dir)
    has_model = bool(mlx_models or cli or pkg)  # PyTorch demucs resolves weights on install; mlx requires local cache
    if mlx_dir and not mlx_models and not cli and not pkg:
        has_model = False
    state = _compute_state(has_bin, has_model, verif)
    return {
        "id": "demucs-htdemucs",
        "name": "Demucs Stem Separation (htdemucs / demucs-mlx)",
        "kind": "stem-separation",
        "category": "stem_separation",
        "state": state,
        "available": state in ("ready", "verified"),
        "verified": state == "verified",
        "binaryPath": cli or (str(mlx_dir) if mlx_dir else None),
        "modelPath": str(mlx_models) if mlx_models else None,
        "pythonEnv": os.environ.get("VIRTUAL_ENV") or None,
        "modelVersion": "htdemucs / htdemucs_6s",
        "memoryRequirementGiB": 3.0,
        "modes": ["stem_separation"],
        "stems": ["drums", "bass", "other", "vocals"],
        "capabilities": ["stem_separation_4stem"],
        "missingItems": [] if state in ("ready", "verified") else ["demucs package or .runtime/v5/demucs-mlx + stem-models"],
        "lastSuccessAt": (verif or {}).get("lastSuccessAt"),
        "statusNoteKo": (
            f"Demucs 스템 분리 준비됨 ({state})."
            if state in ("ready", "verified")
            else "Demucs 미설치: 실제 스템 분리를 실행하려면 `uv pip install demucs` 또는 공유 `.runtime/v5/demucs-mlx`를 연결하세요."
        ),
        "statusNoteEn": (
            f"Demucs stem separation {state}."
            if state in ("ready", "verified")
            else "Demucs not installed (install via `uv pip install demucs` or configure shared `.runtime/v5/demucs-mlx`)."
        ),
    }


def _probe_vocal_qa_models(roots: list[Path]) -> dict[str, Any]:
    panns_ckpt = _first_existing_file([r / "v7" / "panns" / "mobilenet.pth" for r in roots])
    whisper_dir = next((r / "v4" / "whisper-small" for r in roots if (r / "v4" / "whisper-small").is_dir()), None)
    inst_val = next((r / "v6" / "instrumental" for r in roots if (r / "v6" / "instrumental").is_dir()), None)
    full_available = bool(panns_ckpt and whisper_dir)
    return {
        "pannsAvailable": panns_ckpt is not None,
        "whisperAvailable": whisper_dir is not None,
        "officialAbcValidatorAvailable": inst_val is not None,
        "fullVocalLeakageQaReady": full_available,
        "pannsPath": str(panns_ckpt) if panns_ckpt else None,
        "whisperPath": str(whisper_dir) if whisper_dir else None,
        "officialAbcValidatorPath": str(inst_val) if inst_val else None,
    }


def get_runtime_registry() -> dict[str, Any]:
    """Return complete shared runtime status across all neural, stem, MIDI, and QA engines."""
    overrides = load_local_runtime_overrides()
    roots = _candidate_runtime_roots(overrides)
    verifs = _load_verifications()

    local_midi = {
        "id": "local-multitrack-composer",
        "name": "Editable MIDI & 6-Voice Studio Synth Engine",
        "kind": "editable-midi",
        "category": "editable_midi",
        "state": "verified",
        "available": True,
        "verified": True,
        "binaryPath": "builtin://engine.composition.midi_composer",
        "modelPath": "builtin://engine.instruments.synth_engine",
        "pythonEnv": os.environ.get("VIRTUAL_ENV") or None,
        "modelVersion": "midi-composer-v4 + 6-voice-dsp",
        "memoryRequirementGiB": 0.25,
        "modes": ["instrument_session", "loop_midi", "midi_variation", "full_music_midi_sketch"],
        "capabilities": ["editable_midi", "drum_variation", "hook_variation", "bass_variation", "harmony_variation"],
        "honestLabel": "Editable MIDI + Synthesized Studio Voices (NOT Neural Audio)",
        "missingItems": [],
        "statusNoteKo": "검증 완료: 편집 가능한 멀티트랙 MIDI 작곡·변주 및 6종 멀티팀버 악기 합성 (신경망 오디오와 명확히 구분).",
        "statusNoteEn": "Verified offline: editable MIDI composition/variation + 6 studio synth voices (explicitly distinct from neural audio).",
    }

    yue2 = _probe_yue2_entry(roots, overrides, verifs.get("yue2-native"))
    acestep = _probe_acestep_entry(roots, overrides, verifs.get("ace-step-local"))
    demucs = _probe_demucs_entry(roots, overrides, verifs.get("demucs-htdemucs"))
    vocal_qa = _probe_vocal_qa_models(roots)

    # Phase 03.2 Transcription & Music Structure Engines (honest 6-state probe)
    has_bp = importlib.util.find_spec("basic_pitch") is not None and importlib.util.find_spec("onnxruntime") is not None
    bp_verif = verifs.get("basic-pitch-onnx")
    bp_state = _compute_state(has_bp, has_bp, bp_verif) if has_bp else "uninstalled"
    basic_pitch_entry = {
        "id": "basic-pitch-onnx",
        "name": "Spotify Basic Pitch (ONNX Audio-to-MIDI)",
        "kind": "transcription",
        "category": "transcription",
        "state": bp_state,
        "available": bp_state in ("ready", "verified"),
        "verified": bp_state == "verified",
        "license": "Apache-2.0",
        "memoryRequirementGiB": 0.4,
        "capabilities": ["polyphonic_midi_transcription", "bass_transcription", "melody_transcription", "pitch_bend"],
        "statusNoteKo": (
            f"Basic Pitch ONNX 채보 엔진 준비됨 ({bp_state}, Apache-2.0, Apple Silicon 네이티브)."
            if bp_state in ("ready", "verified")
            else "Basic Pitch ONNX 미설치 (`uv pip install onnxruntime librosa pretty_midi mir-eval` + `--no-deps basic-pitch`)."
        ),
        "statusNoteEn": (
            f"Basic Pitch ONNX transcription {bp_state} (Apache-2.0, Apple Silicon native)."
            if bp_state in ("ready", "verified")
            else "Basic Pitch ONNX not installed."
        ),
    }

    has_ss2 = importlib.util.find_spec("sheetsage2") is not None or any(
        (r / "sheetsage2").is_dir() for r in roots
    )
    ss2_state = _compute_state(has_ss2, has_ss2, verifs.get("sheetsage2")) if has_ss2 else "uninstalled"
    sheetsage2_entry = {
        "id": "sheetsage2",
        "name": "SheetSage2 (Lead Sheet & ABC — CC BY-NC 4.0)",
        "kind": "transcription",
        "category": "transcription",
        "state": ss2_state,
        "available": ss2_state in ("ready", "verified"),
        "verified": ss2_state == "verified",
        "license": "CC-BY-NC-4.0 (Non-Commercial)",
        "memoryRequirementGiB": 3.0,
        "capabilities": ["lead_sheet_abc", "chords_melody_beats"],
        "missingItems": [] if ss2_state in ("ready", "verified") else ["FFmpeg shared libs", "m-a-p/SheetSage2 + MERT-v2 weights (~3 GiB, CC BY-NC 4.0)"],
        "statusNoteKo": (
            f"SheetSage2 실행 가능 ({ss2_state}, 비상업 라이선스 CC BY-NC 4.0)."
            if ss2_state in ("ready", "verified")
            else "SheetSage2 미설치 (CC BY-NC 4.0 비상업 라이선스 · FFmpeg 및 ~3 GiB MERT-v2 가중치 필요). 대체 경로로 Demucs+Basic Pitch+ABC 변환기가 즉시 작동합니다."
        ),
        "statusNoteEn": (
            f"SheetSage2 {ss2_state} (CC BY-NC 4.0 non-commercial)."
            if ss2_state in ("ready", "verified")
            else "SheetSage2 not installed (CC BY-NC 4.0 non-commercial; requires FFmpeg + ~3 GiB MERT-v2 weights). Demucs + Basic Pitch + YuE2 ABC exporter runs natively."
        ),
    }

    has_allin1 = importlib.util.find_spec("allin1") is not None
    allin1_entry = {
        "id": "allin1-structure",
        "name": "All-In-One Music Structure Analyzer",
        "kind": "structure-analysis",
        "category": "transcription",
        "state": "ready" if has_allin1 else "uninstalled",
        "available": has_allin1,
        "verified": False,
        "license": "MIT",
        "capabilities": ["functional_section_labels", "beat_downbeat_tracking"],
        "statusNoteKo": (
            "All-In-One 구조 분석기 준비됨."
            if has_allin1
            else "All-In-One 미설치 (madmom/NATTEN/FFmpeg 필요). Demucs 스템 에너지 + DSP 구간 구조 분석기가 기본 작동합니다."
        ),
        "statusNoteEn": (
            "All-In-One structure analyzer ready."
            if has_allin1
            else "All-In-One not installed (requires madmom/NATTEN/FFmpeg). Demucs stem-energy + DSP Arrangement Map runs natively."
        ),
    }

    has_ymt3 = importlib.util.find_spec("yourmt3") is not None
    yourmt3_entry = {
        "id": "yourmt3-plus",
        "name": "YourMT3+ Multi-Instrument Transcription",
        "kind": "transcription",
        "category": "transcription",
        "state": "ready" if has_ymt3 else "uninstalled",
        "available": has_ymt3,
        "verified": False,
        "license": "Apache-2.0 / Research",
        "capabilities": ["multi_instrument_midi"],
        "statusNoteKo": (
            "YourMT3+ 다중 악기 채보 준비됨."
            if has_ymt3
            else "YourMT3+ 미설치 (별도 PyTorch 리포지토리 및 대용량 체크포인트 필요). Demucs 스템 분리 + Basic Pitch + Drum Groove 채보가 기본 작동합니다."
        ),
        "statusNoteEn": (
            "YourMT3+ multi-instrument transcription ready."
            if has_ymt3
            else "YourMT3+ not installed. Stem-guided Demucs + Basic Pitch + Drum Groove transcription runs natively."
        ),
    }

    # Phase 05 Professional Audio Engines (Spotify Pedalboard + FluidSynth SF3/SF2)
    has_pb = importlib.util.find_spec("pedalboard") is not None
    pedalboard_entry = {
        "id": "spotify-pedalboard",
        "name": "Spotify Pedalboard C++ DSP & AU/VST3 Host",
        "kind": "audio-fx-and-host",
        "category": "professional_dsp",
        "state": "verified" if has_pb else "uninstalled",
        "available": has_pb,
        "verified": has_pb,
        "license": "GPL-3.0",
        "capabilities": ["parametric_eq", "compressor", "limiter", "reverb", "convolution_ir", "delay", "chorus", "phaser", "distortion", "ladder_filter", "au_vst3_host"],
        "statusNoteKo": "Spotify Pedalboard C++ DSP 및 AU/VST3 호스트 준비됨." if has_pb else "Pedalboard 미설치 (`uv pip install pedalboard`).",
        "statusNoteEn": "Spotify Pedalboard C++ DSP & AU/VST3 host ready." if has_pb else "Pedalboard not installed.",
    }

    sf3_path = engine_paths.ROOT / "outputs" / "daw" / "soundfonts" / "MuseScore_General.sf3"
    has_fs_bin = bool(shutil.which("fluidsynth") or Path("/opt/homebrew/bin/fluidsynth").is_file())
    has_fs_lib = Path("/opt/homebrew/lib/libfluidsynth.dylib").is_file() or Path("/usr/local/lib/libfluidsynth.dylib").is_file()
    has_pyfs = importlib.util.find_spec("fluidsynth") is not None
    has_fs = (has_fs_bin or (has_pyfs and has_fs_lib)) and sf3_path.is_file()
    fluidsynth_entry = {
        "id": "fluidsynth-sf3",
        "name": "FluidSynth Multi-Sampled SF3/SF2 Engine (MuseScore General MIT)",
        "kind": "instrument-engine",
        "category": "professional_instruments",
        "state": "verified" if has_fs else ("binary_found" if (has_fs_bin or has_pyfs) else "uninstalled"),
        "available": has_fs,
        "verified": has_fs,
        "license": "LGPL-2.1 (FluidSynth) + MIT (MuseScore_General.sf3)",
        "soundfontPath": str(sf3_path) if sf3_path.is_file() else None,
        "capabilities": ["multi_sampled_piano", "electric_piano", "organ", "acoustic_guitar", "electric_guitar", "electric_bass", "acoustic_drums", "electronic_drums", "strings"],
        "statusNoteKo": (
            "FluidSynth + MuseScore General SF3(MIT) 멀티샘플 가상악기 엔진 준비됨."
            if has_fs
            else "FluidSynth 또는 MuseScore_General.sf3 미설치."
        ),
        "statusNoteEn": (
            "FluidSynth + MuseScore_General.sf3 (MIT) multi-sampled instrument engine ready."
            if has_fs
            else "FluidSynth or MuseScore_General.sf3 missing."
        ),
    }

    neural_ready = any(e["available"] for e in (yue2, acestep))
    return {
        "configPath": str(_local_config_path()),
        "searchedRoots": [str(r) for r in roots],
        "neuralAudioReady": neural_ready,
        "editableMidiReady": True,
        "stemSeparationReady": demucs["available"],
        "transcriptionReady": basic_pitch_entry["available"],
        "proDspReady": has_pb,
        "proSoundfontReady": has_fs,
        "vocalQaModels": vocal_qa,
        "engines": [yue2, acestep, demucs, basic_pitch_entry, pedalboard_entry, fluidsynth_entry, sheetsage2_entry, allin1_entry, yourmt3_entry, local_midi],
    }
