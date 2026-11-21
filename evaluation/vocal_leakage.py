"""Conservative evidence fusion for instrumental audio. This is an automated screen."""

import re
from itertools import pairwise

TAGS = {
    "Speech": 0.22,
    "Singing": 0.15,
    "Humming": 0.12,
    "Choir": 0.19,
    "Chant": 0.15,
    "Shout": 0.15,
    "Vocal music": 0.20,
    "Breathing": 0.20,
    "Sigh": 0.20,
    "Groan": 0.20,
}
ASR_ARTIFACTS = {"", "music", "you", "thank you", "thanks for watching"}


def likely_vocal_tags(scores):
    return [tag for tag, limit in TAGS.items() if scores[tag] >= limit]


def suspicious(window):
    # Stem activity sends a window to investigation. Energy alone cannot establish vocals.
    mix_level, *voice_levels = window["rms_dbfs"]
    voice = max(voice_levels)
    audible_estimate = voice > -48 and voice - mix_level > -34
    raw_tags, *estimates = window["tags"]
    return (
        audible_estimate
        or bool(likely_vocal_tags(raw_tags))
        or (voice > -53 and any(likely_vocal_tags(tags) for tags in estimates))
    )


def matched_transcript(evidence):
    normalized = [
        " ".join(re.findall(r"[^\W_]+", text.casefold()))
        for text in evidence["transcripts"]
    ]
    mix, *stems = normalized
    if mix in ASR_ARTIFACTS or not stems:
        return False

    def pairs(text):
        return set(pairwise(text.split()))

    mix_pairs = pairs(mix)
    for stem in stems:
        if stem in ASR_ARTIFACTS:
            return False
        if stem == mix:
            continue
        if not mix_pairs.intersection(pairs(stem)):
            return False
    return True


def assess(windows, *, complete):
    """Combine mix, two voice estimates, event tags and targeted ASR in time alignment."""
    issues = []
    for window in windows:
        if not suspicious(window):
            continue
        raw, *stems = window["tags"]
        tags = set(likely_vocal_tags(raw))
        corroborated = sorted(
            tags.intersection(*(likely_vocal_tags(stem) for stem in stems))
        )
        voice_level = min(window["rms_dbfs"][1:])
        asr = window.get("asr")
        if (
            asr
            and voice_level > -48
            and matched_transcript(asr)
            and min(asr["no_speech"]) < 0.65
        ):
            reason = "aligned_transcript_and_audible_voice_estimates"
            status = "REJECT"
        elif corroborated and voice_level > -44:
            reason = "aligned_vocal_event_tags_and_audible_voice_estimates"
            status = "REJECT"
        else:
            reason = "unresolved_voice_like_evidence"
            status = "UNCERTAIN"
        issues.append(
            {
                "start_seconds": window["start_seconds"],
                "end_seconds": window["end_seconds"],
                "status": status,
                "reason": reason,
                "corroborated_tags": corroborated,
            }
        )
    status = (
        "REJECT"
        if any(issue["status"] == "REJECT" for issue in issues)
        else "UNCERTAIN"
        if issues or not windows or not complete
        else "PASS"
    )
    return {"status": status, "events": issues, "coverage_complete": complete}


def score_evidence(request, score, validator_path):
    """Validate the same text and conditioning sent to YuE2 with upstream rules."""
    import sys

    sys.path.insert(0, str(validator_path))
    try:
        from abc_tools import parse_abc
        from instrumental import validate_request

        parsed = parse_abc(score)
        vocal_notes = len(parsed.voices["Vocal"].notes)
        instrument_notes = len(parsed.voices["Ins"].notes)
        chords = len(parsed.voices["Vocal"].chords)
        official = {
            "id": "studio",
            "style": request["style"],
            "lyrics": request["lyrics"],
            "abc": score,
            "cot": request["cot"],
            "seed": request["seed"],
        }
        validate_request(official)
        submitted_score = request.get("abc")
        if not isinstance(submitted_score, str) or submitted_score.strip() != score.strip():
            raise ValueError("Rendered ABC disagrees with the submitted ABC")
    except (ValueError, KeyError, TypeError, OSError, ImportError, RuntimeError) as exc:
        return {
            "status": "REJECT" if isinstance(exc, ValueError) else "UNCERTAIN",
            "vocal_notes": locals().get("vocal_notes"),
            "reason": str(exc),
        }
    finally:
        sys.path.pop(0)
    return {
        "status": "PASS",
        "vocal_notes": vocal_notes,
        "instrumental_notes": instrument_notes,
        "chord_annotations": chords,
        "lyrics": request["lyrics"],
        "cot": request["cot"],
        "score_bpm": parsed.bpm,
    }


