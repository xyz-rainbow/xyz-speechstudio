"""CrispASR CLI + persistent HTTP server bridge for native C++ TTS/STT backends.

Binary layout (Windows):
  runtime/bin/cuda/crispasr.exe   ← TopBar GPU
  runtime/bin/cpu/crispasr.exe    ← TopBar CPU

Resolution order for device=gpu:
  CRISPASR_BIN → cuda/ → flat runtime/bin/ → cpu/ → PATH

Resolution order for device=cpu:
  CRISPASR_BIN → cpu/ → flat runtime/bin/ → cuda/ (+ --no-gpu) → PATH
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
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
    "f5": "f5-tts",
    "f5-tts": "f5-tts",
    "qwen": "qwen3-tts",
    "qwen3-tts": "qwen3-tts",
    "chatterbox": "chatterbox",
    "chatterbox-turbo": "chatterbox-turbo",
    "cosyvoice3": "cosyvoice3-tts",
    "cosyvoice3-tts": "cosyvoice3-tts",
    "orpheus": "orpheus",
    "indextts": "indextts",
    "bark": "bark",
    "dia": "dia",
    "zonos": "zonos",
    "csm": "csm",
    "supertonic": "supertonic",
    "pocket-tts": "pocket-tts",
    "melotts": "melotts",
    "outetts": "outetts",
    "vibevoice": "vibevoice",
}

# Engines that can use `-m auto` without a pre-downloaded local GGUF.
CRISPASR_AUTO_ENGINES = frozenset({
    "piper",
    "kokoro",
    "qwen",
    "qwen3-tts",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3",
    "cosyvoice3-tts",
    "orpheus",
    "indextts",
})
# Catalog promotion set (see downloader._runtime_supported_for_builtin).
CRISPASR_READY_ENGINES = frozenset({
    "piper",
    "kokoro",
    "f5",
    "f5-tts",
    "qwen",
    "qwen3-tts",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3",
    "cosyvoice3-tts",
    "orpheus",
    "indextts",
})

# Backends verified to support `--server` + POST /v1/audio/speech cleanly.
SERVER_SUPPORTED_BACKENDS = frozenset({
    "piper",
    "kokoro",
    "qwen3-tts",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3-tts",
    "indextts",
    "orpheus",
})

CLONING_BACKENDS = frozenset({
    "qwen3-tts",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3-tts",
    "indextts",
    "f5-tts",
})

# Speech Studio STT model/engine id → CrispASR --backend name
STT_MODEL_BACKEND: dict[str, str] = {
    "whisper": "whisper",
    "parakeet": "parakeet",
    "moonshine": "moonshine",
    "canary": "canary",
    "sensevoice": "sensevoice",
    "granite": "granite",
    "voxtral": "voxtral",
    "cohere": "cohere",
    "qwen3-asr": "qwen3",
    "funasr": "funasr",
    "paraformer": "paraformer",
    "wav2vec2": "wav2vec2",
    "nemotron": "nemotron",
    "gigaam": "gigaam",
}

_backends_lock = threading.Lock()
_backends_cache: dict[str, set[str]] | None = None


def list_compiled_backends(app_root: Optional[Path] = None) -> dict[str, set[str]]:
    """Query and cache `crispasr --list-backends-json` as {backend_name: {caps}}."""
    global _backends_cache
    with _backends_lock:
        if _backends_cache is not None:
            return _backends_cache
    binary, _ = resolve_crispasr_bin(app_root)
    if binary is None:
        return {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [str(binary), "--list-backends-json"],
            cwd=str(binary.parent),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15.0,
            creationflags=creationflags,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        payload = json.loads(proc.stdout)
        parsed = {
            str(b["name"]).strip().lower(): set(str(c) for c in (b.get("caps") or []))
            for b in (payload.get("backends") or [])
            if b.get("name")
        }
        with _backends_lock:
            _backends_cache = parsed
        return parsed
    except Exception:
        return {}


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
    """Return (binary_path, force_no_gpu)."""
    env = (os.environ.get("CRISPASR_BIN") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
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
        for d in ("gpu", "cpu"):
            path, _ = resolve_crispasr_bin(app_root, device=d)  # type: ignore[arg-type]
            if path is not None:
                return True
        return False
    path, _ = resolve_crispasr_bin(app_root, device=device)
    return path is not None


def backend_for_engine(engine: str, model_dir: Optional[Path] = None) -> Optional[str]:
    eng = (engine or "").strip().lower()
    if eng == "chatterbox" and model_dir and model_dir.is_dir():
        if any(model_dir.rglob("*chatterbox-turbo*.gguf")) and not any(
            model_dir.rglob("*chatterbox-v3*.gguf")
        ):
            return "chatterbox-turbo"
    return ENGINE_BACKEND.get(eng)


def supports_engine(
    engine: str,
    app_root: Optional[Path] = None,
    *,
    model_dir: Optional[Path] = None,
    device: Optional[DeviceKind] = None,
) -> bool:
    """True when CrispASR can synthesize for this engine right now."""
    if backend_for_engine(engine, model_dir=model_dir) is None or not is_available(app_root, device=device):
        return False
    eng = (engine or "").strip().lower()
    if eng in CRISPASR_AUTO_ENGINES:
        return True
    if eng in {"f5", "f5-tts"}:
        # Safetensors/pt checkpoints (like Spanish F5) belong on the Python F5 worker unless GGUF exists.
        if model_dir and model_dir.is_dir() and any(model_dir.rglob("*.gguf")):
            return True
        return model_dir is None
    return find_gguf_model(model_dir, engine=engine) is not None


def language_code(language: str) -> str:
    raw = (language or "en").strip()
    if len(raw) <= 3 and raw.isalpha():
        return raw.lower()
    return LANG_LABEL_TO_CODE.get(raw.lower(), "en")


def find_gguf_model(model_dir: Optional[Path], engine: Optional[str] = None) -> Optional[Path]:
    """Resolve the primary LLM/diffusion GGUF for a given engine, ignoring companion/vocoder/legacy GGUFs."""
    if not model_dir or not model_dir.is_dir():
        return None
    ggufs = sorted(model_dir.rglob("*.gguf"))
    if not ggufs:
        return None
    eng = (engine or "").strip().lower()
    if eng in {"qwen", "qwen3-tts"}:
        # Legacy Serveurperso qwen-talker-* / qwen-tokenizer-* GGUFs are incompatible with CrispASR qwen3-tts.
        ggufs = [
            p for p in ggufs if not p.name.lower().startswith(("qwen-talker-", "qwen-tokenizer-"))
        ]
        return ggufs[0] if ggufs else None
    if eng in {"chatterbox", "chatterbox-turbo"}:
        t3 = [p for p in ggufs if "t3" in p.name.lower() and "s3gen" not in p.name.lower()]
        return t3[0] if t3 else ggufs[0]
    if eng in {"cosyvoice3", "cosyvoice3-tts"}:
        llm = [
            p
            for p in ggufs
            if "llm" in p.name.lower()
            and not any(x in p.name.lower() for x in ("campplus", "flow", "hift", "s3tok", "voices"))
        ]
        return llm[0] if llm else ggufs[0]
    if eng in {"indextts"}:
        gpt = [p for p in ggufs if "gpt" in p.name.lower() and "bigvgan" not in p.name.lower()]
        return gpt[0] if gpt else ggufs[0]
    return ggufs[0]


def _crispasr_cache_dir() -> Path:
    return Path.home() / ".cache" / "crispasr"


def normalize_wav_file(path: Path) -> None:
    """Rewrite a WAV with a standard header so WebView fires `ended` and can chain chunks.

    CrispASR (Kokoro in particular) sometimes returns a RIFF file the browser stalls on
    at the last frame, so playback never advances to the next section.
    """
    try:
        with wave.open(str(path), "rb") as src:
            params = src.getparams()
            frames = src.readframes(src.getnframes())
    except (wave.Error, EOFError, OSError):
        return
    if not frames:
        return
    with wave.open(str(path), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(frames)


# Full 54-voice Kokoro catalog (matching onnx-community/Kokoro-82M-v1.0-ONNX).
KOKORO_VOICES_BY_LANG: dict[str, list[str]] = {
    "es": ["ef_dora", "em_alex", "em_santa"],
    "en": [
        "af_heart", "af_bella", "af_nova", "af_sarah", "af_sky", "af_alloy",
        "af_aoede", "af_jessica", "af_kore", "af_nicole", "af_river", "af",
        "am_adam", "am_michael", "am_fenrir", "am_liam", "am_echo", "am_eric",
        "am_onyx", "am_puck",
        "bf_emma", "bf_alice", "bf_isabella", "bf_lily",
        "bm_george", "bm_daniel", "bm_fable", "bm_lewis",
    ],
    "fr": ["ff_siwis"],
    "de": ["df_eva", "df_victoria", "dm_bernd", "dm_martin"],
    "it": ["if_sara", "im_nicola"],
    "pt": ["pf_dora", "pm_alex", "pm_santa"],
    "ja": ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"],
    "zh": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
    "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
}

PIPER_VOICES_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "es": [
        ("es_ES-davefx-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("es_ES-mls_10246-low-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("es_MX-ald-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "en": [
        ("en_US-lessac-medium-f16", "cstr/piper-en_US-lessac-medium-GGUF"),
        ("en_US-libritts_r-medium-f16", "cstr/piper-voices-GGUF"),
        ("en_GB-cori-medium-f16", "cstr/piper-voices-GGUF"),
    ],
    "de": [
        ("de_DE-thorsten-medium-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-eva_k-x_low-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-karlsson-low-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-kerstin-low-f16", "cstr/piper-voices-GGUF"),
        ("de_DE-ramona-low-f16", "cstr/piper-voices-GGUF"),
    ],
    "fr": [
        ("fr_FR-siwis-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("fr_FR-tom-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "it": [
        ("it_IT-paola-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("it_IT-riccardo-x_low-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "pt": [
        ("pt_BR-cadu-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("pt_BR-faber-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "ru": [
        ("ru_RU-denis-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("ru_RU-dmitri-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "nl": [
        ("nl_NL-alex-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("nl_NL-pim-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
    "pl": [
        ("pl_PL-darkman-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
        ("pl_PL-gosia-medium-f16", "LocalAI-Community/piper-voices-GGUF"),
    ],
}


def _download_hf_cache_file(repo_id: str, filename: str, dest: Optional[Path] = None) -> Optional[Path]:
    cache_dir = _crispasr_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = dest or (cache_dir / Path(filename).name)
    if target.is_file() and target.stat().st_size > 0:
        return target
    import httpx

    url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    tmp = target.with_name(target.name + ".part")
    try:
        with httpx.Client(follow_redirects=True, timeout=180.0) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                target.parent.mkdir(parents=True, exist_ok=True)
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                        fh.write(chunk)
        tmp.replace(target)
        return target
    except Exception:
        tmp.unlink(missing_ok=True)
        return None


def _pack_kokoro_bin_to_gguf(voice_id: str, bin_bytes: bytes, dest: Path) -> Path:
    """Pack a raw Kokoro FP32 style embedding (.bin, 510x1x256 floats) into a CrispASR GGUF v3 voice pack."""
    n_floats = len(bin_bytes) // 4
    n_phonemes = max(1, n_floats // 256)
    expected_bytes = n_phonemes * 256 * 4
    payload = bin_bytes[:expected_bytes]

    def kv_str(k: str, v: str) -> bytes:
        kb, vb = k.encode("utf-8"), v.encode("utf-8")
        return struct.pack("<Q", len(kb)) + kb + struct.pack("<I", 8) + struct.pack("<Q", len(vb)) + vb

    def kv_u32(k: str, v: int) -> bytes:
        kb = k.encode("utf-8")
        return struct.pack("<Q", len(kb)) + kb + struct.pack("<I", 4) + struct.pack("<I", v)

    kvs = [
        kv_str("general.architecture", "kokoro-voice"),
        kv_str("general.name", f"kokoro-voice-{voice_id}"),
        kv_str("kokoro_voice.name", voice_id),
        kv_u32("kokoro_voice.max_phonemes", n_phonemes),
        kv_u32("kokoro_voice.style_dim", 256),
        kv_str("crispasr.voice.speaker_identity", "synthetic"),
        kv_str("crispasr.voice.speaker_identity_evidence", "onnx-community/Kokoro-82M-v1.0-ONNX"),
    ]
    tname = b"voice.pack"
    tinfo = (
        struct.pack("<Q", len(tname))
        + tname
        + struct.pack("<I", 3)
        + struct.pack("<QQQ", 256, 1, n_phonemes)
        + struct.pack("<I", 0)
        + struct.pack("<Q", 0)
    )
    header = (
        b"GGUF"
        + struct.pack("<I", 3)
        + struct.pack("<Q", 1)
        + struct.pack("<Q", len(kvs))
        + b"".join(kvs)
        + tinfo
    )
    pad = (32 - (len(header) % 32)) % 32
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(header + (b"\x00" * pad) + payload)
    tmp.replace(dest)
    return dest


ORPHEUS_VOICES = ("tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe")


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

    if eng == "orpheus":
        return [{"id": v, "label": v.capitalize(), "path": v} for v in ORPHEUS_VOICES]

    if eng == "kokoro":
        if lang_iso and lang_iso in KOKORO_VOICES_BY_LANG:
            for vid in KOKORO_VOICES_BY_LANG[lang_iso]:
                seen.add(vid)
                p = _crispasr_cache_dir() / f"kokoro-voice-{vid}.gguf"
                voices.append({"id": vid, "label": f"{vid} ({lang_iso})", "path": str(p)})
        else:
            for iso, vids in KOKORO_VOICES_BY_LANG.items():
                for vid in vids:
                    if vid not in seen:
                        seen.add(vid)
                        p = _crispasr_cache_dir() / f"kokoro-voice-{vid}.gguf"
                        voices.append({"id": vid, "label": f"{vid} ({iso})", "path": str(p)})
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
        elif eng == "kokoro":
            v = "ef_dora" if lang_iso == "es" else "af_heart"
        elif eng == "orpheus":
            return ORPHEUS_VOICES[0]
        else:
            return None
    p = Path(v)
    if p.is_file():
        return str(p)
    if eng == "orpheus":
        if v.lower() in ORPHEUS_VOICES:
            return v.lower()
        return ORPHEUS_VOICES[0]
    if eng == "kokoro":
        fname = f"kokoro-voice-{v}.gguf"
        cached = _crispasr_cache_dir() / fname
        if cached.is_file() and cached.stat().st_size > 1024:
            return str(cached)
        dl = _download_hf_cache_file("cstr/kokoro-voices-GGUF", fname, dest=cached)
        if dl is not None:
            return str(dl)
        # Fallback: fetch raw FP32 voice pack from onnx-community/Kokoro-82M-v1.0-ONNX and wrap in GGUF v3.
        import httpx

        url = f"https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices/{v}.bin"
        try:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                if len(resp.content) >= 1024:
                    _pack_kokoro_bin_to_gguf(v, resp.content, cached)
                    return str(cached)
        except Exception:
            pass
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


def _ensure_cosyvoice3_companions(model_dir: Optional[Path]) -> None:
    """Ensure CosyVoice3 S3Tok / Voices / CAM++ GGUFs live next to the LLM GGUF when present."""
    if not model_dir or not model_dir.is_dir():
        return
    cache_dir = _crispasr_cache_dir()
    required = [
        "cosyvoice3-campplus-f16.gguf",
        "cosyvoice3-s3tok-f16.gguf",
        "cosyvoice3-voices.gguf",
        "cosyvoice3-hift-f16.gguf",
    ]
    for fn in required:
        target = model_dir / fn
        if target.is_file() and target.stat().st_size > 0:
            continue
        cached = cache_dir / fn
        if cached.is_file() and cached.stat().st_size > 0:
            shutil.copy2(str(cached), str(target))
        else:
            _download_hf_cache_file("cstr/cosyvoice3-0.5b-2512-GGUF", fn, dest=target)


def build_tts_command(
    *,
    binary: Path,
    engine: str,
    text: str,
    out_path: Path,
    language: str = "en",
    model_path: Optional[Path] = None,
    voice: Optional[str] = None,
    ref_audio: Optional[Path] = None,
    ref_text: Optional[str] = None,
    force_no_gpu: bool = False,
    model_dir: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
) -> list[str]:
    backend = backend_for_engine(engine, model_dir=model_dir)
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
        "--no-spoken-disclaimer",
        "--accept-marking-responsibility",
    ]
    if force_no_gpu:
        cmd.append("--no-gpu")
    if ref_audio is not None and ref_audio.is_file():
        cmd.extend(["--voice", str(ref_audio), "--i-have-rights"])
        if ref_text and ref_text.strip():
            cmd.extend(["--ref-text", ref_text.strip()])
    elif voice:
        cmd.extend(["--voice", voice])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


class CrispAsrServerManager:
    """Keeps a single persistent `crispasr --server` warm in VRAM across Play chunks & calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._key: Optional[tuple] = None
        self._port: int = 0
        self._backend: str = ""
        self._engine: str = ""
        self._device: DeviceKind = "gpu"
        self._model_arg: str = ""
        self._voice_dir = Path(tempfile.gettempdir()) / "ss_crispasr_voices"
        self._known_voices: dict[str, str] = {}
        self._active_cli_proc: Optional[subprocess.Popen] = None
        self._cancel_event = threading.Event()
        self._started_at: Optional[float] = None

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def _stop_server_locked(self) -> None:
        if self._proc is not None:
            proc = self._proc
            self._proc = None
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
        self._key = None
        self._port = 0
        self._backend = ""
        self._engine = ""
        self._model_arg = ""
        self._known_voices.clear()
        self._started_at = None

    def eject(self) -> bool:
        self.cancel_active()
        with self._lock:
            had = self._proc is not None and self._proc.poll() is None
            self._stop_server_locked()
            return had

    def cancel_active(self) -> None:
        self._cancel_event.set()
        proc = self._active_cli_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def status(self) -> dict:
        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            if self._proc is not None and not alive:
                self._stop_server_locked()
            return {
                "family": "crispasr",
                "venv_ready": is_available(),
                "script_ready": is_available(),
                "running": alive,
                "pid": self._proc.pid if alive and self._proc else None,
                "port": self._port if alive else None,
                "model_id": self._engine if alive else None,
                "device": self._device if alive else None,
                "vram_est_mib": 1400 if (alive and self._device == "gpu") else 0,
                "started_at": self._started_at if alive else None,
            }

    def _sync_voice_in_dir(
        self,
        *,
        ref_audio: Path,
        ref_text: Optional[str],
    ) -> tuple[str, bool]:
        """Stage a 24 kHz ref WAV + .txt into pure-ASCII voice_dir; return (voice_name, changed)."""
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        raw_bytes = ref_audio.read_bytes()
        h = hashlib.sha1(raw_bytes + (ref_text or "").encode("utf-8")).hexdigest()[:12]
        vname = f"ss_{h}"
        dst_wav = self._voice_dir / f"{vname}.wav"
        dst_txt = self._voice_dir / f"{vname}.txt"
        changed = False
        if not dst_wav.is_file() or self._known_voices.get(vname) != h:
            shutil.copy2(str(ref_audio), str(dst_wav))
            if ref_text and ref_text.strip():
                dst_txt.write_text(ref_text.strip(), encoding="utf-8")
            elif dst_txt.is_file():
                dst_txt.unlink(missing_ok=True)
            changed = vname not in self._known_voices or self._known_voices.get(vname) != h
            self._known_voices[vname] = h
        return vname, changed

    def ensure_server(
        self,
        *,
        binary: Path,
        engine: str,
        backend: str,
        model_arg: str,
        device: DeviceKind,
        force_no_gpu: bool,
        language: str = "en",
        cli_voice_arg: Optional[str] = None,
        cloning: bool = False,
        voice_added: bool = False,
        timeout_s: float = 60.0,
    ) -> int:
        import httpx

        lang_iso = language_code(language)
        desired_key = (str(binary), backend, model_arg, device, lang_iso, cli_voice_arg or "")
        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            if alive and self._key == desired_key and not voice_added:
                return self._port

            self._stop_server_locked()
            port = self._free_port()
            cmd = [
                str(binary),
                "--backend",
                backend,
                "-m",
                model_arg,
                "-l",
                lang_iso,
                "--server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-punctuation",
            ]
            if force_no_gpu:
                cmd.append("--no-gpu")
            if cli_voice_arg:
                cmd.extend(["--voice", cli_voice_arg])
            elif cloning:
                self._voice_dir.mkdir(parents=True, exist_ok=True)
                cmd.extend(["--voice-dir", str(self._voice_dir), "--i-have-rights"])

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                cmd,
                cwd=str(binary.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )

            # Drain merged stdout/stderr so Windows 4 KB pipe buffers never deadlock the server.
            tail_lines: list[str] = []

            def _drain() -> None:
                assert proc.stdout is not None
                try:
                    for line in proc.stdout:
                        tail_lines.append(line.rstrip())
                        if len(tail_lines) > 40:
                            del tail_lines[:-40]
                except Exception:
                    pass

            threading.Thread(target=_drain, daemon=True).start()

            deadline = time.time() + timeout_s
            ready = False
            while time.time() < deadline:
                if self._cancel_event.is_set():
                    proc.terminate()
                    raise InterruptedError("Synthesis stopped by user.")
                if proc.poll() is not None:
                    err = "\n".join(tail_lines[-12:])
                    raise RuntimeError(f"CrispASR server exited ({proc.returncode}): {err}")
                try:
                    resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                    if resp.status_code == 200:
                        ready = True
                        break
                except Exception:
                    time.sleep(0.25)

            if not ready:
                proc.terminate()
                err = "\n".join(tail_lines[-12:])
                raise TimeoutError(f"Timed out waiting for CrispASR server ({backend}): {err}")

            self._proc = proc
            self._key = desired_key
            self._port = port
            self._backend = backend
            self._engine = engine
            self._device = device
            self._model_arg = model_arg
            self._started_at = time.time()
            return port

    def run_cli_cancelable(
        self,
        *,
        cmd: list[str],
        cwd: Path,
        timeout_s: float,
    ) -> tuple[int, str, str]:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self._active_cli_proc = proc
        deadline = time.time() + timeout_s
        try:
            while proc.poll() is None:
                if self._cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        proc.kill()
                    raise InterruptedError("Synthesis stopped by user.")
                if time.time() > deadline:
                    proc.kill()
                    raise TimeoutError(f"CrispASR timed out after {timeout_s} seconds")
                time.sleep(0.1)
            out, err = proc.communicate(timeout=5)
            return proc.returncode or 0, out or "", err or ""
        finally:
            if self._active_cli_proc is proc:
                self._active_cli_proc = None


