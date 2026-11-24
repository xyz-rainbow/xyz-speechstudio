"""XTTS language labels map to the fixed code set."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
    with pytest.raises(ValueError, match="Supported languages"):
        xtts_language("Klingon")


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
    with pytest.raises(ValueError, match="needs a language"):
        xtts_language("  ")
