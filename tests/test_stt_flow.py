"""Phase 3 tests: STT compute_type switching, cancel endpoint, external endpoint errors, and real CrispASR STT."""

from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import crispasr, espeak_engine, external_providers, main  # noqa: E402
from backend.orchestrator.config import AppSettings, ExternalEndpointConfig  # noqa: E402


def _write_test_wav(path: Path, seconds: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = 16000
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * int(sr * seconds))


def test_stt_cancel_endpoint_and_compute_type_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models_dir = tmp_path / "models"
    fw_dir = models_dir / "stt" / "faster-whisper-base"
    fw_dir.mkdir(parents=True)
    (fw_dir / "model.bin").write_bytes(b"ct2")
    wav = tmp_path / "clip.wav"
    _write_test_wav(wav)

    client = TestClient(main.app, client=("127.0.0.1", 50000))

    # Cancel endpoint delegates cleanly
    monkeypatch.setattr(crispasr, "cancel_stt", lambda: True)
    c_resp = client.post("/api/stt/cancel")
    assert c_resp.status_code == 200
    assert c_resp.json() == {"cancelled": True}

    # Switching Faster-Whisper compute_type triggers reload via ensure_stt_loaded
    seen: list[str] = []

    class FakeHandle:
        def __init__(self, mid: str) -> None:
            self.port = 9999
            self.model_id = mid

    class FakeResp:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {"text": "hola mundo", "language": "es", "duration_s": 0.5, "elapsed_s": 0.1, "segments": []}

    class FakeClient:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def post(_url, json=None):
            return FakeResp()

    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    for ctype in ("int8", "float16"):
        mid = f"faster-whisper-base-{ctype}"
        s = AppSettings(models_dir=str(models_dir), active_stt_model=mid, stt_device="cpu")
        monkeypatch.setattr(main, "load_settings", lambda cfg=s: cfg)
        monkeypatch.setattr(main, "ensure_stt_loaded", lambda model_id=None, c=mid: seen.append(model_id or "") or FakeHandle(c))

        res = client.post("/api/stt/transcribe", json={"audio_path": str(wav), "language": "es", "model_id": mid})
        assert res.status_code == 200
        assert res.json()["model"] == mid
    assert seen == ["faster-whisper-base-int8", "faster-whisper-base-float16"]


def test_stt_external_endpoint_error_surfaces_502(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = tmp_path / "ext.wav"
    _write_test_wav(wav)
    ep = ExternalEndpointConfig(
        id="ep-stt-1",
        name="Remote Whisper",
        kind="stt",
        protocol="openai",
        base_url="http://127.0.0.1:9/v1",
        api_key="test",
        model="whisper-1",
        voice="",
    )
    s = AppSettings(
        stt_source="endpoint",
        active_stt_endpoint_id="ep-stt-1",
        external_endpoints=[ep],
    )
    monkeypatch.setattr(main, "load_settings", lambda: s)
    monkeypatch.setattr(external_providers, "transcribe_external", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("Connection refused")))

    client = TestClient(main.app, client=("127.0.0.1", 50000))
    resp = client.post("/api/stt/transcribe", json={"audio_path": str(wav), "language": "en"})
    assert resp.status_code == 502
    assert "Remote Whisper" in resp.json()["detail"]


def test_real_local_whisper_ggml_stt_if_available(tmp_path: Path) -> None:
    ggml_base = Path.home() / ".cache" / "crispasr" / "ggml-base.bin"
    if (
        not ggml_base.is_file()
        or not crispasr.is_available(device="cpu")
        or importlib.util.find_spec("espeakng_loader") is None
    ):
        pytest.skip("CrispASR + ggml-base.bin + espeakng_loader required for real local STT smoke check")

    wav = tmp_path / "hello_world.wav"
    espeak_engine.synthesize_tts(
        text="Hello world testing speech recognition",
        out_path=wav,
        language="English",
        voice="en",
    )
    # Use -m auto (model_dir=None) so CrispASR selects ggml-base.bin directly without scanning TTS GGUFs.
    res = crispasr.transcribe_stt(
        model_id="whisper-base",
        audio_path=wav,
        language="English",
        model_dir=None,
        device="cpu",
    )
    assert res["duration_s"] > 0.5
    assert isinstance(res["text"], str) and len(res["text"].strip()) > 0
