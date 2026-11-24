from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from .config import DEFAULT_PROFILES_DIR, ensure_data_dirs

PROFILES_JSON = DEFAULT_PROFILES_DIR / "profiles.json"


class VoiceProfile(BaseModel):
    id: str
    name: str
    language: str = "Spanish"
    engine: Literal["qwen", "xtts"] = "qwen"
    ref_audio_path: str = ""
    ref_text: str = ""
    spk_path: str = ""
    rvq_path: str = ""
    ready: bool = False
    created_at: float
    updated_at: float


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"voice-{uuid.uuid4().hex[:6]}"


def _read_all() -> list[VoiceProfile]:
    ensure_data_dirs()
    if not PROFILES_JSON.exists():
        return []
    try:
        raw = json.loads(PROFILES_JSON.read_text(encoding="utf-8"))
        return [VoiceProfile.model_validate(item) for item in raw]
    except Exception:
        return []


def _write_all(profiles: list[VoiceProfile]) -> None:
    ensure_data_dirs()
    PROFILES_JSON.write_text(
        json.dumps([p.model_dump() for p in profiles], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_profiles() -> list[VoiceProfile]:
    return _read_all()


def get_profile(identifier: str) -> Optional[VoiceProfile]:
    profiles = _read_all()
    low = identifier.strip().lower()
    for p in profiles:
        if p.id.lower() == low or p.name.lower() == low:
            return p
    return None


def create_profile(
    *,
    name: str,
    language: str,
    engine: Literal["qwen", "xtts"],
    ref_audio_path: str,
    ref_text: str,
) -> VoiceProfile:
    profiles = _read_all()
    base_id = _slugify(name)
    pid = base_id
    existing_ids = {p.id for p in profiles}
    if pid in existing_ids:
        pid = f"{base_id}-{uuid.uuid4().hex[:4]}"

    pdir = DEFAULT_PROFILES_DIR / pid
    pdir.mkdir(parents=True, exist_ok=True)

    stored_audio = ""
    if ref_audio_path and Path(ref_audio_path).exists():
        ext = Path(ref_audio_path).suffix or ".wav"
        dst = pdir / f"ref{ext}"
        shutil.copy2(ref_audio_path, dst)
        stored_audio = str(dst)

    now = time.time()
    prof = VoiceProfile(
        id=pid,
        name=name.strip(),
        language=language.strip() or "Spanish",
        engine=engine,
        ref_audio_path=stored_audio,
        ref_text=ref_text.strip(),
        spk_path=str(pdir / "voice.spk"),
        rvq_path=str(pdir / "voice.rvq"),
        ready=engine == "xtts" and bool(stored_audio),
        created_at=now,
        updated_at=now,
    )
    profiles.append(prof)
    _write_all(profiles)
    return prof


def update_profile(
    pid: str,
    *,
    name: Optional[str] = None,
    language: Optional[str] = None,
    engine: Optional[Literal["qwen", "xtts"]] = None,
    ref_audio_path: Optional[str] = None,
    ref_text: Optional[str] = None,
    ready: Optional[bool] = None,
    spk_path: Optional[str] = None,
    rvq_path: Optional[str] = None,
) -> Optional[VoiceProfile]:
    profiles = _read_all()
    for idx, p in enumerate(profiles):
        if p.id != pid:
            continue
        pdir = DEFAULT_PROFILES_DIR / pid
        pdir.mkdir(parents=True, exist_ok=True)

        audio_changed = False
        new_audio = p.ref_audio_path
        if ref_audio_path is not None and ref_audio_path != p.ref_audio_path:
            if ref_audio_path and Path(ref_audio_path).exists():
                ext = Path(ref_audio_path).suffix or ".wav"
                dst = pdir / f"ref{ext}"
                if Path(ref_audio_path).resolve() != dst.resolve():
                    shutil.copy2(ref_audio_path, dst)
                new_audio = str(dst)
                audio_changed = True

        next_engine = engine if engine is not None else p.engine
        if ready is not None:
            next_ready = ready
        elif next_engine == "xtts":
            next_ready = bool(new_audio) and Path(new_audio).exists()
        elif audio_changed or (engine is not None and engine != p.engine):
            next_ready = False
        else:
            next_ready = p.ready
        updated = p.model_copy(
            update={
                "name": name.strip() if name is not None else p.name,
                "language": language.strip() if language is not None else p.language,
                "engine": next_engine,
                "ref_audio_path": new_audio,
                "ref_text": ref_text.strip() if ref_text is not None else p.ref_text,
                "spk_path": spk_path if spk_path is not None else p.spk_path,
                "rvq_path": rvq_path if rvq_path is not None else p.rvq_path,
                "ready": next_ready,
                "updated_at": time.time(),
            }
        )
        profiles[idx] = updated
        _write_all(profiles)
        return updated
    return None


def delete_profile(pid: str) -> bool:
    profiles = _read_all()
    kept = [p for p in profiles if p.id != pid]
    if len(kept) == len(profiles):
        return False
    _write_all(kept)
    pdir = DEFAULT_PROFILES_DIR / pid
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)
    return True
