from pathlib import Path

import pytest

from backend.orchestrator.paths import resolve_data_dir
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
