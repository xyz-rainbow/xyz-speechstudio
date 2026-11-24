from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .config import DEFAULT_OUTPUTS_DIR, DEFAULT_TMP_DIR, ensure_data_dirs

HISTORY_JSON = DEFAULT_OUTPUTS_DIR / "history.json"


class GenerationRecord(BaseModel):
    id: str
    profile_id: str
    profile_name: str
    text: str
    language: str
    file_path: str
    saved_path: str = ""
    duration_s: float
    sr: int
    elapsed_s: float
    rtf: float
    created_at: float


def _read_all() -> list[GenerationRecord]:
    ensure_data_dirs()
    if not HISTORY_JSON.exists():
        return []
    try:
        raw = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
        return [GenerationRecord.model_validate(item) for item in raw]
    except Exception:
        return []


def _write_all(records: list[GenerationRecord]) -> None:
    ensure_data_dirs()
    HISTORY_JSON.write_text(
        json.dumps([r.model_dump() for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_history() -> list[GenerationRecord]:
    return _read_all()


def get_record(rec_id: str) -> Optional[GenerationRecord]:
    for r in _read_all():
        if r.id == rec_id:
            return r
    return None


def add_record(
    *,
    profile_id: str,
    profile_name: str,
    text: str,
    language: str,
    file_path: str,
    duration_s: float,
    sr: int,
    elapsed_s: float,
    rtf: float,
) -> GenerationRecord:
    records = _read_all()
    rec = GenerationRecord(
        id=uuid.uuid4().hex[:10],
        profile_id=profile_id,
        profile_name=profile_name,
        text=text,
        language=language,
        file_path=file_path,
        saved_path="",
        duration_s=duration_s,
        sr=sr,
        elapsed_s=elapsed_s,
        rtf=rtf,
        created_at=time.time(),
    )
    records.insert(0, rec)
    _write_all(records)
    return rec


def set_saved_path(rec_id: str, dest_path: str) -> Optional[GenerationRecord]:
    records = _read_all()
    for idx, r in enumerate(records):
        if r.id != rec_id:
            continue
        src = Path(r.file_path)
        dst = Path(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        updated = r.model_copy(update={"saved_path": str(dst)})
        records[idx] = updated
        _write_all(records)
        return updated
    return None


def delete_record(rec_id: str) -> bool:
    records = _read_all()
    target = next((r for r in records if r.id == rec_id), None)
    if target is None:
        return False
    records = [r for r in records if r.id != rec_id]
    _write_all(records)

    fp = Path(target.file_path)
    try:
        if fp.exists() and (
            DEFAULT_OUTPUTS_DIR.resolve() in fp.resolve().parents
            or DEFAULT_TMP_DIR.resolve() in fp.resolve().parents
        ):
            fp.unlink(missing_ok=True)
    except Exception:
        pass
    return True
