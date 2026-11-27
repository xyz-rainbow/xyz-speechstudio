"""Release parsing and per-platform installer selection. No network."""

from __future__ import annotations

import sys
import hashlib
from contextlib import contextmanager
from pathlib import Path
import httpx
import pytest
from backend.orchestrator import updates

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator.updates import (  # noqa: E402
    asset_url_allowed,
    parse_release,
    pick_asset,
    release_page_allowed,
    summarize,
    version_is_newer,
)

PAYLOAD = {
    "tag_name": "v0.2.0",
    "published_at": "2026-11-24T10:11:31Z",
    "html_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.0",
    "body": "Notes",
    "assets": [
        {
            "name": "SpeechStudio_0.2.0_Setup.exe",
            "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/SpeechStudio_0.2.0_Setup.exe",
            "size": 100,
        },
        {
            "name": "SpeechStudio_0.2.0.dmg",
            "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/SpeechStudio_0.2.0.dmg",
            "size": 200,
        },
        {
            "name": "SpeechStudio_0.2.0.AppImage",
            "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/SpeechStudio_0.2.0.AppImage",
            "size": 300,
        },
        {
            "name": "SpeechStudio_0.2.0.deb",
            "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/SpeechStudio_0.2.0.deb",
            "size": 250,
        },
    ],
}


def test_same_version_is_not_an_update() -> None:
    assert version_is_newer("0.1.0", "0.1.0") is False
    assert version_is_newer("v0.1.0", "0.1.0") is False


def test_newer_version() -> None:
    assert version_is_newer("0.2.0", "0.1.0") is True
    assert version_is_newer("0.1.0-rc.1", "0.1.0") is False


def test_each_desktop_gets_its_own_installer() -> None:
    release = parse_release(PAYLOAD)
    assert pick_asset(release.assets, "win32").name.endswith("_Setup.exe")
    assert pick_asset(release.assets, "darwin").name.endswith(".dmg")
    assert pick_asset(release.assets, "linux").name.endswith(".AppImage")


def test_missing_platform_asset_is_reported() -> None:
    release = parse_release(
        {
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.0",
            "assets": [PAYLOAD["assets"][0]],
        }
    )
    linux = summarize(release, "0.1.0", "linux")
    windows = summarize(release, "0.1.0", "win32")
    assert linux["update_available"] is True
    assert linux["asset"] is None
    assert windows["asset"]["name"].endswith(".exe")


def test_urls_stay_on_this_repo() -> None:
    assert release_page_allowed(
        "https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.0"
    )
    assert not release_page_allowed("https://example.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.0")
    assert asset_url_allowed(
        "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/SpeechStudio_0.2.0_Setup.exe"
    )
    assert asset_url_allowed("https://objects.githubusercontent.com/github-production-release-asset-1/a")
    assert not asset_url_allowed("https://evil.example/SpeechStudio_Setup.exe")


def test_project_versions_stay_in_sync() -> None:
    from scripts.sync_version import read_tauri_version, sync_all

    errors = sync_all(read_tauri_version(), check_only=True)
    assert errors == []


def test_installer_limit_accepts_published_release():
    assert updates.MAX_ASSET_BYTES > 634_503_325


def test_architecture_selection_rejects_other_cpu():
    def asset(name):
        return updates.ReleaseAsset(name, "https://github.com/test", 1)
    assets = [asset("SpeechStudio_arm64_Setup.exe"), asset("SpeechStudio_x64_Setup.exe")]
    assert pick_asset(assets, "win32", "AMD64").name == "SpeechStudio_x64_Setup.exe"
    assert pick_asset(assets, "win32", "aarch64").name == "SpeechStudio_arm64_Setup.exe"
    assert pick_asset(assets[:1], "win32", "x86_64") is None


@pytest.mark.parametrize("failure", [None, "size-mismatch", "digest-mismatch", "too-large"])
def test_download_checks_integrity_before_publishing(tmp_path, monkeypatch, failure):
    data = b"installer-content"
    digest = hashlib.sha256(data).hexdigest()
    asset = updates.ReleaseAsset(
        "SpeechStudio_Setup.exe",
        "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v1/SpeechStudio_Setup.exe",
        len(data) + (1 if failure == "size-mismatch" else 0),
        "sha256:" + ("0" * 64 if failure == "digest-mismatch" else digest),
    )
    monkeypatch.setattr(updates, "tempfile_dir", lambda: str(tmp_path))
    if failure == "too-large":
        monkeypatch.setattr(updates, "MAX_ASSET_BYTES", len(data) - 1)

    @contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(200, content=data, request=httpx.Request("GET", asset.url))

    monkeypatch.setattr(updates.httpx, "stream", stream)
    if failure:
        with pytest.raises(updates.UpdateError) as error:
            updates._download(asset)
        assert error.value.code == failure
        assert not list(tmp_path.rglob("*.exe"))
        assert not list(tmp_path.rglob("*.part"))
    else:
        result = updates._download(asset)
        assert result.read_bytes() == data


def test_windows_msi_is_launched_with_windows_installer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(updates.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    path = tmp_path / "SpeechStudio.msi"
    updates._launch(path, "win32")
    assert calls[0][0] == ["msiexec.exe", "/i", str(path)]
    assert calls[0][1]["creationflags"] & 0x01000000


def test_duplicate_install_request_is_rejected():
    updates._install_lock.acquire()
    try:
        with pytest.raises(updates.UpdateError) as error:
            updates.install_latest("0.2.0")
        assert error.value.code == "busy"
    finally:
        updates._install_lock.release()


def test_cancelled_download_removes_partial_file(tmp_path, monkeypatch):
    asset = updates.ReleaseAsset(
        "SpeechStudio_Setup.exe",
        "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v1/SpeechStudio_Setup.exe", 6,
    )
    monkeypatch.setattr(updates, "tempfile_dir", lambda: str(tmp_path))

    class Download:
        url = asset.url
        def raise_for_status(self):
            pass
        def iter_bytes(self):
            yield b"abc"
            assert updates.download_progress()["downloaded"] == 3
            updates.cancel_download()
            yield b"def"

    @contextmanager
    def stream(*args, **kwargs):
        yield Download()

    monkeypatch.setattr(updates.httpx, "stream", stream)
    updates._cancel_download.clear()
    try:
        with pytest.raises(updates.UpdateError) as error:
            updates._download(asset)
        assert error.value.code == "cancelled"
        assert not list(tmp_path.rglob("*.part"))
        assert not list(tmp_path.rglob("*.exe"))
    finally:
        updates._cancel_download.clear()
