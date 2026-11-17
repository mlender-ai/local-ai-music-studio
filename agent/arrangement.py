"""Genre-specific arrangement targets. Text conditioning, not timed stem control."""

import re
from engine.schema import ArrangementPlan, ArrangementSection


def requested(text):
    return bool(
        re.search(
            r"인트로|처음에는|도입부|점진|잠시 후|\bintro\b|gradual|start with|begin with",
            text,
            re.I,
        )
    )


def draft_arrangement(text, duration, exclusions=()):
    lower = text.lower()
    if re.search(r"앰비언트|ambient", lower):
        palette = [
            ["soft evolving pad"],
            ["soft evolving pad", "low sustained drone"],
            ["soft evolving pad", "low sustained drone", "airy shimmering textures"],
        ]
        withheld = [
            ["drums", "bass pulse", "dense textures"],
            ["drums", "dense textures"],
            ["drums"],
        ]
        actions = [
            "Hint at the tonal motif.",
            "Slow harmonic swell.",
            "Widen the same texture without drums.",
        ]
    elif re.search(r"하우스|house", lower):
        palette = [
            ["filtered chord stab", "closed hi-hat"],
            [
                "filtered chord stab",
                "closed hi-hat",
                "four-on-the-floor kick",
                "synth bass",
            ],
            ["open chord stabs", "hi-hats", "kick", "synth bass", "clap", "warm keys"],
        ]
        withheld = [["kick", "bass", "full keys"], ["full keys"], []]
        actions = [
            "Hint at the main rhythm.",
            "Lock parts together.",
            "Open the filter for a clear lift.",
        ]
    elif re.search(r"펑키|펑크|디스코|funk|disco", lower):
        palette = [
            ["muted clean guitar cutting", "sixteenth-note hi-hat"],
            [
                "muted clean guitar cutting",
                "sixteenth-note hi-hat",
                "four-on-the-floor kick",
                "syncopated electric bass",
            ],
            [
                "muted clean guitar cutting",
                "sixteenth-note hi-hat",
                "four-on-the-floor kick",
                "syncopated electric bass",
                "snare and claps on 2 and 4",
                "brass stabs",
                "analog synth accents",
                "Rhodes piano",
            ],
        ]
        withheld = [
            ["kick", "bass", "brass", "synth", "keys"],
            ["brass", "synth", "keys"],
            [],
        ]
        actions = [
            "Sparse rhythmic hint.",
            "Lock into the same groove.",
            "Short interlocking phrases, clear energetic lift.",
        ]
    else:
        palette = [
            ["one quiet motif instrument"],
            ["same motif instrument", "soft supporting pulse"],
            ["same motif instrument", "supporting pulse", "harmonic layers"],
        ]
        withheld = [["full ensemble"], ["full ensemble"], []]
        actions = [
            "Begin sparsely with one motif.",
            "Introduce support gradually without a reset.",
            "Expand the motif into the main ensemble with a clear lift.",
        ]
    # Global user exclusions must not be reintroduced by a preset.
    banned = []
    for item in exclusions:
        item = item.lower()
        if any(t in item for t in ["drum", "percussion"]):
            banned += ["kick", "hat", "snare", "clap", "drum"]
        if "guitar" in item:
            banned += ["guitar"]
        if "bass" in item:
            banned += ["bass"]
        if "synth" in item:
            banned += ["synth"]
        if "keys" in item:
            banned += ["keys", "piano"]
    if banned:
        palette = [
            [x for x in group if not any(t in x.lower() for t in banned)]
            for group in palette
        ]
        if any(not group for group in palette):
            raise ValueError(
                "Arrangement exclusions remove all intro instruments; edit the Arrangement Plan."
            )
        actions = [
            "Sparse opening motif using only the listed instruments.",
            "Supporting parts join the existing motif without restarting.",
            "Expand the same motif and harmony into the main section.",
        ]
    edges = [
        0,
        round(duration * 4 / 30, 3),
        round(duration * 12 / 30, 3),
        round(duration * 28 / 30, 3),
        duration,
    ]
    sections = [
        ArrangementSection(
            name=name,
            start=edges[i],
            end=edges[i + 1],
            instruments=palette[i],
            withhold=withheld[i],
            development=actions[i],
        )
        for i, name in enumerate(["intro", "groove_entry", "main_groove"])
    ]
    sections.append(
        ArrangementSection(
            name="outro",
            start=edges[3],
            end=edges[4],
            instruments=palette[0],
            development="Ease back to the opening motif while keeping the pulse; no abrupt stop.",
        )
    )
    return ArrangementPlan(
        sections=sections,
        continuity="One tempo, tonal center and motif throughout; smooth entrances, no stops or restarts.",
    )


def arrangement_caption(plan):
    sentences = []
    previous = set()
    for s in plan.sections:
        active = set(s.instruments)
        added = [i for i in s.instruments if i not in previous]
        if s.name == "intro":
            cue = (
                "Only "
                + ", ".join(s.instruments)
                + ". Hold back "
                + ", ".join(s.withhold)
                + "."
            )
        elif s.name == "outro":
            cue = ""
        else:
            cue = "Keep the earlier motif; add " + ", ".join(added) + "."
        sentences.append(
            f"{s.start:g}–{s.end:g}s {s.name}: " + cue + " " + s.development
        )
        previous = active
    sentences.append(plan.continuity)
    return " ".join(sentences)
