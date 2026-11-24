"""Pure-Python Standard MIDI File (SMF Format 0 & 1) parser and writer."""

from __future__ import annotations

import struct
from typing import Any

from .schema import DEFAULT_PPQ, make_id


def _read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("Unexpected EOF while reading MIDI variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            return value, offset
    raise ValueError("MIDI VLQ exceeded 4 bytes")


def _write_vlq(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI delta tick cannot be negative")
    chunks = [value & 0x7F]
    value >>= 7
    while value:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(chunks))


def parse_midi_bytes(data: bytes) -> dict[str, Any]:
    """Parse SMF Format 0/1 bytes into beat-based MIDI notes, PPQ, and tempo."""
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("Invalid Standard MIDI File header")
    header_len = struct.unpack(">I", data[4:8])[0]
    if header_len < 6 or len(data) < 8 + header_len:
        raise ValueError("Truncated MIDI header chunk")
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise ValueError("SMPTE MIDI time division is not supported in Phase 01")
    ppq = max(1, division)

    offset = 8 + header_len
    bpm: float | None = None
    notes: list[dict[str, Any]] = []
    max_tick = 0

    for _ in range(ntracks):
        if offset + 8 > len(data) or data[offset : offset + 4] != b"MTrk":
            break
        trk_len = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        offset += 8
        trk_end = min(len(data), offset + trk_len)

        abs_tick = 0
        running_status = 0
        active: dict[tuple[int, int], list[tuple[int, int]]] = {}

        while offset < trk_end:
            delta, offset = _read_vlq(data, offset)
            abs_tick += delta
            if abs_tick > max_tick:
                max_tick = abs_tick
            if offset >= trk_end:
                break

            status = data[offset]
            if status < 0x80:
                if running_status == 0:
                    raise ValueError("MIDI running status used before status byte")
                status = running_status
            else:
                offset += 1
                if status < 0xF0:
                    running_status = status

            if status == 0xFF:
                if offset >= trk_end:
                    break
                meta_type = data[offset]
                offset += 1
                meta_len, offset = _read_vlq(data, offset)
                meta_data = data[offset : offset + meta_len]
                offset += meta_len
                if meta_type == 0x51 and len(meta_data) == 3 and bpm is None:
                    us_per_quarter = (meta_data[0] << 16) | (meta_data[1] << 8) | meta_data[2]
                    if us_per_quarter > 0:
                        bpm = round(60_000_000.0 / us_per_quarter, 3)
                elif meta_type == 0x2F:
                    break
            elif status in (0xF0, 0xF7):
                sysex_len, offset = _read_vlq(data, offset)
                offset += sysex_len
            else:
                msg_type = status & 0xF0
                channel = status & 0x0F
                if msg_type in (0xC0, 0xD0):
                    offset += 1
                elif msg_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    if offset + 2 > trk_end:
                        break
                    d1, d2 = data[offset], data[offset + 1]
                    offset += 2
                    if msg_type == 0x90 and d2 > 0:
                        active.setdefault((channel, d1), []).append((abs_tick, d2))
                    elif msg_type == 0x80 or (msg_type == 0x90 and d2 == 0):
                        stack = active.get((channel, d1))
                        if stack:
                            start_tick, velocity = stack.pop(0)
                            dur_ticks = max(1, abs_tick - start_tick)
                            notes.append(
                                {
                                    "id": make_id("note"),
                                    "pitch": int(d1),
                                    "velocity": int(max(1, min(127, velocity))),
                                    "startBeat": round(start_tick / ppq, 6),
                                    "durationBeats": round(dur_ticks / ppq, 6),
                                }
                            )
                else:
                    break

        # Close any dangling notes cleanly at track end
        for (_, pitch), stack in active.items():
            for start_tick, velocity in stack:
                dur_ticks = max(ppq // 4, max_tick - start_tick)
                notes.append(
                    {
                        "id": make_id("note"),
                        "pitch": int(pitch),
                        "velocity": int(max(1, min(127, velocity))),
                        "startBeat": round(start_tick / ppq, 6),
                        "durationBeats": round(dur_ticks / ppq, 6),
                    }
                )

        offset = trk_end

    notes.sort(key=lambda n: (n["startBeat"], n["pitch"]))
    end_beats = max((n["startBeat"] + n["durationBeats"] for n in notes), default=4.0)
    duration_beats = max(end_beats, max_tick / ppq if max_tick > 0 else 4.0)
    return {
        "format": fmt,
        "ppq": ppq,
        "bpm": bpm,
        "durationBeats": round(duration_beats, 6),
        "notes": notes,
    }


def write_midi_bytes(
    notes: list[dict[str, Any]],
    bpm: float = 128.0,
    ppq: int = DEFAULT_PPQ,
    track_name: str = "Synth",
) -> bytes:
    """Serialize beat-based notes into a valid SMF Format 0 binary."""
    events: list[tuple[int, int, bytes]] = []
    # Tempo meta event
    us_per_quarter = max(1, int(round(60_000_000.0 / bpm)))
    tempo_bytes = bytes(
        [
            0xFF,
            0x51,
            0x03,
            (us_per_quarter >> 16) & 0xFF,
            (us_per_quarter >> 8) & 0xFF,
            us_per_quarter & 0xFF,
        ]
    )
    name_raw = track_name.encode("ascii", errors="ignore")[:64]
    name_bytes = bytes([0xFF, 0x03]) + _write_vlq(len(name_raw)) + name_raw
    events.append((0, 0, name_bytes))
    events.append((0, 1, tempo_bytes))

    for n in notes:
        pitch = max(0, min(127, int(n["pitch"])))
        vel = max(1, min(127, int(n.get("velocity", 100))))
        start_tick = max(0, int(round(float(n["startBeat"]) * ppq)))
        dur_ticks = max(1, int(round(float(n["durationBeats"]) * ppq)))
        events.append((start_tick, 3, bytes([0x90, pitch, vel])))
        events.append((start_tick + dur_ticks, 2, bytes([0x80, pitch, 0])))

    events.sort(key=lambda e: (e[0], e[1]))
    track_buf = bytearray()
    last_tick = 0
    for tick, _, msg in events:
        track_buf.extend(_write_vlq(max(0, tick - last_tick)))
        track_buf.extend(msg)
        last_tick = tick
    track_buf.extend(b"\x00\xFF\x2F\x00")

    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq)
    track = b"MTrk" + struct.pack(">I", len(track_buf)) + bytes(track_buf)
    return header + track
