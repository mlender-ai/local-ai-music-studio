"""A twelve-bar boom bap quartet. Steps are sixteenths; decimals place the swing."""

from copy import deepcopy

from .harmony import plan_chart
from .mixer import MIX

SECTIONS = [
    ("Intro", 1, 2),
    ("Main Groove", 3, 6),
    ("Variation", 7, 10),
    ("Break", 11, 11),
    ("Return", 12, 12),
]
# Bass root, two chord colors, upper-register answer. No recorded loops.
PARTS = {
    "Fmaj9": (41, [57, 60, 64, 67], [52, 57, 60, 67], 76),
    "Bbmaj9": (34, [50, 57, 60, 65], [53, 57, 60, 62], 74),
    "Gm9": (43, [53, 58, 62, 69], [50, 53, 58, 69], 77),
    "C13": (36, [52, 58, 62, 69], [52, 57, 62, 70], 76),
    "Dm9": (38, [53, 57, 60, 64], [52, 57, 60, 65], 77),
    "Am7": (33, [55, 60, 64, 69], [52, 55, 60, 69], 76),
    "F6/9": (41, [53, 57, 62, 67], [50, 57, 60, 67], 74),
}


def mixer():
    m = deepcopy(MIX)
    m["levels"].update(
        kick=0.51, snare=0.81, hat=1.48, openhat=1.15, bass=0.70, keys=0.12, guitar=0.38
    )
    m["keys"].update(pan=0.28, send=0.095)
    m["keys"]["chain"][0].update(frequency=325, gain_db=-2)
    m["drums"].update(send=0.065)
    m["guitar"].update(pan=-0.36, send=0.055)
    m["drums"]["chain"][0].update(ratio=1.7, attack_ms=24)
    m["master"] = [m["master"][0], dict(m["master"][1], ratio=1.3)]
    m["host_master_gain_db"] = 3.5
    return m


def compose(plan, variant=False):
    chart = plan_chart(plan.harmony.progression, 12)
    if (
        plan.rhythm.meter != "4/4"
        or plan.vocal_mode != "instrumental"
        or any(s not in PARTS for s in chart)
    ):
        raise ValueError("Unsupported quartet chord, meter or vocal mode")
    events = []
    for bar, symbol in enumerate(chart, 1):
        root, low, high, reply = PARTS[symbol]

        def play(voice, step, notes, length, velocity, *, bar=bar):
            track = "drums" if voice in ("kick", "snare", "hat", "openhat") else voice
            events.append(
                {
                    "bar": bar,
                    "step": step,
                    "voice": voice,
                    "track": track,
                    "notes": notes,
                    "length": length,
                    "velocity": velocity,
                    "art": "normal",
                }
            )

        def hit(voice, step, velocity):
            play(
                voice, step, [0], 1.9 if voice in ("snare", "kick") else 1.15, velocity
            )

        if bar in (1, 2, 12):
            # Recognizable three-note descent, then a delayed chord response.
            play("keys", 0, [low[0] + 12], 1.8, 91)
            play("keys", 2.36, [low[-1]], 1.18, 68)
            play("keys", 4.14, [low[-2]], 3.1, 82)
            play("keys", 9.15, low, 5.4, 78)
            if bar == 1:
                hit("hat", 14.34, 55)
                continue
            if bar == 2:
                for step, v in [(8, 57), (10.37, 45), (14.37, 63)]:
                    hit("hat", step, v)
                for step, v in [(12.09, 62), (15.13, 38)]:
                    hit("snare", step, v)
                continue
        if bar == 11:
            play("keys", 0.10, high, 4.4, 79)
            hit("kick", 0, 90)
            hit("snare", 14.3, 47)
            continue
        variation = 7 <= bar <= 10
        for step in (
            ((0, 6.32, 10.3) if bar % 2 else (0, 7.14, 9.06))
            if bar != 12
            else (0, 7.14)
        ):
            hit("kick", step, 110 if step == 0 else 87)
        for step in (4.12, 12.12) if bar != 12 else (4.12,):
            hit("snare", step, 104 if step < 8 else 111)
        for i in range(8 if bar != 12 else 5):
            if bar in (5, 9) and i == 5:
                continue
            hit(
                "openhat" if bar in (6, 10) and i == 7 else "hat",
                2 * i + (0.36 if i % 2 else 0),
                [82, 54, 73, 62][i % 4] + bar % 3,
            )
        if variation or variant:
            hit("snare", 10.54 if bar % 2 else 3.24, 37 + bar % 5)
        if bar in (6, 10):
            hit("snare", 15.21, 53)
        bassline = (
            [(0, 0, 3), (5.35, 7, 1.3), (8.12, 12, 2.2), (13.2, 7, 1)]
            if bar % 2
            else [(0.32, 0, 4.5), (6.4, 7, 0.95), (10.35, 0, 2.6)]
        )
        if variation:
            bassline = (
                [(0.12, 0, 2.3), (3.3, 12, 0.8), (6.34, 7, 2), (11.1, 0, 2.1)]
                if bar % 2
                else [(0, 0, 3.8), (6.34, 12, 1.1), (9, 7, 1.4), (12.34, 0, 1.8)]
            )
        if bar == 12:
            bassline = [(0, 0, 4.2), (6.32, 7, 1.35), (9.1, 0, 5.5)]
        for step, interval, length in bassline:
            play("bass", step, [root + interval], length, 98 if step < 1 else 78)
        if bar in (4, 6, 8):
            play("bass", 15.15, [PARTS[chart[bar]][0] - 1], 0.66, 64)
        if bar != 12:
            shape = high if variation else low
            play(
                "keys",
                0.24 if bar % 2 else 2.38,
                shape,
                3.1 if variation else 4.1,
                76 + bar % 6,
            )
            play(
                "keys",
                8.24 if bar % 2 else 9.12,
                shape[1:] if variation else shape,
                2.6,
                69 + bar % 5,
            )
            if bar in (3, 5, 8, 10):
                play("guitar", 13.15, [reply], 1.05, 80)
                if bar in (5, 8):
                    play("guitar", 15, [reply - 12], 0.67, 69)
    return events
