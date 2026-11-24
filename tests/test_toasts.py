"""Toast queue. Desktop mode must not spawn a notifier."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import toasts  # noqa: E402


def _settings(enabled: bool = True):
    return SimpleNamespace(notifications_enabled=enabled, language="es")


def test_desktop_queues_and_does_not_spawn(monkeypatch) -> None:
    monkeypatch.setenv("SPEECHSTUDIO_DESKTOP", "1")
    monkeypatch.setattr(toasts, "load_settings", lambda: _settings())
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        toasts.subprocess,
        "Popen",
        lambda args, **kwargs: spawned.append(list(args)),
    )
    toasts.drain()
    toasts.deliver("Speech Studio", "hola", 25)
    assert spawned == []
    assert toasts.drain() == [
        {"title": "Speech Studio", "message": "hola", "progress": 25}
    ]
    assert toasts.drain() == []


def test_disabled_notifications_drop_the_toast(monkeypatch) -> None:
    monkeypatch.setenv("SPEECHSTUDIO_DESKTOP", "1")
    monkeypatch.setattr(toasts, "load_settings", lambda: _settings(False))
    toasts.drain()
    toasts.deliver("Speech Studio", "no", None)
    assert toasts.drain() == []


def test_headless_windows_does_not_spawn_powershell(monkeypatch) -> None:
    monkeypatch.delenv("SPEECHSTUDIO_DESKTOP", raising=False)
    monkeypatch.setattr(toasts.sys, "platform", "win32")
    monkeypatch.setattr(toasts, "load_settings", lambda: _settings())
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        toasts.subprocess,
        "Popen",
        lambda args, **kwargs: spawned.append(list(args)),
    )
    toasts.drain()
    toasts.deliver("Speech Studio", "modelo", 50)
    assert spawned == []
    assert toasts.drain() == [
        {"title": "Speech Studio", "message": "modelo", "progress": 50}
    ]


def test_headless_linux_names_speech_studio(monkeypatch) -> None:
    monkeypatch.delenv("SPEECHSTUDIO_DESKTOP", raising=False)
    monkeypatch.setattr(toasts.sys, "platform", "linux")
    monkeypatch.setattr(toasts, "load_settings", lambda: _settings())
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        toasts.subprocess,
        "Popen",
        lambda args, **kwargs: spawned.append(list(args)),
    )
    toasts.drain()
    toasts.deliver("Speech Studio", "listo", None)
    assert spawned == [["notify-send", "-a", "Speech Studio", "Speech Studio", "listo"]]
    assert toasts.drain() == [
        {"title": "Speech Studio", "message": "listo", "progress": None}
    ]
