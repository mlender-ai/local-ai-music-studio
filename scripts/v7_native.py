"""Generate a stereo YuE2 take from a production brief and optional native ABC."""

import argparse
import re
from pathlib import Path

from engine.paths import DATA
from scripts.v4_study import ScoreRejected, run

# Section-only lyrics are allowed by the official YuE2 instrumental workflow.
SECTIONS = frozenset(
    (
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "interlude",
        "bridge",
        "instrumental",
        "outro",
    )
)


def check_resting_voice(score: str):
    """Screen native ABC for a silent vocal lane and a sounding Ins lane."""
    lane = ""
    lanes = set()
    instrumental_notes = False
    for raw in score.splitlines():
        line = raw.strip()
        if line.startswith("%"):
            if line[1:].strip() not in SECTIONS:
                raise ScoreRejected(f"Unsupported section: {line}")
            continue
        if line.startswith("V:"):
            parts = line[2:].split(maxsplit=1)
            lane = parts[0] if parts else ""
            if lane not in {"Vocal", "Ins"}:
                raise ScoreRejected(f"Unsupported ABC voice: {lane}")
            lanes.add(lane)
            continue
        if re.match(r"^[wW]:", line):
            raise ScoreRejected("Sung text in ABC")
        if not line or re.match(r"^[XTMLQK]:", line):
            continue
        music = re.sub(r'"[^"]*"', "", line)
        if re.search(r"\[\s*[VwW]:", music):
            raise ScoreRejected("Inline voice or lyric change in ABC")
        if lane == "Vocal" and not re.fullmatch(r"(?:[zZ]\d*|[| \t])+", music):
            raise ScoreRejected(
                "Vocal ABC contains material other than rests and chords"
            )
        if lane == "Ins" and re.search(r"[A-Ga-g]", music):
            instrumental_notes = True
    if lanes != {"Vocal", "Ins"} or not instrumental_notes:
        raise ScoreRejected(
            "Score must contain Vocal and Ins lanes and an instrumental melody"
        )


def generate(
    style: str,
    seed: int,
    duration_cap: int,
    *,
    genre: str = "instrumental-rock",
    bpm: int | None = None,
    instrumental: bool = True,
    lyrics: str = "",
    cot: str = "full",
    optional_score: str | None = None,
    screen_score: bool = False,
):
    style = style.strip()
    if not style or not 1 <= duration_cap <= 120 or not 0 <= seed < 2**63:
        raise ValueError("Provide a brief, a 1–120 s duration cap and a 63-bit seed")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", genre):
        raise ValueError("Genre must be a lowercase hyphenated label")
    if cot not in {"full", "melody", "off"} or (
        (optional_score or screen_score) and cot == "off"
    ):
        raise ValueError("An ABC score requires full or melody CoT")
    if bpm is not None and not 30 <= bpm <= 300:
        raise ValueError("BPM must be between 30 and 300")
    if (
        instrumental
        and lyrics.strip()
        and any(
            line.strip() not in {f"[{section.title()}]" for section in SECTIONS}
            for line in lyrics.splitlines()
            if line.strip()
        )
    ):
        raise ValueError("Use empty lyrics or section markers for instrumentals")
    if screen_score and not instrumental:
        raise ValueError("The score gate applies to instrumental requests")
    if instrumental and optional_score is not None:
        check_resting_voice(optional_score)
    if instrumental and not re.search(r"\binstrumental\b", style, re.IGNORECASE):
        style = f"{style} Instrumental."
    brief = {
        "style": f"{bpm} BPM. {style}" if bpm is not None else style,
        "lyrics": lyrics,
        "duration": duration_cap,
        "instrumental": instrumental,
    }
    if bpm is not None:
        brief["bpm"] = bpm
    return run(
        "yue2",
        genre,
        seed,
        brief,
        score=optional_score,
        cot=cot,
        output_root=DATA / ("v7" if genre == "instrumental-rock" else "v71"),
        plan_gate=check_resting_voice if screen_score else None,
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("brief", type=Path, help="UTF-8 production brief")
    cli.add_argument("--genre", default="instrumental-rock")
    cli.add_argument("--bpm", type=int)
    cli.add_argument("--seed", type=int, required=True)
    cli.add_argument("--duration-cap", type=int, default=120)
    cli.add_argument("--cot", choices=["full", "melody", "off"], default="full")
    cli.add_argument("--score", type=Path)
    cli.add_argument(
        "--screen-score",
        action="store_true",
        help="Check YuE2's native plan before synthesis",
    )
    cli.add_argument("--lyrics-file", type=Path)
    cli.add_argument("--vocal", action="store_true")
    args = cli.parse_args()
    try:
        generate(
            args.brief.read_text(encoding="utf-8"),
            args.seed,
            args.duration_cap,
            genre=args.genre,
            bpm=args.bpm,
            instrumental=not args.vocal,
            cot=args.cot,
            lyrics=args.lyrics_file.read_text(encoding="utf-8")
            if args.lyrics_file
            else "",
            optional_score=args.score.read_text(encoding="utf-8")
            if args.score
            else None,
            screen_score=args.screen_score,
        )
    except ValueError as exc:
        cli.error(str(exc))


if __name__ == "__main__":
    main()
