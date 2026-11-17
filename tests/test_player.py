import numpy as np
from fastapi.testclient import TestClient
from engine import paths, store, service
from engine.rendering.audio import write_audio
from app.player.server import app


def test_local_player_range_audio_and_write_boundary(tmp_path, monkeypatch):
    data = tmp_path / "outputs"
    data.mkdir()
    for module in [paths, store, service]:
        monkeypatch.setattr(module, "DATA", data)
    x = 0.1 * np.sin(np.arange(48000) * 2 * np.pi * 100 / 48000)
    source = data / "input.wav"
    write_audio(source, np.column_stack([x, x]), 48000)
    version = service.import_audio(str(source))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/state").json()["versions"][0]["id"] == version["id"]
        audio = client.get("/audio/" + version["id"], headers={"Range": "bytes=0-43"})
        assert audio.status_code == 206 and len(audio.content) == 44
        assert audio.content[:4] == b"RIFF" and audio.content[8:12] == b"WAVE"
        payload = {"version_id": version["id"]}
        assert client.post("/api/restore", json=payload).status_code == 403
        assert (
            client.post(
                "/api/restore",
                json=payload,
                headers={"X-Studio-Request": "1", "Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/restore",
                json=payload,
                headers={"X-Studio-Request": "1", "Origin": "http://testserver"},
            ).status_code
            == 200
        )
        assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400
        assert client.get("/audio/unknown").status_code == 400
