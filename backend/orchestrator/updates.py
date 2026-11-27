"""GitHub release check and platform installer launch.

Windows runs the Inno Setup .exe from the release. macOS opens a .dmg or
.pkg. Linux runs an AppImage, or hands a .deb/.rpm to the desktop opener.
The version check itself is the same on every desktop.
"""

from __future__ import annotations

import subprocess
import hashlib
import platform as host_platform
import re
import sys
import threading
import time
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

REPO = "xyz-rainbow/xyz-speechstudio"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_TTL_S = 6 * 60 * 60
MAX_ASSET_BYTES = 4 * 1024 * 1024 * 1024
_NOTES_LIMIT = 8000

_ALLOWED_PAGES = "github.com"
_DOWNLOAD_HOSTS = {
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
}


class UpdateError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class ReleaseAsset:
    name: str
    url: str
    size: int
    digest: Optional[str] = None


@dataclass
class ReleaseInfo:
    tag: str
    published_at: Optional[str]
    notes: str
    html_url: str
    assets: list[ReleaseAsset]


_lock = threading.Lock()
_install_lock = threading.Lock()
_progress_lock = threading.Lock()
_cancel_download = threading.Event()
_progress = {"phase": "idle", "downloaded": 0, "total": 0}


def download_progress() -> dict:
    with _progress_lock:
        return dict(_progress)


def cancel_download() -> dict:
    _cancel_download.set()
    return {"cancel_requested": True}


def _set_progress(phase: str, downloaded: int = 0, total: int = 0) -> None:
    with _progress_lock:
        _progress.update(phase=phase, downloaded=downloaded, total=total)
_cache: dict[str, object] = {"fetched_at": 0.0, "release": None}


def version_key(raw: str) -> tuple[int, int, int, int]:
    text = (raw or "").strip()
    if text[:1] in {"v", "V"}:
        text = text[1:]
    main, _, pre = text.partition("-")
    parts: list[int] = []
    for piece in main.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits or "0"))
    while len(parts) < 3:
        parts.append(0)
    # A final release sorts after a pre-release of the same numbers.
    return (parts[0], parts[1], parts[2], 1 if not pre else 0)


def version_is_newer(latest: str, current: str) -> bool:
    if not latest.strip():
        return False
    return version_key(latest) > version_key(current)


def asset_rank(name: str, platform: str) -> Optional[int]:
    lowered = name.lower()
    if platform == "win32":
        if lowered.endswith(".exe") and "setup" in lowered:
            return 0
        if lowered.endswith(".msi"):
            return 1
        if lowered.endswith(".exe"):
            return 2
        return None
    if platform == "darwin":
        if lowered.endswith(".dmg"):
            return 0
        if lowered.endswith(".pkg"):
            return 1
        return None
    if platform == "linux":
        if lowered.endswith(".appimage"):
            return 0
        if lowered.endswith(".deb"):
            return 1
        if lowered.endswith(".rpm"):
            return 2
        return None
    return None


def pick_asset(assets: list[ReleaseAsset], platform: str, architecture: Optional[str] = None) -> Optional[ReleaseAsset]:
    architecture = (architecture or host_platform.machine()).lower()
    aliases = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}
    architecture = aliases.get(architecture, architecture)
    compatible = []
    for asset in assets:
        labels = set(re.findall(r"(?<![a-z0-9])(x86_64|amd64|x64|aarch64|arm64|i686|x86)(?![a-z0-9])", asset.name.lower()))
        architectures = {aliases.get(label, label) for label in labels}
        if not architectures or architecture in architectures:
            compatible.append(asset)
    ranked = [(asset_rank(asset.name, platform), asset) for asset in compatible]
    choices = [(rank, asset) for rank, asset in ranked if rank is not None]
    if not choices:
        return None
    choices.sort(key=lambda item: item[0])
    return choices[0][1]


def safe_asset_name(name: str) -> str:
    base = Path(name).name
    if not base or base in {".", ".."} or any(ch in base for ch in ("/", "\\", "\x00")):
        raise UpdateError("bad-name")
    return base


def release_page_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != _ALLOWED_PAGES:
        return False
    return parsed.path.startswith(f"/{REPO}/releases/")


def asset_url_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.lower()
    if host == "github.com":
        return parsed.path.startswith(f"/{REPO}/releases/download/")
    return host in _DOWNLOAD_HOSTS


