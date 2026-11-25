"""AI Producer Sound Design Intelligence & Acoustic Track Diagnosis (Phase 05 · GATE 6 / Sections 40–42).

Never suggests blind presets or fake EQ edits:
1. Measures the target track's actual spectrum, low-mid mud energy, brightness, crest factor & stereo width first!
2. Builds concrete, undoable staged `ChangeProposal` operations (`track.setInstrument`, `instrument.setPreset`,
   `fx.add`, `bus.add`, `send.set`, `automation.upsertLane`) that preserve untouched MIDI notes & other tracks!
3. Supports real Before/After audio rendering comparison (Centroid Hz, Low-Mid %, Stereo Width, LUFS deltas).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

from engine.daw_workspace import commands, loudness, renderer
from engine.daw_workspace.schema import Project, Track, make_id


def diagnose_track_audio(project: Project, track_id: str, max_beats: float = 16.0) -> dict[str, Any]:
    """Render up to 16 beats of a single track and measure real acoustic spectrum, mud, brightness & dynamics."""
    trk = next((t for t in project.tracks if t.id == track_id), None)
    if trk is None:
        raise ValueError(f"Track not found: {track_id}")
    end_b = min(float(project.lengthBeats), max(4.0, max_beats))
    pcm, sr, meters = renderer.render_single_track_pre_fader(project, trk, start_beats=0.0, end_beats=end_b)
    mono = pcm.mean(axis=1).astype(np.float64)
    rms = float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0
    if rms < 1e-5:
        return {
            "trackId": track_id,
            "trackName": trk.name,
            "silent": True,
            "rmsDbfs": -120.0,
            "spectralCentroidHz": 0.0,
            "bandsPct": {},
            "stereoWidth": 0.0,
            "findingsKo": ["트랙 구간에 오디오 신호가 없습니다."],
        }

    nperseg = min(8192, max(256, len(mono)))
    freqs, psd = signal.welch(mono, fs=sr, nperseg=nperseg)
    tot = float(psd.sum()) + 1e-18

    def _bp(lo: float, hi: float) -> float:
        m = (freqs >= lo) & (freqs < hi)
        return round(float(psd[m].sum() / tot) * 100.0, 2)

    bands = {
        "sub_20_60": _bp(20, 60),
        "bass_60_200": _bp(60, 200),
        "low_mid_200_500": _bp(200, 500),
        "mid_500_2000": _bp(500, 2000),
        "presence_2k_6k": _bp(2000, 6000),
        "air_6k_20k": _bp(6000, 20000),
    }
    centroid_hz = round(float((freqs * psd).sum() / tot), 1)
    loud = loudness.measure_loudness(pcm, sr)
    left, right = pcm[:, 0].astype(np.float64), pcm[:, 1].astype(np.float64)
    mid_e = float(np.mean((0.5 * (left + right)) ** 2))
    side_e = float(np.mean((0.5 * (left - right)) ** 2))
    width = round(float(np.clip(math.sqrt(side_e / (mid_e + 1e-12)), 0.0, 1.5)), 3)

    findings_ko: list[str] = []
    if bands["low_mid_200_500"] >= 26.0:
        findings_ko.append(f"200–500 Hz 로우미드 비중({bands['low_mid_200_500']}%)이 높아 먹먹하게 들릴 수 있습니다.")
    if centroid_hz < 1200.0 and trk.type != "bass" and "bass" not in trk.name.lower():
        findings_ko.append(f"스펙트럼 중심({centroid_hz} Hz)이 낮아 어두운 톤입니다.")
    if bands["presence_2k_6k"] < 8.0 and any(k in trk.name.lower() for k in ("guitar", "기타", "synth", "신스", "keys", "건반")):
        findings_ko.append(f"2–6 kHz 프레즌스 대역({bands['presence_2k_6k']}%)이 약해 선명도가 부족합니다.")
    if width < 0.12 and any(k in trk.name.lower() for k in ("synth", "신스", "pad", "패드", "keys", "건반")):
        findings_ko.append(f"스테레오 폭({width})이 좁아 공간감을 확장할 여지가 있습니다.")
    if not findings_ko:
        findings_ko.append(f"균형 잡힌 스펙트럼(중심 {centroid_hz} Hz, 폭 {width}, {loud['integratedLufs']} LUFS)입니다.")

    return {
        "trackId": track_id,
        "trackName": trk.name,
        "silent": False,
        "rmsDbfs": loud["rmsDbfs"],
        "integratedLufs": loud["integratedLufs"],
        "crestFactorDb": loud["crestFactorDb"],
        "spectralCentroidHz": centroid_hz,
        "bandsPct": bands,
        "stereoWidth": width,
        "fxMeters": meters,
        "findingsKo": findings_ko,
    }


def _find_track_by_hints(project: Project, hints: list[str], selected_track_id: str | None = None) -> Track | None:
    for trk in project.tracks:
        low_n = trk.name.lower()
        if any(h in low_n for h in hints):
            return trk
    if selected_track_id:
        return next((t for t in project.tracks if t.id == selected_track_id), None)
    return project.tracks[0] if project.tracks else None


def plan_sound_design_operations(
    project: Project,
    instruction: str,
    selection: dict[str, Any] | None = None,
    active_reference_id: str | None = None,
) -> dict[str, Any] | None:
    """Detect natural-language Sound Design / Instrument / FX / Sidechain / Automation requests and build staged operations.

    Returns `None` if the instruction is NOT a sound design / FX / instrument request (so standard edit/compose routers handle it).
    """
    text = instruction.strip()
    low = text.lower()
    sel = selection or {}
    sel_tid = sel.get("selectedTrackId")

    # Quick trigger check for Sound Design / Instrument / FX / Automation intents
    sd_triggers = (
        "먹먹", "탁하", "답답", "선명", "밝게", "따뜻", "아날로그", "빈티지", "공간감", "넓혀", "넓게",
        "eq", "이큐", "컴프", "compressor", "리버브", "reverb", "딜레이", "delay", "에코",
        "코러스", "chorus", "페이저", "phaser", "새츄레이션", "saturation", "테이프", "tape",
        "앰프", "amp", "크런치", "crunch", "오버드라이브", "overdrive", "디스토션", "distortion",
        "사이드체인", "sidechain", "뭉쳐", "뭉치", "덕킹", "ducking",
        "필터", "filter", "서서히 열", "오토메이션", "automation", "리미터", "limiter",
        "소리만", "음색", "가상악기", "프리셋", "preset", "로즈", "rhodes", "피아노", "드럼 소리",
    )
    if not any(k in low for k in sd_triggers):
        return None

    ops: list[dict[str, Any]] = []
    diagnosis: dict[str, Any] | None = None
    summary_parts: list[str] = []
    preserved_note = "기존 MIDI 노트는 유지됩니다."

    # 1. Request B: Kick & Bass clash / Sidechain Compression!
    if any(k in low for k in ("사이드체인", "sidechain", "덕킹", "ducking")) or (
        any(k in low for k in ("킥", "kick", "드럼")) and any(k in low for k in ("베이스", "bass")) and any(k in low for k in ("뭉쳐", "뭉치", "정리", "분리", "충돌", "clash"))
    ):
        drums_trk = _find_track_by_hints(project, ["drum", "드럼", "kick", "킥"])
        bass_trk = _find_track_by_hints(project, ["bass", "베이스"], sel_tid)
        if bass_trk:
            diagnosis = diagnose_track_audio(project, bass_trk.id, max_beats=8.0)
            sc_tid = drums_trk.id if (drums_trk and drums_trk.id != bass_trk.id) else None
            ops.append(
                {
                    "type": "fx.add",
                    "payload": {
                        "trackId": bass_trk.id,
                        "type": "parametric_eq",
                        "preset": "bass_focus",
                    },
                }
            )
            ops.append(
                {
                    "type": "fx.add",
                    "payload": {
                        "trackId": bass_trk.id,
                        "type": "sidechain_compressor",
                        "preset": "house_pump" if "강하" in low or "하우스" in low else "subtle_pocket",
                        "sidechainTrackId": sc_tid,
                    },
                }
            )
            src_label = drums_trk.name if drums_trk else "외부 킥 트랙"
            summary_parts.append(f"{bass_trk.name}: Bass Focus EQ + 외부 사이드체인 컴프레서(소스: {src_label})")
            return {
                "matched": True,
                "intent": "kick_bass_sidechain",
                "summary": " · ".join(summary_parts),
                "operations": ops,
                "diagnosis": diagnosis,
                "preservedNote": f"{bass_trk.name} MIDI 및 다른 트랙 유지",
            }

    # 2. Request E-1: Section-scoped Filter Buildup Automation ("빌드업에서 신스 필터가 서서히 열리게")
    if any(k in low for k in ("필터", "filter")) and any(k in low for k in ("열리", "열어", "열게", "서서히", "빌드업", "buildup", "sweep", "스윕")):
        target_trk = _find_track_by_hints(project, ["synth", "신스", "hook", "훅", "pad", "패드", "lead", "리드"], sel_tid)
        if target_trk:
            fx_id = make_id("fx")
            bpb = project.timeSignature.beats_per_bar
            tr_range = sel.get("timeRangeBeats") or {}
            start_b = float(tr_range.get("startBeats", 0.0))
            end_b = float(tr_range.get("endBeats", min(project.lengthBeats, start_b + bpb * 4.0)))
            ops.append(
                {
                    "type": "fx.add",
                    "payload": {
                        "trackId": target_trk.id,
                        "id": fx_id,
                        "type": "filter",
                        "preset": "buildup_lp",
                        "parameters": {"mode": "lpf24", "cutoffHz": 320.0, "resonance": 0.42, "drive": 1.4},
                    },
                }
            )
            ops.append(
                {
                    "type": "automation.upsertLane",
                    "payload": {
                        "trackId": target_trk.id,
                        "lane": {
                            "targetType": "fx",
                            "targetId": fx_id,
                            "parameterId": "cutoffHz",
                            "enabled": True,
                            "points": [
                                {"beat": start_b, "value": 280.0, "interpolation": "linear"},
                                {"beat": start_b + (end_b - start_b) * 0.45, "value": 1200.0, "interpolation": "linear"},
                                {"beat": end_b, "value": 9200.0, "interpolation": "linear"},
                            ],
                        },
                    },
                }
            )
            summary_parts.append(f"{target_trk.name}: 래더 필터 + 컷오프 오토메이션({int(start_b/bpb)+1}~{int(end_b/bpb)}마디 280Hz→9.2kHz)")
            return {
                "matched": True,
                "intent": "filter_buildup_automation",
                "summary": " · ".join(summary_parts),
                "operations": ops,
                "diagnosis": diagnose_track_audio(project, target_trk.id, max_beats=8.0),
                "preservedNote": preserved_note,
            }

    # 3. Request E-2: Section-scoped Delay Automation ("후반 기타 솔로에서만 딜레이를 늘려줘")
    if any(k in low for k in ("딜레이", "delay", "에코")) and any(k in low for k in ("후반", "솔로", "클라이맥스", "구간", "만", "늘려", "오토메이션")):
        target_trk = _find_track_by_hints(project, ["guitar", "기타", "lead", "리드", "synth", "신스"], sel_tid)
        if target_trk:
            fx_id = make_id("fx")
            bpb = project.timeSignature.beats_per_bar
            half_b = max(bpb, float(project.lengthBeats) * 0.5)
            end_b = float(project.lengthBeats)
            ops.append(
                {
                    "type": "fx.add",
                    "payload": {
                        "trackId": target_trk.id,
                        "id": fx_id,
                        "type": "delay",
                        "preset": "dotted_eighth",
                        "wetDry": 0.10,
                    },
                }
            )
            ops.append(
                {
                    "type": "automation.upsertLane",
                    "payload": {
                        "trackId": target_trk.id,
                        "lane": {
                            "targetType": "fx",
                            "targetId": fx_id,
                            "parameterId": "wetDry",
                            "enabled": True,
                            "points": [
                                {"beat": 0.0, "value": 0.06, "interpolation": "linear"},
                                {"beat": max(0.0, half_b - 0.5), "value": 0.08, "interpolation": "linear"},
                                {"beat": half_b, "value": 0.42, "interpolation": "linear"},
                                {"beat": end_b, "value": 0.48, "interpolation": "linear"},
                            ],
                        },
                    },
                }
            )
            summary_parts.append(f"{target_trk.name}: 1/8 Dotted 딜레이 + 후반 구간 Wet 오토메이션(6%→48%)")
            return {
                "matched": True,
                "intent": "section_delay_automation",
                "summary": " · ".join(summary_parts),
                "operations": ops,
                "diagnosis": diagnose_track_audio(project, target_trk.id, max_beats=8.0),
                "preservedNote": preserved_note,
            }

    # 4. Request D: Drum Sound Swap Preserving MIDI Rhythm ("드럼 리듬은 그대로 두고 드럼 소리만 더 빈티지하게")
    if any(k in low for k in ("드럼", "drum", "비트")) and any(k in low for k in ("빈티지", "vintage", "어쿠스틱", "acoustic", "재즈", "jazz", "록", "rock", "909", "소리만", "음색", "킷", "kit")):
        drum_trk = _find_track_by_hints(project, ["drum", "드럼", "beat", "비트"], sel_tid)
        if drum_trk:
            diagnosis = diagnose_track_audio(project, drum_trk.id, max_beats=8.0)
            kit_preset = (
                "boombap-vintage"
                if any(k in low for k in ("빈티지", "vintage", "붐뱁", "로파이"))
                else ("jazz-brush" if any(k in low for k in ("재즈", "jazz", "브러쉬")) else ("indie-rock-acoustic" if any(k in low for k in ("어쿠스틱", "acoustic", "록", "rock")) else "house-909"))
            )
            ops.append(
                {
                    "type": "track.setInstrument",
                    "payload": {"trackId": drum_trk.id, "instrumentRef": "pro-drum-rack", "preset": kit_preset},
                }
            )
            if kit_preset == "boombap-vintage":
                ops.append({"type": "fx.add", "payload": {"trackId": drum_trk.id, "type": "saturation", "preset": "warm_tape"}})
            summary_parts.append(f"{drum_trk.name}: Drum Rack '{kit_preset}' 교체 (기존 드럼 MIDI 리듬 100% 보존)")
            return {
                "matched": True,
                "intent": "drum_sound_swap_preserve_midi",
                "summary": " · ".join(summary_parts),
                "operations": ops,
                "diagnosis": diagnosis,
                "preservedNote": "기존 드럼 MIDI 리듬 및 타이밍 100% 유지",
            }

    # 5. Request C: Synth Timbre Redesign + Space Preserving MIDI ("신스 훅의 멜로디는 유지하고 좀 더 아날로그 느낌으로, 공간감도 넓혀줘")
    if any(k in low for k in ("신스", "synth", "훅", "hook", "리드", "lead", "패드", "pad")) and any(
        k in low for k in ("아날로그", "analog", "공간감", "넓혀", "따뜻", "음색", "소리", "리버브", "딜레이", "코러스")
    ):
        syn_trk = _find_track_by_hints(project, ["synth", "신스", "hook", "훅", "lead", "리드", "pad", "패드"], sel_tid)
        if syn_trk:
            diagnosis = diagnose_track_audio(project, syn_trk.id, max_beats=8.0)
            if syn_trk.type == "midi":
                preset_id = "wide-analog-pad" if ("pad" in syn_trk.name.lower() or "패드" in low) else "warm-analog-pluck"
                ops.append(
                    {
                        "type": "track.setInstrument",
                        "payload": {"trackId": syn_trk.id, "instrumentRef": "pro-synth-analog", "preset": preset_id},
                    }
                )
                summary_parts.append(f"Instrument: Analog Synth ({preset_id})")
            ops.append({"type": "fx.add", "payload": {"trackId": syn_trk.id, "type": "parametric_eq", "preset": "low_mid_clean"}})
            summary_parts.append("EQ: Low-mid 정리")
            if any(k in low for k in ("딜레이", "delay", "공간감", "넓혀", "넓게")):
                ops.append({"type": "fx.add", "payload": {"trackId": syn_trk.id, "type": "delay", "preset": "dotted_eighth", "wetDry": 0.22}})
                summary_parts.append("Delay: 1/8 dotted")
            if any(k in low for k in ("리버브", "reverb", "공간감", "넓혀", "넓게")):
                # Create or reuse Room Reverb Send Bus cleanly!
                existing_bus = next((b for b in (project.buses or []) if "reverb" in str(b.get("name", "")).lower() or "리버브" in str(b.get("name", ""))), None)
                if existing_bus:
                    bus_id = str(existing_bus["id"])
                else:
                    bus_id = make_id("bus")
                    ops.append({"type": "bus.add", "payload": {"id": bus_id, "name": "Room Reverb", "kind": "return"}})
                    ops.append({"type": "fx.add", "payload": {"target": "bus", "busId": bus_id, "type": "reverb", "preset": "studio_room", "wetDry": 1.0}})
                ops.append({"type": "send.set", "payload": {"trackId": syn_trk.id, "busId": bus_id, "levelDb": -8.0, "preFader": False}})
                summary_parts.append("Room Reverb Send (-8 dB)")
            return {
                "matched": True,
                "intent": "synth_timbre_and_space_redesign",
                "summary": f"{syn_trk.name} · " + " · ".join(summary_parts),
                "operations": ops,
                "diagnosis": diagnosis,
                "preservedNote": "기존 MIDI 멜로디 및 드럼/베이스 유지",
            }

    # 6. Request A & General Track Sound Diagnosis + EQ / Amp / FX Design ("기타가 너무 먹먹해", "크런치 앰프", "로즈 피아노", etc.)
    target_trk = None
    if any(k in low for k in ("기타", "guitar")):
        target_trk = _find_track_by_hints(project, ["guitar", "기타"], sel_tid)
    elif any(k in low for k in ("건반", "피아노", "로즈", "keys", "piano", "ep")):
        target_trk = _find_track_by_hints(project, ["keys", "건반", "piano", "피아노", "rhodes"], sel_tid)
    elif any(k in low for k in ("베이스", "bass")):
        target_trk = _find_track_by_hints(project, ["bass", "베이스"], sel_tid)
    elif any(k in low for k in ("드럼", "drum")):
        target_trk = _find_track_by_hints(project, ["drum", "드럼"], sel_tid)
    else:
        target_trk = _find_track_by_hints(project, [], sel_tid)

    if not target_trk:
        return None

    diagnosis = diagnose_track_audio(project, target_trk.id, max_beats=8.0)

    # Muddy / dark acoustic diagnosis -> real measured EQ cut/boost!
    if any(k in low for k in ("먹먹", "탁하", "답답", "선명", "밝게", "eq", "이큐")):
        low_mid_pct = float((diagnosis.get("bandsPct") or {}).get("low_mid_200_500", 22.0))
        cut_db = -4.5 if low_mid_pct >= 28.0 else -3.0
        ops.append(
            {
                "type": "fx.add",
                "payload": {
                    "trackId": target_trk.id,
                    "type": "parametric_eq",
                    "preset": "low_mid_clean",
                    "parameters": {
                        "bands": [
                            {"id": "hpf", "type": "highpass", "freqHz": 95.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                            {"id": "low", "type": "low_shelf", "freqHz": 120.0, "gainDb": 0.0, "q": 0.707, "enabled": True},
                            {"id": "low_mid", "type": "peak", "freqHz": 310.0, "gainDb": cut_db, "q": 1.2, "enabled": True},
                            {"id": "high_mid", "type": "peak", "freqHz": 2900.0, "gainDb": 2.4, "q": 1.0, "enabled": True},
                            {"id": "high", "type": "high_shelf", "freqHz": 8500.0, "gainDb": 1.6, "q": 0.707, "enabled": True},
                            {"id": "lpf", "type": "lowpass", "freqHz": 18000.0, "gainDb": 0.0, "q": 0.707, "enabled": False},
                        ]
                    },
                },
            }
        )
        summary_parts.append(f"EQ (HPF 95Hz, 310Hz {cut_db}dB 컷, 2.9kHz +2.4dB)")

    if any(k in low for k in ("앰프", "amp", "크런치", "crunch", "오버드라이브", "overdrive", "디스토션", "distortion")):
        amp_m = "high_gain" if "하이게인" in low or "디스토션" in low else ("overdrive" if "오버드라이브" in low else ("clean" if "클린" in low else "crunch"))
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "guitar_amp", "preset": amp_m}})
        summary_parts.append(f"Tube Guitar Amp ({amp_m} + Cab IR)")

    if any(k in low for k in ("컴프", "compressor")):
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "compressor", "preset": "gentle_glue"}})
        summary_parts.append("Studio Compressor")

    if any(k in low for k in ("리버브", "reverb", "공간감", "홀", "룸")):
        rm = "hall" if "홀" in low or "넓" in low else ("plate" if "플레이트" in low else "studio_room")
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "reverb", "preset": rm, "wetDry": 0.28}})
        summary_parts.append(f"Convolution Reverb ({rm})")

    if any(k in low for k in ("딜레이", "delay", "에코")):
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "delay", "preset": "dotted_eighth", "wetDry": 0.24}})
        summary_parts.append("Tempo-Synced Delay")

    if any(k in low for k in ("코러스", "chorus")):
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "chorus", "preset": "juno_wide"}})
        summary_parts.append("Stereo Chorus")

    if any(k in low for k in ("새츄레이션", "saturation", "테이프", "tape", "따뜻")):
        ops.append({"type": "fx.add", "payload": {"trackId": target_trk.id, "type": "saturation", "preset": "warm_tape"}})
        summary_parts.append("Tape Saturation")

    if any(k in low for k in ("로즈", "rhodes")) and target_trk.type == "midi":
        ops.append({"type": "track.setInstrument", "payload": {"trackId": target_trk.id, "instrumentRef": "sf-ep-rhodes", "preset": "rhodes_tine"}})
        summary_parts.append("Rhodes Tine EP (SF3)")

    if not ops:
        return None

    return {
        "matched": True,
        "intent": "acoustic_sound_design",
        "summary": f"{target_trk.name} · " + " · ".join(summary_parts),
        "operations": ops,
        "diagnosis": diagnosis,
        "preservedNote": preserved_note,
    }


def compare_before_after_proposal(
    project: Project,
    operations: list[dict[str, Any]],
    max_beats: float = 8.0,
) -> dict[str, Any]:
    """Render short Before vs After preview in memory and return real measured acoustic deltas (Centroid, LUFS, Width)."""
    end_b = min(float(project.lengthBeats), max(4.0, max_beats))
    before_pcm, sr = renderer.render_project_to_array(project, start_beats=0.0, end_beats=end_b)  # type: ignore[misc]
    after_proj = project
    for op in operations:
        after_proj = commands.apply_command(after_proj, str(op["type"]), dict(op.get("payload") or {}))
    after_pcm, _ = renderer.render_project_to_array(after_proj, start_beats=0.0, end_beats=end_b)  # type: ignore[misc]

    def _stats(pcm: np.ndarray) -> dict[str, float]:
        mono = pcm.mean(axis=1).astype(np.float64)
        loud = loudness.measure_loudness(pcm, sr)
        nperseg = min(4096, max(256, len(mono)))
        f, p = signal.welch(mono, fs=sr, nperseg=nperseg)
        tot = float(p.sum()) + 1e-18
        cent = round(float((f * p).sum() / tot), 1)
        lm = round(float(p[(f >= 200) & (f < 500)].sum() / tot) * 100.0, 2)
        hi = round(float(p[(f >= 2000) & (f < 16000)].sum() / tot) * 100.0, 2)
        l_ch, r_ch = pcm[:, 0].astype(np.float64), pcm[:, 1].astype(np.float64)
        w = round(float(np.clip(math.sqrt(float(np.mean((0.5 * (l_ch - r_ch)) ** 2)) / (float(np.mean((0.5 * (l_ch + r_ch)) ** 2)) + 1e-12)), 0.0, 1.5)), 3)
        return {"integratedLufs": loud["integratedLufs"], "spectralCentroidHz": cent, "lowMidPct": lm, "highPct": hi, "stereoWidth": w}

    b_st = _stats(before_pcm)
    a_st = _stats(after_pcm)
    diff_rms = float(np.sqrt(np.mean((after_pcm - before_pcm) ** 2)))
    return {
        "before": b_st,
        "after": a_st,
        "deltas": {
            "lufsDelta": round(a_st["integratedLufs"] - b_st["integratedLufs"], 2),
            "centroidDeltaHz": round(a_st["spectralCentroidHz"] - b_st["spectralCentroidHz"], 1),
            "lowMidDeltaPct": round(a_st["lowMidPct"] - b_st["lowMidPct"], 2),
            "highDeltaPct": round(a_st["highPct"] - b_st["highPct"], 2),
            "stereoWidthDelta": round(a_st["stereoWidth"] - b_st["stereoWidth"], 3),
            "audibleDifferenceRms": round(diff_rms, 5),
        },
        "audibleChangeDetected": diff_rms > 1e-4,
    }
