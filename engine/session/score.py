"""A 14-bar soul chart. Times are sixteenth notes from each bar's downbeat."""

from engine.music_plan import MusicPlan
from .harmony import plan_chart

TRACKS = ("drums", "bass", "keys", "guitar")
SECTIONS = [
    ("Intro", 1, 2),
    ("Groove A", 3, 6),
    ("Groove B", 7, 10),
    ("Variation", 11, 12),
    ("Hook Return", 13, 14),
]
# Root MIDI number, two rootless/right-hand voicings. Bass supplies the root.
CHORDS = {
    "Dm9": (38, [53, 60, 64, 69], [53, 57, 60, 64]),
    "G13": (31, [53, 59, 64, 69], [53, 57, 59, 64]),
    "Cmaj9": (36, [52, 59, 62, 67], [55, 59, 62, 64]),
    "A7": (33, [55, 61, 64, 69], [55, 57, 61, 64]),
}
GUITAR_REPLY = {"Dm9": 77, "G13": 76, "Cmaj9": 74, "A7": 76}
CHART = [
    "Dm9",
    "A7",
    "Dm9",
    "G13",
    "Cmaj9",
    "A7",
    "Dm9",
    "G13",
    "Cmaj9",
    "A7",
    "Dm9",
    "A7",
    "G13",
    "Dm9",
]


def compose(plan: MusicPlan, variant=False):
    chart = plan_chart(plan.harmony.progression, 14)
    if (plan.harmony.key, plan.rhythm.meter, plan.vocal_mode) != (
        "D minor",
        "4/4",
        "instrumental",
    ) or any(c not in CHORDS for c in chart):
        raise ValueError("Unsupported harmony for the instrumental soul arrangement.")
    events = []
    for bar, chord in enumerate(chart, 1):
        root, v1, v2 = CHORDS[chord]
        late = 7 <= bar <= 12

        def add(track, step, voice, notes, velocity, length, art="normal"):
            events.append(
                dict(
                    track=track,
                    bar=bar,
                    step=step,
                    voice=voice,
                    notes=list(notes),
                    velocity=velocity,
                    length=length,
                    art=art,
                )
            )

        last = bar == 14
        if bar <= 2:
            for step, pitch in [
                (0, 69),
                (3, 72 if bar == 1 else 73),
                (6, 76),
                (10, 69),
            ]:
                if chord != ("Dm9" if bar == 1 else "A7"):
                    pitch = min(
                        (p for p in range(60, 81) if p % 12 in {n % 12 for n in v1}),
                        key=lambda p: abs(p - pitch),
                    )
                add("keys", step, "keys", [pitch], 82 if step == 0 else 65, 2.3)
            for step in [7, 12, 14, 15] if bar == 1 else [4, 10, 12, 13, 14, 15]:
                add("drums", step, "snare", [0], 43 + 3 * step, 0.85)
            add("drums", 2, "hat", [0], 58, 0.9)
            continue
        stop = 9 if bar == 11 else 10 if last else 16
        for step in range(0, stop, 4):
            add("drums", step, "kick", [0], 106 if step == 0 else 97, 3)
        for step in (4, 12):
            if step < stop:
                add("drums", step, "snare", [0], 105, 2.8)
        for step in range(stop):
            if step % 2 and (step + bar) % 4 != 0:
                continue
            if step == 6 and variant and bar % 2:
                continue
            voice = "openhat" if step == 14 and bar % 2 == 0 else "hat"
            add(
                "drums",
                step,
                voice,
                [0],
                [71, 41, 88, 49][step % 4],
                1.65 if voice == "openhat" else 0.78,
            )
        if stop == 16:
            add("drums", 9 if late else 3, "snare", [0], 39, 0.75)
            if bar in (6, 10, 12) or variant and bar % 2 == 0:
                for i, step in enumerate([13, 14.5, 15.25] if variant else [14, 15]):
                    add("drums", step, "snare", [0], 58 + i * 12, 0.65)
        pattern = [
            (0, 0, 2.9),
            (3, 12, 0.7),
            (6, 7, 1.4),
            (8, 0, 2.6),
            (11, 12, 0.8),
            (14, 7, 0.9),
        ]
        if late or variant and bar % 2:
            pattern = [
                (0, 0, 2),
                (2.5, 7, 0.8),
                (5, 12, 1.8),
                (8, 0, 2.4),
                (11, 7, 0.8),
                (13, 12, 1.3),
            ]
        for step, interval, length in pattern:
            if step < stop:
                add(
                    "bass",
                    step,
                    "bass",
                    [root + interval],
                    104 if step % 8 == 0 else 76,
                    length,
                    "mute" if length < 1 else "normal",
                )
        if stop == 16:
            nextroot = CHORDS[chart[bar % len(chart)]][0]
            add(
                "bass",
                15,
                "bass",
                [nextroot - 1],
                77,
                0.88,
                "slide" if variant or late else "passing",
            )
        keys = v2 if late else v1
        for step, length in [(0, 5), (9, 3.2)] if not late else [(2, 4.5), (10, 3.6)]:
            if step < stop and not (last and step == 9):
                pitches = [55, 62, 64, 69] if chord == "A7" and step < 5 else keys
                add("keys", step, "keys", pitches, 73 if step == 0 else 81, length)
        for i, step in enumerate(([2, 6, 11, 14] if not late else [1, 6, 9, 14])):
            if step >= stop or (bar % 3 == 0 and i == 1):
                continue
            step += 0.5 if variant and i == 2 else 0
            add(
                "guitar",
                step,
                "guitar",
                [GUITAR_REPLY[chord]],
                86 if i % 2 == 0 else 73,
                0.65 if i % 2 else 0.9,
                "down" if i % 2 == 0 else "up",
            )
            if i == 1:
                add("guitar", step + 1, "chuck", [0], 50, 0.5)
        if last:
            add("keys", 9, "keys", v1, 68, 5.6)
    return events
