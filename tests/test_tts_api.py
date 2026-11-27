import wave
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.orchestrator import crispasr, main, profiles
from backend.orchestrator.config import AppSettings


def _write_test_wav(path, frames: int = 2400) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * frames)


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


def test_build_qwen_profile_uses_crispasr_inline_without_worker(tmp_path, monkeypatch):
    pdir = tmp_path / "profiles"
    src_wav = tmp_path / "sample.wav"
    _write_test_wav(src_wav)

    monkeypatch.setattr(main, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", pdir / "profiles.json")
    monkeypatch.setattr(main, "fire_toast", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "load_settings", lambda: AppSettings(tts_device="cpu"))
    monkeypatch.setattr(
        main,
        "_active_tts_catalog_entry",
        lambda _s: SimpleNamespace(engine="qwen", active_runtime="crispasr", install_dir=None),
    )
    monkeypatch.setattr(crispasr, "supports_engine", lambda engine, **_kw: engine == "qwen")
    monkeypatch.setattr(
        main,
        "ensure_qwen_loaded",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("legacy qwen worker must not run")),
    )

    prof = profiles.create_profile(
        name="Carlos Test",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(src_wav),
        ref_text="Hola mundo",
    )
    updated = main.build_qwen_profile(prof)
    assert updated.ready is True
    assert (pdir / prof.id / "ref_24k.wav").is_file()


def test_create_qwen_profile_route_succeeds_with_crispasr_without_legacy_gguf_or_venv(tmp_path, monkeypatch):
    pdir = tmp_path / "profiles"
    src_wav = tmp_path / "voice.wav"
    _write_test_wav(src_wav)

    monkeypatch.setattr(main, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", pdir / "profiles.json")
    monkeypatch.setattr(main, "fire_toast", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "load_settings", lambda: AppSettings(tts_device="cpu"))
    monkeypatch.setattr(
        main,
        "_active_tts_catalog_entry",
        lambda _s: SimpleNamespace(engine="qwen", active_runtime="crispasr", install_dir=None),
    )
    monkeypatch.setattr(crispasr, "supports_engine", lambda engine, **_kw: engine == "qwen")
    monkeypatch.setattr(
        main,
        "resolve_qwen_gguf",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("legacy resolve_qwen_gguf must not run")),
    )
    monkeypatch.setattr(
        main,
        "ensure_qwen_loaded",
        lambda **_kw: (_ for _ in ()).throw(AssertionError("legacy qwen worker must not run")),
    )

    client = TestClient(main.app, client=("127.0.0.1", 50000))
    response = client.post(
        "/api/profiles",
        json={
            "name": "Crisp Voice",
            "language": "Spanish",
            "engine": "qwen",
            "ref_audio_path": str(src_wav),
            "ref_text": "Prueba corta",
            "build_voice": True,
        },
    )
    assert response.status_code == 200
    data = response.json()["profile"]
    assert data["engine"] == "qwen"
    assert data["ready"] is True


def test_build_qwen_profile_raises_503_when_python_runtime_missing(tmp_path, monkeypatch):
    pdir = tmp_path / "profiles"
    src_wav = tmp_path / "ref.wav"
    _write_test_wav(src_wav)

    monkeypatch.setattr(main, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", pdir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", pdir / "profiles.json")
    monkeypatch.setattr(main, "fire_toast", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "load_settings", lambda: AppSettings(tts_device="cpu"))
    monkeypatch.setattr(
        main,
        "_active_tts_catalog_entry",
        lambda _s: SimpleNamespace(engine="qwen", active_runtime="python", install_dir=None),
    )
    monkeypatch.setattr(
        main,
        "ensure_qwen_loaded",
        lambda **_kw: (_ for _ in ()).throw(FileNotFoundError("Python environment for 'qwen' not found")),
    )

    prof = profiles.create_profile(
        name="Python Missing",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(src_wav),
        ref_text="Hola",
    )
    with pytest.raises(HTTPException) as exc_info:
        main.build_qwen_profile(prof)
    assert exc_info.value.status_code == 503
