"""Loquendo TTS 7 installation and voice selection through Windows SAPI."""

import os
import sys
from pathlib import Path
from typing import Optional

from . import sapi5_engine

MODEL_ID = "loquendo-tts7"


def installed_voices(force_refresh: bool = False) -> list[dict[str, str]]:
    return [
        voice for voice in sapi5_engine.discover_voices(force_refresh=force_refresh)
        if sapi5_engine._is_loquendo(voice)
    ]


def list_voices(language: Optional[str] = None) -> list[dict[str, str]]:
    voices = installed_voices()
    matched = [voice for voice in voices if sapi5_engine._match_language_filter(voice, language)]
    return [
        {"id": voice["id"], "label": voice["label"], "locale": voice["locale"]}
        for voice in matched or voices
    ]


def installed_languages() -> list[str]:
    return sorted({voice["locale"] for voice in installed_voices() if voice.get("locale") != "und"})


def resolve_voice(voice: Optional[str], language: Optional[str]) -> str:
    voices = installed_voices()
    if not voices:
        raise RuntimeError("Loquendo TTS 7 voices are not installed. Install the engine and voices, then rescan.")
    if voice and voice.lower() not in {"auto", "default"}:
        match = next((item for item in voices if voice in {item["id"], item["token_id"], item["name"]}), None)
        if match is None:
            raise ValueError("The selected voice does not belong to Loquendo TTS 7.")
        return match["id"]
    matched = [item for item in voices if sapi5_engine._match_language_filter(item, language)]
    return (matched or voices)[0]["id"]


def launch_installer(source_path: str) -> dict:
    if sys.platform != "win32":
        raise ValueError("The Loquendo SAPI installer requires Windows.")
    path = Path(source_path).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in {".exe", ".msi"}:
        raise ValueError("Select a Loquendo engine or voice installer (.exe or .msi).")
    os.startfile(str(path))
    return {"launched": True, "refresh_required": True}
