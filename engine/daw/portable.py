"""Relativize the first RS5K waveform filename in projects produced by build.lua.

REAPER 7 stores this filename in the sampler's VST state even for a sample
inside the project. Preserve all other plugin bytes, and reject unknown layouts.
"""

import base64
import re
import struct


def make_portable(project, expected_zones):
    pattern = r'(      <VST "VSTi: ReaSamplOmatic5000 [^\n]+\n)((?:        [A-Za-z0-9+/=]+\n)+)'
    prefix = bytes(project.parent / "Samples") + b"/"

    def relative(match):
        blocks = [base64.b64decode(line, validate=True) for line in match[2].split()]
        header = bytearray(blocks[0])
        state = b"".join(blocks[1:-1])
        filename, nul, params = state.partition(b"\0")
        if (
            len(header) != 44
            or header[:4] != b"mosr"
            or struct.unpack_from("<I", header, 32)[0] != len(state)
            or not nul
            or not filename.startswith(prefix)
        ):
            raise ValueError("Unknown RS5K state or external sample path")
        sample = filename[len(prefix) :]
        if not re.fullmatch(rb"[a-f0-9]{40}\.(wav|flac)", sample):
            raise ValueError("Unexpected sample name")
        state = b"Samples/" + sample + nul + params
        struct.pack_into("<I", header, 32, len(state))
        blocks = [
            header,
            *(state[i : i + 96] for i in range(0, len(state), 96)),
            blocks[-1],
        ]
        return match[1] + "".join(
            "        " + base64.b64encode(b).decode() + "\n" for b in blocks
        )

    text, count = re.subn(pattern, relative, project.read_text())
    if count != expected_zones:
        raise ValueError(
            f"Expected {expected_zones} portable sample zones, found {count}"
        )
    project.write_text(text)
