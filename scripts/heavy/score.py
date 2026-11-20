"""Compose the shared harmonic chart, sixteenth-note parts and native YuE2 ABC."""

import argparse

from engine.paths import DATA, ROOT
from engine.session.render import write_json
from scripts.v4_study import run

BPM = 108
OUT = ROOT / "examples/v61"
SECTIONS = (
    ("Opening", "intro", "D5(add9) A7sus4>A7"),
    ("Groove A1", "verse", "Dm Bb C A7"),
    ("Groove A2", "verse", "Dm F Gm A7"),
    ("Development", "pre-chorus", "Gm Bb C A7(b9)"),
    ("Explosion A", "chorus", "D5 Bb5 C5 A5"),
    ("Explosion B", "chorus", "D5 F5 G5 A5"),
    ("Mechanical break", "interlude", "Dped Eb5 Gm A7"),
    ("Guitar solo A", "instrumental", "Dm Bb Gm A7"),
    ("Guitar solo B", "instrumental", "F C Gm A7(b9)"),
    ("Bass and drum bridge", "bridge", "D C Bb A"),
    ("Final expansion A", "chorus", "D5 Bb5 C5 A5"),
    ("Final expansion B", "chorus", "Dm Gm A7(b9) Dm"),
    ("Resolution", "outro", "Dm(add9) D5"),
)
ROOTS = {"D": 38, "Bb": 34, "C": 36, "A": 33, "F": 41, "G": 43, "Eb": 39}
SOLO = (
    [(0, 74, 3), (3, 77, 1), (4, 81, 8), (13, 77, 2)],
    [(0, 77, 4), (6, 74, 2), (8, 70, 6)],
    [(0, 79, 6), (7, 77, 1), (8, 74, 4), (13, 70, 2)],
    [(0, 76, 3), (4, 79, 2), (7, 82, 1), (8, 81, 4), (13, 73, 3)],
    [(0, 77, 2), (2, 81, 2), (4, 84, 7), (13, 81, 2)],
    [
        (0, 79, 2),
        (2, 84, 2),
        (4, 88, 4),
        (9, 86, 1),
        (10, 84, 1),
        (11, 83, 1),
        (12, 79, 3),
    ],
    [(0, 86, 6), (7, 82, 1), (8, 79, 1), (9, 82, 1), (10, 86, 2), (12, 89, 4)],
    [(0, 88, 3), (3, 86, 1), (4, 82, 3), (8, 81, 2), (10, 85, 4)],
)
STYLE = (
    "Instrumental heavy experimental alternative metal, D minor, 108 bpm, drop D guitars, tight palm muted low "
    "pedal riffs answering broken snare and kick accents, blasting open distorted power chords and grunge fuzz, "
    "clear articulate bass and hard live drums, two bars of feedback then syncopated riff, explosive thick band, "
    "short mechanical break, eight bars of soaring lead guitar over the full drum kit and bass, sustained bends "
    "and upper octave fast answers, four bars of bass and drums alone, final huge riff and ringing D ending; "
    "no singing, voices, spoken words or choir."
)


def root_name(symbol):
    return next(
        k for k in ("Bb", "Eb", "D", "G", "F", "A", "C") if symbol.startswith(k)
    )


