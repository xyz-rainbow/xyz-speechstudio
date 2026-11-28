"""Release parsing and per-platform installer selection. No network."""

from __future__ import annotations

import hashlib
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import updates  # noqa: E402
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


def test_windows_update_never_launches_a_bare_application_exe() -> None:
    assets = [
        updates.ReleaseAsset(
            "speech-studio.exe",
            "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.0/speech-studio.exe",
            100,
        )
    ]
    assert pick_asset(assets, "win32", "x64") is None


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
        assert not list(tmp_path.glob("download-*"))
    finally:
        updates._cancel_download.clear()


def test_macos_intel_and_apple_silicon_selection() -> None:
    def asset(name: str) -> updates.ReleaseAsset:
        return updates.ReleaseAsset(name, f"https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/{name}", 10)

    assets = [
        asset("SpeechStudio_0.2.2_aarch64.dmg"),
        asset("SpeechStudio_0.2.2_x64.dmg"),
        asset("SpeechStudio_0.2.2_universal.dmg"),
    ]
    assert pick_asset(assets, "darwin", "arm64").name == "SpeechStudio_0.2.2_aarch64.dmg"
    assert pick_asset(assets, "darwin", "aarch64").name == "SpeechStudio_0.2.2_aarch64.dmg"
    assert pick_asset(assets, "darwin", "x86_64").name == "SpeechStudio_0.2.2_x64.dmg"
    assert pick_asset(assets, "darwin", "Intel").name == "SpeechStudio_0.2.2_x64.dmg"

    only_arm = [asset("SpeechStudio_0.2.2_aarch64.dmg")]
    assert pick_asset(only_arm, "darwin", "x86_64") is None
    only_intel = [asset("SpeechStudio_0.2.2_x64.dmg")]
    assert pick_asset(only_intel, "darwin", "arm64") is None
    with_universal = [asset("SpeechStudio_0.2.2_universal.dmg")]
    assert pick_asset(with_universal, "darwin", "x86_64").name == "SpeechStudio_0.2.2_universal.dmg"
    assert pick_asset(with_universal, "darwin", "arm64").name == "SpeechStudio_0.2.2_universal.dmg"


def test_linux_architecture_selection() -> None:
    def asset(name: str) -> updates.ReleaseAsset:
        return updates.ReleaseAsset(name, f"https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/{name}", 10)

    assets = [asset("SpeechStudio_0.2.2_amd64.deb"), asset("SpeechStudio_0.2.2_arm64.deb")]
    assert pick_asset(assets, "linux", "x86_64").name == "SpeechStudio_0.2.2_amd64.deb"
    assert pick_asset(assets, "linux", "aarch64").name == "SpeechStudio_0.2.2_arm64.deb"


