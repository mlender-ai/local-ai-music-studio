import hashlib
import numpy as np
import pytest
from engine import paths, store, service
from engine.rendering.audio import write_audio, analyze


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "outputs"
    data.mkdir()
    for module in [paths, store, service]:
        monkeypatch.setattr(module, "DATA", data)
    return data


def test_paths_and_symlink_escape(sandbox, tmp_path):
    with pytest.raises(ValueError):
        paths.audio_path("../escape.wav", False)
    outside = tmp_path / "outside.wav"
    outside.touch()
    (sandbox / "evil.wav").symlink_to(outside)
    with pytest.raises(ValueError):
        paths.audio_path(sandbox / "evil.wav")


def test_versions_do_not_overwrite_and_restore_preserves_history(sandbox):
    x = 0.1 * np.sin(np.arange(48000) * 2 * np.pi * 100 / 48000)
    path = sandbox / "originals" / "source.wav"
    write_audio(path, np.column_stack([x, x * 0.5]), 48000)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    version = service.import_audio(str(path))
    modified = service.produce(version["id"], "베이스를 묵직하게")
    assert modified["comparison"]["changed_samples"] > 0
    assert modified["comparison"]["same_format"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    store.restore(version["id"])
    state = store.list_versions()
    assert state["current_version"] == version["id"] and len(state["versions"]) == 2
    export = service.export(modified["version"]["id"], "mix.wav")
    assert analyze(export["path"])["clipped_samples"] == 0
    with pytest.raises(FileExistsError):
        service.export(version["id"], "mix.wav")
    with pytest.raises(ValueError):
        service.export(version["id"], "../escape.wav")
    with pytest.raises(ValueError):
        write_audio(path, np.column_stack([x, x]), 48000)
