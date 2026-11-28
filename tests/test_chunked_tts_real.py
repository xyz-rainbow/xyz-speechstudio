"""Phase 3 tests: long chunked TTS session ordering, WAV stitching, cancel, and real synthesis."""

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

from backend.orchestrator import espeak_engine, history, main  # noqa: E402
from backend.orchestrator.config import AppSettings  # noqa: E402


def _write_pcm_tone_wav(path: Path, *, sr: int = 24000, seconds: float = 0.6) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sr * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x10\x00" * frames)


def test_long_chunked_session_order_save_and_cancel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_dir = tmp_path / "tmp"
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True)
    monkeypatch.setattr(main, "DEFAULT_TMP_DIR", tmp_dir)
    monkeypatch.setattr(main, "PLAY_SESSION_DIR", tmp_dir / "play_session")
    monkeypatch.setattr(main, "resolved_outputs_dir", lambda _s: out_dir)
    monkeypatch.setattr(main, "fire_toast", lambda *a, **kw: None)
    monkeypatch.setattr(history, "HISTORY_JSON", out_dir / "history.json")
    monkeypatch.setattr(main, "load_settings", lambda: AppSettings(models_dir=str(tmp_path / "models"), outputs_dir=str(out_dir), active_tts_model="espeak-ng", tts_chunk_enabled=True, tts_chunk_max_chars=120))

    calls: list[int] = []

    def fake_run_tts(*, prof, text: str, lang: str, out_path: Path, **_kw):
        calls.append(len(calls))
        sec = 0.4 + 0.1 * len(calls)
        _write_pcm_tone_wav(out_path, sr=24000, seconds=sec)
        return {"duration_s": sec, "sr": 24000, "elapsed_s": 0.05, "rtf": 0.1}, "eSpeak NG"

    monkeypatch.setattr(main, "_run_tts", fake_run_tts)
    client = TestClient(main.app, client=("127.0.0.1", 50000))

    long_text = (
        "Primera frase larga para comprobar el reproductor por tramos en español sin cortar palabras y manteniendo la continuidad del texto. "
        "Segunda oración igualmente extensa diseñada específicamente para superar ciento veinte caracteres por bloque en la prueba automática. "
        "Tercera oración final también detallada para confirmar que el tercer fragmento se guarda y concatena en orden exacto."
    )
    start_resp = client.post(
        "/api/tts/session/start",
        json={"profile_id": "builtin", "text": long_text, "language": "Spanish", "voice": "es"},
    )
    assert start_resp.status_code == 200
    sdata = start_resp.json()
    sid = sdata["session_id"]
    chunks = sdata["chunks"]
    assert len(chunks) >= 3

    chunk_durs: list[float] = []
    for idx in range(len(chunks)):
        cr = client.post(f"/api/tts/session/{sid}/chunk/{idx}")
        assert cr.status_code == 200
        cdata = cr.json()
        assert cdata["index"] == idx
        chunk_durs.append(cdata["duration_s"])
        audio_res = client.get(cdata["audio_url"])
        assert audio_res.status_code == 200
        assert audio_res.content[:4] == b"RIFF"

    save_resp = client.post(f"/api/tts/session/{sid}/save")
    assert save_resp.status_code == 200
    rec = save_resp.json()["record"]
    stitched = Path(rec["saved_path"])
    assert stitched.is_file()
    with wave.open(str(stitched), "rb") as wf:
        stitched_dur = wf.getnframes() / float(wf.getframerate())
    assert stitched_dur == pytest.approx(sum(chunk_durs), abs=0.05)

    # Cancel endpoint + clear session clean up safely
    assert client.post("/api/tts/cancel").status_code == 200
    assert client.post("/api/tts/session/clear").status_code == 200


def test_real_local_espeak_multi_chunk_synthesis_if_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("espeakng_loader") is None:
        pytest.skip("espeakng_loader not installed in environment")
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True)
    tmp_dir = tmp_path / "tmp"
    monkeypatch.setattr(main, "DEFAULT_TMP_DIR", tmp_dir)
    monkeypatch.setattr(main, "PLAY_SESSION_DIR", tmp_dir / "play_session")
    monkeypatch.setattr(main, "resolved_outputs_dir", lambda _s: out_dir)
    monkeypatch.setattr(main, "fire_toast", lambda *a, **kw: None)
    monkeypatch.setattr(history, "HISTORY_JSON", out_dir / "history.json")
    monkeypatch.setattr(
        main,
        "load_settings",
        lambda: AppSettings(
            models_dir=str(tmp_path / "models"),
            outputs_dir=str(out_dir),
            active_tts_model="espeak-ng",
            tts_chunk_enabled=True,
            tts_chunk_max_chars=120,
        ),
    )

    client = TestClient(main.app, client=("127.0.0.1", 50000))
    long_text = (
        "This is the first real audio chunk synthesized on this machine with enough words to fill more than one hundred and twenty characters cleanly. "
        "This is the second real audio chunk queued immediately after the first one so the stitched output combines both speech waveforms."
    )
    start_resp = client.post(
        "/api/tts/session/start",
        json={"profile_id": "builtin", "text": long_text, "language": "English", "voice": "en"},
    )
    assert start_resp.status_code == 200
    sid = start_resp.json()["session_id"]
    chunks = start_resp.json()["chunks"]
    assert len(chunks) >= 2

    total_dur = 0.0
    for idx in range(len(chunks)):
        cr = client.post(f"/api/tts/session/{sid}/chunk/{idx}")
        assert cr.status_code == 200
        total_dur += cr.json()["duration_s"]

    save_resp = client.post(f"/api/tts/session/{sid}/save")
    assert save_resp.status_code == 200
    saved = Path(save_resp.json()["record"]["saved_path"])
    assert saved.is_file()
    with wave.open(str(saved), "rb") as wf:
        actual = wf.getnframes() / float(wf.getframerate())
    assert actual == pytest.approx(total_dur, abs=0.05)
