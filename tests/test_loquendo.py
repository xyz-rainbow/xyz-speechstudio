from pathlib import Path

import pytest

from backend.orchestrator import downloader, loquendo
from backend.orchestrator.config import AppSettings


def voice(name: str, vendor: str = "Loquendo", source: str = "sapi32") -> dict[str, str]:
    return {
        "id": f"{source}|{vendor}/{name}", "token_id": f"{vendor}/{name}",
        "name": name, "vendor": vendor, "source": source, "locale": "es-ES",
        "label": f"{name} · es-ES", "display": "Spanish",
    }


def test_catalog_distinguishes_loquendo_from_system_voices(tmp_path, monkeypatch):
    monkeypatch.setattr(loquendo.sapi5_engine, "discover_voices", lambda **kwargs: [voice("Microsoft Helena", "Microsoft", "sapi64")])
    settings = AppSettings(models_dir=str(tmp_path))
    model = next(item for item in downloader.build_catalog(settings) if item.id == loquendo.MODEL_ID)
    assert model.family_id == loquendo.MODEL_ID
    assert model.engine == "sapi5"
    assert not model.installed
    monkeypatch.setattr(loquendo.sapi5_engine, "discover_voices", lambda **kwargs: [voice("Jorge")])
    installed = next(item for item in downloader.build_catalog(settings) if item.id == loquendo.MODEL_ID)
    assert installed.installed
    assert installed.capabilities.languages == ["es-ES"]


def test_voice_selection_cannot_fall_back_to_microsoft(monkeypatch):
    jorge = voice("Jorge")
    helena = voice("Microsoft Helena", "Microsoft", "sapi64")
    monkeypatch.setattr(loquendo.sapi5_engine, "discover_voices", lambda **kwargs: [helena, jorge])
    assert loquendo.resolve_voice(None, "Spanish") == jorge["id"]
    assert [item["id"] for item in loquendo.list_voices()] == [jorge["id"]]
    with pytest.raises(ValueError, match="does not belong"):
        loquendo.resolve_voice(helena["id"], "Spanish")


def test_missing_loquendo_voices_reports_installation_needed(monkeypatch):
    monkeypatch.setattr(loquendo.sapi5_engine, "discover_voices", lambda **kwargs: [])
    with pytest.raises(RuntimeError, match="not installed"):
        loquendo.resolve_voice(None, "Spanish")


def test_launch_installer_uses_selected_file(tmp_path, monkeypatch):
    installer = tmp_path / "Loquendo TTS 7.msi"
    installer.touch()
    launched = []
    monkeypatch.setattr(loquendo.sys, "platform", "win32")
    monkeypatch.setattr(loquendo.os, "startfile", lambda path: launched.append(path), raising=False)
    result = loquendo.launch_installer(str(installer))
    assert launched == [str(installer.resolve())]
    assert result == {"launched": True, "refresh_required": True}


def test_installer_rejects_other_platform_and_wrong_file(tmp_path, monkeypatch):
    monkeypatch.setattr(loquendo.sys, "platform", "linux")
    with pytest.raises(ValueError, match="Windows"):
        loquendo.launch_installer(str(tmp_path / "setup.exe"))
    monkeypatch.setattr(loquendo.sys, "platform", "win32")
    other = tmp_path / "voice.wav"
    other.touch()
    with pytest.raises(ValueError, match="installer"):
        loquendo.launch_installer(str(other))


def test_loquendo_download_does_not_claim_a_missing_source(tmp_path):
    manager = downloader.DownloadManager()
    with pytest.raises(ValueError, match="no downloadable files"):
        manager.start_catalog_download(AppSettings(models_dir=str(tmp_path)), loquendo.MODEL_ID)


def test_installer_requires_license_confirmation(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.orchestrator.main import app

    launched = []
    monkeypatch.setattr(loquendo, "launch_installer", lambda source: launched.append(source) or {"launched": True})
    client = TestClient(app, client=("127.0.0.1", 50000))
    rejected = client.post("/api/tts/loquendo/install", json={"source_path": "installer.exe"})
    assert rejected.status_code == 400
    assert not launched
    accepted = client.post("/api/tts/loquendo/install", json={"source_path": "installer.exe", "license_confirmed": True})
    assert accepted.status_code == 200
    assert launched == ["installer.exe"]
