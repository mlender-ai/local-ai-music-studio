"""YuE2 Native Adapter aligned 1:1 with V7.2 `scripts/v4_study.py` & `scripts/v7_native.py` (Phase 03.1 · Section 3).

Verified against `origin/codex/v7-2-house-hook-first`:
- Real CLI flags:
  - Planner: `yue-plan --model YuE2-3B-Q8_0.gguf --request planner-request.json --max-seq 8192 --out planned.abc`
  - Synth:   `yue-synth --model YuE2-3B-Q8_0.gguf --vae YuE2-Vae-F32.gguf --request request.json --max-seq 8192 --out original.wav --score plan.abc`
- Supports CoT (`full`/`melody`/`off`), `cfg_scale`, `semantic_sampling.temperature`, `abc` score conditioning,
  `source_tokens` continuation, and `semantic_tokens` resynthesis.
- Wires strict `check_resting_voice()` directly into pre-synthesis execution gate.
- Vocal leakage screening uses strict 3-state verdict (`PASS`, `REJECT`, `UNCERTAIN`) and NEVER auto-approves
  `UNCERTAIN` or `REJECT` neural audio as confirmed vocal-free.
- Runs under `run_cancellable_guarded()` (true process-group SIGTERM/SIGKILL cancellation + 10 GiB RAM guard).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

from engine.composition.schemas import CompositionPlan
from engine.generation.process_guard import run_cancellable_guarded
from engine.runtime import get_runtime_registry, record_engine_verification

ALLOWED_YUE2_SECTIONS = frozenset(
    (
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "interlude",
        "bridge",
        "instrumental",
        "outro",
    )
)


def probe_yue2() -> dict[str, Any]:
    reg = get_runtime_registry()
    return next(e for e in reg["engines"] if e["id"] == "yue2-native")


def check_resting_voice(abc_text: str) -> tuple[bool, list[str]]:
    """Exact strict instrumental ABC gate matching `scripts/v7_native.py`:
    - Only allowed section comments (`% intro`, `% verse`, `% chorus`, etc.)
    - Only `V:Vocal` and `V:Ins` voices (no extra voices)
    - Zero `w:`/`W:` lyrics and zero inline `[V:...]`/`[w:...]` voice/lyric switches
    - `V:Vocal` must contain ONLY rests (`z`/`Z`), barlines, chord quotes, and whitespace
    - `V:Ins` must contain sounding pitch notes (`A-Ga-g`)
    """
    issues: list[str] = []
    if not abc_text or not abc_text.strip():
        return False, ["ABC score is empty."]

    lane = ""
    lanes: set[str] = set()
    instrumental_notes = False

    for raw_line in abc_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%"):
            sec = line[1:].strip().lower()
            if sec and sec not in ALLOWED_YUE2_SECTIONS:
                issues.append(f"Unsupported ABC section marker: '{line}'")
            continue
        if line.startswith("V:"):
            parts = line[2:].strip().split(maxsplit=1)
            lane = parts[0] if parts else ""
            if lane not in {"Vocal", "Ins"}:
                issues.append(f"Unsupported ABC voice '{lane}' (only Vocal and Ins allowed).")
            else:
                lanes.add(lane)
            continue
        if re.match(r"^[wW]:", line):
            issues.append("Sung lyric directive (w:/W:) is forbidden in instrumental-only mode.")
            continue
        if re.match(r"^[XTMLQK]:", line):
            continue

        music = re.sub(r'"[^"]*"', "", line)
        if re.search(r"\[\s*[VwW]:", music):
            issues.append("Inline voice or lyric directive ([V:]/[w:]) is forbidden.")
            continue
        if lane == "Vocal":
            if not re.fullmatch(r"(?:[zZxX]\d*|[|:\[\]\s/().>-])+", music):
                issues.append(f"V:Vocal contains non-rest pitch material: '{music[:32]}'")
        elif lane == "Ins":
            if re.search(r"[A-Ga-g]", music):
                instrumental_notes = True

    if lanes != {"Vocal", "Ins"}:
        issues.append(f"Score must declare both V:Vocal and V:Ins lanes (found: {sorted(lanes)}).")
    if not instrumental_notes:
        issues.append("V:Ins contains no sounding instrumental pitch notes.")

    return len(issues) == 0, issues


def build_yue2_request_from_plan(
    plan: CompositionPlan,
    seed: int = 42,
    *,
    cot: str = "melody",
    abc_score: str | None = None,
    cfg_scale: float | None = 2.0,
    semantic_temperature: float | None = 0.80,
    source_tokens: tuple[str, float] | None = None,
    semantic_tokens: str | None = None,
) -> dict[str, Any]:
    """Build exact `v4_study.py`-compatible YuE2 request JSON from a CompositionPlan."""
    ident = plan.musicalIdentity
    genre = str(ident.get("genre", "electronic"))
    mood = str(ident.get("mood", "focused"))
    bpm = int(round(float(ident.get("tempoBpm", 124.0))))
    key = str(ident.get("key", "F minor"))
    instrumental = bool(ident.get("instrumentalOnly", True))
    duration = int(min(120, max(16, round(float(ident.get("durationSec") or 48.0)))))

    role_names = ", ".join(r.get("name", r.get("role", "")) for r in plan.instrumentRoles)
    motif_desc = str(plan.signatureMotif.get("concept") or "")
    style = f"{bpm} BPM instrumental {genre} in {key}, {ident.get('timeSignature', '4/4')}. {mood}. Ensemble: {role_names}."
    if motif_desc:
        style += f" {motif_desc}."
    if instrumental and not re.search(r"\binstrumental\b", style, re.IGNORECASE):
        style += " Instrumental."

    if abc_score is None:
        abc_meta = (plan.referenceBinding.appliedFeatures or {}).get("abcScore")
        if isinstance(abc_meta, dict) and abc_meta.get("validInstrumentalYuE2") and abc_meta.get("abc"):
            abc_score = str(abc_meta["abc"])

    if abc_score is not None and instrumental:
        ok, issues = check_resting_voice(abc_score)
        if not ok:
            raise ValueError(f"Instrumental ABC gate rejected score: {'; '.join(issues)}")

    # Official V7.2 instrumental workflow uses empty lyrics ("") or strictly section markers
    req: dict[str, Any] = {
        "style": style,
        "lyrics": "",
        "duration": duration,
        "seed": int(seed),
        "lm_seed": int(seed),
        "cot": cot if cot in ("full", "melody", "off") else "melody",
        "steps": 32,
        "output_format": "wav32",
    }
    if cfg_scale is not None:
        req["cfg_scale"] = float(cfg_scale)
    if semantic_temperature is not None:
        req["semantic_sampling"] = {"temperature": float(semantic_temperature)}
    if abc_score is not None:
        req["abc"] = abc_score
    if source_tokens is not None:
        toks, end_sec = source_tokens
        req["source_tokens"] = toks
        req["source_start"] = 0.0
        req["source_end"] = float(end_sec)
    if semantic_tokens is not None:
        if source_tokens is not None:
            raise ValueError("Replay (`semantic_tokens`) and continuation (`source_tokens`) are separate modes")
        req["semantic_tokens"] = semantic_tokens
    return req


def screen_vocal_leakage(
    audio: np.ndarray,
    sr: int,
    *,
    source_kind: str = "neural_audio",  # "neural_audio" | "deterministic_midi_synth"
    vocals_stem_audio: np.ndarray | None = None,
    vocals_stem_sr: int | None = None,
    audio_path: Path | None = None,
    use_demucs: bool = False,
) -> dict[str, Any]:
    """Honest 3-state vocal-leakage screen (`PASS`, `REJECT`, `UNCERTAIN`) per Phase 03.1 + GATE 2.

    Upgrades in GATE 2:
    - Supports Demucs-isolated `vocals` stem multi-window screening (4s windows, 2s hop) measuring real
      isolated vocal-stem RMS dBFS, vocal-to-mix RMS ratio, and 3–8 Hz syllabic modulation!
    - Never treats center-band energy alone as definitive vocal-free proof on neural audio!
    - For neural audio WITH Demucs vocal stem:
      - Any window with vocal RMS > -28 dBFS and ratio > 0.12 (or strong syllabic modulation > 0.25 with RMS > -32 dBFS) -> `REJECT`
      - All windows silent (`maxVocalRmsDbfs < -40 dBFS` and `maxVocalToMixRatio < 0.05`) -> `PASS` (`demucs_isolated_vocal_stem_screen`)
      - Borderline ambient bleed -> `UNCERTAIN` (never auto-approved!)
    - For neural audio WITHOUT Demucs / PANNs / Whisper:
      - Extreme corroborated vocal signature -> `REJECT`
      - Otherwise -> `UNCERTAIN` (never auto-approved!)
    - For deterministic built-in instrumental MIDI/SoundFont/Synth rendering (zero vocal oscillators/samples):
      - Returns `PASS` (`deterministic_non_vocal_synth`).
    """
    if len(audio) < max(1, sr // 4):
        return {
            "checked": True,
            "status": "UNCERTAIN",
            "suspectedVocal": False,
            "method": "dsp_window_screen",
            "autoApprovedInstrumental": False,
            "note": "Audio too short for vocal screening.",
        }

    stereo = audio if audio.ndim == 2 and audio.shape[1] >= 2 else np.stack([audio, audio], axis=1)
    mid = 0.5 * (stereo[:, 0].astype(np.float64) + stereo[:, 1].astype(np.float64))
    side = 0.5 * (stereo[:, 0].astype(np.float64) - stereo[:, 1].astype(np.float64))

    # Optional Demucs vocal stem extraction when audio_path + use_demucs requested
    demucs_vocal_arr = vocals_stem_audio
    demucs_vocal_sr = vocals_stem_sr or sr
    if demucs_vocal_arr is None and use_demucs and audio_path is not None and audio_path.is_file():
        try:
            from engine.generation.adapters.stem_separator import probe_demucs, separate_stems_demucs

            if probe_demucs().get("available"):
                stems = separate_stems_demucs(audio_path, audio_path.parent / "vocal_qa_stems", use_cache=True)
                v_item = next((s for s in stems if s.get("role") == "vocals"), None)
                if v_item and Path(v_item["wavPath"]).is_file():
                    demucs_vocal_arr, demucs_vocal_sr = sf.read(str(v_item["wavPath"]), dtype="float32", always_2d=True)
        except Exception:
            demucs_vocal_arr = None

    win_len = min(len(mid), 4 * sr)
    hop = max(sr, 2 * sr)
    starts = list(range(0, max(1, len(mid) - win_len + 1), hop))
    if not starts:
        starts = [0]

    flagged_windows: list[dict[str, Any]] = []
    max_center_ratio = 0.0
    max_mod_score = 0.0

    for st in starts:
        seg_m = mid[st : st + win_len]
        seg_s = side[st : st + win_len]
        nperseg = min(4096, len(seg_m))
        f, p_m = signal.welch(seg_m, fs=sr, nperseg=nperseg)
        _, p_s = signal.welch(seg_s, fs=sr, nperseg=nperseg)
        tot = float(np.sum(p_m + p_s)) + 1e-18
        v_mask = (f >= 300.0) & (f <= 3400.0)
        mid_v = float(np.sum(p_m[v_mask]))
        side_v = float(np.sum(p_s[v_mask]))
        center_ratio = mid_v / tot
        center_dom = mid_v / (mid_v + side_v + 1e-18)
        max_center_ratio = max(max_center_ratio, center_ratio)

        # Syllabic / vibrato amplitude modulation (3–8 Hz) on vocal-bandpassed mid channel
        mod_score = 0.0
        if len(seg_m) >= sr:
            try:
                sos = signal.butter(2, [320.0, 3200.0], btype="bandpass", fs=sr, output="sos")
                vb = signal.sosfilt(sos, seg_m)
                env = np.abs(vb)
                dec = max(1, sr // 100)
                env_ds = env[::dec]
                env_ds = env_ds - np.mean(env_ds)
                ef, ep = signal.welch(env_ds, fs=sr / dec, nperseg=min(256, len(env_ds)))
                e_tot = float(np.sum(ep)) + 1e-18
                syll_e = float(np.sum(ep[(ef >= 3.0) & (ef <= 8.5)]))
                mod_score = syll_e / e_tot
                max_mod_score = max(max_mod_score, mod_score)
            except Exception:
                pass

        if center_ratio > 0.68 and center_dom > 0.90 and mod_score > 0.28:
            flagged_windows.append(
                {
                    "startSec": round(st / sr, 2),
                    "endSec": round((st + len(seg_m)) / sr, 2),
                    "centerVocalRatio": round(center_ratio, 3),
                    "syllabicModulation": round(mod_score, 3),
                }
            )

    if source_kind == "deterministic_midi_synth":
        return {
            "checked": True,
            "status": "PASS",
            "suspectedVocal": False,
            "autoApprovedInstrumental": True,
            "method": "deterministic_non_vocal_synth",
            "windowsChecked": len(starts),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": [],
            "note": "비보컬 결정론적 악기/사운드폰트 합성 출력(보컬 모델 미사용)입니다.",
        }

    # Demucs-isolated vocal stem multi-window screening!
    if demucs_vocal_arr is not None and len(demucs_vocal_arr) >= max(1, demucs_vocal_sr // 4):
        v_mono = demucs_vocal_arr.mean(axis=1).astype(np.float64) if demucs_vocal_arr.ndim == 2 else demucs_vocal_arr.astype(np.float64)
        mix_rms_all = float(np.sqrt(np.mean(mid * mid))) + 1e-9
        v_win = min(len(v_mono), 4 * demucs_vocal_sr)
        v_hop = max(demucs_vocal_sr, 2 * demucs_vocal_sr)
        v_starts = list(range(0, max(1, len(v_mono) - v_win + 1), v_hop)) or [0]
        max_v_db = -120.0
        max_v_ratio = 0.0
        demucs_flagged: list[dict[str, Any]] = []
        for vst in v_starts:
            vseg = v_mono[vst : vst + v_win]
            v_rms = float(np.sqrt(np.mean(vseg * vseg)))
            v_db = 20.0 * float(np.log10(max(v_rms, 1e-9)))
            v_ratio = v_rms / mix_rms_all
            max_v_db = max(max_v_db, v_db)
            max_v_ratio = max(max_v_ratio, v_ratio)
            if (v_db > -28.0 and v_ratio > 0.12) or (v_db > -32.0 and v_ratio > 0.08 and max_mod_score > 0.24):
                demucs_flagged.append(
                    {
                        "startSec": round(vst / demucs_vocal_sr, 2),
                        "endSec": round((vst + len(vseg)) / demucs_vocal_sr, 2),
                        "vocalStemRmsDbfs": round(v_db, 2),
                        "vocalToMixRatio": round(v_ratio, 3),
                    }
                )
        if demucs_flagged or flagged_windows:
            return {
                "checked": True,
                "status": "REJECT",
                "suspectedVocal": True,
                "autoApprovedInstrumental": False,
                "method": "demucs_isolated_vocal_stem_screen",
                "windowsChecked": len(v_starts),
                "maxVocalStemRmsDbfs": round(max_v_db, 2),
                "maxVocalToMixRatio": round(max_v_ratio, 3),
                "vocalBandCenterRatio": round(max_center_ratio, 3),
                "syllabicModulationPeak": round(max_mod_score, 3),
                "flaggedWindows": demucs_flagged or flagged_windows,
                "note": f"Demucs 분리 보컬 스템에서 유의미한 보컬/허밍 에너지 감지(최대 {max_v_db:.1f} dBFS) — 무보컬 승인 거부(REJECT).",
            }
        if max_v_db < -40.0 and max_v_ratio < 0.05:
            return {
                "checked": True,
                "status": "PASS",
                "suspectedVocal": False,
                "autoApprovedInstrumental": True,
                "method": "demucs_isolated_vocal_stem_screen",
                "windowsChecked": len(v_starts),
                "maxVocalStemRmsDbfs": round(max_v_db, 2),
                "maxVocalToMixRatio": round(max_v_ratio, 3),
                "vocalBandCenterRatio": round(max_center_ratio, 3),
                "syllabicModulationPeak": round(max_mod_score, 3),
                "flaggedWindows": [],
                "note": f"Demucs 분리 보컬 스템 전 구간 정숙 확인(최대 {max_v_db:.1f} dBFS, 비율 {max_v_ratio:.3f}) — 무보컬 통과(PASS).",
            }
        return {
            "checked": True,
            "status": "UNCERTAIN",
            "suspectedVocal": False,
            "autoApprovedInstrumental": False,
            "method": "demucs_isolated_vocal_stem_screen",
            "windowsChecked": len(v_starts),
            "maxVocalStemRmsDbfs": round(max_v_db, 2),
            "maxVocalToMixRatio": round(max_v_ratio, 3),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": [],
            "note": f"Demucs 보컬 스템 잔여 블리드 경계 구간(최대 {max_v_db:.1f} dBFS) — 수동 청취 확인 필요(UNCERTAIN).",
        }

    reg = get_runtime_registry()
    full_qa_ready = bool(reg.get("vocalQaModels", {}).get("fullVocalLeakageQaReady"))
    if flagged_windows:
        return {
            "checked": True,
            "status": "REJECT",
            "suspectedVocal": True,
            "autoApprovedInstrumental": False,
            "method": "dsp_formant_modulation_screen",
            "windowsChecked": len(starts),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": flagged_windows,
            "note": f"보컬 대역 집중 및 음절 변조 의심 구간 {len(flagged_windows)}개 감지 — 무보컬 자동 승인 거부(REJECT).",
        }

    if not full_qa_ready:
        return {
            "checked": True,
            "status": "UNCERTAIN",
            "suspectedVocal": False,
            "autoApprovedInstrumental": False,
            "method": "dsp_only_without_panns_whisper",
            "windowsChecked": len(starts),
            "vocalBandCenterRatio": round(max_center_ratio, 3),
            "syllabicModulationPeak": round(max_mod_score, 3),
            "flaggedWindows": [],
            "note": "DSP 1차 검사에서 명백한 보컬은 미감지이나, Demucs 보컬 스템 분리 또는 PANNs/Whisper 검증이 미실행되어 UNCERTAIN(수동 청취 확인 필요)으로 분류합니다.",
        }

    return {
        "checked": True,
        "status": "PASS",
        "suspectedVocal": False,
        "autoApprovedInstrumental": True,
        "method": "multi_window_dsp_plus_qa_models",
        "windowsChecked": len(starts),
        "vocalBandCenterRatio": round(max_center_ratio, 3),
        "syllabicModulationPeak": round(max_mod_score, 3),
        "flaggedWindows": [],
        "note": "전 구간 무보컬 검사 통과 (PASS).",
    }


def run_yue2_generation(
    plan: CompositionPlan,
    out_wav: Path,
    *,
    seed: int = 42,
    cot: str = "melody",
    abc_score: str | None = None,
    cfg_scale: float | None = 2.0,
    semantic_temperature: float | None = 0.80,
    source_tokens: tuple[str, float] | None = None,
    semantic_tokens: str | None = None,
    cancel_event: threading.Event | None = None,
    timeout_sec: float = 480.0,
) -> dict[str, Any]:
    """Execute real native YuE2 (`yue-plan` preflight gate + `yue-synth`) matching V7.2 exactly."""
    info = probe_yue2()
    if not info["available"]:
        raise RuntimeError(info["statusNoteEn"])

    synth_bin = Path(info["binaryPath"])
    backbone = Path(info["modelPath"])
    vae = Path(info["vaePath"])
    plan_bin = Path(info["plannerBinaryPath"]) if info.get("plannerBinaryPath") else None

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    req_payload = build_yue2_request_from_plan(
        plan,
        seed=seed,
        cot=cot,
        abc_score=abc_score,
        cfg_scale=cfg_scale,
        semantic_temperature=semantic_temperature,
        source_tokens=source_tokens,
        semantic_tokens=semantic_tokens,
    )

    # Real V7.2 instrumental ABC preflight gate when no manual ABC score provided and yue-plan exists!
    instrumental = bool(plan.musicalIdentity.get("instrumentalOnly", True))
    score_source = "user_abc" if abc_score else "model_inline"
    if instrumental and abc_score is None and plan_bin and plan_bin.is_file() and req_payload["cot"] != "off":
        planner_req_path = out_wav.parent / "planner-request.json"
        planner_req_path.write_text(json.dumps(req_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        planned_abc_path = out_wav.parent / "planned.abc"
        run_cancellable_guarded(
            [
                str(plan_bin),
                "--model",
                str(backbone),
                "--request",
                str(planner_req_path),
                "--max-seq",
                "8192",
                "--out",
                str(planned_abc_path),
            ],
            out_wav.parent / "planner.log",
            cancel_event=cancel_event,
            timeout_sec=180.0,
        )
        planned_text = planned_abc_path.read_text(encoding="utf-8")
        ok, issues = check_resting_voice(planned_text)
        if not ok:
            raise ValueError(f"YuE2 native preflight ABC rejected (vocal notes detected): {'; '.join(issues)}")
        req_payload["abc"] = planned_text
        score_source = "native_preflight_verified"

    req_path = out_wav.parent / "request.json"
    req_path.write_text(json.dumps(req_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    plan_out_path = out_wav.parent / "plan.abc"

    cmd = [
        str(synth_bin),
        "--model",
        str(backbone),
        "--vae",
        str(vae),
        "--request",
        str(req_path),
        "--max-seq",
        "8192",
        "--out",
        str(out_wav),
        "--score",
        str(plan_out_path),
    ]
    run_meta = run_cancellable_guarded(
        cmd,
        out_wav.parent / "yue2.log",
        cancel_event=cancel_event,
        timeout_sec=timeout_sec,
    )
    if not out_wav.is_file():
        record_engine_verification("yue2-native", False, error="yue-synth finished without producing output WAV")
        raise RuntimeError("YuE2 binary finished without creating output WAV")

    audio, sr = sf.read(str(out_wav), dtype="float32", always_2d=True)
    vocal_check = screen_vocal_leakage(audio, sr, source_kind="neural_audio")
    record_engine_verification(
        "yue2-native",
        True,
        wav_path=str(out_wav),
        details={"durationSec": round(len(audio) / sr, 3), "peakRssGiB": run_meta["peakRssGiB"]},
    )
    return {
        "engine": "yue2-native",
        "wavPath": str(out_wav),
        "sampleRate": sr,
        "durationSec": round(len(audio) / sr, 3),
        "scoreSource": score_source,
        "vocalScreening": vocal_check,
        "request": req_payload,
        "runMeta": run_meta,
    }