def score():
    bars = []
    for section, native, changes in SECTIONS:
        for j, chord in enumerate(changes.split()):
            n = len(bars) + 1
            root = root_name(chord)
            bass = ROOTS[root]
            bridge = 35 <= n <= 38
            solo = 27 <= n <= 34
            power = "5" in chord or chord == "Dped"
            dominant = "A7" in chord
            big = 15 <= n <= 22 or 39 <= n <= 46
            accents = (
                ([0, 6, 10, 14] if j % 2 == 0 else [0, 3, 8, 11])
                if not big
                else ([0, 8, 11] if j % 2 == 0 else [0, 6, 10])
            )
            if n < 3:
                accents = [0, 10] if n == 1 else [0, 8, 14]
            if 23 <= n <= 26:
                accents = [[0, 10], [12], [2, 10], [0, 8, 13]][j]
            if n >= 47:
                accents = [0, 8] if n == 47 else [0]
            guitar = [] if bridge else accents
            if solo:
                melody = SOLO[n - 27]
            elif bridge:
                melody = [
                    (0, bass, 4),
                    (6, bass + 12, 2),
                    (9, bass + 7, 2),
                    (13, 37 if n == 38 else bass, 3),
                ]
            elif dominant:
                melody = [
                    (0, 69, 4),
                    (5, 67, 2),
                    (8, 70 if "b9" in chord else 76, 3),
                    (12, 73, 2),
                ]
                if n == 2:
                    melody = [(0, 74, 6), (8, 69, 2), (12, 73, 3)]
            elif n == 24:
                melody = [(0, 50, 3), (12, 51, 2), (14, 58, 1)]
            else:
                fifth = bass + 19
                melody = [(0, bass + 12, 3), (6, fifth, 2), (10, bass + 24, 3)]
                if not power and not big:
                    melody[-1] = (
                        10,
                        bass + 15 if chord.startswith(("Dm", "Gm")) else bass + 16,
                        4,
                    )
                if n == 1:
                    melody = [(0, 50, 6), (8, 64, 2), (12, 57, 2)]
                if n == 47:
                    melody = [(0, 62, 6), (7, 65, 2), (10, 64, 4)]
                if n == 48:
                    melody = [(0, 62, 12)]
            fill = {
                2: "snare pickup",
                10: "snare drag",
                14: "choked snare",
                18: "rack tom answer",
                22: "descending toms",
                26: "snare flam",
                30: "snare to tom",
                34: "toms then choke",
                37: "ghost and tom",
                38: "full tom run",
                42: "kick pickup",
                45: "dominant snare roll",
            }.get(n)
            active = ["drums", "bass"] if bridge else ["drums", "bass", "rhythm guitar"]
            if n == 1:
                active.remove("drums")
            if solo or n in (14, 26, 45, 46, 47):
                active += ["lead guitar"]
            fx = {
                1: ["scratch", "pipe"],
                14: ["stutter"],
                23: ["scratch"],
                24: ["pipe"],
                26: ["scratch"],
            }.get(n, [])
            active.extend(cue for cue in fx if cue in ("scratch", "pipe"))
            function = (
                "bass descent"
                if bridge
                else "V7(b9)"
                if "b9" in chord
                else "V7"
                if dominant
                else {
                    "D": "i",
                    "Bb": "bVI",
                    "C": "bVII",
                    "G": "iv",
                    "A": "V",
                    "F": "bIII",
                    "Eb": "bII accent",
                }[root]
            )
            bars.append(
                {
                    "bar": n,
                    "section": section,
                    "native_section": native,
                    "chord_symbols": chord,
                    "harmonic_functions": function,
                    "bass_root": ROOTS["D"] if n == 24 else bass,
                    "lead_motif": melody,
                    "active_instruments": active,
                    "instrument_roles": {
                        "guitar": "rest"
                        if bridge
                        else "lead and supporting stabs"
                        if solo
                        else "open fifths"
                        if big
                        else "choked riff",
                        "bass": "root, rests and connecting notes",
                        "drums": "half-time"
                        if bridge or 23 <= n <= 26
                        else "pickup"
                        if n <= 2
                        else "ring out"
                        if n >= 47
                        else "full-kit backbeat",
                    },
                    "drum_pattern_type": "pickup"
                    if n < 3
                    else "ring out"
                    if n >= 47
                    else "half-time"
                    if bridge or 23 <= n <= 26
                    else "open kit"
                    if big or solo
                    else "closed groove",
                    "rhythmic_accents": guitar,
                    "fills": fill,
                    "fx_cues": fx,
                    "transitions": {
                        14: "stop before explosion",
                        34: "full stop before duo",
                        38: "fill into re-entry",
                        48: "D5 ring",
                    }.get(n),
                }
            )
    return {
        "key": "D minor",
        "scale": "D natural minor; C# on A7",
        "bpm": BPM,
        "time_signature": "4/4",
        "sections": [x[0] for x in SECTIONS],
        "bars": bars,
    }


def abc(plan):
    lines = [
        "X:1",
        "T:",
        "M:4/4",
        "L:1/16",
        "Q:1/4=108",
        'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
        'V: Ins clef=treble name="Ins Melody" snm="Inst."',
        "K:Dm",
    ]
    previous = None
    for b in plan["bars"]:
        if previous != b["native_section"]:
            lines.append("% " + b["native_section"])
            previous = b["native_section"]
        chord = b["chord_symbols"]
        # Native YuE2 has no power-chord quality. Leave its chord field blank and spell the fifths in Ins.
        if "5" in chord or chord == "Dped" or 35 <= b["bar"] <= 38:
            harmony = "Z"
        elif chord == "A7sus4>A7":
            harmony = '"A7sus4"z8"A7"z8'
        else:
            harmony = '"' + chord.split("(")[0] + '"z16'
        body = []

        def token(name, length, body=body):
            for d in (16, 12, 8, 6, 4, 3, 2, 1):
                if length >= d:
                    body.append(name + (str(d) if d > 1 else ""))
                    length -= d
                    if length and name != "z":
                        body.append("-")

        pos = 0
        for start, midi, length in b["lead_motif"]:
            token("z", start - pos)
            name = (
                "=C",
                "^C",
                "=D",
                "_E",
                "=E",
                "=F",
                "^F",
                "=G",
                "^G",
                "=A",
                "_B",
                "=B",
            )[midi % 12]
            octv = midi // 12 - 5
            if octv > 0:
                name = name.lower() + "'" * (octv - 1)
            elif octv < 0:
                name += "," * (-octv)
            token(name, length)
            pos = start + length
        token("z", 16 - pos)
        lines += ["V: Vocal", harmony + "|", "V: Ins", "".join(body) + "|"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--generate", action="store_true")
    cli.add_argument("--seed", type=int, default=81)
    cli.add_argument(
        "--instrumental-trio",
        action="store_true",
        help="Emphasize string articulations and kit in a second take",
    )
    args = cli.parse_args()
    plan = score()
    sheet = abc(plan)
    write_json(OUT / "plan.json", plan)
    (OUT / "heavy.abc").write_text(sheet)
    if args.generate:
        run(
            "yue2",
            "iron-return",
            args.seed,
            {
                "style": (
                    "Instrumental guitar trio, instrumental math-metal record, all melodies played on steel electric guitar strings, "
                    "picked and bent strings, acoustic drum kit, electric bass, drop-D staccato palm-muted chugs, huge open fifths, "
                    "8 bars of lead guitar and full band in D minor at 108 bpm, four-bar bass and drum duet, "
                    "full kit reentry and a ringing low D chord. Entirely instrumental."
                    if args.instrumental_trio
                    else STYLE
                ),
                "lyrics": "",
                "duration": 110 if args.instrumental_trio else 116,
                "bpm": BPM,
            },
            score=sheet,
            output_root=DATA / "v61",
        )
