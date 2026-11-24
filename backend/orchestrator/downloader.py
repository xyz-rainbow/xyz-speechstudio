from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import urlparse

import httpx
from huggingface_hub import HfApi, hf_hub_url
from pydantic import BaseModel, Field

from .config import AppSettings, resolved_models_dir

FALLBACK_QWEN_DIR = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b")


class QuantOption(BaseModel):
    id: str
    label: str
    disk_mb: int
    vram_mib: int
    files: list[str] = Field(default_factory=list)
    compute_type: Optional[str] = None
    recommended: bool = False


class CatalogModelEntry(BaseModel):
    id: str
    name: str
    kind: Literal["tts", "stt"]
    engine: str
    repo_id: str
    description: str = ""
    runtime_supported: bool = True
    quants: list[QuantOption] = Field(default_factory=list)
    installed: bool = False
    installed_quant: Optional[str] = None
    install_dir: Optional[str] = None
    external: bool = False
    removable: bool = False
    custom: bool = False
    disk_mb: int = 0
    vram_mib: int = 0


class DownloadJob(BaseModel):
    job_id: str
    model_id: str
    name: str
    kind: Literal["tts", "stt"]
    quant: str
    status: Literal["queued", "downloading", "completed", "failed", "cancelled"] = "queued"
    progress: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    current_file: str = ""
    error: str = ""
    started_at: float = 0.0


class HfInspectFile(BaseModel):
    filename: str
    size_bytes: int
    size_mb: float
    recommended: bool = False


class HfInspectResponse(BaseModel):
    repo_id: str
    suggested_name: str
    suggested_kind: Literal["tts", "stt"]
    files: list[HfInspectFile]


