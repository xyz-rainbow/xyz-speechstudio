"""Tests for Qwen3-TTS VoiceDesign (--instruct, preview, save profile, reuse in Qwen Base Q4)."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import crispasr, main, profiles, voice_design_routes  # noqa: E402
from backend.orchestrator.config import AppSettings  # noqa: E402


def _write_wav(path: Path, sr: int = 24000, seconds: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(sr * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x01\x00" * frames)


def test_build_tts_command_passes_instruct_flag(tmp_path: Path) -> None:
    bin_p = tmp_path / "crispasr.exe"
    bin_p.write_text("")
    model_p = tmp_path / "qwen3-tts-12hz-1.7b-voicedesign-q8_0.gguf"
    model_p.write_bytes(b"GGUF")
    cmd = crispasr.build_tts_command(
        binary=bin_p,
        engine="qwen",
        text="Hola mundo",
        out_path=tmp_path / "out.wav",
        language="Spanish",
        model_path=model_p,
        instruct="Voz grave y serena",
    )
    idx = cmd.index("--instruct")
    assert cmd[idx + 1] == "Voz grave y serena"


def test_voice_design_preview_save_and_reuse_with_qwen_base_q4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    models_dir = tmp_path / "models"
    prof_dir = tmp_path / "profiles"
    tmp_dir = tmp_path / "tmp"

    monkeypatch.setattr(voice_design_routes.cfg, "DEFAULT_TMP_DIR", tmp_dir)
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(main, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(crispasr, "is_available", lambda *a, **kw: True)

    client = TestClient(main.app, client=("127.0.0.1", 50000))

    # Before VoiceDesign weights are installed -> status.ready is False & preview returns 409
    s0 = AppSettings(models_dir=str(models_dir), tts_device="cpu")
    monkeypatch.setattr(voice_design_routes.cfg, "load_settings", lambda: s0)
    st0 = client.get("/api/tts/voice-design/status").json()
    assert st0["installed"] is False
    r409 = client.post(
        "/api/tts/voice-design/preview",
        json={"instructions": "Calm narrator", "language": "Spanish", "sample_text": "Hola prueba."},
    )
    assert r409.status_code == 409

    # Install VoiceDesign GGUF + Qwen Base Q4 weights
    vd_dir = models_dir / "tts" / "qwen3-1.7b-voicedesign"
    vd_dir.mkdir(parents=True)
    vd_model = vd_dir / "qwen3-tts-12hz-1.7b-voicedesign-q8_0.gguf"
    vd_model.write_bytes(b"GGUF")

    qbase_dir = models_dir / "tts" / "qwen3-1.7b"
    qbase_dir.mkdir(parents=True)
    (qbase_dir / "qwen-talker-1.7b-base-Q4_K_M.gguf").write_bytes(b"GGUF")
    (qbase_dir / "qwen-tokenizer-12hz-Q4_K_M.gguf").write_bytes(b"GGUF")

    s1 = AppSettings(models_dir=str(models_dir), active_tts_model="qwen3-1.7b-base-Q4_K_M", tts_device="cpu")
    monkeypatch.setattr(voice_design_routes.cfg, "load_settings", lambda: s1)
    monkeypatch.setattr(main, "load_settings", lambda: s1)

    st1 = client.get("/api/tts/voice-design/status").json()
    assert st1["installed"] is True
    assert st1["ready"] is True

    calls: list[dict] = []

    def fake_vd_synth(**kwargs):
        calls.append(kwargs)
        _write_wav(Path(kwargs["out_path"]), sr=24000, seconds=1.2)
        return {"duration_s": 1.2, "sr": 24000, "elapsed_s": 0.4}

    monkeypatch.setattr(crispasr, "synthesize_tts", fake_vd_synth)

    prev = client.post(
        "/api/tts/voice-design/preview",
        json={
            "instructions": "Warm Spanish documentary narrator",
            "language": "Spanish",
            "sample_text": "Hola, esta es una referencia diseñada.",
        },
    )
    assert prev.status_code == 200
    pdata = prev.json()
    assert calls and calls[0]["instruct"] == "Warm Spanish documentary narrator"
    assert calls[0]["model_path"] == vd_model

    wav_resp = client.get(pdata["audio_url"])
    assert wav_resp.status_code == 200
    assert wav_resp.content[:4] == b"RIFF"

    saved = client.post(
        "/api/tts/voice-design/save",
        json={
            "preview_id": pdata["preview_id"],
            "name": "Narrador Custom",
            "language": "Spanish",
            "sample_text": "Hola, esta es una referencia diseñada.",
            "engine": "qwen",
        },
    )
    assert saved.status_code == 200
    prof_dict = saved.json()["profile"]
    assert prof_dict["engine"] == "qwen"
    assert prof_dict["ready"] is True
    assert prof_dict["ref_original_text"] == "Hola, esta es una referencia diseñada."
    assert Path(prof_dict["ref_audio_path"]).is_file()

    # Use saved VoiceDesign profile as reference for Qwen Base Q4 synthesis context
    text_out, _settings, prof_obj, lang_out = main._resolve_tts_context(
        main.SynthesizeRequest(
            text="Texto nuevo usando la voz diseñada.",
            profile_id=prof_dict["id"],
            language="Spanish",
        )
    )
    assert "Texto nuevo" in text_out
    assert prof_obj is not None
    assert prof_obj.id == prof_dict["id"]
    assert Path(prof_obj.ref_audio_path).is_file()
    assert lang_out == "Spanish"
