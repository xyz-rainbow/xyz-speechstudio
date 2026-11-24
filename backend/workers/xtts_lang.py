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


def xtts_output_sample_rate(config: object) -> int:
    """Return the decoder rate. The checkpoint stores 22050 as the input rate."""
    sources = (getattr(config, "audio", None), getattr(config, "model_args", None))
    for source in sources:
        if source is None:
            continue
        if isinstance(source, dict):
            value = source.get("output_sample_rate")
        else:
            value = getattr(source, "output_sample_rate", None)
        if value:
            return int(value)
    return 24000


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