BUILTIN_MODELS: list[dict[str, Any]] = [
    # --- TTS Models ---
    {
        "id": "qwen3-1.7b-base",
        "name": "Qwen3-TTS 1.7B Base",
        "kind": "tts",
        "engine": "qwen",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-1.7b", "qwen3-1.7b-base"],
        "description": "High-fidelity zero-shot voice cloning GGUF (Talker + 12Hz codec).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "Q4_K_M",
                "label": "Q4_K_M (4-bit)",
                "disk_mb": 1950,
                "vram_mib": 2200,
                "files": ["qwen-talker-1.7b-base-Q4_K_M.gguf", "qwen-tokenizer-12hz-Q4_K_M.gguf"],
            },
            {
                "id": "Q8_0",
                "label": "Q8_0 (Balanced)",
                "disk_mb": 3180,
                "vram_mib": 3300,
                "files": ["qwen-talker-1.7b-base-Q8_0.gguf", "qwen-tokenizer-12hz-Q8_0.gguf"],
                "recommended": True,
            },
            {
                "id": "BF16",
                "label": "BF16 (Full Precision)",
                "disk_mb": 4250,
                "vram_mib": 4500,
                "files": ["qwen-talker-1.7b-base-BF16.gguf", "qwen-tokenizer-12hz-BF16.gguf"],
            },
        ],
    },
    {
        "id": "qwen3-0.6b-base",
        "name": "Qwen3-TTS 0.6B Base",
        "kind": "tts",
        "engine": "qwen",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-0.6b-base"],
        "description": "Compact fast Qwen3-TTS GGUF voice cloner for low-VRAM GPUs.",
        "runtime_supported": True,
        "quants": [
            {
                "id": "Q4_K_M",
                "label": "Q4_K_M (4-bit)",
                "disk_mb": 780,
                "vram_mib": 1150,
                "files": ["qwen-talker-0.6b-base-Q4_K_M.gguf", "qwen-tokenizer-12hz-Q4_K_M.gguf"],
            },
            {
                "id": "Q8_0",
                "label": "Q8_0 (Balanced)",
                "disk_mb": 1220,
                "vram_mib": 1550,
                "files": ["qwen-talker-0.6b-base-Q8_0.gguf", "qwen-tokenizer-12hz-Q8_0.gguf"],
                "recommended": True,
            },
            {
                "id": "BF16",
                "label": "BF16 (Full Precision)",
                "disk_mb": 1750,
                "vram_mib": 2100,
                "files": ["qwen-talker-0.6b-base-BF16.gguf", "qwen-tokenizer-12hz-BF16.gguf"],
            },
        ],
    },
    {
        "id": "qwen3-1.7b-customvoice",
        "name": "Qwen3-TTS 1.7B CustomVoice",
        "kind": "tts",
        "engine": "qwen",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-1.7b-customvoice"],
        "description": "Instruction-steerable Qwen3-TTS variant with custom style & emotion control.",
        "runtime_supported": True,
        "quants": [
            {
                "id": "Q4_K_M",
                "label": "Q4_K_M (4-bit)",
                "disk_mb": 1950,
                "vram_mib": 2200,
                "files": [
                    "qwen-talker-1.7b-customvoice-Q4_K_M.gguf",
                    "qwen-tokenizer-12hz-Q4_K_M.gguf",
                ],
            },
            {
                "id": "Q8_0",
                "label": "Q8_0 (Balanced)",
                "disk_mb": 3180,
                "vram_mib": 3300,
                "files": [
                    "qwen-talker-1.7b-customvoice-Q8_0.gguf",
                    "qwen-tokenizer-12hz-Q8_0.gguf",
                ],
                "recommended": True,
            },
            {
                "id": "BF16",
                "label": "BF16 (Full Precision)",
                "disk_mb": 4250,
                "vram_mib": 4500,
                "files": [
                    "qwen-talker-1.7b-customvoice-BF16.gguf",
                    "qwen-tokenizer-12hz-BF16.gguf",
                ],
            },
        ],
    },
    {
        "id": "xtts-v2",
        "name": "Coqui XTTS v2",
        "kind": "tts",
        "engine": "xtts",
        "repo_id": "coqui/XTTS-v2",
        "dir_names": ["xtts-v2"],
        "description": "Multilingual XTTS v2 expressive voice cloner (worker hooks in Phase 4).",
        "runtime_supported": False,
        "quants": [
            {
                "id": "fp16",
                "label": "FP16 Checkpoint",
                "disk_mb": 1880,
                "vram_mib": 2300,
                "files": ["config.json", "model.pth", "vocab.json", "speakers_xtts.pth"],
                "recommended": True,
            },
        ],
    },
    # --- STT Models ---
    {
        "id": "faster-whisper-tiny",
        "name": "Faster-Whisper Tiny",
        "kind": "stt",
        "engine": "faster-whisper",
        "repo_id": "Systran/faster-whisper-tiny",
        "model_size": "tiny",
        "description": "Ultra-fast CTranslate2 speech recognition (~250 MiB VRAM).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "int8",
                "label": "INT8",
                "compute_type": "int8",
                "disk_mb": 45,
                "vram_mib": 220,
            },
            {
                "id": "int8_float16",
                "label": "INT8_FP16 (Balanced)",
                "compute_type": "int8_float16",
                "disk_mb": 78,
                "vram_mib": 250,
                "recommended": True,
            },
            {
                "id": "float16",
                "label": "FP16",
                "compute_type": "float16",
                "disk_mb": 82,
                "vram_mib": 320,
            },
        ],
    },
    {
        "id": "faster-whisper-base",
        "name": "Faster-Whisper Base",
        "kind": "stt",
        "engine": "faster-whisper",
        "repo_id": "Systran/faster-whisper-base",
        "model_size": "base",
        "description": "Fast everyday transcription & Live Captions default (~350 MiB VRAM).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "int8",
                "label": "INT8",
                "compute_type": "int8",
                "disk_mb": 80,
                "vram_mib": 300,
            },
            {
                "id": "int8_float16",
                "label": "INT8_FP16 (Balanced)",
                "compute_type": "int8_float16",
                "disk_mb": 145,
                "vram_mib": 350,
                "recommended": True,
            },
            {
                "id": "float16",
                "label": "FP16",
                "compute_type": "float16",
                "disk_mb": 150,
                "vram_mib": 460,
            },
        ],
    },
    {
        "id": "faster-whisper-small",
        "name": "Faster-Whisper Small",
        "kind": "stt",
        "engine": "faster-whisper",
        "repo_id": "Systran/faster-whisper-small",
        "model_size": "small",
        "description": "Strong multilingual accuracy with modest VRAM (~700 MiB).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "int8",
                "label": "INT8",
                "compute_type": "int8",
                "disk_mb": 255,
                "vram_mib": 580,
            },
            {
                "id": "int8_float16",
                "label": "INT8_FP16 (Balanced)",
                "compute_type": "int8_float16",
                "disk_mb": 485,
                "vram_mib": 700,
                "recommended": True,
            },
            {
                "id": "float16",
                "label": "FP16",
                "compute_type": "float16",
                "disk_mb": 490,
                "vram_mib": 960,
            },
        ],
    },
    {
        "id": "faster-whisper-medium",
        "name": "Faster-Whisper Medium",
        "kind": "stt",
        "engine": "faster-whisper",
        "repo_id": "Systran/faster-whisper-medium",
        "model_size": "medium",
        "description": "High-precision multilingual transcription (~1500 MiB VRAM).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "int8",
                "label": "INT8",
                "compute_type": "int8",
                "disk_mb": 780,
                "vram_mib": 1250,
            },
            {
                "id": "int8_float16",
                "label": "INT8_FP16 (Balanced)",
                "compute_type": "int8_float16",
                "disk_mb": 1530,
                "vram_mib": 1500,
                "recommended": True,
            },
            {
                "id": "float16",
                "label": "FP16",
                "compute_type": "float16",
                "disk_mb": 1540,
                "vram_mib": 2100,
            },
        ],
    },
    {
        "id": "faster-whisper-large-v3-turbo",
        "name": "Faster-Whisper Large v3 Turbo",
        "kind": "stt",
        "engine": "faster-whisper",
        "repo_id": "Systran/faster-whisper-large-v3-turbo",
        "model_size": "large-v3-turbo",
        "description": "Near-flagship speed & accuracy for RTX 2060 (~2100 MiB VRAM).",
        "runtime_supported": True,
        "quants": [
            {
                "id": "int8",
                "label": "INT8 (Compact)",
                "compute_type": "int8",
                "disk_mb": 840,
                "vram_mib": 1450,
            },
            {
                "id": "int8_float16",
                "label": "INT8_FP16 (Balanced)",
                "compute_type": "int8_float16",
                "disk_mb": 1620,
                "vram_mib": 2100,
                "recommended": True,
            },
            {
                "id": "float16",
                "label": "FP16",
                "compute_type": "float16",
                "disk_mb": 1640,
                "vram_mib": 2800,
            },
        ],
    },
    {
        "id": "parakeet-tdt-0.6b-v3",
        "name": "NVIDIA Parakeet TDT 0.6B v3",
        "kind": "stt",
        "engine": "onnx-asr",
        "repo_id": "istupakov/parakeet-tdt-0.6b-v3-onnx",
        "description": "Fast ONNX ASR model (downloadable; ONNX runtime hooks in Phase 4).",
        "runtime_supported": False,
        "quants": [
            {
                "id": "int8",
                "label": "INT8 ONNX",
                "disk_mb": 660,
                "vram_mib": 950,
                "files": ["encoder-model.int8.onnx", "decoder_joint-model.int8.onnx", "vocab.txt", "nemo128.onnx", "config.json"],
                "recommended": True,
            },
            {
                "id": "fp32",
                "label": "FP32 ONNX",
                "disk_mb": 2480,
                "vram_mib": 2700,
                "files": ["encoder-model.onnx", "decoder_joint-model.onnx", "vocab.txt", "nemo128.onnx", "config.json"],
            },
        ],
    },
    {
        "id": "moonshine-base",
        "name": "Moonshine Base ONNX",
        "kind": "stt",
        "engine": "onnx-asr",
        "repo_id": "onnx-community/moonshine-base-ONNX",
        "description": "Ultra-lightweight edge English STT (downloadable; ONNX runtime in Phase 4).",
        "runtime_supported": False,
        "quants": [
            {
                "id": "int8",
                "label": "INT8 ONNX",
                "disk_mb": 95,
                "vram_mib": 280,
                "files": ["onnx/encoder_model_quantized.onnx", "onnx/decoder_model_merged_quantized.onnx", "config.json", "tokenizer.json"],
                "recommended": True,
            },
        ],
    },
]

