"""CrispASR CLI bridge — shared C++ runtime for TTS/STT backends.

Binary layout (Windows):
  runtime/bin/cuda/crispasr.exe   ← TopBar GPU
  runtime/bin/cpu/crispasr.exe    ← TopBar CPU

Resolution order for device=gpu:
  CRISPASR_BIN → cuda/ → flat runtime/bin/ → cpu/ → PATH

Resolution order for device=cpu:
  CRISPASR_BIN → cpu/ → flat runtime/bin/ → cuda/ (+ --no-gpu) → PATH
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Literal, Optional

from .config import APP_ROOT

DeviceKind = Literal["gpu", "cpu"]

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


def _exe_names() -> list[str]:
    return ["crispasr.exe", "crispasr"] if sys.platform == "win32" else ["crispasr", "crispasr.exe"]


def _find_in_dir(directory: Path) -> Optional[Path]:
    if not directory.is_dir():
        return None
    for name in _exe_names():
        p = directory / name
        if p.is_file():
            return p
    return None


def resolve_crispasr_bin(
    app_root: Optional[Path] = None,
    *,
    device: DeviceKind = "gpu",
) -> tuple[Optional[Path], bool]:
    """Return (binary_path, force_no_gpu).

    force_no_gpu is True when CPU was requested but only a CUDA build was found.
    """
    env = (os.environ.get("CRISPASR_BIN") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            # Caller asked for CPU via selector but forced a specific bin — still pass --no-gpu.
            return p, device == "cpu"

    bin_dir = resolve_runtime_bin_dir(app_root)
    cuda_bin = _find_in_dir(bin_dir / "cuda")
    cpu_bin = _find_in_dir(bin_dir / "cpu")
    flat_bin = _find_in_dir(bin_dir)

    if device == "cpu":
        if cpu_bin:
            return cpu_bin, False
        if flat_bin:
            return flat_bin, True
        if cuda_bin:
            return cuda_bin, True
    else:
        if cuda_bin:
            return cuda_bin, False
        if flat_bin:
            return flat_bin, False
        if cpu_bin:
            return cpu_bin, False

    which_name = "crispasr.exe" if sys.platform == "win32" else "crispasr"
    which = shutil.which(which_name)
    if which:
        return Path(which), device == "cpu"
    if sys.platform == "win32":
        which = shutil.which("crispasr")
        if which:
            return Path(which), device == "cpu"
    return None, False


def is_available(app_root: Optional[Path] = None, *, device: Optional[DeviceKind] = None) -> bool:
    if device is None:
        # Any variant counts for catalog promotion.
        for d in ("gpu", "cpu"):
            path, _ = resolve_crispasr_bin(app_root, device=d)  # type: ignore[arg-type]
            if path is not None:
                return True
        return False
    path, _ = resolve_crispasr_bin(app_root, device=device)
    return path is not None


def backend_for_engine(engine: str) -> Optional[str]:
    return ENGINE_BACKEND.get((engine or "").strip().lower())


def supports_engine(
    engine: str,
    app_root: Optional[Path] = None,
    *,
    model_dir: Optional[Path] = None,
    device: Optional[DeviceKind] = None,
) -> bool:
    """True when CrispASR can synthesize for this engine right now."""
    if backend_for_engine(engine) is None or not is_available(app_root, device=device):
        return False
    eng = (engine or "").strip().lower()
    if eng in CRISPASR_AUTO_ENGINES:
        return True
    if eng in {"f5", "f5-tts"}:
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
    force_no_gpu: bool = False,
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
    if force_no_gpu:
        cmd.append("--no-gpu")
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
    device: DeviceKind = "gpu",
    timeout_s: float = 300.0,
    app_root: Optional[Path] = None,
) -> dict:
    binary, force_no_gpu = resolve_crispasr_bin(app_root, device=device)
    if binary is None:
        raise FileNotFoundError(
            "CrispASR binary not found. Place cuda/ and cpu/ under runtime/bin/ "
            "(scripts/fetch-crispasr.ps1) or set CRISPASR_BIN. See runtime/bin/README.md"
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
        force_no_gpu=force_no_gpu,
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(binary.parent),  # DLLs next to the chosen variant
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
        "device": device,
        "binary": str(binary),
        "force_no_gpu": force_no_gpu,
        "out_path": str(out_path),
        "model": str(gguf) if gguf else "auto",
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(rtf, 3),
    }
