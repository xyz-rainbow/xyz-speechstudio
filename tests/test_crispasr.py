"""CrispASR bridge helpers (Fase 4) — device selector + cuda/cpu layout."""

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
    assert "--no-gpu" not in cmd


def test_build_tts_command_force_no_gpu(tmp_path: Path):
    binary = tmp_path / "crispasr.exe"
    binary.write_text("")
    out = tmp_path / "out.wav"
    cmd = crispasr.build_tts_command(
        binary=binary,
        engine="piper",
        text="Hi",
        out_path=out,
        force_no_gpu=True,
    )
    assert "--no-gpu" in cmd


def test_resolve_prefers_cuda_for_gpu(tmp_path: Path, monkeypatch):
    root = tmp_path
    cuda = root / "runtime" / "bin" / "cuda"
    cpu = root / "runtime" / "bin" / "cpu"
    cuda.mkdir(parents=True)
    cpu.mkdir(parents=True)
    (cuda / "crispasr.exe").write_text("")
    (cpu / "crispasr.exe").write_text("")
    monkeypatch.delenv("CRISPASR_BIN", raising=False)

    path, no_gpu = crispasr.resolve_crispasr_bin(root, device="gpu")
    assert path == cuda / "crispasr.exe"
    assert no_gpu is False

    path, no_gpu = crispasr.resolve_crispasr_bin(root, device="cpu")
    assert path == cpu / "crispasr.exe"
    assert no_gpu is False


def test_resolve_cpu_falls_back_to_cuda_with_no_gpu(tmp_path: Path, monkeypatch):
    root = tmp_path
    cuda = root / "runtime" / "bin" / "cuda"
    cuda.mkdir(parents=True)
    (cuda / "crispasr.exe").write_text("")
    monkeypatch.delenv("CRISPASR_BIN", raising=False)

    path, no_gpu = crispasr.resolve_crispasr_bin(root, device="cpu")
    assert path == cuda / "crispasr.exe"
    assert no_gpu is True


def test_supports_engine_requires_binary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        crispasr,
        "resolve_crispasr_bin",
        lambda app_root=None, device="gpu": (None, False),
    )
    assert crispasr.supports_engine("piper") is False

    fake = tmp_path / "crispasr.exe"
    fake.write_text("")
    monkeypatch.setattr(
        crispasr,
        "resolve_crispasr_bin",
        lambda app_root=None, device="gpu": (fake, False),
    )
    assert crispasr.supports_engine("piper") is True
    assert crispasr.supports_engine("kokoro") is True
    assert crispasr.supports_engine("espeak") is False
    assert crispasr.supports_engine("f5-tts") is True
    assert crispasr.supports_engine("unknown-engine") is False
    assert crispasr.stt_backend_for_model("parakeet-tdt-0.6b-v3") == "parakeet"
    assert crispasr.stt_backend_for_model("moonshine-base") == "moonshine"
    assert crispasr.stt_backend_for_model("faster-whisper-base") is None


def test_synthesize_tts_uses_ascii_temp_for_non_ascii_output(monkeypatch, tmp_path: Path):
    import wave

    fake_bin = tmp_path / "crispasr.exe"
    fake_bin.write_text("")
    monkeypatch.setattr(
        crispasr,
        "resolve_crispasr_bin",
        lambda app_root=None, device="gpu": (fake_bin, False),
    )

    seen_out: list[str] = []

    def fake_run(*, cmd, **_kwargs):
        out_arg = Path(cmd[cmd.index("--tts-output") + 1])
        seen_out.append(str(out_arg))
        with wave.open(str(out_arg), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 100)

        return 0, "", ""

    monkeypatch.setattr(crispasr.server_manager, "run_cli_cancelable", fake_run)
    dest = tmp_path / "[🛠️]" / "out.wav"
    res = crispasr.synthesize_tts(engine="piper", text="Hola", out_path=dest)
    assert dest.is_file() and dest.stat().st_size > 44
    assert seen_out and seen_out[0].isascii()
    assert res["sr"] == 22050