BUILTIN_BY_ID: dict[str, dict[str, Any]] = {m["id"]: m for m in BUILTIN_MODELS}

_ALLOWED_HF_EXTS = (".gguf", ".onnx", ".bin", ".safetensors", ".pth", ".pt")
_META_HF_EXTS = (".json", ".txt", ".model")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip(".-")
    return slug or f"hf-{uuid.uuid4().hex[:6]}"


def _registry_path(settings: AppSettings) -> Path:
    return resolved_models_dir(settings) / "registry.json"


def _meta_file(folder: Path) -> Path:
    return folder / ".speech_studio_model.json"


def load_custom_registry(settings: AppSettings) -> list[dict[str, Any]]:
    p = _registry_path(settings)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict) and r.get("id")]
    except Exception:
        pass
    return []


def save_custom_registry(settings: AppSettings, items: list[dict[str, Any]]) -> None:
    p = _registry_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _dir_size_mb(folder: Path) -> int:
    total = 0
    if not folder.exists():
        return 0
    for item in folder.rglob("*"):
        if item.is_file() and not item.name.endswith(".part"):
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return max(1, round(total / (1024 * 1024))) if total > 0 else 0


def _detect_builtin_install(entry: dict[str, Any], settings: AppSettings) -> tuple[bool, Optional[str], Optional[Path], bool, int]:
    """Return (installed, installed_quant, install_dir, external, disk_mb)."""
    models_root = resolved_models_dir(settings)
    mid = entry["id"]
    kind = entry["kind"]
    engine = entry["engine"]

    if engine == "qwen":
        dir_names: list[str] = entry.get("dir_names", [mid])
        candidates: list[tuple[Path, bool]] = []
        for dn in dir_names:
            candidates.append((models_root / "tts" / dn, False))
            candidates.append((models_root / dn, False))
        candidates.append((models_root, False))
        if mid == "qwen3-1.7b-base":
            candidates.append((FALLBACK_QWEN_DIR, True))

        for base_dir, is_ext in candidates:
            if not base_dir.is_dir():
                continue
            for q in entry["quants"]:
                if all((base_dir / f).is_file() for f in q.get("files", [])):
                    meta_q = q["id"]
                    mf = _meta_file(base_dir)
                    if mf.is_file():
                        try:
                            meta_q = json.loads(mf.read_text(encoding="utf-8")).get("quant") or meta_q
                        except Exception:
                            pass
                    size_mb = sum(
                        max(1, round((base_dir / f).stat().st_size / (1024 * 1024)))
                        for f in q["files"]
                    )
                    return True, meta_q, base_dir, is_ext, size_mb
        return False, None, None, False, 0

    if kind == "stt":
        stt_root = models_root / "stt"
        direct_dir = stt_root / mid
        if direct_dir.is_dir():
            meta_q = entry["quants"][0]["id"] if entry["quants"] else "default"
            mf = _meta_file(direct_dir)
            if mf.is_file():
                try:
                    meta_q = json.loads(mf.read_text(encoding="utf-8")).get("quant") or meta_q
                except Exception:
                    pass
            has_weights = (direct_dir / "model.bin").is_file() or any(
                direct_dir.rglob("*.onnx")
            )
            if has_weights:
                return True, meta_q, direct_dir, False, _dir_size_mb(direct_dir)

        # Also detect HuggingFace Hub cache downloaded by faster-whisper itself under stt/
        repo_cache_name = f"models--{entry['repo_id'].replace('/', '--')}"
        cache_dir = stt_root / repo_cache_name
        if cache_dir.is_dir() and any(cache_dir.rglob("model.bin")):
            return True, "int8_float16", cache_dir, False, _dir_size_mb(cache_dir)
        return False, None, None, False, 0

    # Other TTS (e.g. xtts-v2)
    tts_dir = models_root / "tts" / mid
    if tts_dir.is_dir() and any(
        (tts_dir / fn).is_file() for fn in ("model.pth", "config.json", "model.safetensors")
    ):
        if (tts_dir / "model.pth").is_file() or (tts_dir / "model.safetensors").is_file():
            q_id = entry["quants"][0]["id"] if entry["quants"] else "fp16"
            return True, q_id, tts_dir, False, _dir_size_mb(tts_dir)
    return False, None, None, False, 0


