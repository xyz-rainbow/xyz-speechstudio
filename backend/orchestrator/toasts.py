"""Desktop toasts in the language stored in settings. Linux and macOS paths are ready and not built yet."""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from .config import APP_ROOT, load_settings

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


def say(key: str, **kwargs: object) -> str:
    lang = load_settings().language
    table = _PHRASES.get(lang) or _PHRASES["en"]
    template = table.get(key) or _PHRASES["en"][key]
    return template.format(**kwargs)


def _quote_applescript(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def deliver(title: str, message: str, progress: Optional[int] = None) -> None:
    settings = load_settings()
    if not settings.notifications_enabled:
        return
    if sys.platform == "win32":
        script = APP_ROOT / "scripts" / "notify.ps1"
        if not script.exists():
            return
        shell = "pwsh"
        cmd = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Title",
            title,
            "-Message",
            message,
        ]
        if progress is not None:
            cmd.extend(["-Progress", str(max(0, min(100, progress)))])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(cmd, creationflags=flags)
        except OSError:
            cmd[0] = "powershell"
            try:
                subprocess.Popen(cmd, creationflags=flags)
            except OSError:
                return
        return
    text = message if progress is None else f"{message} ({max(0, min(100, progress))}%)"
    if sys.platform == "darwin":
        script = (
            f"display notification {_quote_applescript(text)} "
            f"with title {_quote_applescript(title)}"
        )
        try:
            subprocess.Popen(["osascript", "-e", script])
        except OSError:
            return
        return
    try:
        subprocess.Popen(["notify-send", title, text])
    except OSError:
        return
