"""Inspect rendered PCM and chart together. Never infer a listening score."""

import argparse
import json
import hashlib
from collections import Counter
from pathlib import Path
import numpy as np
import soundfile as sf
from engine.paths import DATA
from engine.session.score import TRACKS


def verify(root, replay=None):
    spec = json.loads((root / "session.json").read_text())
    stats = json.loads((root / "qa/audio-analysis.json").read_text())
    sr = spec["sample_rate"]
    frames = spec["frames"]

    def read(name):
        x, rate = sf.read(root / name, always_2d=True)
        assert (
            rate == sr
            and x.shape == (frames, 2)
            and np.max(abs(x)) < 1
            and np.all(np.isfinite(x))
        )
        return x

    dry = read("dry-mix.wav")
    produced = read("processed-mix.wav")
    variant = read("variation-b.wav")
    assert not np.array_equal(produced, dry) and not np.array_equal(produced, variant)
    total = np.zeros_like(dry)
    delta = {}
    hashes = {}
    for track in TRACKS:
        name = f"stems/{track}.wav"
        x = read(name)
        total += x
        wet = read(f"wet/{track}.wav")
        delta[track] = float(np.sqrt(np.mean((wet - x) ** 2)))
        assert delta[track] > 0 and np.sqrt(np.mean(x * x)) > 0.001
        hashes[track] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if track in ("bass", "guitar"):
            assert not np.any(
                x[: round(8 * 60 / spec["music_plan"]["rhythm"]["bpm"] * sr)]
            )
    assert len(set(hashes.values())) == 4 and np.max(abs(total - dry)) < 5 / 2**23
    assert (
        np.all(read("final.wav") == produced) and np.max(abs(produced[-100:])) < 0.0002
    )
    if replay:
        for p in root.rglob("*.wav"):
            assert (
                hashlib.sha256(p.read_bytes()).digest()
                == hashlib.sha256((replay / p.relative_to(root)).read_bytes()).digest()
            )
    counts = {
        section["name"]: dict(
            Counter(
                e["track"]
                for e in spec["events"]
                if section["first"] <= e["bar"] <= section["last"]
            )
        )
        for section in spec["sections"]
    }
    results = dict(
        frame_count=frames,
        dry_stem_sum_max_error=float(np.max(abs(total - dry))),
        dry_wet_delta_rms=delta,
        stem_sha256=hashes,
        section_event_counts=counts,
        produced_variation_delta_rms=float(np.sqrt(np.mean((produced - variant) ** 2))),
        bit_identical_replay=True if replay else None,
        human_listening_scores=None,
    )
    (root / "qa/session-checks.json").write_text(json.dumps(results, indent=2))
    lines = [
        "# 116 BPM 소울 세션 검증",
        "",
        f"{frames:,} frames · {sr} Hz · 24-bit stereo. 청취 판정 대기.",
        "",
        "| 버전 | 피크 dBFS | RMS dBFS | 저중역 180–500 Hz | 존재감 2–6 kHz | L/R 상관 | 모노 합산 dB |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for k, a in stats.items():
        lines.append(
            f"| {k} | {a['peak_dbfs']:.2f} | {a['rms_dbfs']:.2f} | {a['low_mid_fraction']:.1%} | {a['presence_fraction']:.2%} | {a['lr_correlation']:.3f} | {a['mono_fold_db']:.2f} |"
        )
    lines += [
        "",
        "대역 비율은 좌우 채널 Welch 파워 합산 기준. 구간별 이벤트 수는 코드 하나를 한 이벤트로 집계한다.",
        "",
        json.dumps(counts, ensure_ascii=False),
        "",
        "세션에 사용한 전자피아노 녹음은 Greg Sullivan의 Wurlitzer EP200, 매핑은 kinwie. CC BY 3.0에 따라 피치 전환, 음 길이 조절 및 믹싱. 다른 녹음은 Virtuosity Drums 및 Karoryfer의 CC0 자산. 각 소스와 라이선스는 아래 링크를 따른다.",
        "",
    ]
    for b in spec["sources"].values():
        lines.append(
            f"- {b['author']} · [{b['repo']} / {b['license']}](https://github.com/{b['repo']}/blob/{b['revision']}/LICENSE)"
        )
    (root / "qa/session-report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--replay", type=Path)
    args = p.parse_args()
    verify(DATA / "session-engine", args.replay)
