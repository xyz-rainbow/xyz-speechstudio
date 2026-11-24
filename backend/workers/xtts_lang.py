"""Map Speech Studio language labels to XTTS v2 language codes.

XTTS v2 accepts a fixed set of codes. The UI stores names such as "Spanish".
"""

from __future__ import annotations

XTTS_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "tr": "Turkish",
    "ru": "Russian",
    "nl": "Dutch",
    "cs": "Czech",
    "ar": "Arabic",
    "zh-cn": "Chinese",
    "ja": "Japanese",
    "hu": "Hungarian",
    "ko": "Korean",
    "hi": "Hindi",
}

_BY_NAME = {name.casefold(): code for code, name in XTTS_LANGUAGES.items()}


def xtts_language(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("XTTS needs a language.")
    code = raw.casefold().replace("_", "-")
    if code in XTTS_LANGUAGES:
        return code
    mapped = _BY_NAME.get(raw.casefold())
    if mapped:
        return mapped
    names = ", ".join(XTTS_LANGUAGES.values())
    raise ValueError(f"XTTS v2 does not speak '{raw}'. Supported languages: {names}.")
