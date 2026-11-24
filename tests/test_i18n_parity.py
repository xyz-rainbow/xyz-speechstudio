"""English and Spanish UI catalogs must expose the same key tree."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src" / "i18n" / "locales"


def _flatten(data: object, prefix: str = "") -> list[str]:
    if isinstance(data, dict):
        keys: list[str] = []
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.extend(_flatten(value, path))
        return keys
    return [prefix]


def test_en_and_es_locale_keys_match() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    assert _flatten(en) == _flatten(es)
