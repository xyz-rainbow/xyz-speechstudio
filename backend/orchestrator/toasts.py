"""Desktop toasts in the language stored in settings.

The desktop shell drains the queue and shows them as Speech Studio.
A headless process (no SPEECHSTUDIO_DESKTOP) falls back to notify-send
or osascript. Windows headless does not spawn PowerShell, because that
brands the toast as PowerShell.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Optional

from .config import load_settings

_PHRASES = {
    "en": {
        "app": "Speech Studio",
        "profile_ready": "Voice profile '{name}' is ready",
        "wav_saved": "Audio saved ({speaker}, {seconds}s)",
        "download_progress": "Downloading {name} ({quant})",
        "download_ready": "{name} ({quant}) is ready",
        "download_failed": "Download failed: {name}",
    },
    "es": {
        "app": "Speech Studio",
        "profile_ready": "Perfil de voz '{name}' listo",
        "wav_saved": "Audio guardado ({speaker}, {seconds} s)",
        "download_progress": "Descargando {name} ({quant})",
        "download_ready": "{name} ({quant}) listo",
        "download_failed": "Falló la descarga: {name}",
    },
}

_lock = threading.Lock()
_queue: list[dict] = []


def say(key: str, **kwargs: object) -> str:
    lang = load_settings().language
    table = _PHRASES.get(lang) or _PHRASES["en"]
    template = table.get(key) or _PHRASES["en"][key]
    return template.format(**kwargs)


def drain() -> list[dict]:
    with _lock:
        items = list(_queue)
        _queue.clear()
        return items


def deliver(title: str, message: str, progress: Optional[int] = None) -> None:
    settings = load_settings()
    if not settings.notifications_enabled:
        return
    item = {
        "title": title,
        "message": message,
        "progress": None if progress is None else max(0, min(100, int(progress))),
    }
    with _lock:
        _queue.append(item)
        if len(_queue) > 20:
            del _queue[:-20]
    if os.environ.get("SPEECHSTUDIO_DESKTOP") == "1":
        return
    _deliver_headless(title, message, item["progress"])


def _quote_applescript(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _deliver_headless(title: str, message: str, progress: Optional[int]) -> None:
    text = message if progress is None else f"{message} ({progress}%)"
    try:
        if sys.platform == "darwin":
            script = (
                f"display notification {_quote_applescript(text)} "
                f"with title {_quote_applescript(title)}"
            )
            subprocess.Popen(["osascript", "-e", script])
            return
        if sys.platform.startswith("linux"):
            subprocess.Popen(["notify-send", "-a", "Speech Studio", title, text])
    except OSError:
        return
