from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from .audio_adaptation import adapt_audio_for_engine, engine_supports_cloning
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
    ref_original_text: str = ""
    spk_path: str = ""
    rvq_path: str = ""
    ready: bool = False
    created_at: float
    updated_at: float


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"voice-{uuid.uuid4().hex[:6]}"


def align_transcript_for_trim(
    original_text: str,
    full_duration_s: float,
    trim_seconds: float,
) -> str:
    """Keep leading word-aligned transcript proportional to the trimmed audio clip."""
    cleaned = (original_text or "").strip()
    if not cleaned or full_duration_s <= 0 or trim_seconds <= 0 or trim_seconds >= full_duration_s:
        return cleaned
    words = cleaned.split()
    if len(words) <= 1:
        return cleaned
    ratio = max(0.05, min(1.0, float(trim_seconds) / float(full_duration_s)))
    keep = max(1, min(len(words), round(len(words) * ratio)))
    return " ".join(words[:keep])


def _is_inline_clone_ready(engine: str, ref_audio_path: str) -> bool:
    return (engine or "").strip().lower() in INLINE_CLONE_ENGINES and bool(ref_audio_path) and Path(ref_audio_path).exists()


def _is_derived_profile_audio(candidate: Path, pdir: Path) -> bool:
    """Return True if candidate is an internal converted/trimmed copy rather than the user's original."""
    try:
        resolved_cand = candidate.resolve()
        resolved_dir = pdir.resolve()
        if resolved_dir not in resolved_cand.parents:
            return False
    except OSError:
        return False
    name = candidate.name.lower()
    return (
        name in {"ref_24k.wav", "ref_trim_24k.wav"}
        or name.startswith("adapted_")
    )


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
        if not p.ref_original_text and p.ref_text and not p.ref_trimmed:
            updates["ref_original_text"] = p.ref_text
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
        ref_original_text=ref_text.strip(),
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
        new_orig_text = p.ref_original_text or (p.ref_text if not p.ref_trimmed else "")
        restored_from_original = False
        if ref_audio_path is not None and ref_audio_path != p.ref_audio_path:
            cand = Path(ref_audio_path)
            if ref_audio_path and cand.exists():
                if new_orig and cand.absolute() == Path(new_orig).absolute():
                    # Restoring the untouched original file (e.g. undoing a previous trim).
                    new_audio = new_orig
                    new_trimmed = False
                    audio_changed = True
                    restored_from_original = True
                    info = probe_audio_info(cand)
                    new_dur = info["duration_s"]
                    try:
                        r24, _ = ensure_ref_24k(cand, pdir / "ref_24k.wav")
                        new_24k = str(r24)
                    except Exception:
                        new_24k = ""
                elif _is_derived_profile_audio(cand, pdir):
                    # Derived copy inside profile folder: preserve ref_original_path untouched.
                    new_audio = str(cand)
                    audio_changed = True
                    info = probe_audio_info(cand)
                    new_dur = info["duration_s"]
                else:
                    ext = cand.suffix or ".wav"
                    dst = pdir / f"ref{ext}"
                    if cand.absolute() != dst.absolute():
                        shutil.copy2(cand, dst)
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
        if next_engine != p.engine:
            src_for_adapt = Path(new_orig) if new_orig and Path(new_orig).is_file() else (Path(new_audio) if new_audio and Path(new_audio).is_file() else None)
            if src_for_adapt is not None and engine_supports_cloning(next_engine):
                try:
                    adapt_audio_for_engine(src_for_adapt, next_engine, pdir / "adapted")
                except Exception:
                    pass
        if ready is not None:
            next_ready = ready
        elif _is_inline_clone_ready(next_engine, new_audio):
            next_ready = True
        elif audio_changed or (engine is not None and engine != p.engine):
            next_ready = False
        else:
            next_ready = p.ready
        if ref_text is not None:
            next_text = ref_text.strip()
            if not new_trimmed:
                new_orig_text = next_text
        elif restored_from_original and new_orig_text:
            next_text = new_orig_text
        else:
            next_text = p.ref_text

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
                "ref_text": next_text,
                "ref_original_text": new_orig_text,
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
        orig_dur = probe_audio_info(Path(src_str))["duration_s"] or p.ref_duration_s
        dst = pdir / "ref_trim_24k.wav"
        _, info = trim_ref_audio(Path(src_str), dst, max_seconds=max_seconds)
        orig_text = p.ref_original_text or p.ref_text
        aligned_text = align_transcript_for_trim(orig_text, orig_dur, info["duration_s"])
        updated = p.model_copy(
            update={
                "ref_audio_path": str(dst),
                "ref_24k_path": str(dst),
                "ref_original_path": src_str,
                "ref_duration_s": info["duration_s"],
                "ref_trimmed": True,
                "ref_text": aligned_text,
                "ref_original_text": orig_text,
                "ready": _is_inline_clone_ready(p.engine, str(dst)),
                "updated_at": time.time(),
            }
        )
        profiles[idx] = updated
        _write_all(profiles)
        return updated
    return None


@json_transaction
def switch_profile_engine(
    pid: str,
    engine: str,
    *,
    preserve_original: bool = True,
) -> Optional[VoiceProfile]:
    """
    Switch a profile's target TTS engine without mutating its original reference audio.
    Prepares an engine-specific adapted WAV inside `<profile_dir>/adapted/`.
    """
    profiles = _read_all()
    target = next((item for item in profiles if item.id == pid), None)
    if target is None:
        return None
    src_str = target.ref_original_path or target.ref_audio_path
    pdir = DEFAULT_PROFILES_DIR / pid
    if src_str and Path(src_str).is_file() and engine_supports_cloning(engine):
        adapt_audio_for_engine(Path(src_str), engine, pdir / "adapted")
    updated = update_profile(pid, engine=engine)
    if updated is not None and preserve_original and target.ref_original_path:
        if updated.ref_original_path != target.ref_original_path:
            all_items = _read_all()
            for idx, item in enumerate(all_items):
                if item.id == pid:
                    all_items[idx] = item.model_copy(update={"ref_original_path": target.ref_original_path})
                    _write_all(all_items)
                    return all_items[idx]
    return updated


@json_transaction
def restore_original_audio(pid: str) -> Optional[VoiceProfile]:
    """Restore a trimmed profile back to its untouched `ref_original_path` and `ref_original_text`."""
    profiles = _read_all()
    target = next((item for item in profiles if item.id == pid), None)
    if target is None or not target.ref_original_path or not Path(target.ref_original_path).is_file():
        return None
    restored_text = target.ref_original_text or target.ref_text
    return update_profile(pid, ref_audio_path=target.ref_original_path, ref_text=restored_text)


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
