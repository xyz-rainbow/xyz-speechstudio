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
import tempfile
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

# Engines that can use `-m auto` without a local GGUF (Piper, Kokoro, eSpeak fallback).
CRISPASR_AUTO_ENGINES = frozenset({"piper", "kokoro", "espeak"})
# Catalog promotion set (see downloader._runtime_supported_for_builtin).
CRISPASR_READY_ENGINES = frozenset({"piper", "kokoro", "espeak", "f5", "f5-tts"})

# Speech Studio STT model/engine id → CrispASR --backend name
STT_MODEL_BACKEND: dict[str, str] = {
    "parakeet": "parakeet",
    "moonshine": "moonshine",
}

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


def _crispasr_cache_dir() -> Path:
    return Path.home() / ".cache" / "crispasr"


KOKORO_VOICES_BY_LANG: dict[str, list[str]] = {
    "en": ["af_heart"],
    "es": ["ef_dora"],
    "fr": ["ff_siwis"],
    "de": ["df_eva", "df_victoria", "dm_bernd", "dm_martin"],
}

PIPER_VOICES_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("en_US-lessac-medium-f16", "cstr/piper-en_US-lessac-medium-GGUF"),
        ("en_US-libritts_r-medium-f16", "cstr/piper-voices-GGUF"),
        ("en_GB-cori-medium-f16", "cstr/piper-voices-GGUF"),
    ],
    "de": [
        ("de_DE-thorsten-medium-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-eva_k-x_low-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-karlsson-low-f16", "cstr/piper-voices-GGUF"),
    ],
}


def _download_hf_cache_file(repo_id: str, filename: str) -> Optional[Path]:
    cache_dir = _crispasr_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    import httpx

    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    tmp = dest.with_name(dest.name + ".part")
    try:
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        fh.write(chunk)
        tmp.replace(dest)
        return dest
    except Exception:
        tmp.unlink(missing_ok=True)
        return None


def list_builtin_voices(
    engine: str,
    model_dir: Optional[Path] = None,
    language: Optional[str] = None,
) -> list[dict[str, str]]:
    """Return available built-in voices for CrispASR TTS engines, filtered by language when known."""
    eng = (engine or "").strip().lower()
    lang_iso = language_code(language) if language else ""
    voices: list[dict[str, str]] = []
    seen: set[str] = set()
    search_dirs = [d for d in (model_dir, _crispasr_cache_dir()) if d and d.is_dir()]

    if eng == "kokoro":
        if lang_iso and lang_iso in KOKORO_VOICES_BY_LANG:
            for vid in KOKORO_VOICES_BY_LANG[lang_iso]:
                seen.add(vid)
                p = _crispasr_cache_dir() / f"kokoro-voice-{vid}.gguf"
                voices.append({"id": vid, "label": f"{vid} ({lang_iso})", "path": str(p)})
        else:
            for d in search_dirs:
                for p in sorted(d.glob("kokoro-voice-*.gguf")):
                    vid = p.stem.replace("kokoro-voice-", "")
                    if vid not in seen:
                        seen.add(vid)
                        voices.append({"id": vid, "label": vid, "path": str(p)})
    elif eng == "piper":
        if lang_iso and lang_iso in PIPER_VOICES_BY_LANG:
            for vid, _repo in PIPER_VOICES_BY_LANG[lang_iso]:
                seen.add(vid)
                p = _crispasr_cache_dir() / f"piper-{vid}.gguf"
                voices.append({"id": vid, "label": f"{vid} ({lang_iso})", "path": str(p)})
        else:
            for d in search_dirs:
                for p in sorted(d.glob("piper-*.gguf")):
                    vid = p.stem.replace("piper-", "")
                    if lang_iso and not vid.lower().startswith(f"{lang_iso}_"):
                        continue
                    if vid not in seen:
                        seen.add(vid)
                        voices.append({"id": vid, "label": vid, "path": str(p)})
    return voices


def resolve_voice_arg(
    engine: str,
    voice: Optional[str],
    model_dir: Optional[Path] = None,
    language: Optional[str] = None,
) -> Optional[str]:
    eng = (engine or "").strip().lower()
    lang_iso = language_code(language) if language else ""
    v = (voice or "").strip()
    if v.lower() in ("", "auto", "default"):
        if eng == "kokoro" and lang_iso in KOKORO_VOICES_BY_LANG:
            v = KOKORO_VOICES_BY_LANG[lang_iso][0]
        else:
            return None
    p = Path(v)
    if p.is_file():
        return str(p)
    if eng == "kokoro":
        fname = f"kokoro-voice-{v}.gguf"
        cached = _crispasr_cache_dir() / fname
        if cached.is_file():
            return str(cached)
        dl = _download_hf_cache_file("cstr/kokoro-voices-GGUF", fname)
        if dl is not None:
            return str(dl)
    for item in list_builtin_voices(engine, model_dir=model_dir, language=language):
        if item["id"] == v and Path(item["path"]).is_file():
            return item["path"]
    return None


