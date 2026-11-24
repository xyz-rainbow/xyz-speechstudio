"""CrispASR CLI bridge — shared C++ runtime for TTS/STT backends.

Binary resolution order:
1. CRISPASR_BIN env
2. runtime/bin/crispasr(.exe)
3. PATH (`crispasr` / `crispasr.exe`)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Optional

from .config import APP_ROOT

# Speech Studio engine id → CrispASR --backend name
ENGINE_BACKEND: dict[str, str] = {
    "piper": "piper",
    "kokoro": "kokoro",
    "espeak": "piper",  # formant fallback via Piper + espeak G2P when available
    "f5": "f5-tts",
    "f5-tts": "f5-tts",
    "qwen": "qwen3-tts",
}

# Engines that can use `-m auto` without a local GGUF (Piper).
# F5 still needs a GGUF on disk or CrispASR auto-download via engine path in synthesize.
CRISPASR_AUTO_ENGINES = frozenset({"piper"})
# Catalog promotion set (see downloader._runtime_supported_for_builtin).
CRISPASR_READY_ENGINES = frozenset({"piper", "f5", "f5-tts"})

# Display labels (Qwen/XTTS legacy) → ISO used by CrispASR -l
LANG_LABEL_TO_CODE: dict[str, str] = {
    "spanish": "es",
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
    "russian": "ru",
    "hindi": "hi",
    "arabic": "ar",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
}


def resolve_runtime_bin_dir(app_root: Optional[Path] = None) -> Path:
    root = app_root or APP_ROOT
    return root / "runtime" / "bin"


def resolve_crispasr_bin(app_root: Optional[Path] = None) -> Optional[Path]:
    env = (os.environ.get("CRISPASR_BIN") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p

    bin_dir = resolve_runtime_bin_dir(app_root)
    candidates = ["crispasr.exe", "crispasr"] if sys.platform == "win32" else ["crispasr", "crispasr.exe"]
    for name in candidates:
        p = bin_dir / name
        if p.is_file():
            return p

    which = shutil.which("crispasr.exe" if sys.platform == "win32" else "crispasr")
    if which:
        return Path(which)
    if sys.platform == "win32":
        which = shutil.which("crispasr")
        if which:
            return Path(which)
    return None


def is_available(app_root: Optional[Path] = None) -> bool:
    return resolve_crispasr_bin(app_root) is not None


def backend_for_engine(engine: str) -> Optional[str]:
    return ENGINE_BACKEND.get((engine or "").strip().lower())


def supports_engine(
    engine: str,
    app_root: Optional[Path] = None,
    *,
    model_dir: Optional[Path] = None,
) -> bool:
    """True when CrispASR can synthesize for this engine right now."""
    if backend_for_engine(engine) is None or not is_available(app_root):
        return False
    eng = (engine or "").strip().lower()
    if eng in CRISPASR_AUTO_ENGINES:
        return True
    # F5 / Kokoro / others: require a local GGUF (or rely on -m auto only for piper).
    if eng in {"f5", "f5-tts"}:
        # Allow -m auto for F5 when no local file (CrispASR can fetch F16).
        return True
    return find_gguf_model(model_dir) is not None


def language_code(language: str) -> str:
    raw = (language or "en").strip()
    if len(raw) <= 3 and raw.isalpha():
        return raw.lower()
    return LANG_LABEL_TO_CODE.get(raw.lower(), "en")


def find_gguf_model(model_dir: Optional[Path]) -> Optional[Path]:
    if not model_dir or not model_dir.is_dir():
        return None
    ggufs = sorted(model_dir.rglob("*.gguf"))
    return ggufs[0] if ggufs else None


def build_tts_command(
    *,
    binary: Path,
    engine: str,
    text: str,
    out_path: Path,
    language: str = "en",
    model_path: Optional[Path] = None,
    voice: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
) -> list[str]:
    backend = backend_for_engine(engine)
    if not backend:
        raise ValueError(f"Engine '{engine}' has no CrispASR backend mapping")

    model_arg = str(model_path) if model_path and model_path.is_file() else "auto"
    cmd = [
        str(binary),
        "--backend",
        backend,
        "-m",
        model_arg,
        "-l",
        language_code(language),
        "--tts",
        text,
        "--tts-output",
        str(out_path),
    ]
    if voice:
        cmd.extend(["--voice", voice])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def synthesize_tts(
    *,
    engine: str,
    text: str,
    out_path: Path,
    language: str = "en",
    model_dir: Optional[Path] = None,
    voice: Optional[str] = None,
    timeout_s: float = 300.0,
    app_root: Optional[Path] = None,
) -> dict:
    binary = resolve_crispasr_bin(app_root)
    if binary is None:
        raise FileNotFoundError(
            "CrispASR binary not found. Place it under runtime/bin/ or set CRISPASR_BIN. "
            "See runtime/bin/README.md"
        )
    text = text.strip()
    if not text:
        raise ValueError("Input text is empty.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gguf = find_gguf_model(model_dir)
    cmd = build_tts_command(
        binary=binary,
        engine=engine,
        text=text,
        out_path=out_path,
        language=language,
        model_path=gguf,
        voice=voice,
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(app_root or APP_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        creationflags=creationflags,
    )
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-1500:]
        raise RuntimeError(f"CrispASR failed ({proc.returncode}): {err or 'no output'}")
    if not out_path.is_file() or out_path.stat().st_size < 44:
        raise RuntimeError("CrispASR finished but no WAV was written.")

    with wave.open(str(out_path), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.getnframes()
        dur = frames / float(sr) if sr else 0.0
    rtf = (elapsed / dur) if dur > 0 else 0.0

    return {
        "engine": engine,
        "backend": backend_for_engine(engine),
        "out_path": str(out_path),
        "model": str(gguf) if gguf else "auto",
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(rtf, 3),
    }
