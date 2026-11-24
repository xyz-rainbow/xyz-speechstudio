"""XTTS language labels map to the fixed code set."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "backend" / "workers"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from xtts_lang import xtts_language, xtts_output_sample_rate  # noqa: E402


def test_names_and_codes() -> None:
    assert xtts_language("Spanish") == "es"
    assert xtts_language("es") == "es"
    assert xtts_language("ZH_CN") == "zh-cn"
    assert xtts_language("Chinese") == "zh-cn"
    assert xtts_language("Japanese") == "ja"


def test_unknown_lists_supported_names() -> None:
    try:
        xtts_language("Klingon")
    except ValueError as exc:
        assert "Supported languages" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported language")


def test_output_sample_rate_is_the_decoder_rate() -> None:
    class Audio:
        sample_rate = 22050
        output_sample_rate = 24000

    class Config:
        audio = Audio()

    assert xtts_output_sample_rate(Config()) == 24000
    assert xtts_output_sample_rate(type("C", (), {"audio": {"sample_rate": 22050, "output_sample_rate": 24000}})()) == 24000
    assert xtts_output_sample_rate(object()) == 24000


def test_empty_language_is_rejected() -> None:
    try:
        xtts_language("  ")
    except ValueError as exc:
        assert "needs a language" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty language")
