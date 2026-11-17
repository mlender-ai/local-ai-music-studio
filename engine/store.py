"""Transactional job and immutable version history, shared by every frontend."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from engine.paths import DATA, initialize


@contextmanager
def database():
    initialize()
    db = sqlite3.connect(DATA / "studio.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT, created REAL, updated REAL, pid INTEGER,
      request_key TEXT UNIQUE, request TEXT, result TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, parent TEXT, path TEXT UNIQUE, created REAL, metadata TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def add_version(path, metadata, parent=None):
    version_id = uuid.uuid4().hex
    with database() as db:
        db.execute(
            "INSERT INTO versions VALUES(?,?,?,?,?)",
            (
                version_id,
                parent,
                str(path),
                time.time(),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO settings VALUES('current_version', ?)",
            (version_id,),
        )
    return get_version(version_id)


def get_version(version_id):
    with database() as db:
        row = db.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown audio version.")
    result = dict(row)
    result["metadata"] = json.loads(result["metadata"])
    return result


def list_versions():
    with database() as db:
        rows = db.execute("SELECT * FROM versions ORDER BY created DESC").fetchall()
        current = db.execute(
            "SELECT value FROM settings WHERE key='current_version'"
        ).fetchone()
    return dict(
        current_version=current[0] if current else None,
        versions=[dict(r, metadata=json.loads(r["metadata"])) for r in rows],
    )


def restore(version_id):
    version = get_version(version_id)
    with database() as db:
        db.execute(
            "INSERT OR REPLACE INTO settings VALUES('current_version', ?)",
            (version_id,),
        )
    return version


def update_job(job_id, **fields):
    allowed = {"state", "pid", "result", "error"}
    if not fields.keys() <= allowed:
        raise ValueError("Invalid job update")
    fields["updated"] = time.time()
    with database() as db:
        db.execute(
            "UPDATE jobs SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
            (*fields.values(), job_id),
        )


def get_job(job_id):
    with database() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown job ID.")
    result = dict(row)
    for key in ["request", "result"]:
        result[key] = json.loads(result[key]) if result[key] else None
    return result
