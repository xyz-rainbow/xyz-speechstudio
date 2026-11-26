"""Native CPU eSpeak NG formant TTS synthesis using espeak-ng shared library via ctypes."""

from __future__ import annotations

import ctypes
import shutil
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()
_LIB = None
_SR = 22050
_AUDIO_CHUNKS: list[bytes] = []

_LANG_MAP: dict[str, str] = {
    "spanish": "es",
    "english": "en-us",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt-br",
    "russian": "ru",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "cmn",
}

ESPEAK_VOICES_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "es": [
        ("es", "Spanish (Spain)"),
        ("es-419", "Spanish (Latin America)"),
        ("es+m1", "Spanish Male 1"),
        ("es+m3", "Spanish Male 3"),
        ("es+f2", "Spanish Female 2"),
    ],
    "en": [
        ("en-us", "English (US)"),
        ("en-gb", "English (UK)"),
        ("en-us+m1", "English US Male"),
        ("en-us+f2", "English US Female"),
    ],
    "fr": [("fr", "French"), ("fr+m1", "French Male"), ("fr+f2", "French Female")],
    "de": [("de", "German"), ("de+m1", "German Male"), ("de+f2", "German Female")],
    "it": [("it", "Italian"), ("it+m1", "Italian Male"), ("it+f2", "Italian Female")],
    "pt": [("pt-br", "Portuguese (BR)"), ("pt", "Portuguese (PT)")],
    "ru": [("ru", "Russian")],
    "nl": [("nl", "Dutch")],
    "pl": [("pl", "Polish")],
}

# t_espeak_callback(short *wav, int numsamples, espeak_EVENT *events) -> int
_CALLBACK_TYPE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)


def _synth_callback(wav_ptr, numsamples: int, _events) -> int:
    if wav_ptr and numsamples > 0:
        _AUDIO_CHUNKS.append(ctypes.string_at(wav_ptr, numsamples * 2))
    return 0


_CB_REF = _CALLBACK_TYPE(_synth_callback)


def _ensure_ascii_espeak_assets() -> tuple[Path, Path]:
    """Copy espeak-ng DLL and data to a pure-ASCII temp dir so Windows C fopen() always succeeds."""
    ascii_dir = Path(tempfile.gettempdir()) / "ss_espeak_ng"
    ascii_data = ascii_dir / "espeak-ng-data"

    import espeakng_loader

    src_data = Path(espeakng_loader.get_data_path())
    src_lib = Path(espeakng_loader.get_library_path())
    ascii_lib = ascii_dir / src_lib.name
    if not (ascii_data / "phontab").is_file():
        shutil.copytree(src_data, ascii_data, dirs_exist_ok=True)
    if not ascii_lib.is_file():
        ascii_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_lib, ascii_lib)
    return ascii_lib, ascii_data


def _init_lib():
    global _LIB, _SR
    if _LIB is not None:
        return _LIB, _SR
    lib_path, data_path = _ensure_ascii_espeak_assets()
    lib = ctypes.CDLL(str(lib_path))
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_SetSynthCallback.argtypes = [_CALLBACK_TYPE]
    lib.espeak_SetSynthCallback.restype = None
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_Synth.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    lib.espeak_Synth.restype = ctypes.c_int

    sr = lib.espeak_Initialize(2, 0, str(data_path).encode("ascii"), 0)  # 2 = AUDIO_OUTPUT_SYNCHRONOUS
    if sr <= 0:
        raise RuntimeError(f"espeak_Initialize failed (rc={sr})")
    lib.espeak_SetSynthCallback(_CB_REF)
    _LIB = lib
    _SR = int(sr)
    return _LIB, _SR


def _lang_iso(language: Optional[str]) -> str:
    raw = (language or "es").strip().lower()
    if raw in _LANG_MAP:
        return _LANG_MAP[raw][:2] if _LANG_MAP[raw].startswith("en") else _LANG_MAP[raw].split("-")[0]
    return raw[:2] if len(raw) >= 2 else "en"


def list_voices(language: Optional[str] = None) -> list[dict[str, str]]:
    iso = _lang_iso(language)
    items = ESPEAK_VOICES_BY_LANG.get(iso)
    if items is None:
        items = [(iso, iso.upper()), *ESPEAK_VOICES_BY_LANG["en"]]
    return [{"id": vid, "label": label} for vid, label in items]


def synthesize_tts(*, text: str, out_path: Path, language: str = "es", voice: Optional[str] = None) -> dict:
    clean = text.strip()
    if not clean:
        raise ValueError("Input text is empty.")

    iso = _lang_iso(language)
    v = (voice or "").strip()
    if not v or v.lower() in ("auto", "default"):
        v = _LANG_MAP.get((language or "es").strip().lower(), iso)

    t0 = time.perf_counter()
    with _LOCK:
        lib, sr = _init_lib()
        rc_voice = lib.espeak_SetVoiceByName(v.encode("utf-8"))
        if rc_voice != 0:
            lib.espeak_SetVoiceByName(iso.encode("utf-8"))
        _AUDIO_CHUNKS.clear()
        encoded = clean.encode("utf-8") + b"\x00"
        # espeakCHARS_UTF8 = 1, POS_CHARACTER = 1
        rc_synth = lib.espeak_Synth(
            encoded,
            len(encoded),
            0,
            1,
            0,
            1,
            None,
            None,
        )
        if rc_synth != 0:
            raise RuntimeError(f"eSpeak NG synthesis failed (rc={rc_synth})")
        pcm_bytes = b"".join(_AUDIO_CHUNKS)
        _AUDIO_CHUNKS.clear()

    if not pcm_bytes:
        raise RuntimeError("eSpeak NG produced no audio samples.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_bytes)

    elapsed = time.perf_counter() - t0
    dur = (len(pcm_bytes) / 2.0) / float(sr)
    return {
        "out_path": str(out_path),
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(elapsed / max(dur, 1e-4), 3),
        "engine": "espeak",
        "backend": "espeak-ng",
        "device": "cpu",
    }
