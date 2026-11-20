from scripts import v7_native


def test_instrumental_brief_dispatches_to_native_yue2_without_score(monkeypatch, tmp_path):
    request = {}

    def run(engine, genre, seed, brief, *, output_root):
        request.update(engine=engine, genre=genre, seed=seed, **brief)
        return output_root / "take"

    monkeypatch.setattr(v7_native, "DATA", tmp_path)
    monkeypatch.setattr(v7_native, "run", run)
    assert v7_native.generate("Grunge guitars", 42, 120) == tmp_path / "v7/take"
    assert request == {
        "engine": "yue2",
        "genre": "instrumental-rock",
        "seed": 42,
        "duration": 120,
        "style": "Instrumental guitar rock. Grunge guitars",
        "lyrics": "",
    }