def resolve_qwen_paths(settings: AppSettings, model_id: Optional[str] = None) -> tuple[Path, Path, str]:
    """Find best installed Qwen3-TTS (talker_gguf, codec_gguf, resolved_model_id)."""
    preferred_id = model_id or settings.active_tts_model or "qwen3-1.7b-base"
    # Map legacy default name "qwen3-1.7b-base-Q8_0" -> "qwen3-1.7b-base"
    if preferred_id.startswith("qwen3-1.7b-base"):
        preferred_id = "qwen3-1.7b-base"

    order = [BUILTIN_BY_ID[preferred_id]] if preferred_id in BUILTIN_BY_ID else []
    for m in BUILTIN_MODELS:
        if m["engine"] == "qwen" and m["id"] != preferred_id:
            order.append(m)

    for entry in order:
        installed, q_id, install_dir, _, _ = _detect_builtin_install(entry, settings)
        if installed and install_dir and q_id:
            for q in entry["quants"]:
                if q["id"] == q_id:
                    talker = install_dir / q["files"][0]
                    codec = install_dir / q["files"][1]
                    if talker.is_file() and codec.is_file():
                        return talker, codec, f"{entry['id']}-{q_id}"

    # Check custom installed GGUF TTS models in registry
    models_root = resolved_models_dir(settings)
    for custom in load_custom_registry(settings):
        if custom.get("kind") == "tts":
            cdir = models_root / "tts" / custom["id"]
            if cdir.is_dir():
                ggufs = sorted(cdir.glob("*.gguf"))
                if len(ggufs) >= 2:
                    talkers = [g for g in ggufs if "talker" in g.name.lower()]
                    codecs = [g for g in ggufs if "tokenizer" in g.name.lower() or "codec" in g.name.lower()]
                    if talkers and codecs:
                        return talkers[0], codecs[0], custom["id"]

    raise FileNotFoundError(
        f"Qwen3-TTS GGUF files not found in {models_root} or {FALLBACK_QWEN_DIR}."
    )


