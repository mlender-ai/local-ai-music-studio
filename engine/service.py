"""Core production operations; frontends only translate transport schemas."""

import re
import uuid
from agent.command_parser import production_plan
from engine import store
from engine.paths import DATA, audio_path
from engine.rendering.audio import analyze, read_audio, write_audio, compare
from engine.dsp.chain import process
from engine.schema import Chain


def render(version_id: str, effects: list[dict], instruction: str = ""):
    source = store.get_version(version_id)
    chain = Chain(effects=effects)
    x, sr = read_audio(source["path"])
    y = process(x, sr, chain.model_dump()["effects"])
    target = DATA / "processed" / f"{uuid.uuid4().hex}.wav"
    write_audio(target, y, sr)
    comparison = compare(source["path"], target)
    version = store.add_version(
        target,
        dict(
            kind="dsp",
            instruction=instruction,
            effects=chain.model_dump()["effects"],
            analysis=analyze(target),
        ),
        parent=version_id,
    )
    return dict(version=version, comparison=comparison)


def produce(version_id: str, instruction: str):
    store.get_version(version_id)
    plan = production_plan(instruction)
    if plan["status"] != "ready":
        return dict(plan=plan, applied=False)
    return dict(
        plan=plan, applied=True, **render(version_id, plan["effects"], instruction)
    )


def compare_versions(original_id: str, modified_id: str):
    return compare(
        store.get_version(original_id)["path"], store.get_version(modified_id)["path"]
    )


def export(version_id: str, filename: str | None = None):
    version = store.get_version(version_id)
    name = filename or f"music-{version_id[:8]}-{uuid.uuid4().hex[:8]}.wav"
    if not re.fullmatch(r"[A-Za-z0-9가-힣_.-]{1,100}\.wav", name) or name.startswith(
        "."
    ):
        raise ValueError("Use a plain .wav filename without directories.")
    source = audio_path(version["path"])
    target = audio_path(DATA / "exports" / name, must_exist=False)
    with source.open("rb") as src, target.open("xb") as dest:
        import shutil

        shutil.copyfileobj(src, dest)
    return dict(path=str(target), version_id=version_id, analysis=analyze(target))


def import_audio(path: str):
    source = audio_path(path)
    analyze(source)
    snapshot = audio_path(
        DATA / "originals" / f"import-{uuid.uuid4().hex}.wav", must_exist=False
    )
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, snapshot.open("xb") as dest:
        import shutil

        shutil.copyfileobj(src, dest)
    return store.add_version(
        snapshot,
        dict(
            kind="import",
            analysis=analyze(snapshot),
            provenance="User supplied WAV; not claimed as AI generation",
        ),
    )
