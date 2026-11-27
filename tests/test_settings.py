"""Default settings and catalog identifiers stay consistent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from backend.orchestrator.config import (  # noqa: E402
    AppSettings,
    reject_public_bind_without_token,
    repair_open_lan_bind,
)
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
    assert settings.tts_device == "cpu"
    assert settings.stt_device == "cpu"
    assert settings.tts_source == "local"
    assert settings.stt_source == "local"
    assert settings.api_endpoint_enabled is False
    assert settings.api_bind_host == "127.0.0.1"
    assert settings.api_bearer_token == ""
    assert settings.active_stt_model == "faster-whisper-base"
    assert settings.close_behavior == "ask"


def test_explicit_gpu_settings_are_preserved() -> None:
    settings = AppSettings.model_validate({"tts_device": "gpu", "stt_device": "gpu"})
    assert settings.tts_device == "gpu"
    assert settings.stt_device == "gpu"


def test_public_bind_requires_bearer_token() -> None:
    with pytest.raises(ValidationError):
        AppSettings(api_bind_host="0.0.0.0", api_bearer_token="")
    with pytest.raises(ValidationError):
        AppSettings(api_bind_host="0.0.0.0", api_bearer_token="   ")
    with pytest.raises(ValidationError):
        AppSettings(
            api_bind_host="0.0.0.0",
            api_bearer_token="",
            api_endpoint_enabled=True,
        )
    with pytest.raises(ValueError):
        reject_public_bind_without_token("0.0.0.0", "")
    with pytest.raises(ValueError):
        reject_public_bind_without_token("0.0.0.0", "  ")

    opened = AppSettings(api_bind_host="0.0.0.0", api_bearer_token="sk-speech-test")
    assert opened.api_bearer_token == "sk-speech-test"
    reject_public_bind_without_token("0.0.0.0", opened.api_bearer_token)
    reject_public_bind_without_token("127.0.0.1", "")

    repaired = repair_open_lan_bind(
        {"api_bind_host": "0.0.0.0", "api_bearer_token": "", "language": "es"}
    )
    assert repaired is not None
    assert repaired["api_bind_host"] == "127.0.0.1"
    assert repaired["language"] == "es"
    assert repair_open_lan_bind({"api_bind_host": "127.0.0.1", "api_bearer_token": ""}) is None
    assert (
        repair_open_lan_bind({"api_bind_host": "0.0.0.0", "api_bearer_token": "sk-speech-test"})
        is None
    )


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


def test_xtts_catalog_is_runtime_supported() -> None:
    entry = BUILTIN_BY_ID["xtts-v2"]
    assert entry["engine"] == "xtts"
    assert entry["runtime_supported"] is True
    assert entry["quants"][0]["files"] == [
        "config.json",
        "model.pth",
        "vocab.json",
        "speakers_xtts.pth",
    ]


def test_package_and_tauri_versions_match() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    version = package["version"]
    assert tauri["version"] == version
    assert f'version = "{version}"' in cargo