def resolve_stt_load_target(settings: AppSettings, model_id: str) -> tuple[str, Optional[str], int]:
    """Return (whisper_model_arg, compute_type_override, vram_est_mib)."""
    entry = BUILTIN_BY_ID.get(model_id)
    if entry and entry["kind"] == "stt":
        installed, q_id, install_dir, _, _ = _detect_builtin_install(entry, settings)
        compute_type: Optional[str] = None
        vram_est = entry["quants"][0]["vram_mib"] if entry.get("quants") else 350
        for q in entry.get("quants", []):
            if q["id"] == q_id:
                compute_type = q.get("compute_type")
                vram_est = q["vram_mib"]
                break
        if installed and install_dir and (install_dir / "model.bin").is_file():
            return str(install_dir), compute_type, vram_est
        return entry.get("model_size", "base"), compute_type, vram_est

    # Custom HF STT model
    for custom in load_custom_registry(settings):
        if custom["id"] == model_id and custom.get("kind") == "stt":
            cdir = resolved_models_dir(settings) / "stt" / model_id
            if cdir.is_dir() and (cdir / "model.bin").is_file():
                return str(cdir), None, 700
            return custom["repo_id"], None, 700

    return "base", None, 350


def build_catalog(settings: AppSettings) -> list[CatalogModelEntry]:
    models_root = resolved_models_dir(settings)
    entries: list[CatalogModelEntry] = []

    for m in BUILTIN_MODELS:
        installed, q_id, install_dir, is_ext, disk_mb = _detect_builtin_install(m, settings)
        quants = [QuantOption(**q) for q in m.get("quants", [])]
        rec_q = next((q for q in quants if q.recommended), quants[0] if quants else None)
        active_q = next((q for q in quants if q.id == q_id), rec_q)
        entries.append(
            CatalogModelEntry(
                id=m["id"],
                name=m["name"],
                kind=m["kind"],
                engine=m["engine"],
                repo_id=m["repo_id"],
                description=m.get("description", ""),
                runtime_supported=m.get("runtime_supported", True),
                quants=quants,
                installed=installed,
                installed_quant=q_id,
                install_dir=str(install_dir) if install_dir else None,
                external=is_ext,
                removable=installed and not is_ext and install_dir is not None and _is_within(install_dir, models_root),
                custom=False,
                disk_mb=disk_mb if installed else (active_q.disk_mb if active_q else 0),
                vram_mib=active_q.vram_mib if active_q else 0,
            )
        )

    # Custom HF models from registry.json
    for custom in load_custom_registry(settings):
        cid = custom["id"]
        kind = custom.get("kind", "stt")
        sub = "stt" if kind == "stt" else "tts"
        cdir = models_root / sub / cid
        installed = cdir.is_dir() and any(
            f.is_file() and f.suffix.lower() in _ALLOWED_HF_EXTS for f in cdir.rglob("*")
        )
        disk_mb = _dir_size_mb(cdir) if installed else int(custom.get("disk_mb", 0))
        files = [str(f) for f in custom.get("files", [])]
        is_ct2 = kind == "stt" and any(Path(f).name == "model.bin" for f in files)
        is_gguf_qwen = kind == "tts" and any(f.lower().endswith(".gguf") for f in files)
        entries.append(
            CatalogModelEntry(
                id=cid,
                name=custom.get("name", cid),
                kind=kind,
                engine="faster-whisper" if is_ct2 else ("qwen" if is_gguf_qwen else "custom-hf"),
                repo_id=custom.get("repo_id", ""),
                description=f"Custom HF: {custom.get('repo_id', '')}",
                runtime_supported=is_ct2 or is_gguf_qwen,
                quants=[
                    QuantOption(
                        id="custom",
                        label="Custom HF Selection",
                        disk_mb=int(custom.get("disk_mb", disk_mb or 500)),
                        vram_mib=int(custom.get("vram_mib", 1200)),
                        files=files,
                        recommended=True,
                    )
                ],
                installed=installed,
                installed_quant="custom" if installed else None,
                install_dir=str(cdir) if installed else None,
                external=False,
                removable=installed and _is_within(cdir, models_root),
                custom=True,
                disk_mb=disk_mb,
                vram_mib=int(custom.get("vram_mib", 1200)),
            )
        )

    # Sort: installed first (external/local ready before downloadable), then curated catalog order
    entries.sort(key=lambda e: (0 if e.installed else 1, e.kind))
    return entries


