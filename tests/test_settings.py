"""Default settings and catalog identifiers stay consistent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator.config import AppSettings  # noqa: E402
from backend.orchestrator.downloader import BUILTIN_BY_ID, BUILTIN_MODELS  # noqa: E402

STT_CATALOG_IDS = (
    "faster-whisper-tiny",
    "faster-whisper-base",
    "faster-whisper-small",
    "faster-whisper-medium",
    "faster-whisper-large-v3-turbo",
)


def test_default_settings() -> None:
    settings = AppSettings()
    assert settings.language == "en"
    assert settings.theme == "dark"
    assert settings.tts_device == "gpu"
    assert settings.stt_device == "gpu"
    assert settings.tts_source == "local"
    assert settings.stt_source == "local"
    assert settings.api_endpoint_enabled is False
    assert settings.api_bind_host == "127.0.0.1"
    assert settings.api_bearer_token == ""
    assert settings.active_stt_model == "faster-whisper-base"


def test_builtin_catalog_ids_are_unique() -> None:
    ids = [entry["id"] for entry in BUILTIN_MODELS]
    assert ids
    assert len(ids) == len(set(ids))
    assert set(BUILTIN_BY_ID) == set(ids)
    for required in ("qwen3-1.7b-base", "qwen3-0.6b-base", *STT_CATALOG_IDS):
        assert required in BUILTIN_BY_ID


def test_stt_catalog_ids_exist_in_builtin_models() -> None:
    for model_id in STT_CATALOG_IDS:
        assert model_id in BUILTIN_BY_ID
        assert BUILTIN_BY_ID[model_id]["engine"] == "faster-whisper"


def test_package_and_tauri_versions_match() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    version = package["version"]
    assert tauri["version"] == version
    assert f'version = "{version}"' in cargo
