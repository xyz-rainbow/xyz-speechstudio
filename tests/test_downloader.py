"""Model catalog fresh-install invariants, URL inspect routing, and local import tests."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import downloader, profiles  # noqa: E402
from backend.orchestrator.config import AppSettings  # noqa: E402


def test_no_hardcoded_external_model_or_mario_seed() -> None:
    assert not hasattr(downloader, "FALLBACK_QWEN_DIR")
    assert not hasattr(profiles, "ensure_mario_imported")
    assert not hasattr(profiles, "MARIO_SEED_DIR")


def test_builtin_catalog_has_family_grouping_and_fish_audio() -> None:
    families = {entry.get("family_id") for entry in downloader.BUILTIN_MODELS}
    assert "qwen3-tts" in families
    assert "xtts-v2" in families
    assert "fish-audio" in families
    assert "f5-tts" in families
    assert "faster-whisper" in families
    assert "parakeet-v3" in families
    assert "moonshine" in families
    f5 = [m for m in downloader.BUILTIN_MODELS if m.get("family_id") == "f5-tts"]
    assert {m["id"] for m in f5} >= {
        "f5-tts-v1-base",
        "f5-tts-spanish",
        "f5-tts-french",
        "f5-tts-german",
        "f5-tts-gguf-f16",
    }
    assert "kokoro" in families
    assert "kitten-tts" in families
    assert "piper" in families
    assert all(m.get("runtime_supported") is False for m in f5)
    assert all(m.get("install_mode") == "per_language_checkpoint" for m in f5)
    assert all(len(m.get("quants", [])) >= 1 for m in f5)


def test_empty_models_dir_reports_zero_installed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ss_cat_"))
    try:
        settings = AppSettings(models_dir=str(tmp))
        entries = downloader.build_catalog(settings)
        assert entries
        assert all(not entry.installed for entry in entries)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_local_model_copies_files_cleanly() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ss_imp_"))
    try:
        src_dir = tmp / "source_model"
        src_dir.mkdir()
        (src_dir / "model.bin").write_bytes(b"weights")
        (src_dir / "config.json").write_text("{}", encoding="utf-8")

        models_dir = tmp / "models"
        settings = AppSettings(models_dir=str(models_dir))

        entry = downloader.import_local_model(
            settings,
            source_path=str(src_dir),
            name="Local Whisper Test",
            kind="stt",
        )
        assert entry.installed is True
        assert entry.custom is True
        assert entry.kind == "stt"
        assert entry.removable is True
        dest = Path(entry.install_dir or "")
        assert (dest / "model.bin").is_file()
        assert (dest / "config.json").is_file()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