def parse_hf_repo_id(url_or_id: str) -> str:
    raw = url_or_id.strip().rstrip("/")
    if not raw:
        raise ValueError("Hugging Face URL or repo ID is empty.")
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        if "huggingface.co" not in parsed.netloc.lower():
            raise ValueError("URL must point to huggingface.co")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("Could not extract owner/repo from Hugging Face URL.")
        return f"{parts[0]}/{parts[1]}"
    parts = [p for p in raw.split("/") if p]
    if len(parts) != 2:
        raise ValueError("Expected format owner/repo or https://huggingface.co/owner/repo")
    return f"{parts[0]}/{parts[1]}"


def inspect_hf_repo(url_or_id: str) -> HfInspectResponse:
    repo_id = parse_hf_repo_id(url_or_id)
    api = HfApi()
    info = api.model_info(repo_id, files_metadata=True)
    siblings = info.siblings or []

    files: list[HfInspectFile] = []
    for s in siblings:
        fname = getattr(s, "rfilename", "") or ""
        size = int(getattr(s, "size", 0) or 0)
        low = fname.lower()
        if low.endswith(_ALLOWED_HF_EXTS) or low in ("config.json", "tokenizer.json", "vocabulary.txt", "vocabulary.json", "preprocessor_config.json", "vocab.txt", "vocab.json"):
            rec = low.endswith((".gguf", ".onnx", "model.bin")) and "f32" not in low
            files.append(
                HfInspectFile(
                    filename=fname,
                    size_bytes=size,
                    size_mb=round(size / (1024 * 1024), 1),
                    recommended=rec,
                )
            )

    low_repo = repo_id.lower()
    is_tts = any(k in low_repo for k in ("tts", "xtts", "kokoro", "qwen3-tts", "bark", "f5"))
    suggested_kind: Literal["tts", "stt"] = "tts" if is_tts else "stt"
    suggested_name = repo_id.split("/")[-1].replace("-", " ")
    return HfInspectResponse(
        repo_id=repo_id,
        suggested_name=suggested_name,
        suggested_kind=suggested_kind,
        files=files,
    )


def remove_installed_model(settings: AppSettings, model_id: str) -> dict[str, Any]:
    models_root = resolved_models_dir(settings).resolve()
    catalog = build_catalog(settings)
    target = next((m for m in catalog if m.id == model_id), None)
    if target is None:
        raise FileNotFoundError(f"Unknown model: {model_id}")
    if target.external:
        raise PermissionError("External models outside app models folder cannot be deleted.")
    if not target.installed or not target.install_dir:
        raise FileNotFoundError(f"Model is not installed locally: {model_id}")

    install_path = Path(target.install_dir).resolve()
    if not _is_within(install_path, models_root):
        raise PermissionError("Refusing to delete files outside Speech Studio models folder.")

    if install_path == models_root:
        # Remove only this model's known quant files if installed at root
        removed_files = 0
        for q in target.quants:
            for fname in q.files:
                fp = install_path / fname
                if fp.is_file() and _is_within(fp, models_root):
                    fp.unlink()
                    removed_files += 1
        return {"removed": removed_files > 0, "model_id": model_id}

    shutil.rmtree(install_path, ignore_errors=False)

    if target.custom:
        reg = [r for r in load_custom_registry(settings) if r.get("id") != model_id]
        save_custom_registry(settings, reg)

    return {"removed": True, "model_id": model_id}


