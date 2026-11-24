"""CrispASR bridge helpers (Fase 4)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import crispasr  # noqa: E402


def test_language_code_maps_labels():
    assert crispasr.language_code("Spanish") == "es"
    assert crispasr.language_code("en") == "en"
    assert crispasr.language_code("FR") == "fr"


def test_backend_mapping():
    assert crispasr.backend_for_engine("piper") == "piper"
    assert crispasr.backend_for_engine("kokoro") == "kokoro"
    assert crispasr.backend_for_engine("f5-tts") == "f5-tts"
    assert crispasr.backend_for_engine("unknown") is None


def test_build_tts_command_uses_auto_when_no_gguf(tmp_path: Path):
    binary = tmp_path / "crispasr.exe"
    binary.write_text("")
    out = tmp_path / "out.wav"
    cmd = crispasr.build_tts_command(
        binary=binary,
        engine="piper",
        text="Hola",
        out_path=out,
        language="Spanish",
    )
    assert cmd[0] == str(binary)
    assert "--backend" in cmd and "piper" in cmd
    assert "-m" in cmd and "auto" in cmd
    assert "-l" in cmd and "es" in cmd
    assert "--tts" in cmd and "Hola" in cmd
    assert "--tts-output" in cmd and str(out) in cmd


def test_build_tts_command_prefers_gguf(tmp_path: Path):
    binary = tmp_path / "crispasr"
    binary.write_text("")
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"GGUF")
    out = tmp_path / "out.wav"
    cmd = crispasr.build_tts_command(
        binary=binary,
        engine="f5-tts",
        text="Hi",
        out_path=out,
        language="en",
        model_path=gguf,
    )
    assert str(gguf) in cmd


def test_supports_engine_requires_binary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(crispasr, "resolve_crispasr_bin", lambda app_root=None: None)
    assert crispasr.supports_engine("piper") is False

    fake = tmp_path / "crispasr.exe"
    fake.write_text("")
    monkeypatch.setattr(crispasr, "resolve_crispasr_bin", lambda app_root=None: fake)
    assert crispasr.supports_engine("piper") is True
    assert crispasr.supports_engine("f5-tts") is True
    assert crispasr.supports_engine("kokoro") is False
    gguf_dir = tmp_path / "voices"
    gguf_dir.mkdir()
    (gguf_dir / "voice.gguf").write_bytes(b"GGUF")
    assert crispasr.supports_engine("kokoro", model_dir=gguf_dir) is True
