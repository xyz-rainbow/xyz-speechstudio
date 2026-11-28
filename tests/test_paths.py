from pathlib import Path

import pytest

from backend.orchestrator.paths import (
    ensure_user_dirs,
    migrate_legacy_app_data,
    resolve_cache_dir,
    resolve_data_dir,
)
from backend.orchestrator.catalog_capabilities import resolve_runtime_python


@pytest.mark.parametrize("platform,suffix", [
    ("win32", "AppData/Local/Speech Studio"),
    ("darwin", "Library/Application Support/Speech Studio"),
    ("linux", ".local/share/speech-studio"),
])
def test_new_installs_use_user_data(tmp_path, platform, suffix):
    home = tmp_path / "home"
    assert resolve_data_dir(tmp_path / "resources", platform=platform, environ={}, home=home) == home / suffix


@pytest.mark.parametrize("marker", [".git", "portable.txt", "data/settings.json"])
def test_existing_installs_and_portable_preserve_data(tmp_path, marker):
    file = tmp_path / marker
    file.parent.mkdir(parents=True, exist_ok=True)
    file.touch()
    assert resolve_data_dir(tmp_path, environ={}) == tmp_path / "data"


def test_data_override_is_independent_of_cwd(tmp_path):
    assert resolve_data_dir(tmp_path, environ={"SPEECHSTUDIO_DATA_DIR": "separate"}) == tmp_path / "separate"
    absolute = tmp_path / "external"
    assert resolve_data_dir(tmp_path, environ={"SPEECHSTUDIO_DATA_DIR": str(absolute)}) == absolute


def test_xdg_ignores_relative_base(tmp_path):
    home = tmp_path / "home"
    assert resolve_data_dir(tmp_path, platform="linux", environ={"XDG_DATA_HOME": "relative"}, home=home) == home / ".local/share/speech-studio"


@pytest.mark.parametrize("windows", [True, False])
def test_partial_runtime_upgrade_keeps_legacy_workers(tmp_path, windows):
    (tmp_path / "runtime/envs/core").mkdir(parents=True)
    suffix = Path("Scripts/python.exe") if windows else Path("bin/python")
    worker = tmp_path / ".venvs/stt" / suffix
    worker.parent.mkdir(parents=True)
    worker.touch()
    assert resolve_runtime_python(tmp_path, "stt", windows=windows) == worker


def test_unified_legacy_runtime_is_available_after_partial_upgrade(tmp_path):
    unified = tmp_path / ".venvs/pytts/bin/python"
    unified.parent.mkdir(parents=True)
    unified.touch()
    (tmp_path / "runtime/envs").mkdir(parents=True)
    assert resolve_runtime_python(tmp_path, "fish", windows=False) == unified


def test_paths_with_spaces_unicode_and_brackets(tmp_path):
    root = tmp_path / "[Tools]" / "xyz-speech-studio"
    fancy = root / "datos áéí" / "Speech Studio"
    resolved = resolve_data_dir(root, environ={"SPEECHSTUDIO_DATA_DIR": str(fancy)})
    assert resolved == fancy
    created = ensure_user_dirs(fancy)
    assert (fancy / "models").is_dir()
    assert (fancy / "cache").is_dir()
    assert fancy in created


def test_cache_dir_uses_xdg_outside_portable(tmp_path):
    home = tmp_path / "home"
    app = tmp_path / "Program Files" / "Speech Studio"
    app.mkdir(parents=True)
    cache = resolve_cache_dir(app, platform="linux", environ={}, home=home)
    assert cache == home / ".cache" / "speech-studio"


def test_portable_keeps_cache_under_data(tmp_path):
    (tmp_path / "portable.txt").touch()
    cache = resolve_cache_dir(tmp_path, platform="win32", environ={})
    assert cache == tmp_path / "data" / "cache"


def test_migrate_report_does_not_move_files(tmp_path):
    app = tmp_path / "app"
    user = tmp_path / "user-data"
    legacy = app / "data"
    (legacy / "models").mkdir(parents=True)
    (legacy / "settings.json").write_text("{}", encoding="utf-8")
    report = migrate_legacy_app_data(app, user)
    assert report["action"] == "prefer_legacy_until_settings_migrated"
    assert (legacy / "settings.json").is_file()
    assert not (user / "settings.json").exists()
