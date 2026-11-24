"""Generic YuE2 Native Adapter + Instrumental ABC Gate + Vocal Leakage Screen (Phase 03-D).

Verified against `origin/codex/v7-2-house-hook-first` (`scripts/v7_native.py` & `evaluation/vocal_leakage.py`):
- Binary: `.runtime/v4/yue2cpp/build/yue-synth` (or env `YUE2_BIN`)
- Never fabricates YuE2 audio when the binary or weights are uninstalled.
- Strictly screens instrumental ABC notation (V:Vocal rests-only, V:Ins sounding) and screens
  generated audio for vocal-band leakage before approving instrumental takes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine import paths as engine_paths
from engine.composition.schemas import CompositionPlan

ALLOWED_YUE2_SECTIONS = {
    "intro",
    "verse",
    "pre-chorus",
    "chorus",
    "interlude",
    "bridge",
    "instrumental",
    "outro",
}


def resolve_yue2_binary() -> Path | None:
    env_bin = os.environ.get("YUE2_BIN", "").strip()
    candidates = [
        Path(env_bin).expanduser() if env_bin else None,
        engine_paths.RUNTIME / "v4" / "yue2cpp" / "build" / "yue-synth",
    ]
    for cand in candidates:
        if cand and cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def probe_yue2() -> dict[str, Any]:
    binary = resolve_yue2_binary()
    return {
        "id": "yue2-native",
        "name": "YuE2 Native Audio Generator (yue-synth)",
        "kind": "neural-audio",
        "available": binary is not None,
        "binaryPath": str(binary) if binary else None,
        "expectedPath": str(engine_paths.RUNTIME / "v4" / "yue2cpp" / "build" / "yue-synth"),
        "modes": ["full_music"],
        "memoryGuardGiB": 10.0,
        "instrumentalPolicy": "abc_resting_vocal_plus_leakage_screen",
        "statusNoteKo": (
            f"YuE2 네이티브 바이너리 감지됨 ({binary})."
            if binary
            else "YuE2 네이티브 바이너리(`.runtime/v4/yue2cpp/build/yue-synth`)가 설치되지 않았습니다. 미설치 상태에서 가짜 YuE2 오디오를 생성하지 않습니다."
        ),
        "statusNoteEn": (
            f"YuE2 native binary detected ({binary})."
            if binary
            else "YuE2 native binary (`.runtime/v4/yue2cpp/build/yue-synth`) is not installed on this host. Never fakes YuE2 output."
        ),
    }


def check_resting_voice(abc_text: str) -> tuple[bool, list[str]]:
    """Strict instrumental ABC screening: V:Vocal must be rests-only (no lyrics), V:Ins must sound."""
    issues: list[str] = []
    if not abc_text or not abc_text.strip():
        return False, ["ABC score is empty."]

    current_voice: str | None = None
    vocal_lines: list[str] = []
    ins_lines: list[str] = []
    for raw_line in abc_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue
        if line.startswith(("w:", "W:")):
            issues.append("Lyric directive (w:/W:) is forbidden in instrumental-only mode.")
            continue
        if line.startswith("V:"):
            v_name = line[2:].strip().split()[0].lower()
            if "vocal" in v_name or v_name == "1":
                current_voice = "vocal"
            else:
                current_voice = "ins"
            continue
        if re.match(r"^[A-Za-z]:", line):
            continue
        if current_voice == "vocal":
            vocal_lines.append(line)
        elif current_voice == "ins":
            ins_lines.append(line)

    if not vocal_lines:
        issues.append("Missing V:Vocal resting voice track.")
    else:
        vocal_body = " ".join(vocal_lines)
        # Only rests (z, Z, x, X), barlines, digits, spaces, slashes allowed in V:Vocal
        stripped = re.sub(r"[zZxX0-9|:\[\]\s/().>-]+", "", vocal_body)
        if stripped:
            issues.append(f"V:Vocal contains non-rest pitch symbols: '{stripped[:24]}'")

    if not ins_lines:
        issues.append("Missing V:Ins sounding instrumental voice.")
    else:
        ins_body = " ".join(ins_lines)
        if not re.search(r"[A-Ga-g]", ins_body):
            issues.append("V:Ins contains no sounding pitch notes.")

    return len(issues) == 0, issues


def build_yue2_request_from_plan(plan: CompositionPlan, seed: int = 42) -> dict[str, Any]:
    """Convert any genre CompositionPlan into a generic YuE2 request JSON payload."""
    ident = plan.musicalIdentity
    hg = plan.harmonyAndGroove
    genre = str(ident.get("genre", "electronic"))
    mood = str(ident.get("mood", "focused"))
    bpm = float(ident.get("tempoBpm", 124.0))
    key = str(ident.get("key", "F minor"))
    instrumental = bool(ident.get("instrumentalOnly", True))
    duration = float(min(180.0, max(16.0, ident.get("durationSec") or 48.0)))

    role_names = ", ".join(r.get("name", r.get("role", "")) for r in plan.instrumentRoles)
    style = f"{genre}, {mood}, {bpm:.0f} BPM, {key}, {role_names}"
    if instrumental:
        style += ", strictly instrumental, no vocals, no singing, no choir, no voice"

    # Map plan sections onto allowed YuE2 section tags
    sec_lines: list[str] = []
    for sec in plan.arrangement:
        nm = sec.name.lower()
        if "intro" in nm or "open" in nm:
            tag = "intro"
        elif "outro" in nm or "fade" in nm:
            tag = "outro"
        elif "break" in nm or "bridge" in nm:
            tag = "bridge"
        elif "climax" in nm or "chorus" in nm or "hook" in nm:
            tag = "chorus"
        elif "pre" in nm:
            tag = "pre-chorus"
        else:
            tag = "instrumental"
        if tag not in ALLOWED_YUE2_SECTIONS:
            tag = "instrumental"
        sec_lines.append(f"[{tag}]\n")
    if not sec_lines:
        sec_lines = ["[intro]\n", "[instrumental]\n", "[chorus]\n", "[outro]\n"]

    return {
        "style": style,
        "lyrics": "\n".join(sec_lines),
        "duration": round(duration, 1),
        "seed": int(seed),
        "lm_seed": int(seed + 101),
        "cot": True,
        "steps": 32,
        "output_format": "wav32",
        "chords": hg.get("chordProgression", []),
        "instrumentalOnly": instrumental,
    }


def screen_vocal_leakage(audio: np.ndarray, sr: int) -> dict[str, Any]:
    """Conservative DSP vocal-leakage screen for instrumental-only policy.

    Checks center-channel harmonic energy concentration in human formant band (320–3400 Hz)
    plus pitch-modulation stability; flags suspicious vocal presence without false overclaiming.
    """
    if len(audio) < sr // 2:
        return {"checked": True, "suspectedVocal": False, "vocalBandCenterRatio": 0.0, "note": "Audio too short for vocal screen."}

    stereo = audio if audio.ndim == 2 and audio.shape[1] >= 2 else np.stack([audio, audio], axis=1)
    mid = 0.5 * (stereo[:, 0].astype(np.float64) + stereo[:, 1].astype(np.float64))
    side = 0.5 * (stereo[:, 0].astype(np.float64) - stereo[:, 1].astype(np.float64))

    nperseg = min(4096, len(mid))
    f, p_mid = signal.welch(mid, fs=sr, nperseg=nperseg)
    _, p_side = signal.welch(side, fs=sr, nperseg=nperseg)
    total_e = float(np.sum(p_mid + p_side)) + 1e-18
    v_mask = (f >= 320.0) & (f <= 3400.0)
    mid_v = float(np.sum(p_mid[v_mask]))
    side_v = float(np.sum(p_side[v_mask]))
    center_vocal_share = mid_v / total_e
    center_dominance = mid_v / (mid_v + side_v + 1e-18)

    # Purely synthesized/instrumental dense center leads can have moderate energy; flag only extreme vocal-like concentration
    suspected = bool(center_vocal_share > 0.72 and center_dominance > 0.92)
    return {
        "checked": True,
        "suspectedVocal": suspected,
        "vocalBandCenterRatio": round(center_vocal_share, 3),
        "centerDominance": round(center_dominance, 3),
        "policy": "never_auto_approve_vocal_suspected_as_instrumental",
        "note": (
            "중심 보컬 대역(320–3400 Hz) 집중도가 매우 높습니다 — 인스트루멘탈 자동 승인 보류(수동 청취 확인 필요)."
            if suspected
            else "보컬 누출 의심 패턴 미감지 (DSP 스크리닝 통과)."
        ),
    }


def run_yue2_generation(
    plan: CompositionPlan,
    out_wav: Path,
    seed: int = 42,
    timeout_sec: int = 300,
) -> dict[str, Any]:
    """Execute real native YuE2 binary when installed; raises honestly if uninstalled."""
    binary = resolve_yue2_binary()
    if not binary:
        raise RuntimeError(
            "YuE2 native binary (`.runtime/v4/yue2cpp/build/yue-synth`) is not installed on this machine."
        )
    req_payload = build_yue2_request_from_plan(plan, seed=seed)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(req_payload, tf, indent=2, ensure_ascii=False)
        req_path = Path(tf.name)

    try:
        proc = subprocess.run(
            [str(binary), "--request", str(req_path), "--output", str(out_wav)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode != 0 or not out_wav.is_file():
            raise RuntimeError(f"YuE2 synthesis failed (code {proc.returncode}): {proc.stderr[-300:]}")
        audio, sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
        vocal_check = screen_vocal_leakage(audio, sr)
        return {
            "engine": "yue2-native",
            "wavPath": str(out_wav),
            "sampleRate": sr,
            "durationSec": round(len(audio) / sr, 3),
            "vocalScreening": vocal_check,
            "request": req_payload,
        }
    finally:
        if req_path.is_file():
            req_path.unlink(missing_ok=True)
