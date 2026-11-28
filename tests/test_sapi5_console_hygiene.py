from __future__ import annotations

import subprocess
import sys

from backend.orchestrator import sapi5_engine


def test_discover_voices_caches_empty_result(monkeypatch):
    monkeypatch.setattr(sapi5_engine, "is_available", lambda: True)
    monkeypatch.setattr(sapi5_engine, "_CACHED_VOICES", [])
    monkeypatch.setattr(sapi5_engine, "_CACHED_AT", 0.0)
    monkeypatch.setattr(sapi5_engine, "_CACHE_POPULATED", False)

    calls: list[str] = []

    def fake_run(exe: str, script: str, timeout_s: float = 60.0) -> str:
        calls.append(exe)
        return "[]"

    monkeypatch.setattr(sapi5_engine, "_run_ps_encoded", fake_run)
    monkeypatch.setattr(sapi5_engine, "_ps32_exe", lambda: None)

    assert sapi5_engine.discover_voices() == []
    assert len(calls) == 1
    assert sapi5_engine._CACHE_POPULATED is True

    # Subsequent poll within TTL must reuse empty cache without spawning PowerShell
    assert sapi5_engine.discover_voices() == []
    assert len(calls) == 1

    # Explicit refresh bypasses cache
    assert sapi5_engine.discover_voices(force_refresh=True) == []
    assert len(calls) == 2


def test_run_ps_encoded_hides_console_window(monkeypatch):
    captured: dict = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(sapi5_engine.subprocess, "run", fake_subprocess_run)

    out = sapi5_engine._run_ps_encoded("powershell.exe", "Write-Output '[]'", timeout_s=5.0)
    assert out == "[]"
    assert "-WindowStyle" in captured["cmd"]
    idx = captured["cmd"].index("-WindowStyle")
    assert captured["cmd"][idx + 1] == "Hidden"
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    if sys.platform == "win32":
        assert captured["kwargs"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if hasattr(subprocess, "STARTUPINFO"):
            si = captured["kwargs"].get("startupinfo")
            assert si is not None
            assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW
            assert si.wShowWindow == subprocess.SW_HIDE
