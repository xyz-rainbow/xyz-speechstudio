from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .external_providers import ExternalEndpointConfig

APP_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = APP_ROOT / "data"
DEFAULT_MODELS_DIR = DATA_DIR / "models"
DEFAULT_PROFILES_DIR = DATA_DIR / "profiles"
DEFAULT_OUTPUTS_DIR = DATA_DIR / "outputs"
DEFAULT_TMP_DIR = DATA_DIR / "tmp"
SETTINGS_PATH = DATA_DIR / "settings.json"


class AppSettings(BaseModel):
    language: Literal["en", "es"] = "en"
    theme: Literal["dark", "light"] = "dark"
    accent: Literal["cyber", "emerald", "amber", "rose"] = "cyber"
    ascii_fx_enabled: bool = True
    ascii_fx_opacity: float = Field(default=0.13, ge=0.04, le=0.25)
    sidebar_collapsed: bool = False
    models_dir: str = ""
    outputs_dir: str = ""
    tts_device: Literal["gpu", "cpu"] = "gpu"
    stt_device: Literal["gpu", "cpu"] = "gpu"
    tts_source: Literal["local", "endpoint"] = "local"
    stt_source: Literal["local", "endpoint"] = "local"
    active_tts_model: str = "qwen3-1.7b-base-Q8_0"
    active_stt_model: str = "faster-whisper-base"
    active_tts_endpoint_id: str = ""
    active_stt_endpoint_id: str = ""
    captions_max_history: int = Field(default=20, ge=5, le=200)
    notifications_enabled: bool = True
    api_endpoint_enabled: bool = False
    api_fixed_port: int = Field(default=0, ge=0, le=65535)
    api_bind_host: Literal["127.0.0.1", "0.0.0.0"] = "127.0.0.1"
    api_bearer_token: str = ""
    read_hotkey: str = ""
    external_endpoints: list[ExternalEndpointConfig] = Field(default_factory=list)


def ensure_data_dirs() -> None:
    for d in (DATA_DIR, DEFAULT_MODELS_DIR, DEFAULT_PROFILES_DIR, DEFAULT_OUTPUTS_DIR, DEFAULT_TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    ensure_data_dirs()
    if SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return AppSettings.model_validate(raw)
        except Exception:
            pass
    settings = AppSettings()
    save_settings(settings)
    return settings


def save_settings(settings: AppSettings) -> AppSettings:
    ensure_data_dirs()
    SETTINGS_PATH.write_text(
        json.dumps(settings.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return settings


def resolved_models_dir(settings: AppSettings) -> Path:
    p = Path(settings.models_dir.strip()) if settings.models_dir.strip() else DEFAULT_MODELS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolved_outputs_dir(settings: AppSettings) -> Path:
    p = Path(settings.outputs_dir.strip()) if settings.outputs_dir.strip() else DEFAULT_OUTPUTS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p
