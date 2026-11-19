"""Expose only the published session files. Register immutable versions transactionally."""

import json
import time
import uuid
from pathlib import Path
from engine.paths import DATA, audio_path
from engine.store import database
from .score import TRACKS

FILES = {
    "B": "dry-mix.wav",
    "C": "processed-mix.wav",
    "D": "variation-b.wav",
    "final": "final.wav",
}
FILES.update(
    {
        f"{mode}-{track}": f"{folder}/{track}.wav"
        for mode, folder in [("dry", "stems"), ("wet", "wet")]
        for track in TRACKS
    }
)


def folder():
    return DATA / "session-engine"


def register(root=None):
    root = root or folder()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        ids = {}
        for label, filename in FILES.items():
            path = str(audio_path(root / filename))
            old = db.execute("SELECT id FROM versions WHERE path=?", (path,)).fetchone()
            ident = old[0] if old else uuid.uuid4().hex
            if not old:
                meta = dict(
                    kind="session",
                    label=label,
                    source_type="sampled_instrument" if "-" in label else "session_mix",
                    session=str(root / "session.json"),
                )
                parent = (
                    ids.get("B")
                    if label == "C"
                    else ids.get("C")
                    if label in ("D", "final")
                    else None
                )
                db.execute(
                    "INSERT INTO versions VALUES(?,?,?,?,?)",
                    (ident, parent, path, time.time(), json.dumps(meta)),
                )
            ids[label] = ident
    return ids


def manifest():
    root = folder()
    if not (root / "session.json").is_file():
        raise ValueError("Render the soul session first.")
    spec = json.loads((root / "session.json").read_text())
    stats = json.loads((root / "qa/audio-analysis.json").read_text())
    with database() as db:
        rows = db.execute("SELECT id,path FROM versions").fetchall()
        registered = {r["path"]: r["id"] for r in rows}
        # Prefer the recorded V2 director comparison with this exact input plan.
        reference = db.execute(
            "SELECT result FROM jobs WHERE request_key=? AND state='succeeded'",
            ("producer-v1-soul-B",),
        ).fetchone()
    audio = {}
    for label, filename in FILES.items():
        path = root / filename
        audio[label] = dict(
            url="/session-audio/" + label,
            version_id=registered.get(str(path)),
            path=str(path),
            rms_dbfs=stats[filename]["rms_dbfs"],
        )
    if reference:
        v = json.loads(reference["result"])
        if (
            Path(v["path"]).is_file()
            and v["metadata"]["plan"].get("music_plan") == spec["music_plan"]
        ):
            audio["A"] = dict(
                url="/audio/" + v["id"],
                version_id=v["id"],
                path=v["path"],
                rms_dbfs=v["metadata"]["analysis"]["rms_dbfs"],
            )
    return dict(
        audio=audio,
        sections=spec["sections"],
        mixer=spec["mixer"],
        sources=spec["sources"],
        tracks=TRACKS,
        bpm=spec["music_plan"]["rhythm"]["bpm"],
        duration=spec["frames"] / spec["sample_rate"],
        score_file=str(root / "session.json"),
        quality="needs_listening",
    )