server_manager = CrispAsrServerManager()


def synthesize_tts(
    *,
    engine: str,
    text: str,
    out_path: Path,
    language: str = "en",
    model_dir: Optional[Path] = None,
    voice: Optional[str] = None,
    ref_audio: Optional[Path] = None,
    ref_text: Optional[str] = None,
    device: DeviceKind = "gpu",
    timeout_s: float = 180.0,
    app_root: Optional[Path] = None,
) -> dict:
    import httpx

    binary, force_no_gpu = resolve_crispasr_bin(app_root, device=device)
    if binary is None:
        raise FileNotFoundError(
            "CrispASR binary not found. Place cuda/ and cpu/ under runtime/bin/ "
            "(scripts/fetch-crispasr.ps1) or set CRISPASR_BIN."
        )
    text = text.strip()
    if not text:
        raise ValueError("Input text is empty.")

    server_manager.reset_cancel()
    out_path = Path(out_path).absolute()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    eng_low = (engine or "").strip().lower()
    backend = backend_for_engine(engine, model_dir=model_dir)
    if not backend:
        raise ValueError(f"Engine '{engine}' has no CrispASR backend mapping")

    if backend == "cosyvoice3-tts":
        _ensure_cosyvoice3_companions(model_dir)

    if eng_low == "piper":
        gguf = _resolve_piper_model_arg(voice, language, model_dir)
        resolved_voice = None
    else:
        gguf = find_gguf_model(model_dir, engine=engine)
        resolved_voice = None if ref_audio else resolve_voice_arg(engine, voice, model_dir=model_dir, language=language)

    model_arg = str(gguf) if gguf and gguf.is_file() else "auto"

    # Try persistent --server mode first so weights remain warm in VRAM across Play requests & chunks.
    if backend in SERVER_SUPPORTED_BACKENDS:
        try:
            voice_name: Optional[str] = None
            voice_added = False
            cli_voice: Optional[str] = None

            if backend == "kokoro" and resolved_voice:
                # Server expects preset voice pack bound at launch via --voice <gguf>.
                cli_voice = resolved_voice
            elif ref_audio is not None and ref_audio.is_file():
                voice_name, voice_added = server_manager._sync_voice_in_dir(
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                )

            port = server_manager.ensure_server(
                binary=binary,
                engine=engine,
                backend=backend,
                model_arg=model_arg,
                device=device,
                force_no_gpu=force_no_gpu,
                language=language,
                cli_voice_arg=cli_voice,
                cloning=bool(ref_audio and ref_audio.is_file()),
                voice_added=voice_added,
            )

            payload: dict = {
                "input": text,
                "language": language_code(language),
                "response_format": "wav",
                "spoken_disclaimer": False,
                "marking_attestation": "Local Speech Studio desktop synthesis.",
            }
            if voice_name:
                payload["voice"] = voice_name
                payload["consent_attestation"] = (
                    "I have the consent of the speaker whose voice this clones, or it is my own voice."
                )
            elif resolved_voice and backend != "kokoro":
                payload["voice"] = resolved_voice

            t0 = time.perf_counter()
            resp = httpx.post(
                f"http://127.0.0.1:{port}/v1/audio/speech",
                json=payload,
                timeout=timeout_s,
            )
            if server_manager.is_cancelled():
                raise InterruptedError("Synthesis stopped by user.")
            if resp.status_code == 200 and len(resp.content) > 44 and resp.content[:4] == b"RIFF":
                out_path.write_bytes(resp.content)
                normalize_wav_file(out_path)
                elapsed = time.perf_counter() - t0
                with wave.open(str(out_path), "rb") as wf:
                    sr = wf.getframerate()
                    dur = wf.getnframes() / float(sr) if sr else 0.0
                return {
                    "engine": engine,
                    "backend": backend,
                    "device": device,
                    "binary": str(binary),
                    "force_no_gpu": force_no_gpu,
                    "out_path": str(out_path),
                    "model": model_arg,
                    "duration_s": round(dur, 3),
                    "sr": sr,
                    "elapsed_s": round(elapsed, 3),
                    "rtf": round((elapsed / dur) if dur > 0 else 0.0, 3),
                    "persistent_server": True,
                }
        except InterruptedError:
            raise
        except Exception:
            # Eject any wedged server and fall back cleanly to cancelable one-shot CLI.
            server_manager.eject()

    resolved_ref: Optional[Path] = Path(ref_audio).absolute() if ref_audio else None
    need_tmp_out = not str(out_path).isascii()
    need_tmp_ref = bool(resolved_ref and resolved_ref.is_file() and not str(resolved_ref).isascii())
    tmp_ctx = tempfile.TemporaryDirectory(prefix="crispasr_") if (need_tmp_out or need_tmp_ref) else None
    try:
        cli_out = (Path(tmp_ctx.name) / "out.wav") if (tmp_ctx is not None and need_tmp_out) else out_path
        cli_ref = resolved_ref
        if tmp_ctx is not None and need_tmp_ref and resolved_ref is not None:
            cli_ref = Path(tmp_ctx.name) / f"ref{resolved_ref.suffix or '.wav'}"
            shutil.copy2(str(resolved_ref), str(cli_ref))
        cmd = build_tts_command(
            binary=binary,
            engine=engine,
            text=text,
            out_path=cli_out,
            language=language,
            model_path=gguf,
            voice=resolved_voice,
            ref_audio=cli_ref,
            ref_text=ref_text,
            force_no_gpu=force_no_gpu,
            model_dir=model_dir,
        )

        t0 = time.perf_counter()
        rc, out_txt, err_txt = server_manager.run_cli_cancelable(
            cmd=cmd,
            cwd=binary.parent,
            timeout_s=timeout_s,
        )
        elapsed = time.perf_counter() - t0
        if rc != 0:
            err = (err_txt or out_txt or "").strip()[-1500:]
            raise RuntimeError(f"CrispASR failed ({rc}): {err or 'no output'}")
        if not cli_out.is_file() or cli_out.stat().st_size < 44:
            raise RuntimeError("CrispASR finished but no WAV was written.")
        if tmp_ctx is not None and need_tmp_out:
            shutil.move(str(cli_out), str(out_path))
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()

    normalize_wav_file(out_path)
    with wave.open(str(out_path), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.getnframes()
        dur = frames / float(sr) if sr else 0.0
    rtf = (elapsed / dur) if dur > 0 else 0.0

    return {
        "engine": engine,
        "backend": backend,
        "device": device,
        "binary": str(binary),
        "force_no_gpu": force_no_gpu,
        "out_path": str(out_path),
        "model": model_arg,
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(rtf, 3),
        "persistent_server": False,
    }


def stt_backend_for_model(model_id: str) -> Optional[str]:
    low = (model_id or "").strip().lower()
    # CTranslate2 checkpoints are executed by faster-whisper, not the GGUF backend.
    if low.startswith("faster-whisper"):
        return None
    for key, backend in STT_MODEL_BACKEND.items():
        if key in low:
            return backend
    return None


def transcribe_stt(
    *,
    model_id: str,
    audio_path: Path,
    language: Optional[str] = None,
    model_dir: Optional[Path] = None,
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
    audio_path = Path(audio_path).absolute()
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    gguf = find_gguf_model(model_dir)
    model_arg = str(gguf) if gguf else "auto"

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
            model_arg,
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
            encoding="utf-8",
            errors="replace",
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
