"""Replace JSON files only after the complete new content reaches disk."""

import json
import os
import tempfile
import threading
from functools import wraps
from pathlib import Path


_transaction_lock = threading.RLock()


def json_transaction(function):
    """Serialize read-modify-write operations inside the orchestrator process."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _transaction_lock:
            return function(*args, **kwargs)
    return wrapped


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