def parse_release(payload: dict) -> ReleaseInfo:
    assets: list[ReleaseAsset] = []
    for row in payload.get("assets") or []:
        name = str(row.get("name") or "")
        url = str(row.get("browser_download_url") or "")
        if not name or not url:
            continue
        try:
            size = int(row.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        assets.append(ReleaseAsset(name=name, url=url, size=size, digest=row.get("digest")))
    notes = str(payload.get("body") or "").strip()
    if len(notes) > _NOTES_LIMIT:
        notes = notes[:_NOTES_LIMIT].rstrip() + "…"
    published = payload.get("published_at")
    return ReleaseInfo(
        tag=str(payload.get("tag_name") or ""),
        published_at=str(published) if published else None,
        notes=notes,
        html_url=str(payload.get("html_url") or ""),
        assets=assets,
    )


def summarize(release: ReleaseInfo, current: str, platform: str) -> dict:
    latest = release.tag[1:] if release.tag[:1] in {"v", "V"} else release.tag
    chosen = pick_asset(release.assets, platform)
    asset = None
    if chosen is not None:
        asset = {"name": chosen.name, "size": chosen.size}
    return {
        "current": current,
        "latest": latest,
        "tag": release.tag,
        "published_at": release.published_at,
        "notes": release.notes,
        "html_url": release.html_url,
        "update_available": version_is_newer(latest, current),
        "platform": platform,
        "asset": asset,
    }


def _fetch_release() -> ReleaseInfo:
    try:
        response = httpx.get(
            API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "speech-studio",
            },
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpdateError("github") from exc
    if not isinstance(payload, dict):
        raise UpdateError("github")
    return parse_release(payload)


def load_release(force: bool = False) -> ReleaseInfo:
    now = time.monotonic()
    with _lock:
        cached = _cache.get("release")
        fetched_at = float(_cache.get("fetched_at") or 0.0)
        if not force and isinstance(cached, ReleaseInfo) and (now - fetched_at) < CACHE_TTL_S:
            return cached
    release = _fetch_release()
    with _lock:
        _cache["release"] = release
        _cache["fetched_at"] = time.monotonic()
    return release


def check_latest(current: str, force: bool = False, platform: Optional[str] = None) -> dict:
    release = load_release(force=force)
    return summarize(release, current.strip(), platform or sys.platform)


def _open_url(url: str) -> None:
    if not release_page_allowed(url):
        raise UpdateError("bad-url")
    if sys.platform == "win32":
        subprocess.Popen(  # noqa: S603
            ["cmd", "/c", "start", "", url],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", url], start_new_session=True)  # noqa: S603
        return
    subprocess.Popen(["xdg-open", url], start_new_session=True)  # noqa: S603


def open_release_page(current: str) -> str:
    info = check_latest(current or "0.0.0", force=False)
    url = str(info.get("html_url") or "")
    if not url:
        raise UpdateError("github")
    _open_url(url)
    return url


def _download(asset: ReleaseAsset) -> Path:
    if not asset_url_allowed(asset.url):
        raise UpdateError("bad-url")
    name = safe_asset_name(asset.name)
    if asset.size > MAX_ASSET_BYTES:
        raise UpdateError("too-large")
    expected_digest = None
    if asset.digest:
        if not isinstance(asset.digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset.digest):
            raise UpdateError("bad-digest")
        expected_digest = asset.digest.split(":", 1)[1].lower()
    cache_dir = Path(tempfile_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest_dir = Path(tempfile.mkdtemp(prefix="download-", dir=cache_dir))
    dest = dest_dir / name
    partial = dest.with_suffix(dest.suffix + ".part")
    written = 0
    digest = hashlib.sha256()
    _set_progress("downloading", 0, asset.size)
    try:
        with httpx.stream(
            "GET",
            asset.url,
            headers={"User-Agent": "speech-studio", "Accept": "application/octet-stream"},
            timeout=180.0,
            follow_redirects=True,
        ) as response:
            if not asset_url_allowed(str(response.url)):
                raise UpdateError("bad-url")
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if _cancel_download.is_set():
                        raise UpdateError("cancelled")
                    written += len(chunk)
                    if written > MAX_ASSET_BYTES:
                        raise UpdateError("too-large")
                    handle.write(chunk)
                    digest.update(chunk)
                    _set_progress("downloading", written, asset.size)
        if _cancel_download.is_set():
            raise UpdateError("cancelled")
        _set_progress("verifying", written, asset.size)
        if written == 0 or (asset.size > 0 and written != asset.size):
            raise UpdateError("size-mismatch")
        if expected_digest and digest.hexdigest() != expected_digest:
            raise UpdateError("digest-mismatch")
        partial.replace(dest)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("github") from exc
    return dest


def tempfile_dir() -> str:
    import tempfile

    return str(Path(tempfile.gettempdir()) / "speech-studio-updates")


def _launch(path: Path, platform: str) -> None:
    if platform == "win32":
        detached = 0x00000008  # DETACHED_PROCESS
        new_group = 0x00000200  # CREATE_NEW_PROCESS_GROUP
        breakaway = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
        subprocess.Popen(  # noqa: S603
            ["msiexec.exe", "/i", str(path)] if path.suffix.lower() == ".msi" else [str(path)],
            close_fds=True,
            creationflags=detached | new_group | breakaway,
        )
        return
    if platform == "darwin":
        subprocess.Popen(["open", str(path)], start_new_session=True)  # noqa: S603
        return
    if path.suffix.lower() == ".appimage":
        path.chmod(path.stat().st_mode | 0o755)
        subprocess.Popen([str(path)], start_new_session=True)  # noqa: S603
        return
    subprocess.Popen(["xdg-open", str(path)], start_new_session=True)  # noqa: S603


def install_latest(current: str, platform: Optional[str] = None) -> dict:
    if not _install_lock.acquire(blocking=False):
        raise UpdateError("busy")
    try:
        _cancel_download.clear()
        return _install_latest(current, platform)
    except Exception:
        progress = download_progress()
        _set_progress("failed", progress["downloaded"], progress["total"])
        raise
    finally:
        _install_lock.release()


def _install_latest(current: str, platform: Optional[str] = None) -> dict:
    plat = platform or sys.platform
    release = load_release(force=False)
    summary = summarize(release, current.strip(), plat)
    if not summary["update_available"]:
        raise UpdateError("already-current")
    chosen = pick_asset(release.assets, plat)
    if chosen is None:
        raise UpdateError("no-asset")
    path = _download(chosen)
    if _cancel_download.is_set():
        raise UpdateError("cancelled")
    _launch(path, plat)
    _set_progress("launched", chosen.size, chosen.size)
    return {
        "launched": True,
        "asset_name": chosen.name,
        "platform": plat,
        "quits_app": plat == "win32",
    }
