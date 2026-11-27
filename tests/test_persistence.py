import json

import pytest

from backend.orchestrator import persistence


def test_failed_replace_preserves_previous_file(tmp_path, monkeypatch):
    destination = tmp_path / "settings.json"
    destination.write_text('{"value": "previous"}', encoding="utf-8")

    def fail_replace(*args):
        raise PermissionError("in use")

    monkeypatch.setattr(persistence.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        persistence.write_json_atomic(destination, {"value": "new"})
    assert json.loads(destination.read_text()) == {"value": "previous"}
    assert list(tmp_path.iterdir()) == [destination]


def test_atomic_write_preserves_unicode(tmp_path):
    destination = tmp_path / "profiles" / "data.json"
    value = {"name": "Español 🛠️"}
    persistence.write_json_atomic(destination, value)
    assert json.loads(destination.read_text(encoding="utf-8")) == value


def test_concurrent_history_additions_are_preserved(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from backend.orchestrator import history

    monkeypatch.setattr(history, "HISTORY_JSON", tmp_path / "history.json")
    monkeypatch.setattr(history, "ensure_data_dirs", lambda: None)

    def add(index):
        return history.add_record(
            profile_id="test", profile_name="test", text=str(index), language="es",
            file_path=str(tmp_path / f"{index}.wav"), duration_s=1, sr=22050,
            elapsed_s=1, rtf=1,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(executor.map(add, range(24)))
    assert {record.id for record in history.list_history()} == {record.id for record in records}