def _resolve_piper_model_arg(
    voice: Optional[str],
    language: Optional[str],
    model_dir: Optional[Path],
) -> Optional[Path]:
    v = (voice or "").strip()
    lang_iso = language_code(language) if language else ""
    if v.lower() in ("", "auto", "default"):
        if lang_iso in PIPER_VOICES_BY_LANG:
            v = PIPER_VOICES_BY_LANG[lang_iso][0][0]
        else:
            return find_gguf_model(model_dir)
    for _lang, items in PIPER_VOICES_BY_LANG.items():
        for vid, repo in items:
            if vid == v:
                dl = _download_hf_cache_file(repo, f"piper-{vid}.gguf")
                if dl is not None:
                    return dl
    cached = _crispasr_cache_dir() / f"piper-{v}.gguf"
    if cached.is_file():
        return cached
    return find_gguf_model(model_dir)


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

    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    eng_low = (engine or "").strip().lower()
    if eng_low == "piper":
        gguf = _resolve_piper_model_arg(voice, language, model_dir)
        resolved_voice = None
    else:
        gguf = find_gguf_model(model_dir)
        resolved_voice = resolve_voice_arg(engine, voice, model_dir=model_dir, language=language)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    # CrispASR uses narrow Win32 fopen() on Windows and fails on non-ASCII paths (e.g. emojis/accents).
    use_ascii_tmp = not str(out_path).isascii()
    tmp_ctx = tempfile.TemporaryDirectory(prefix="crispasr_") if use_ascii_tmp else None
    try:
        cli_out = (Path(tmp_ctx.name) / "out.wav") if tmp_ctx is not None else out_path
        cmd = build_tts_command(
            binary=binary,
            engine=engine,
            text=text,
            out_path=cli_out,
            language=language,
            model_path=gguf,
            voice=resolved_voice,
            force_no_gpu=force_no_gpu,
        )

        t0 = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(binary.parent),  # DLLs next to the chosen variant
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            creationflags=creationflags,
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[-1500:]
            raise RuntimeError(f"CrispASR failed ({proc.returncode}): {err or 'no output'}")
        if not cli_out.is_file() or cli_out.stat().st_size < 44:
            raise RuntimeError("CrispASR finished but no WAV was written.")
        if tmp_ctx is not None:
            shutil.move(str(cli_out), str(out_path))
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()

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


def stt_backend_for_model(model_id: str) -> Optional[str]:
    low = (model_id or "").strip().lower()
    for key, backend in STT_MODEL_BACKEND.items():
        if key in low:
            return backend
    return None


def transcribe_stt(
    *,
    model_id: str,
    audio_path: Path,
    language: Optional[str] = None,
    device: DeviceKind = "gpu",
    timeout_s: float = 300.0,
    app_root: Optional[Path] = None,
) -> dict:
    backend = stt_backend_for_model(model_id)
    if not backend:
        raise ValueError(f"STT model '{model_id}' has no CrispASR backend mapping")
    binary, force_no_gpu = resolve_crispasr_bin(app_root, device=device)
    if binary is None:
        raise FileNotFoundError(
            "CrispASR binary not found. Place cuda/ and cpu/ under runtime/bin/ "
            "(scripts/fetch-crispasr.ps1) or set CRISPASR_BIN."
        )
    audio_path = Path(audio_path).resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    use_ascii_tmp = not str(audio_path).isascii()
    tmp_ctx = tempfile.TemporaryDirectory(prefix="crispasr_stt_") if use_ascii_tmp else None
    try:
        if tmp_ctx is not None:
            cli_audio = Path(tmp_ctx.name) / f"in{audio_path.suffix or '.wav'}"
            shutil.copy2(str(audio_path), str(cli_audio))
        else:
            cli_audio = audio_path

        cmd = [
            str(binary),
            "--backend",
            backend,
            "-m",
            "auto",
            "-nt",
            "-np",
        ]
        if language and language.strip().lower() not in ("", "auto"):
            cmd.extend(["-l", language_code(language)])
        else:
            cmd.extend(["--lid-backend", "off"])
        if force_no_gpu:
            cmd.append("--no-gpu")
        cmd.append(str(cli_audio))

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        t0 = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(binary.parent),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            creationflags=creationflags,
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[-1500:]
            raise RuntimeError(f"CrispASR STT failed ({proc.returncode}): {err or 'no output'}")

        text = (proc.stdout or "").strip()
        dur = 0.0
        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    sr = wf.getframerate()
                    dur = wf.getnframes() / float(sr) if sr else 0.0
            except Exception:
                dur = 0.0
        segments = [{"start": 0.0, "end": round(dur, 2), "text": text}] if text else []
        return {
            "text": text,
            "language": (language or "auto").strip() or "auto",
            "duration_s": round(dur, 2),
            "elapsed_s": round(elapsed, 3),
            "segments": segments,
        }
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
