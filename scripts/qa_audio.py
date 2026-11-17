"""Render each effect on actual generated music and record objective evidence."""

import hashlib
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from engine import service, store
from engine.rendering.audio import read_audio

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = [
    dict(type="eq", mode="low_shelf", frequency=110, gain_db=4),
    dict(type="eq", mode="high_shelf", frequency=5000, gain_db=-4),
    dict(type="eq", mode="peaking", frequency=1000, gain_db=-5, q=1.5),
    dict(type="compressor", threshold_db=-24, ratio=4, attack_ms=10, release_ms=130),
    dict(type="reverb", wet=0.28, decay=3.5, pre_delay_ms=30),
    dict(type="distortion", drive_db=12, tone_hz=5000, output_db=-9),
    dict(type="limiter", ceiling_db=-6),
]


def main(version_id):
    source = store.get_version(version_id)
    source_path = Path(source["path"])
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    report = []
    for effect in EFFECTS:
        effects = [effect]
        # An explicit terminal limiter prevents PCM clipping after boosts.
        if effect["type"] != "limiter":
            effects.append(dict(type="limiter", ceiling_db=-1))
        result = service.render(
            version_id, effects, "Objective individual-effect verification"
        )
        check = result["comparison"]
        assert (
            check["same_format"]
            and check["changed_samples"] > 0
            and check["modified"]["finite"]
        )
        assert check["modified"]["clipped_samples"] == 0
        report.append(dict(effect=effect, **result))
    produced = service.produce(
        version_id, "베이스를 좀 더 묵직하게, 조금 더 몽환적으로 만들어줘."
    )
    assert produced["applied"]
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == digest
    x, sr = read_audio(source_path)
    y, _ = read_audio(produced["version"]["path"])
    fig, ax = plt.subplots(3, 1, figsize=(12, 8), constrained_layout=True)
    step = max(1, len(x) // 12000)
    t = np.arange(0, len(x), step) / sr
    ax[0].plot(t, x[::step, 0], lw=0.4, color="#56768f")
    ax[0].set_title("Original AI generation • left channel")
    ax[1].plot(t, y[::step, 0], lw=0.4, color="#a67850")
    ax[1].set_title("Low shelf + compressor + high shelf + reverb + limiter")
    ax[2].plot(t, (y - x)[::step, 0], lw=0.4, color="#7960a0")
    ax[2].set_title("Difference waveform")
    for axis in ax:
        axis.set_xlabel("Seconds")
        axis.set_ylabel("Amplitude")
        axis.grid(alpha=0.15)
    fig.savefig(ROOT / "docs/audio-comparison.png", dpi=130)
    plt.close(fig)
    result = dict(
        original=source, original_sha256=digest, effects=report, producer=produced
    )
    (ROOT / "docs/audio-qa.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            dict(
                original_id=version_id,
                modified_id=produced["version"]["id"],
                checks=len(report),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    import sys

    main(sys.argv[1])
