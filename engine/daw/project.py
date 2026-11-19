"""Prepare immutable bar MIDI and sample assignments for REAPER's stock sampler."""

import hashlib
import math
from collections import defaultdict
from pathlib import Path

from engine.session.bank import CACHE, select_sample
from engine.session.score import CHART, SECTIONS

from .instruments import key_region

PPQ = 960
LANES = ("kick", "snare", "hat", "openhat", "bass", "guitar", "chuck", "keys")
PERCUSSION = {"kick": 36, "snare": 38, "hat": 42, "openhat": 46, "chuck": 37}


def assignments(spec):
    bpm = spec["music_plan"]["rhythm"]["bpm"]
    notes = defaultdict(list)
    zones = defaultdict(dict)
    # Channel distinguishes takes/layers that share the same played MIDI note.
    for i, e in enumerate(spec["events"]):
        if e.get("muted"):
            continue
        pitches = e["notes"][::-1] if e["art"] == "up" else e["notes"]
        voice = e["voice"]
        for j, p in enumerate(pitches):
            if voice == "keys" and spec.get("keyboard_mapping"):
                root, cents, gain, source, digest = key_region(
                    p, e["velocity"], spec["keyboard_mapping"]
                )
            else:
                _, root, _, _, source, digest = select_sample(
                    e["track"], voice, p, e["velocity"], i + j
                )
                cents = gain = 0
            # Match the Session Engine chord fader without changing the MIDI
            # velocity or the recorded attack selected for this note.
            gain -= 11 * math.log10(len(pitches))
            midi = PERCUSSION.get(voice, p)
            zone = (digest, source, e["track"], p - root + cents / 100, gain)
            bucket = zones[voice, midi]
            channel = bucket.setdefault(zone, len(bucket))
            if channel >= 16:
                raise ValueError("Too many sample zones for one MIDI note")
            spread = {"guitar": 0.005, "keys": 0.002}.get(voice, 0)
            start = round((e["step"] / 4 + j * spread * bpm / 60) * PPQ)
            end = min(PPQ * 4, start + round(e["length"] * PPQ / 4))
            notes[voice, e["bar"]].append((start, end, channel, midi, e["velocity"]))
    return notes, zones


def midi_lines(notes):
    messages = []
    for start, end, channel, pitch, velocity in notes:
        for tick, status, vel in [(start, 0x90, velocity), (end, 0x80, 0)]:
            messages.append((tick, status, channel, pitch, vel))
    last = 0
    for tick, status, channel, pitch, vel in sorted(messages):
        yield f"E {tick - last} {status + channel:02x} {pitch:02x} {vel:02x}"
        last = tick
    yield f"E {4 * PPQ - last} b0 7b 00"


def export(spec, folder):
    bpm = spec["music_plan"]["rhythm"]["bpm"]
    # Only the published 14-bar soul score has a verified export. Restrict all
    # user-derived labels interpolated into a REAPER chunk to this chart.
    if (
        spec["chart"] != CHART
        or not isinstance(bpm, (int, float))
        or not 45 <= bpm <= 240
    ):
        raise ValueError("Unsupported DAW chart or tempo")
    if [(s["name"], s["first"], s["last"]) for s in spec["sections"]] != SECTIONS:
        raise ValueError("Unsupported regions")
    notes, zones = assignments(spec)
    bar_seconds = 240 / bpm
    lines = [
        '<REAPER_PROJECT 0.1 "7" 0',
        f"TEMPO {bpm} 4 4",
        "SAMPLERATE 48000 1 0",
        "RENDER_FMT 0 2 48000",
    ]
    for bar, chord in enumerate(spec["chart"], 1):
        lines.append(f'MARKER {bar} {(bar - 1) * bar_seconds} "{bar} {chord}" 0 0 1')
    for i, section in enumerate(spec["sections"], 100):
        lines.extend(
            [
                f'MARKER {i} {float(section["start"])} "{section["name"]}" 1 0 1',
                f'MARKER {i} {float(section["end"])} "" 1 0 1',
            ]
        )
    for voice in LANES:
        lines.extend(["<TRACK", f'NAME "{voice}"'])
        for bar in range(1, len(spec["chart"]) + 1):
            lines.extend(
                [
                    "<ITEM",
                    f"POSITION {(bar - 1) * bar_seconds}",
                    f"LENGTH {bar_seconds}",
                    "LOOP 0",
                    f'NAME "{voice} | {bar}"',
                    "<SOURCE MIDI",
                    f"HASDATA 1 {PPQ} QN",
                ]
            )
            lines.extend(midi_lines(notes[voice, bar]))
            lines.extend([">", ">"])
        lines.append(">")
    (folder / "Score.RPP").write_text("\n".join(lines + [">", ""]))
    samples = folder / "Samples"
    samples.mkdir()
    rows = []
    for (voice, midi), bucket in zones.items():
        for (digest, source, track, transpose, gain), ch in bucket.items():
            dest = samples / (digest + Path(source).suffix)
            if not dest.exists():
                data = (CACHE / digest).read_bytes()
                if (
                    hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                    != digest
                ):
                    raise ValueError(f"Invalid pinned sample: {source}")
                # Copies remain recoverable even if the global cache moves.
                dest.write_bytes(data)
            rows.append([voice, midi, ch + 1, dest.name, transpose, gain])
    (folder / "zones.tsv").write_text(
        "".join("\t".join(map(str, row)) + "\n" for row in rows)
    )
    mix = spec["mixer"]
    settings = dict(
        mix["levels"],
        duration=spec["frames"] / spec["sample_rate"],
        keys_bell_db=mix["keys"]["chain"][0]["gain_db"],
    )
    settings["guitar_highpass_hz"] = mix["guitar"]["highpass_hz"]
    for group in ("drums", "bass"):
        compressor = next(
            fx for fx in mix[group]["chain"] if fx["type"] == "compressor"
        )
        for field in ("threshold_db", "ratio", "attack_ms", "release_ms"):
            settings[f"{group}_{field}"] = compressor[field]
    for voice in LANES:
        group = (
            "drums"
            if voice in ("kick", "snare", "hat", "openhat")
            else "guitar"
            if voice == "chuck"
            else voice
        )
        settings[voice + "_pan"] = mix[group]["pan"]
        settings[group + "_send"] = mix[group]["send"]
    (folder / "mix.tsv").write_text("".join(f"{k}\t{v}\n" for k, v in settings.items()))
    (folder / "build.lua").write_bytes(
        Path(__file__).with_name("build.lua").read_bytes()
    )
    return {
        "items": len(LANES) * len(spec["chart"]),
        "sampler_zones": len(rows),
        "midi_notes": sum(map(len, notes.values())),
        "unique_recordings": len(list(samples.iterdir())),
    }
