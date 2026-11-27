from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.orchestrator import main
from backend.orchestrator.config import AppSettings


@pytest.mark.parametrize("engine", ["espeak", "sapi5", "kitten"])
def test_public_speech_uses_builtin_voice_without_profile(engine, tmp_path, monkeypatch):
    settings = AppSettings(api_endpoint_enabled=True, tts_device="cpu")
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "DEFAULT_TMP_DIR", tmp_path)
    monkeypatch.setattr(main.profiles, "get_profile", lambda _: None)
    monkeypatch.setattr(main.profiles, "list_profiles", lambda: [])
    monkeypatch.setattr(main, "_active_tts_catalog_entry", lambda _: SimpleNamespace(engine=engine))
    calls = []

    def synthesize(**kwargs):
        calls.append(kwargs)
        kwargs["out_path"].write_bytes(b"generated-wave")
        return {}, "test"

    monkeypatch.setattr(main, "_run_tts", synthesize)
    client = TestClient(main.app, client=("127.0.0.1", 50000))
    response = client.post("/v1/audio/speech", json={"input": "Hola"})
    assert response.status_code == 200
    assert response.content == b"generated-wave"
    assert calls[0]["prof"] is None
    assert not list(tmp_path.iterdir())
