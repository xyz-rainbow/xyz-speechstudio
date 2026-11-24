"""CLI parsing, shorthand normalization, value coercion, and cross-platform playback tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.cli import main as cli_main  # noqa: E402


def test_cli_imports_without_winsound_on_all_platforms() -> None:
    src = (ROOT / "backend" / "cli" / "main.py").read_text(encoding="utf-8")
    top_imports = src.split("def ", 1)[0]
    assert "import winsound" not in top_imports


def test_normalize_shorthands() -> None:
    assert cli_main._normalize_shorthands(["--models", "--installed"]) == ["models", "--installed"]
    assert cli_main._normalize_shorthands(["--status", "--json"]) == ["status", "--json"]
    assert cli_main._normalize_shorthands(["--profiles"]) == ["profiles"]
    assert cli_main._normalize_shorthands(["--config", "show"]) == ["config", "show"]
    assert cli_main._normalize_shorthands(["--endpoints"]) == ["endpoints"]
    # Already has a positional subcommand -> do not rewrite later flags
    assert cli_main._normalize_shorthands(["play", "hola", "--models"]) == ["play", "hola", "--models"]


def test_coerce_value_types() -> None:
    assert cli_main._coerce_value("true") is True
    assert cli_main._coerce_value("FALSE") is False
    assert cli_main._coerce_value("none") is None
    assert cli_main._coerce_value("42") == 42
    assert cli_main._coerce_value("0.15") == 0.15
    assert cli_main._coerce_value("spanish") == "spanish"


def test_parser_supports_core_commands() -> None:
    parser = cli_main.build_parser()
    args_play = parser.parse_args(["play", "hola", "mundo", "--no-play", "--out", "out.wav"])
    assert args_play.command == "play"
    assert args_play.text == ["hola", "mundo"]
    assert args_play.no_play is True
    assert args_play.out == "out.wav"

    args_search = parser.parse_args(["models", "search", "whisper", "--kind", "stt", "--page", "2"])
    assert args_search.command == "models"
    assert args_search.models_action == "search"
    assert args_search.query == "whisper"
    assert args_search.kind == "stt"
    assert args_search.page == 2

    args_imp = parser.parse_args(["models", "import", "/tmp/model", "--kind", "tts", "--name", "MyTTS"])
    assert args_imp.models_action == "import"
    assert args_imp.kind == "tts"
    assert args_imp.name == "MyTTS"