@pytest.mark.parametrize("tamper", [False, True])
def test_download_verifies_sha256sums_fallback(tmp_path: Path, monkeypatch, tamper: bool) -> None:
    data = b"deb-package-bytes"
    digest = hashlib.sha256(data).hexdigest()
    sums_hex = ("0" * 64) if tamper else digest
    sums_text = f"{sums_hex}  Speech Studio_0.2.2_amd64.deb\n"
    deb_url = "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/Speech.Studio_0.2.2_amd64.deb"
    sums_url = "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/SHA256SUMS.txt"
    deb_asset = updates.ReleaseAsset("Speech.Studio_0.2.2_amd64.deb", deb_url, len(data), digest=None)
    sums_asset = updates.ReleaseAsset("SHA256SUMS.txt", sums_url, len(sums_text), digest=None)

    monkeypatch.setattr(updates, "tempfile_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        updates.httpx,
        "get",
        lambda url, **kwargs: httpx.Response(200, text=sums_text, request=httpx.Request("GET", url)),
    )

    @contextmanager
    def stream(method, url, **kwargs):
        yield httpx.Response(200, content=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(updates.httpx, "stream", stream)
    if tamper:
        with pytest.raises(updates.UpdateError) as err:
            updates._download(deb_asset, [deb_asset, sums_asset])
        assert err.value.code == "digest-mismatch"
        assert not list(tmp_path.glob("download-*"))
    else:
        dest = updates._download(deb_asset, [deb_asset, sums_asset])
        assert dest.read_bytes() == data


def test_download_retries_once_on_transport_error(tmp_path: Path, monkeypatch) -> None:
    data = b"setup-installer-bytes"
    digest = hashlib.sha256(data).hexdigest()
    asset = updates.ReleaseAsset(
        "SpeechStudio_0.2.2_Setup.exe",
        "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/SpeechStudio_0.2.2_Setup.exe",
        len(data),
        f"sha256:{digest}",
    )
    monkeypatch.setattr(updates, "tempfile_dir", lambda: str(tmp_path))
    attempts = {"count": 0}

    @contextmanager
    def stream(method, url, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("transient failure", request=httpx.Request("GET", url))
        yield httpx.Response(200, content=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(updates.httpx, "stream", stream)
    dest = updates._download(asset)
    assert attempts["count"] == 2
    assert dest.read_bytes() == data


def test_install_latest_reports_launched_not_completed_and_supports_cancel_retry(tmp_path: Path, monkeypatch) -> None:
    setup_bytes = b"MZsetup-binary"
    setup_sha = hashlib.sha256(setup_bytes).hexdigest()
    release = parse_release(
        {
            "tag_name": "v0.2.2",
            "html_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.2",
            "assets": [
                {
                    "name": "SpeechStudio_0.2.2_Setup.exe",
                    "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/SpeechStudio_0.2.2_Setup.exe",
                    "size": len(setup_bytes),
                    "digest": f"sha256:{setup_sha}",
                },
                {
                    "name": "SpeechStudio_0.2.2_amd64.deb",
                    "browser_download_url": "https://github.com/xyz-rainbow/xyz-speechstudio/releases/download/v0.2.2/SpeechStudio_0.2.2_amd64.deb",
                    "size": len(setup_bytes),
                    "digest": f"sha256:{setup_sha}",
                },
            ],
        }
    )
    monkeypatch.setattr(updates, "tempfile_dir", lambda: str(tmp_path))
    monkeypatch.setattr(updates, "load_release", lambda force=False: release)
    launched: list[tuple[Path, str]] = []
    monkeypatch.setattr(updates, "_launch", lambda path, plat: launched.append((path, plat)))

    should_cancel = {"flag": True}

    class FakeStream:
        def __init__(self, url: str) -> None:
            self.url = url

        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            yield setup_bytes[:4]
            if should_cancel["flag"]:
                updates.cancel_download()
            yield setup_bytes[4:]

    @contextmanager
    def stream(method, url, **kwargs):
        yield FakeStream(url)

    monkeypatch.setattr(updates.httpx, "stream", stream)

    with pytest.raises(updates.UpdateError) as err:
        updates.install_latest("0.2.1", platform="win32", architecture="AMD64")
    assert err.value.code == "cancelled"
    assert updates.download_progress()["phase"] == "cancelled"
    assert not launched

    should_cancel["flag"] = False
    win_res = updates.install_latest("0.2.1", platform="win32", architecture="AMD64")
    assert win_res["launched"] is True
    assert win_res["completed"] is False
    assert win_res["quits_app"] is True
    assert win_res["asset_name"] == "SpeechStudio_0.2.2_Setup.exe"
    assert updates.download_progress()["phase"] == "launched"

    linux_res = updates.install_latest("0.2.1", platform="linux", architecture="x86_64")
    assert linux_res["launched"] is True
    assert linux_res["completed"] is False
    assert linux_res["quits_app"] is False
    assert linux_res["asset_name"] == "SpeechStudio_0.2.2_amd64.deb"


def test_release_and_installer_workflows_stay_synchronized() -> None:
    build_wf = (ROOT / ".github" / "workflows" / "build-installers.yml").read_text(encoding="utf-8")
    release_wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    stt_cpu = (ROOT / "installer" / "requirements-stt-cpu.txt").read_text(encoding="utf-8")
    fetch_unix = (ROOT / "scripts" / "fetch_unix_runtime.py").read_text(encoding="utf-8")

    # Separate Intel and Apple Silicon macOS jobs + Linux amd64 + Windows
    assert "macos-15" in build_wf and "macos-15-intel" in build_wf and "ubuntu-24.04" in build_wf
    assert "arch_label: aarch64" in build_wf and "arch_label: x64" in build_wf and "arch_label: amd64" in build_wf
    # Version sync runs on both unix and windows jobs
    assert build_wf.count("scripts/sync_version.py --check") >= 2
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in build_wf
    # Release workflow routes all installers through build-installers.yml with tag version and blocks publish on all 4 packages + SHA256SUMS.txt
    assert "uses: ./.github/workflows/build-installers.yml" in release_wf
    assert "version: ${{ github.ref_name }}" in release_wf
    assert "needs: [release, installers]" in release_wf
    for expected in (
        "SpeechStudio_${VER}_Setup.exe",
        "SpeechStudio_${VER}_amd64.deb",
        "SpeechStudio_${VER}_aarch64.dmg",
        "SpeechStudio_${VER}_x64.dmg",
        "SHA256SUMS.txt",
        "sha256sum -c SHA256SUMS.txt",
    ):
        assert expected in release_wf
    # Intel macOS onnxruntime compatibility pin and authenticated CrispASR fetch
    assert re.search(r"onnxruntime==1\.23\.2;.*platform_machine == \"x86_64\"", stt_cpu)
    assert "GITHUB_TOKEN" in fetch_unix and "Authorization" in fetch_unix
