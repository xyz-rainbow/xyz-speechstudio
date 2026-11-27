from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from .audio_prep import ensure_ref_24k, probe_audio_info, trim_ref_audio
from .config import DEFAULT_PROFILES_DIR, ensure_data_dirs
from .persistence import json_transaction, write_json_atomic

PROFILES_JSON = DEFAULT_PROFILES_DIR / "profiles.json"

INLINE_CLONE_ENGINES = frozenset({
    "qwen",
    "xtts",
    "f5",
    "f5-tts",
    "fish",
    "fish-audio",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3-tts",
    "indextts",
    "orpheus",
})


class VoiceProfile(BaseModel):
    id: str
    name: str
    language: str = "Spanish"
    engine: Literal[
        "qwen",
        "xtts",
        "f5",
        "fish",
        "chatterbox",
        "chatterbox-turbo",
        "cosyvoice3-tts",
        "orpheus",
        "indextts",
    ] = "qwen"
    ref_audio_path: str = ""
    ref_24k_path: str = ""
    ref_original_path: str = ""
    ref_duration_s: float = 0.0
    ref_trimmed: bool = False
    ref_text: str = ""
    spk_path: str = ""
    rvq_path: str = ""
    ready: bool = False
    created_at: float
    updated_at: float


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"voice-{uuid.uuid4().hex[:6]}"


def _is_inline_clone_ready(engine: str, ref_audio_path: str) -> bool:
    return (engine or "").strip().lower() in INLINE_CLONE_ENGINES and bool(ref_audio_path) and Path(ref_audio_path).exists()


@json_transaction
def _read_all() -> list[VoiceProfile]:
    ensure_data_dirs()
    if not PROFILES_JSON.exists():
        return []
    try:
        raw = json.loads(PROFILES_JSON.read_text(encoding="utf-8"))
        items = [VoiceProfile.model_validate(item) for item in raw]
    except Exception:
        return []
    changed = False
    for idx, p in enumerate(items):
        updates: dict = {}
        ref_p = Path(p.ref_audio_path) if p.ref_audio_path else None
        if ref_p and ref_p.exists():
            expected_ready = _is_inline_clone_ready(p.engine, p.ref_audio_path)
            if expected_ready and not p.ready:
                updates["ready"] = True
            if p.ref_duration_s <= 0:
                info = probe_audio_info(ref_p)
                if info["duration_s"] > 0:
                    updates["ref_duration_s"] = info["duration_s"]
            if not p.ref_original_path:
                updates["ref_original_path"] = p.ref_audio_path
        if updates:
            items[idx] = p.model_copy(update=updates)
            changed = True
    if changed:
        _write_all(items)
    return items


def _write_all(profiles: list[VoiceProfile]) -> None:
    ensure_data_dirs()
    write_json_atomic(PROFILES_JSON, [p.model_dump() for p in profiles])


def list_profiles() -> list[VoiceProfile]:
    return _read_all()


def get_profile(identifier: str) -> Optional[VoiceProfile]:
    profiles = _read_all()
    low = identifier.strip().lower()
    for p in profiles:
        if p.id.lower() == low or p.name.lower() == low:
            return p
    return None


@json_transaction
def create_profile(
    *,
    name: str,
    language: str,
    engine: str,
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
    ref_24k = ""
    ref_duration_s = 0.0
    if ref_audio_path and Path(ref_audio_path).exists():
        ext = Path(ref_audio_path).suffix or ".wav"
        dst = pdir / f"ref{ext}"
        shutil.copy2(ref_audio_path, dst)
        stored_audio = str(dst)
        info = probe_audio_info(dst)
        ref_duration_s = info["duration_s"]
        try:
            r24, info24 = ensure_ref_24k(dst, pdir / "ref_24k.wav")
            ref_24k = str(r24)
            if ref_duration_s <= 0:
                ref_duration_s = info24["duration_s"]
        except Exception:
            ref_24k = ""

    now = time.time()
    prof = VoiceProfile(
        id=pid,
        name=name.strip(),
        language=language.strip() or "Spanish",
        engine=engine,  # type: ignore[arg-type]
        ref_audio_path=stored_audio,
        ref_24k_path=ref_24k,
        ref_original_path=stored_audio,
        ref_duration_s=ref_duration_s,
        ref_trimmed=False,
        ref_text=ref_text.strip(),
        spk_path=str(pdir / "voice.spk"),
        rvq_path=str(pdir / "voice.rvq"),
        ready=_is_inline_clone_ready(engine, stored_audio),
        created_at=now,
        updated_at=now,
    )
    profiles.append(prof)
    _write_all(profiles)
    return prof


@json_transaction
def update_profile(
    pid: str,
    *,
    name: Optional[str] = None,
    language: Optional[str] = None,
    engine: Optional[str] = None,
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
        new_orig = p.ref_original_path or p.ref_audio_path
        new_24k = p.ref_24k_path
        new_dur = p.ref_duration_s
        new_trimmed = p.ref_trimmed
        if ref_audio_path is not None and ref_audio_path != p.ref_audio_path:
            if ref_audio_path and Path(ref_audio_path).exists():
                ext = Path(ref_audio_path).suffix or ".wav"
                dst = pdir / f"ref{ext}"
                if Path(ref_audio_path).absolute() != dst.absolute():
                    shutil.copy2(ref_audio_path, dst)
                new_audio = str(dst)
                new_orig = str(dst)
                audio_changed = True
                new_trimmed = False
                info = probe_audio_info(dst)
                new_dur = info["duration_s"]
                try:
                    r24, _ = ensure_ref_24k(dst, pdir / "ref_24k.wav")
                    new_24k = str(r24)
                except Exception:
                    new_24k = ""
        elif new_audio and Path(new_audio).exists() and (not new_24k or not Path(new_24k).exists()):
            try:
                r24, info24 = ensure_ref_24k(Path(new_audio), pdir / "ref_24k.wav")
                new_24k = str(r24)
                if new_dur <= 0:
                    new_dur = info24["duration_s"]
            except Exception:
                pass

        next_engine = engine if engine is not None else p.engine
        if ready is not None:
            next_ready = ready
        elif _is_inline_clone_ready(next_engine, new_audio):
            next_ready = True
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
                "ref_24k_path": new_24k,
                "ref_original_path": new_orig,
                "ref_duration_s": new_dur,
                "ref_trimmed": new_trimmed,
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


@json_transaction
def trim_profile_audio(pid: str, max_seconds: float = 12.0) -> Optional[VoiceProfile]:
    """Create a trimmed 24 kHz mono reference copy for profile pid without altering original audio."""
    profiles = _read_all()
    for idx, p in enumerate(profiles):
        if p.id != pid:
            continue
        src_str = p.ref_original_path or p.ref_audio_path
        if not src_str or not Path(src_str).exists():
            return None
        pdir = DEFAULT_PROFILES_DIR / pid
        pdir.mkdir(parents=True, exist_ok=True)
        dst = pdir / "ref_trim_24k.wav"
        _, info = trim_ref_audio(Path(src_str), dst, max_seconds=max_seconds)
        updated = p.model_copy(
            update={
                "ref_audio_path": str(dst),
                "ref_24k_path": str(dst),
                "ref_original_path": src_str,
                "ref_duration_s": info["duration_s"],
                "ref_trimmed": True,
                "ready": _is_inline_clone_ready(p.engine, str(dst)),
                "updated_at": time.time(),
            }
        )
        profiles[idx] = updated
        _write_all(profiles)
        return updated
    return None


@json_transaction
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