def measure(source, stems, tagger, transcriber):
    import math

    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    sources = []
    for path in (source, *stems):
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
        if not np.isfinite(audio).all() or not len(audio):
            raise ValueError("Invalid audio input to the leakage detector")
        divisor = math.gcd(rate, 32000)
        sources.append(
            resample_poly(audio.mean(axis=1), 32000 // divisor, rate // divisor)
        )
    if len(sources) != 3 or max(map(len, sources)) - min(map(len, sources)) > 640:
        raise ValueError(
            "Leakage QA needs the mix and two time-aligned voice estimates"
        )
    frames = len(sources[0])
    sources[1:] = [
        np.pad(s[:frames], (0, max(0, frames - len(s)))) for s in sources[1:]
    ]
    window = 4 * 32000
    final_start = max(0, frames - window)
    starts = sorted({*range(0, final_start, 2 * 32000), final_start})
    rows = []
    for offset in starts:
        samples = np.stack([s[offset : min(frames, offset + window)] for s in sources])
        level = 10 * np.log10(np.maximum(1e-12, np.mean(samples**2, axis=1)))
        scores = tagger(samples, TAGS)
        if not all(
            np.isfinite(value) for prediction in scores for value in prediction.values()
        ):
            raise ValueError("Non-finite audio-event score")
        rows.append(
            {
                "start_seconds": offset / 32000,
                "end_seconds": min(frames, offset + window) / 32000,
                "rms_dbfs": level.tolist(),
                "tags": scores,
            }
        )
    pending = [row for row in rows if suspicious(row)]
    # Several independent windows are enough to reject a candidate. Any
    # unexamined concerning window remains UNCERTAIN and cannot pass.
    for row in sorted(
        pending, key=lambda item: min(item["rms_dbfs"][1:]), reverse=True
    )[:3]:
        start = max(0, round(row["start_seconds"] * 32000) - 32000)
        end = min(frames, start + 6 * 32000)
        payload = [resample_poly(s[start:end], 1, 2) for s in sources]
        row["asr"] = transcriber(payload)
        row["asr"]["start_seconds"] = start / 32000
        row["asr"]["end_seconds"] = end / 32000
    return {
        "audio": assess(rows, complete=True),
        "windows": rows,
        "seconds": frames / 32000,
    }


def review(folder):
    import hashlib
    import json

    from engine.paths import RUNTIME
    from evaluation.vocal_models import (
        PANN_MD5,
        PANN_REVISION,
        WHISPER_REVISION,
        panns,
        separate,
        whisper,
    )

    request_path = folder / "request.json"
    request = json.loads(request_path.read_text())
    plan = (folder / "plan.abc").read_text()
    step = score_evidence(request, plan, RUNTIME / "v6/instrumental")
    output = {"status": step["status"], "score": step, "human_listening": "unverified"}
    if step["status"] == "PASS":
        try:
            source = folder / "original.wav"
            with source.open("rb") as handle:
                original_digest = hashlib.file_digest(handle, "sha256").hexdigest()
            diagnostics = folder / "diagnostics"
            stamp = diagnostics / "source.sha256"
            existing = [
                diagnostics / m / "vocals.wav" for m in ("htdemucs", "htdemucs_6s")
            ]
            if (
                stamp.is_file()
                and stamp.read_text().strip() == original_digest
                and all(p.is_file() for p in existing)
            ):
                stems = existing
            else:
                stems = separate(source.resolve(), diagnostics.resolve())
                stamp.write_text(original_digest + "\n")
            tagger = panns(RUNTIME / "v7/panns")
            asr = None

            def transcribe(audio):
                nonlocal asr
                if asr is None:
                    asr = whisper(RUNTIME / "v4/whisper-small")
                return asr(audio)

            output.update(measure(source, stems, tagger, transcribe))
            output["status"] = output["audio"]["status"]
            output["models"] = {
                "audio_tags": {
                    "panns_mobilenetv1": PANN_REVISION,
                    "checkpoint_md5": PANN_MD5,
                },
                "asr": f"openai/whisper-small@{WHISPER_REVISION}",
                "voice_estimates": ["htdemucs", "htdemucs_6s"],
            }
            for key, file in (("wav", source), ("request", request_path)):
                with file.open("rb") as handle:
                    output[f"{key}_sha256"] = hashlib.file_digest(
                        handle, "sha256"
                    ).hexdigest()
        except (
            ValueError,
            KeyError,
            TypeError,
            OSError,
            ImportError,
            RuntimeError,
        ) as exc:
            output.update(status="UNCERTAIN", error=f"{type(exc).__name__}: {exc}")
    (folder / "vocal-leakage.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    )
    return output


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("take", type=Path)
    path = parser.parse_args().take
    result = review(path)
    print(path, result["status"], result.get("error", ""), flush=True)