class _DownloadCancelled(Exception):
    pass


class DownloadManager:
    def __init__(self, notify_cb: Optional[Callable[[str, str, Optional[int]], None]] = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, DownloadJob] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._notify_cb = notify_cb

    def list_jobs(self) -> list[DownloadJob]:
        with self._lock:
            return [job.model_copy() for job in self._jobs.values()]

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            ev = self._cancels.get(job_id)
            job = self._jobs.get(job_id)
            if ev is None or job is None:
                return False
            ev.set()
            if job.status in ("queued", "downloading"):
                job.status = "cancelled"
            return True

    def start_catalog_download(
        self,
        settings: AppSettings,
        model_id: str,
        quant_id: Optional[str] = None,
    ) -> DownloadJob:
        entry = BUILTIN_BY_ID.get(model_id)
        if entry is None:
            raise ValueError(f"Unknown built-in model: {model_id}")

        quants = entry.get("quants", [])
        chosen = next((q for q in quants if q["id"] == quant_id), None) or next(
            (q for q in quants if q.get("recommended")), quants[0]
        )

        models_root = resolved_models_dir(settings)
        if entry["kind"] == "stt":
            dest_dir = models_root / "stt" / model_id
        else:
            dn = entry.get("dir_names", [model_id])[0]
            dest_dir = models_root / "tts" / dn

        explicit_files = list(chosen.get("files", []))
        return self._enqueue(
            model_id=model_id,
            name=entry["name"],
            kind=entry["kind"],
            quant=chosen["id"],
            repo_id=entry["repo_id"],
            dest_dir=dest_dir,
            explicit_files=explicit_files,
            engine=entry["engine"],
        )

    def start_custom_hf_download(
        self,
        settings: AppSettings,
        *,
        repo_id: str,
        name: str,
        kind: Literal["tts", "stt"],
        selected_files: list[str],
    ) -> DownloadJob:
        clean_id = _slugify(name or repo_id.split("/")[-1])
        models_root = resolved_models_dir(settings)
        sub = "stt" if kind == "stt" else "tts"
        dest_dir = models_root / sub / clean_id

        reg = [r for r in load_custom_registry(settings) if r.get("id") != clean_id]
        reg.append(
            {
                "id": clean_id,
                "name": name.strip() or clean_id,
                "kind": kind,
                "repo_id": repo_id,
                "files": selected_files,
                "disk_mb": 0,
                "vram_mib": 1200 if kind == "tts" else 800,
            }
        )
        save_custom_registry(settings, reg)

        return self._enqueue(
            model_id=clean_id,
            name=name.strip() or clean_id,
            kind=kind,
            quant="custom",
            repo_id=repo_id,
            dest_dir=dest_dir,
            explicit_files=selected_files,
            engine="custom-hf",
        )

    def _enqueue(
        self,
        *,
        model_id: str,
        name: str,
        kind: Literal["tts", "stt"],
        quant: str,
        repo_id: str,
        dest_dir: Path,
        explicit_files: list[str],
        engine: str,
    ) -> DownloadJob:
        with self._lock:
            for existing in self._jobs.values():
                if existing.model_id == model_id and existing.status in ("queued", "downloading"):
                    return existing.model_copy()

            job_id = uuid.uuid4().hex[:10]
            job = DownloadJob(
                job_id=job_id,
                model_id=model_id,
                name=name,
                kind=kind,
                quant=quant,
                status="queued",
                started_at=time.time(),
            )
            ev = threading.Event()
            self._jobs[job_id] = job
            self._cancels[job_id] = ev

        t = threading.Thread(
            target=self._run_job,
            args=(job_id, repo_id, dest_dir, explicit_files, engine, quant, ev),
            daemon=True,
        )
        t.start()
        return job.model_copy()

    def _run_job(
        self,
        job_id: str,
        repo_id: str,
        dest_dir: Path,
        explicit_files: list[str],
        engine: str,
        quant: str,
        cancel_ev: threading.Event,
    ) -> None:
        part_files: list[Path] = []
        last_milestone = 0
        existed_before = dest_dir.exists()

        try:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "downloading"

            dest_dir.mkdir(parents=True, exist_ok=True)
            api = HfApi()
            info = api.model_info(repo_id, files_metadata=True)
            size_map: dict[str, int] = {}
            all_repo_files: list[str] = []
            for s in info.siblings or []:
                rf = getattr(s, "rfilename", "") or ""
                if rf:
                    all_repo_files.append(rf)
                    size_map[rf] = int(getattr(s, "size", 0) or 0)

            if explicit_files:
                target_files = explicit_files
            elif engine == "faster-whisper":
                target_files = [
                    rf
                    for rf in all_repo_files
                    if rf == "model.bin"
                    or rf.endswith(_META_HF_EXTS)
                    or rf in ("config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.txt", "vocabulary.json")
                ]
            else:
                target_files = [
                    rf for rf in all_repo_files if rf.lower().endswith(_ALLOWED_HF_EXTS + _META_HF_EXTS)
                ]

            if not target_files:
                raise RuntimeError(f"No matching downloadable files found in {repo_id}.")

            total_bytes = sum(max(size_map.get(f, 0), 1) for f in target_files)
            with self._lock:
                self._jobs[job_id].total_bytes = total_bytes

            downloaded_so_far = 0
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=20.0)) as client:
                for rel_path in target_files:
                    if cancel_ev.is_set():
                        raise _DownloadCancelled()

                    out_path = dest_dir / rel_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    if out_path.is_file() and size_map.get(rel_path, 0) > 0 and out_path.stat().st_size == size_map[rel_path]:
                        downloaded_so_far += out_path.stat().st_size
                        continue

                    part_path = out_path.with_name(out_path.name + ".part")
                    part_files.append(part_path)
                    url = hf_hub_url(repo_id=repo_id, filename=rel_path)

                    with self._lock:
                        self._jobs[job_id].current_file = Path(rel_path).name

                    with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        file_len = int(resp.headers.get("content-length") or size_map.get(rel_path) or 0)
                        if size_map.get(rel_path, 0) == 0 and file_len > 0:
                            with self._lock:
                                self._jobs[job_id].total_bytes += file_len
                                total_bytes = self._jobs[job_id].total_bytes

                        with part_path.open("wb") as fh:
                            for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                                if cancel_ev.is_set():
                                    raise _DownloadCancelled()
                                fh.write(chunk)
                                downloaded_so_far += len(chunk)
                                pct = min(99, int((downloaded_so_far * 100) / max(total_bytes, 1)))
                                with self._lock:
                                    self._jobs[job_id].downloaded_bytes = downloaded_so_far
                                    self._jobs[job_id].progress = pct

                                for ms in (25, 50, 75):
                                    if pct >= ms and last_milestone < ms:
                                        last_milestone = ms
                                        if self._notify_cb:
                                            self._notify_cb(
                                                "Speech Studio",
                                                f"Downloading {self._jobs[job_id].name} ({quant})",
                                                ms,
                                            )

                    if part_path.exists():
                        part_path.replace(out_path)

            _meta_file(dest_dir).write_text(
                json.dumps({"repo_id": repo_id, "quant": quant, "files": target_files}, indent=2),
                encoding="utf-8",
            )

            with self._lock:
                j = self._jobs[job_id]
                j.status = "completed"
                j.progress = 100
                j.current_file = ""
            if self._notify_cb:
                self._notify_cb("Speech Studio", f"{self._jobs[job_id].name} ({quant}) ready", 100)

        except _DownloadCancelled:
            for pf in part_files:
                try:
                    pf.unlink(missing_ok=True)
                except OSError:
                    pass
            if not existed_before and dest_dir.exists():
                try:
                    if not any(dest_dir.iterdir()):
                        shutil.rmtree(dest_dir, ignore_errors=True)
                except OSError:
                    pass
            with self._lock:
                self._jobs[job_id].status = "cancelled"
                self._jobs[job_id].current_file = ""

        except Exception as exc:
            for pf in part_files:
                try:
                    pf.unlink(missing_ok=True)
                except OSError:
                    pass
            with self._lock:
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = str(exc)
                self._jobs[job_id].current_file = ""
            if self._notify_cb:
                self._notify_cb("Speech Studio", f"Download failed: {self._jobs[job_id].name}", None)
