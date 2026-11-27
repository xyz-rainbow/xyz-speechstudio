from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from .external_providers import ExternalEndpointConfig
from .persistence import write_json_atomic
from .paths import resolve_data_dir

APP_ROOT = Path(__file__).absolute().parents[2]
DATA_DIR = resolve_data_dir(APP_ROOT)
DEFAULT_MODELS_DIR = DATA_DIR / "models"
DEFAULT_PROFILES_DIR = DATA_DIR / "profiles"
DEFAULT_OUTPUTS_DIR = DATA_DIR / "outputs"
DEFAULT_TMP_DIR = DATA_DIR / "tmp"
SETTINGS_PATH = DATA_DIR / "settings.json"
RUNTIME_JSON_PATH = DATA_DIR / "runtime.json"


def reject_public_bind_without_token(bind_host: str, token: str) -> None:
    """Listening on every interface without a bearer token is rejected."""
    if bind_host == "0.0.0.0" and not (token or "").strip():
        raise ValueError("api_bearer_token is required when api_bind_host is 0.0.0.0")


def repair_open_lan_bind(raw: dict) -> dict | None:
    """Drop an open LAN bind so a saved file cannot be served without a token."""
    token = raw.get("api_bearer_token")
    token_text = token if isinstance(token, str) else ""
    if raw.get("api_bind_host") == "0.0.0.0" and not token_text.strip():
        repaired = dict(raw)
        repaired["api_bind_host"] = "127.0.0.1"
        return repaired
    return None


class AppSettings(BaseModel):
    language: Literal["en", "es"] = "en"
    theme: Literal["dark", "light"] = "dark"
    accent: Literal["cyber", "emerald", "amber", "rose"] = "cyber"
    ascii_fx_enabled: bool = True
    ascii_fx_opacity: float = Field(default=0.13, ge=0.04, le=0.25)
    sidebar_collapsed: bool = False
    models_dir: str = ""
    outputs_dir: str = ""
    tts_device: Literal["gpu", "cpu"] = "cpu"
    stt_device: Literal["gpu", "cpu"] = "cpu"
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
    close_behavior: Literal["ask", "minimize", "quit"] = "ask"
    tts_chunk_enabled: bool = True
    tts_chunk_max_chars: int = Field(default=300, ge=120, le=800)
    model_runtimes: dict[str, Literal["crispasr", "python"]] = Field(default_factory=dict)
    external_endpoints: list[ExternalEndpointConfig] = Field(default_factory=list)
    # TTS capabilities UX (Fase 1): feature flag + per-family language stock.
    capabilities_v1: bool = True
    installed_languages: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def lan_bind_requires_bearer_token(self) -> "AppSettings":
        reject_public_bind_without_token(self.api_bind_host, self.api_bearer_token)
        return self


def ensure_data_dirs() -> None:
    for d in (DATA_DIR, DEFAULT_MODELS_DIR, DEFAULT_PROFILES_DIR, DEFAULT_OUTPUTS_DIR, DEFAULT_TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    ensure_data_dirs()
    if SETTINGS_PATH.exists():
        raw: object | None
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = None
        if isinstance(raw, dict):
            try:
                return AppSettings.model_validate(raw)
            except ValidationError:
                repaired = repair_open_lan_bind(raw)
                if repaired is not None:
                    try:
                        settings = AppSettings.model_validate(repaired)
                    except ValidationError:
                        settings = None
                    else:
                        return save_settings(settings)
    settings = AppSettings()
    return save_settings(settings)


def save_settings(settings: AppSettings) -> AppSettings:
    ensure_data_dirs()
    write_json_atomic(SETTINGS_PATH, settings.model_dump())
    return settings


def resolved_models_dir(settings: AppSettings) -> Path:
    p = Path(settings.models_dir.strip()) if settings.models_dir.strip() else DEFAULT_MODELS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolved_outputs_dir(settings: AppSettings) -> Path:
    p = Path(settings.outputs_dir.strip()) if settings.outputs_dir.strip() else DEFAULT_OUTPUTS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p
