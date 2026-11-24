"""Release parsing and per-platform installer selection. No network."""

from __future__ import annotations

import sys
from pathlib import Path

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
