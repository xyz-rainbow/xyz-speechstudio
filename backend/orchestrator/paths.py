"""Data / cache directory policy shared by desktop and headless entry points.

Read-only app resources live next to the executable (backend/, runtime/).
User-writable data (settings, models, profiles, outputs) and cache are separate
unless portable mode or a legacy `data/` install is detected.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


USER_DATA_SUBDIRS = ("models", "profiles", "outputs", "tmp", "cache", "updates")


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


def resolve_cache_dir(
    app_root: Path,
    *,
    platform: str = sys.platform,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    data_dir: Path | None = None,
) -> Path:
    """Return the preferred cache directory (downloads scratch, HF caches, etc.)."""
    environ = os.environ if environ is None else environ
    override = environ.get("SPEECHSTUDIO_CACHE_DIR", "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else app_root / path
    data = data_dir or resolve_data_dir(app_root, platform=platform, environ=environ, home=home)
    # Portable / legacy installs keep cache under data/ for a single folder.
    if data == app_root / "data" or (app_root / "portable.txt").is_file():
        return data / "cache"
    home = Path.home() if home is None else home
    if platform == "win32":
        base = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return base / "Speech Studio" / "cache"
    if platform == "darwin":
        return home / "Library" / "Caches" / "Speech Studio"
    base = Path(environ.get("XDG_CACHE_HOME") or home / ".cache")
    if not base.is_absolute():
        base = home / ".cache"
    return base / "speech-studio"


def ensure_user_dirs(data_dir: Path, *, cache_dir: Path | None = None) -> list[Path]:
    """Create the standard writable layout. Safe with Unicode/spaces/brackets in paths."""
    created: list[Path] = []
    data_dir.mkdir(parents=True, exist_ok=True)
    created.append(data_dir)
    for name in USER_DATA_SUBDIRS:
        target = data_dir / name
        target.mkdir(parents=True, exist_ok=True)
        created.append(target)
    if cache_dir is not None and cache_dir != data_dir / "cache":
        cache_dir.mkdir(parents=True, exist_ok=True)
        created.append(cache_dir)
    return created


def migrate_legacy_app_data(app_root: Path, user_data: Path) -> dict[str, str]:
    """
    If an older Program Files install left models under <app>/data while the
    new policy points at the user profile, report what still lives next to the app.

    Does not move files automatically (avoids surprising large copies); the desktop
    can surface the report and copy on demand.
    """
    legacy = app_root / "data"
    report = {
        "legacy_data": str(legacy),
        "user_data": str(user_data),
        "action": "none",
    }
    if not legacy.is_dir() or legacy.resolve() == user_data.resolve():
        return report
    if (legacy / "settings.json").is_file() and not (user_data / "settings.json").is_file():
        report["action"] = "prefer_legacy_until_settings_migrated"
    elif any((legacy / name).exists() for name in ("models", "profiles", "outputs")):
        report["action"] = "legacy_artifacts_present"
    return report
