"""Data directory policy shared by desktop and headless entry points."""

import os
import sys
from pathlib import Path
from typing import Mapping


def resolve_data_dir(
    app_root: Path,
    *,
    platform: str = sys.platform,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environ = os.environ if environ is None else environ
    override = environ.get("SPEECHSTUDIO_DATA_DIR", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else app_root / path
    legacy = app_root / "data"
    if (app_root / ".git").exists() or (app_root / "portable.txt").is_file() or (legacy / "settings.json").is_file():
        return legacy
    home = Path.home() if home is None else home
    if platform == "win32":
        base = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return base / "Speech Studio"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Speech Studio"
    base = Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    if not base.is_absolute():
        base = home / ".local" / "share"
    return base / "speech-studio"
