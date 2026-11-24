from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import unquote, urlparse

import httpx
from huggingface_hub import HfApi, hf_hub_url
from pydantic import BaseModel, Field

from .catalog_capabilities import ModelCapabilities, capabilities_from_spec
from .config import AppSettings, resolved_models_dir


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
    family_id: str = ""
    family_name: str = ""
    variant_label: str = ""
    repo_id: str
    description: str = ""
    runtime_supported: bool = True
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
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
    download_url: Optional[str] = None


class HfInspectResponse(BaseModel):
    source: Literal["huggingface", "modelscope", "direct"] = "huggingface"
    repo_id: str
    suggested_name: str
    suggested_kind: Literal["tts", "stt"]
    files: list[HfInspectFile]


class HubModelSummary(BaseModel):
    repo_id: str
    name: str
    author: str = ""
    downloads: int = 0
    likes: int = 0
    tags: list[str] = Field(default_factory=list)
    pipeline_tag: str = ""


class HubSearchResponse(BaseModel):
    kind: Literal["tts", "stt"]
    query: str = ""
    page: int = 1
    page_size: int = 6
    has_more: bool = False
    items: list[HubModelSummary] = Field(default_factory=list)


BUILTIN_MODELS: list[dict[str, Any]] = [
    # --- TTS Models ---
    {
        "id": "qwen3-1.7b-base",
        "name": "Qwen3-TTS 1.7B Base",
        "kind": "tts",
        "engine": "qwen",
        "family_id": "qwen3-tts",
        "family_name": "Qwen3-TTS",
        "variant_label": "1.7B Base (Voice Clone)",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-1.7b", "qwen3-1.7b-base"],
        "description": "Zero-shot voice cloning GGUF (Talker + 12Hz codec).",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
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
        "family_id": "qwen3-tts",
        "family_name": "Qwen3-TTS",
        "variant_label": "0.6B Base (Compact)",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-0.6b-base"],
        "description": "Compact Qwen3-TTS GGUF voice cloner for low-VRAM GPUs.",
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
        "family_id": "qwen3-tts",
        "family_name": "Qwen3-TTS",
        "variant_label": "1.7B CustomVoice",
        "repo_id": "Serveurperso/Qwen3-TTS-GGUF",
        "dir_names": ["qwen3-1.7b-customvoice"],
        "description": "Instruction-steerable Qwen3-TTS with style and emotion control.",
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
        "family_id": "xtts-v2",
        "family_name": "Coqui XTTS v2",
        "variant_label": "v2 Multilingual",
        "repo_id": "coqui/XTTS-v2",
        "dir_names": ["xtts-v2"],
        "description": "Multilingual expressive voice cloning (Coqui Public Model License).",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
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
    {
        "id": "fish-speech-1.5",
        "name": "Fish Speech 1.5",
        "kind": "tts",
        "engine": "fish-audio",
        "family_id": "fish-audio",
        "family_name": "Fish Audio",
        "variant_label": "Fish Speech 1.5",
        "repo_id": "fishaudio/fish-speech-1.5",
        "dir_names": ["fish-speech-1.5"],
        "description": "Multilingual neural TTS from Fish Audio (catalog download; worker upcoming).",
        "runtime_supported": False,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "post_quantize",
        "languages": ["en", "zh", "ja", "de", "fr", "es", "ko", "ar", "ru", "nl", "it", "pl", "pt"],
        "quants": [
            {
                "id": "bf16",
                "label": "BF16 Weights",
                "disk_mb": 1400,
                "vram_mib": 2200,
                "files": [
                    "config.json",
                    "model.pth",
                    "firefly-gan-vq-fsq-8x1024-21hz-generator.pth",
                    "tokenizer.tiktoken",
                ],
                "recommended": True,
            },
            {
                "id": "int8",
                "label": "INT8 (quantize after BF16)",
                "disk_mb": 700,
                "vram_mib": 1200,
                "files": [],
                "recommended": False,
            },
            {
                "id": "int4",
                "label": "INT4 (quantize after BF16)",
                "disk_mb": 400,
                "vram_mib": 800,
                "files": [],
                "recommended": False,
            },
        ],
    },
    {
        "id": "f5-tts-v1-base",
        "name": "F5-TTS v1 Base",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "v1 Base (EN+zh)",
        "repo_id": "SWivid/F5-TTS",
        "dir_names": ["f5-tts-v1-base"],
        "description": (
            "Flow-matching voice clone (SWivid). EN+zh base. "
            "FP16/safetensors; GGUF F16 via CrispASR later. "
            "Catalog download; worker not wired yet."
        ),
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["en", "zh"],
        "quants": [
            {
                "id": "fp16",
                "label": "FP16 Safetensors",
                "disk_mb": 1300,
                "vram_mib": 2500,
                "files": [
                    "F5TTS_v1_Base/model_1250000.safetensors",
                    "F5TTS_v1_Base/vocab.txt",
                ],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-spanish",
        "name": "F5-TTS Spanish",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "Spanish fine-tune",
        "repo_id": "jpgallegoar/F5-Spanish",
        "dir_names": ["f5-tts-spanish"],
        "description": (
            "Spanish fine-tune of F5-TTS (jpgallegoar; multi-accent ES data). "
            "Not a single checkpoint for all languages — use v1 Base for EN, this for ES. "
            "Catalog download; worker not wired yet."
        ),
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["es"],
        "quants": [
            {
                "id": "fp16",
                "label": "FP16 Safetensors",
                "disk_mb": 1300,
                "vram_mib": 2500,
                "files": [
                    "model_1200000.safetensors",
                    "vocab.txt",
                ],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-french",
        "name": "F5-TTS French",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "French (reduced)",
        "repo_id": "RASPIAUDIO/F5-French-MixedSpeakers-reduced",
        "dir_names": ["f5-tts-french"],
        "description": "French F5-TTS fine-tune (.pt). Catalog only until CrispASR/worker.",
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["fr"],
        "quants": [
            {
                "id": "pt",
                "label": "PyTorch .pt",
                "disk_mb": 1200,
                "vram_mib": 2500,
                "files": ["model_last_reduced.pt", "vocab.txt"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-german",
        "name": "F5-TTS German",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "German",
        "repo_id": "hvoss-techfak/F5-TTS-German",
        "dir_names": ["f5-tts-german"],
        "description": "German F5-TTS fine-tune. Catalog only until CrispASR/worker.",
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["de"],
        "quants": [
            {
                "id": "fp16",
                "label": "FP16 Safetensors",
                "disk_mb": 1300,
                "vram_mib": 2500,
                "files": ["model_f5tts_german.safetensors", "vocab.txt"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-japanese",
        "name": "F5-TTS Japanese",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "Japanese",
        "repo_id": "Jmica/F5TTS",
        "dir_names": ["f5-tts-japanese"],
        "description": "Japanese F5-TTS (.pt). Catalog only until CrispASR/worker.",
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["ja"],
        "quants": [
            {
                "id": "pt",
                "label": "PyTorch .pt",
                "disk_mb": 1300,
                "vram_mib": 2500,
                "files": ["JA_21999120/model_21999120.pt", "JA_21999120/vocab_japanese.txt"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-pt-br",
        "name": "F5-TTS Portuguese (BR)",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "Portuguese BR",
        "repo_id": "firstpixel/F5-TTS-pt-br",
        "dir_names": ["f5-tts-pt-br"],
        "description": "Brazilian Portuguese F5-TTS. Catalog only until CrispASR/worker.",
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": ["pt"],
        "quants": [
            {
                "id": "fp16",
                "label": "FP16 Safetensors",
                "disk_mb": 1300,
                "vram_mib": 2500,
                "files": ["pt-br/model_last.safetensors"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "f5-tts-gguf-f16",
        "name": "F5-TTS GGUF F16",
        "kind": "tts",
        "engine": "f5-tts",
        "family_id": "f5-tts",
        "family_name": "F5-TTS",
        "variant_label": "GGUF F16 (CrispASR EN+zh)",
        "repo_id": "cstr/f5-tts-GGUF",
        "dir_names": ["f5-tts-gguf-f16"],
        "description": (
            "Single F16 GGUF for CrispASR (--backend f5-tts). EN+zh. "
            "Prefer over Q4/Q8 for flow-matching quality."
        ),
        "runtime_supported": False,
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "zh"],
        "quants": [
            {
                "id": "gguf-f16",
                "label": "GGUF F16",
                "disk_mb": 953,
                "vram_mib": 2000,
                "files": ["f5-tts-v1-base-f16.gguf"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "kokoro-82m",
        "name": "Kokoro 82M",
        "kind": "tts",
        "engine": "kokoro",
        "family_id": "kokoro",
        "family_name": "Kokoro",
        "variant_label": "82M ONNX",
        "repo_id": "onnx-community/Kokoro-82M-v1.0-ONNX",
        "dir_names": ["kokoro-82m"],
        "description": "Fast multilingual TTS (StyleTTS2-derived ONNX). Voices installed per language pack.",
        "runtime_supported": False,
        "install_mode": "voices_pack",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": ["en", "es", "fr", "hi", "it", "ja", "pt", "zh"],
        "quants": [
            {
                "id": "fp16",
                "label": "ONNX FP16",
                "disk_mb": 163,
                "vram_mib": 400,
                "files": ["onnx/model_fp16.onnx"],
                "recommended": True,
            },
            {
                "id": "quantized",
                "label": "ONNX quantized",
                "disk_mb": 92,
                "vram_mib": 300,
                "files": ["onnx/model_quantized.onnx"],
                "recommended": False,
            },
            {
                "id": "fp32",
                "label": "ONNX FP32",
                "disk_mb": 326,
                "vram_mib": 500,
                "files": ["onnx/model.onnx"],
                "recommended": False,
            },
            {
                "id": "q4",
                "label": "ONNX Q4",
                "disk_mb": 50,
                "vram_mib": 250,
                "files": ["onnx/model_q4.onnx"],
                "recommended": False,
            },
        ],
    },
    {
        "id": "piper-voices",
        "name": "Piper",
        "kind": "tts",
        "engine": "piper",
        "family_id": "piper",
        "family_name": "Piper",
        "variant_label": "Community voices",
        "repo_id": "rhasspy/piper-voices",
        "dir_names": ["piper"],
        "description": "Lightweight VITS voices. Install by language/quality (medium recommended).",
        "runtime_supported": False,
        "install_mode": "voices_pack",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": ["en", "es", "de", "fr", "it", "pt", "ru", "zh", "ar", "nl", "pl"],
        "quants": [
            {
                "id": "medium",
                "label": "Quality medium",
                "disk_mb": 60,
                "vram_mib": 200,
                "files": [
                    "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
                    "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
                ],
                "recommended": True,
            },
            {
                "id": "low",
                "label": "Quality low",
                "disk_mb": 30,
                "vram_mib": 150,
                "files": [
                    "en/en_US/lessac/low/en_US-lessac-low.onnx",
                    "en/en_US/lessac/low/en_US-lessac-low.onnx.json",
                ],
                "recommended": False,
            },
            {
                "id": "high",
                "label": "Quality high",
                "disk_mb": 100,
                "vram_mib": 250,
                "files": [
                    "en/en_US/lessac/high/en_US-lessac-high.onnx",
                    "en/en_US/lessac/high/en_US-lessac-high.onnx.json",
                ],
                "recommended": False,
            },
        ],
    },
    {
        "id": "espeak-ng",
        "name": "eSpeak NG",
        "kind": "tts",
        "engine": "espeak",
        "family_id": "espeak",
        "family_name": "eSpeak NG",
        "variant_label": "Binary runtime",
        "repo_id": "espeak-ng/espeak-ng",
        "dir_names": ["espeak-ng"],
        "direct_urls": {
            "espeak-ng.msi": "https://github.com/espeak-ng/espeak-ng/releases/download/1.52.0/espeak-ng.msi",
        },
        "description": "Tiny formant TTS binary. Install once; languages come with the package.",
        "runtime_supported": False,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "ru", "hi", "ar", "nl", "pl", "tr"],
        "quants": [
            {
                "id": "binary",
                "label": "Runtime binary",
                "disk_mb": 13,
                "vram_mib": 0,
                "files": ["espeak-ng.msi"],
                "recommended": True,
            },
        ],
    },
    {
        "id": "kitten-tts-2-mini",
        "name": "KittenTTS 2 Mini",
        "kind": "tts",
        "engine": "kitten",
        "family_id": "kitten-tts",
        "family_name": "KittenTTS",
        "variant_label": "2 Mini",
        "repo_id": "KittenML/kitten-tts-2-mini",
        "dir_names": ["kitten-tts-2-mini"],
        "description": "Compact ONNX TTS (16 langs). Install voice packs per language. 0.8/nano/pico excluded.",
        "runtime_supported": False,
        "install_mode": "voices_pack",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": [
            "en", "de", "es", "it", "pt", "ru", "hi", "fr", "da", "fi", "ja", "ko", "nl", "sv", "sw", "tr",
        ],
        "quants": [
            {
                "id": "int8",
                "label": "ONNX INT8",
                "disk_mb": 80,
                "vram_mib": 250,
                "files": ["kitten_tts_2_mini.onnx"],
                "recommended": True,
            },
            {
                "id": "int4",
                "label": "ONNX INT4",
                "disk_mb": 45,
                "vram_mib": 200,
                "files": ["kitten_tts_2_mini_int4.onnx"],
                "recommended": False,
            },
        ],
    },
    # --- STT Models ---
    {
        "id": "faster-whisper-tiny",
        "name": "Faster-Whisper Tiny",
        "kind": "stt",
        "engine": "faster-whisper",
        "family_id": "faster-whisper",
        "family_name": "Whisper (CTranslate2)",
        "variant_label": "Tiny",
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
        "family_id": "faster-whisper",
        "family_name": "Whisper (CTranslate2)",
        "variant_label": "Base",
        "repo_id": "Systran/faster-whisper-base",
        "model_size": "base",
        "description": "Balanced everyday transcription & Live Captions default.",
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
        "family_id": "faster-whisper",
        "family_name": "Whisper (CTranslate2)",
        "variant_label": "Small",
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
        "family_id": "faster-whisper",
        "family_name": "Whisper (CTranslate2)",
        "variant_label": "Medium",
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
        "family_id": "faster-whisper",
        "family_name": "Whisper (CTranslate2)",
        "variant_label": "Large v3 Turbo",
        "repo_id": "Systran/faster-whisper-large-v3-turbo",
        "model_size": "large-v3-turbo",
        "description": "Near-flagship speed & accuracy for 6 GB+ GPUs (~2.1 GB VRAM).",
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
        "family_id": "parakeet-v3",
        "family_name": "NVIDIA Parakeet v3",
        "variant_label": "TDT 0.6B v3 (ONNX)",
        "repo_id": "istupakov/parakeet-tdt-0.6b-v3-onnx",
        "description": "Fast ONNX ASR model (downloadable; sherpa-onnx worker upcoming).",
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
        "family_id": "moonshine",
        "family_name": "Moonshine",
        "variant_label": "Base ONNX",
        "repo_id": "onnx-community/moonshine-base-ONNX",
        "description": "Lightweight edge English STT (downloadable; ONNX worker upcoming).",
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

_ALLOWED_HF_EXTS = (".gguf", ".onnx", ".bin", ".safetensors", ".pth", ".pt", ".tiktoken")
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
        candidates: list[Path] = []
        for dn in dir_names:
            candidates.append(models_root / "tts" / dn)
            candidates.append(models_root / dn)
        candidates.append(models_root)

        for base_dir in candidates:
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
                    return True, meta_q, base_dir, False, size_mb
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

        repo_cache_name = f"models--{entry['repo_id'].replace('/', '--')}"
        cache_dir = stt_root / repo_cache_name
        if cache_dir.is_dir() and any(cache_dir.rglob("model.bin")):
            return True, "int8_float16", cache_dir, False, _dir_size_mb(cache_dir)
        return False, None, None, False, 0

    # Other TTS (xtts-v2, fish-speech-1.5, f5-tts, kokoro, piper, kitten, etc.)
    tts_dirs = [models_root / "tts" / dn for dn in entry.get("dir_names", [mid])]
    weight_exts = {".pth", ".pt", ".safetensors", ".gguf", ".onnx"}
    for tts_dir in tts_dirs:
        if not tts_dir.is_dir():
            continue
        meta_q = None
        mf = _meta_file(tts_dir)
        if mf.is_file():
            try:
                meta_q = json.loads(mf.read_text(encoding="utf-8")).get("quant")
            except Exception:
                meta_q = None
        for q in entry.get("quants", []):
            q_files = q.get("files") or []
            if q_files and all((tts_dir / f).is_file() for f in q_files):
                return True, meta_q or q["id"], tts_dir, False, _dir_size_mb(tts_dir)
        has_weight = any(
            p.is_file() and p.suffix.lower() in weight_exts
            for p in tts_dir.rglob("*")
        )
        if has_weight:
            q_id = meta_q or (entry["quants"][0]["id"] if entry.get("quants") else "fp16")
            return True, q_id, tts_dir, False, _dir_size_mb(tts_dir)
    return False, None, None, False, 0


def resolve_xtts_dir(settings: AppSettings, model_id: Optional[str] = None) -> tuple[Path, str]:
    """Return the installed XTTS v2 checkpoint directory and catalog id."""
    preferred = model_id or "xtts-v2"
    if preferred.startswith("xtts"):
        preferred = "xtts-v2"
    entry = BUILTIN_BY_ID.get(preferred)
    if entry is None or entry.get("engine") != "xtts":
        raise FileNotFoundError(f"Unknown XTTS model: {model_id or 'xtts-v2'}")
    installed, _, install_dir, _, _ = _detect_builtin_install(entry, settings)
    if not installed or install_dir is None:
        raise FileNotFoundError(
            "XTTS v2 checkpoint is not installed. Download xtts-v2 from Models."
        )
    required = ("config.json", "model.pth", "vocab.json", "speakers_xtts.pth")
    missing = [name for name in required if not (install_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"XTTS checkpoint at {install_dir} is missing {', '.join(missing)}."
        )
    return install_dir, entry["id"]


def resolve_qwen_paths(settings: AppSettings, model_id: Optional[str] = None) -> tuple[Path, Path, str]:
    """Find best installed Qwen3-TTS (talker_gguf, codec_gguf, resolved_model_id)."""
    preferred_id = model_id or settings.active_tts_model or "qwen3-1.7b-base"
    for suffix in ("-Q8_0", "-Q4_K_M", "-BF16", "-F32"):
        if preferred_id.endswith(suffix):
            preferred_id = preferred_id[: -len(suffix)]
            break

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
        f"Qwen3-TTS model not installed in {models_root}. Open Models (+) to download one."
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

    for custom in load_custom_registry(settings):
        if custom["id"] == model_id and custom.get("kind") == "stt":
            cdir = resolved_models_dir(settings) / "stt" / model_id
            if cdir.is_dir() and (cdir / "model.bin").is_file():
                return str(cdir), None, 700
            return custom["repo_id"], None, 700

    return "base", None, 350


def _runtime_supported_for_builtin(m: dict) -> bool:
    """Honor catalog flag; promote CrispASR-ready engines when binary is present."""
    if m.get("runtime_supported", True):
        return True
    engine = (m.get("engine") or "").lower()
    mid = (m.get("id") or "").lower()
    try:
        from .crispasr import is_available

        if not is_available():
            return False
        if engine in {"piper", "kokoro", "espeak", "f5", "f5-tts", "fish", "fish-audio", "kitten"}:
            return True
        if engine == "onnx-asr" and ("parakeet" in mid or "moonshine" in mid):
            return True
    except Exception:
        return False
    return False


def build_catalog(settings: AppSettings) -> list[CatalogModelEntry]:
    models_root = resolved_models_dir(settings)
    entries: list[CatalogModelEntry] = []

    for m in BUILTIN_MODELS:
        installed, q_id, install_dir, is_ext, disk_mb = _detect_builtin_install(m, settings)
        quants = [QuantOption(**q) for q in m.get("quants", [])]
        rec_q = next((q for q in quants if q.recommended), quants[0] if quants else None)
        active_q = next((q for q in quants if q.id == q_id), rec_q)
        caps = capabilities_from_spec(m)
        entries.append(
            CatalogModelEntry(
                id=m["id"],
                name=m["name"],
                kind=m["kind"],
                engine=m["engine"],
                family_id=m.get("family_id", m["id"]),
                family_name=m.get("family_name", m["name"]),
                variant_label=m.get("variant_label", m["name"]),
                repo_id=m["repo_id"],
                description=m.get("description", ""),
                runtime_supported=_runtime_supported_for_builtin(m),
                capabilities=caps,
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
        source = custom.get("source", "huggingface")
        is_ct2 = kind == "stt" and (
            any(Path(f).name == "model.bin" for f in files) or (cdir / "model.bin").is_file()
        )
        is_gguf_qwen = kind == "tts" and (
            any(f.lower().endswith(".gguf") for f in files) or any(cdir.glob("*.gguf"))
        )
        entries.append(
            CatalogModelEntry(
                id=cid,
                name=custom.get("name", cid),
                kind=kind,
                engine="faster-whisper" if is_ct2 else ("qwen" if is_gguf_qwen else f"custom-{source}"),
                family_id=cid,
                family_name=custom.get("name", cid),
                variant_label=source,
                repo_id=custom.get("repo_id", source),
                description=f"{source}: {custom.get('repo_id', '')}",
                runtime_supported=is_ct2 or is_gguf_qwen,
                capabilities=capabilities_from_spec(
                    {
                        "engine": "faster-whisper" if is_ct2 else ("qwen" if is_gguf_qwen else f"custom-{source}"),
                        "install_mode": "shared_weights",
                        "voice_mode": "clone_profile" if is_gguf_qwen else "builtin_voices",
                        "quant_policy": "gguf" if is_gguf_qwen else "checkpoint",
                        "languages": [],
                    }
                ),
                quants=[
                    QuantOption(
                        id=source,
                        label=f"Imported ({source})",
                        disk_mb=int(custom.get("disk_mb", disk_mb or 500)),
                        vram_mib=int(custom.get("vram_mib", 1200)),
                        files=files,
                        recommended=True,
                    )
                ],
                installed=installed,
                installed_quant=source if installed else None,
                install_dir=str(cdir) if installed else None,
                external=False,
                removable=installed and _is_within(cdir, models_root),
                custom=True,
                disk_mb=disk_mb,
                vram_mib=int(custom.get("vram_mib", 1200)),
            )
        )

    entries.sort(key=lambda e: (0 if e.installed else 1, e.kind))
    return entries


def search_hf_hub(
    kind: Literal["tts", "stt"],
    query: str = "",
    page: int = 1,
    page_size: int = 6,
) -> HubSearchResponse:
    safe_page = max(1, page)
    safe_size = max(1, min(20, page_size))
    pipeline_tag = "text-to-speech" if kind == "tts" else "automatic-speech-recognition"

    api = HfApi()
    limit = safe_page * safe_size + 1
    models = list(
        api.list_models(
            pipeline_tag=pipeline_tag,
            search=query.strip() or None,
            sort="downloads",
            limit=limit,
        )
    )
    start = (safe_page - 1) * safe_size
    page_items = models[start : start + safe_size]
    has_more = len(models) > start + safe_size

    out: list[HubModelSummary] = []
    for m in page_items:
        rid = getattr(m, "id", "") or ""
        parts = rid.split("/", 1)
        author = parts[0] if len(parts) == 2 else ""
        short_name = parts[1] if len(parts) == 2 else rid
        out.append(
            HubModelSummary(
                repo_id=rid,
                name=short_name,
                author=author,
                downloads=int(getattr(m, "downloads", 0) or 0),
                likes=int(getattr(m, "likes", 0) or 0),
                tags=[str(t) for t in (getattr(m, "tags", None) or [])[:6]],
                pipeline_tag=str(getattr(m, "pipeline_tag", pipeline_tag) or pipeline_tag),
            )
        )
    return HubSearchResponse(
        kind=kind,
        query=query.strip(),
        page=safe_page,
        page_size=safe_size,
        has_more=has_more,
        items=out,
    )


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
        if low.endswith(_ALLOWED_HF_EXTS) or low in (
            "config.json",
            "tokenizer.json",
            "vocabulary.txt",
            "vocabulary.json",
            "preprocessor_config.json",
            "vocab.txt",
            "vocab.json",
        ):
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
    is_tts = any(k in low_repo for k in ("tts", "xtts", "kokoro", "qwen3-tts", "bark", "f5", "fish"))
    suggested_kind: Literal["tts", "stt"] = "tts" if is_tts else "stt"
    suggested_name = repo_id.split("/")[-1].replace("-", " ")
    return HfInspectResponse(
        source="huggingface",
        repo_id=repo_id,
        suggested_name=suggested_name,
        suggested_kind=suggested_kind,
        files=files,
    )


def _inspect_modelscope(url: str) -> HfInspectResponse:
    parsed = urlparse(url.strip())
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "models":
        owner, repo = parts[1], parts[2]
    elif len(parts) >= 2:
        owner, repo = parts[0], parts[1]
    else:
        raise ValueError("Could not extract owner/repo from ModelScope URL.")

    api_url = f"https://modelscope.cn/api/v1/models/{owner}/{repo}/repo/files?Recursive=True"
    with httpx.Client(follow_redirects=True, timeout=20.0) as client:
        resp = client.get(api_url)
        resp.raise_for_status()
        payload = resp.json()

    raw_files = (payload.get("Data") or {}).get("Files") or []
    files: list[HfInspectFile] = []
    for item in raw_files:
        if item.get("Type") != "blob":
            continue
        fpath = str(item.get("Path") or "")
        size = int(item.get("Size") or 0)
        low = fpath.lower()
        if low.endswith(_ALLOWED_HF_EXTS + _META_HF_EXTS):
            dl_url = f"https://modelscope.cn/models/{owner}/{repo}/resolve/master/{fpath}"
            files.append(
                HfInspectFile(
                    filename=fpath,
                    size_bytes=size,
                    size_mb=round(size / (1024 * 1024), 1),
                    recommended=low.endswith((".gguf", ".onnx", "model.bin", ".pth")),
                    download_url=dl_url,
                )
            )
    low_repo = f"{owner}/{repo}".lower()
    is_tts = any(k in low_repo for k in ("tts", "xtts", "kokoro", "cosyvoice", "fish"))
    return HfInspectResponse(
        source="modelscope",
        repo_id=f"{owner}/{repo}",
        suggested_name=repo.replace("-", " "),
        suggested_kind="tts" if is_tts else "stt",
        files=files,
    )


def _inspect_direct_url(url: str) -> HfInspectResponse:
    clean = url.strip()
    parsed = urlparse(clean)
    fname = Path(unquote(parsed.path)).name or "model.bin"
    size = 0
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            r = client.head(clean)
            if r.status_code < 400:
                size = int(r.headers.get("content-length") or 0)
    except Exception:
        pass

    low = fname.lower()
    is_tts = any(k in clean.lower() for k in ("tts", "qwen", "xtts", "kokoro", "fish"))
    return HfInspectResponse(
        source="direct",
        repo_id=clean,
        suggested_name=Path(fname).stem.replace("-", " "),
        suggested_kind="tts" if is_tts else "stt",
        files=[
            HfInspectFile(
                filename=fname,
                size_bytes=size,
                size_mb=round(size / (1024 * 1024), 1),
                recommended=True,
                download_url=clean,
            )
        ],
    )


def inspect_model_url(url_or_id: str) -> HfInspectResponse:
    raw = url_or_id.strip()
    if not raw:
        raise ValueError("Model URL is empty.")
    low = raw.lower()
    if low.startswith(("http://", "https://")):
        host = urlparse(raw).netloc.lower()
        if "huggingface.co" in host:
            return inspect_hf_repo(raw)
        if "modelscope.cn" in host:
            return _inspect_modelscope(raw)
        return _inspect_direct_url(raw)
    return inspect_hf_repo(raw)


def import_local_model(
    settings: AppSettings,
    *,
    source_path: str,
    name: str,
    kind: Literal["tts", "stt"],
) -> CatalogModelEntry:
    src = Path(source_path.strip()).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Path not found: {src}")

    clean_id = _slugify(name or src.stem)
    models_root = resolved_models_dir(settings)
    sub = "stt" if kind == "stt" else "tts"
    dest_dir = models_root / sub / clean_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    if src.is_file():
        dst = dest_dir / src.name
        shutil.copy2(src, dst)
        copied_files.append(src.name)
    else:
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                dst = dest_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
                copied_files.append(rel.as_posix())

    if not copied_files:
        raise ValueError("Selected folder contains no files.")

    disk_mb = _dir_size_mb(dest_dir)
    _meta_file(dest_dir).write_text(
        json.dumps({"source": "local", "quant": "local", "files": copied_files}, indent=2),
        encoding="utf-8",
    )

    reg = [r for r in load_custom_registry(settings) if r.get("id") != clean_id]
    reg.append(
        {
            "id": clean_id,
            "name": (name or src.stem).strip(),
            "kind": kind,
            "source": "local",
            "repo_id": str(src),
            "files": copied_files,
            "disk_mb": disk_mb,
            "vram_mib": 1200 if kind == "tts" else 800,
        }
    )
    save_custom_registry(settings, reg)
    cat = build_catalog(settings)
    entry = next((m for m in cat if m.id == clean_id), None)
    assert entry is not None
    return entry


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
        removed_files = 0
        for q in target.quants:
            for fname in q.files:
                fp = install_path / fname
                if fp.is_file() and _is_within(fp, models_root):
                    fp.unlink()
                    removed_files += 1
        return {"removed": removed_files > 0, "model_id": model_id}

    for attempt in range(3):
        try:
            shutil.rmtree(install_path, ignore_errors=False)
            break
        except (PermissionError, OSError):
            if attempt == 2:
                raise
            time.sleep(0.2)

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
        has_files_key = "files" in chosen
        explicit_files = list(chosen.get("files") or [])
        # Post-quantize options (Fish int8/int4) share the BF16 download pack;
        # full-repo STT models (faster-whisper-*) omit "files" to download the whole repo.
        if has_files_key and not explicit_files:
            fallback = next((q for q in quants if q.get("files")), None)
            if fallback is None:
                raise ValueError(
                    f"Model {model_id} quant {chosen['id']} has no downloadable files yet "
                    "(bundled runtime or external binary)."
                )
            explicit_files = list(fallback["files"])
            chosen = {**chosen, "id": chosen["id"], "files": explicit_files}

        models_root = resolved_models_dir(settings)
        if entry["kind"] == "stt":
            dest_dir = models_root / "stt" / model_id
        else:
            dn = entry.get("dir_names", [model_id])[0]
            dest_dir = models_root / "tts" / dn

        return self._enqueue(
            model_id=model_id,
            name=entry["name"],
            kind=entry["kind"],
            quant=chosen["id"],
            repo_id=entry["repo_id"],
            dest_dir=dest_dir,
            explicit_files=explicit_files,
            engine=entry["engine"],
            direct_urls=dict(entry.get("direct_urls") or {}),
        )

    def start_url_download(
        self,
        settings: AppSettings,
        *,
        source: Literal["huggingface", "modelscope", "direct"] = "huggingface",
        repo_id: str,
        name: str,
        kind: Literal["tts", "stt"],
        selected_files: list[str],
        direct_urls: Optional[dict[str, str]] = None,
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
                "source": source,
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
            quant=source,
            repo_id=repo_id,
            dest_dir=dest_dir,
            explicit_files=selected_files,
            engine=f"custom-{source}",
            direct_urls=direct_urls or {},
        )

    # Kept as an alias for older callers
    def start_custom_hf_download(
        self,
        settings: AppSettings,
        *,
        repo_id: str,
        name: str,
        kind: Literal["tts", "stt"],
        selected_files: list[str],
    ) -> DownloadJob:
        return self.start_url_download(
            settings,
            source="huggingface",
            repo_id=repo_id,
            name=name,
            kind=kind,
            selected_files=selected_files,
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
        direct_urls: dict[str, str],
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
            args=(job_id, repo_id, dest_dir, explicit_files, engine, quant, direct_urls, ev),
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
        direct_urls: dict[str, str],
        cancel_ev: threading.Event,
    ) -> None:
        part_files: list[Path] = []
        last_milestone = 0
        existed_before = dest_dir.exists()

        try:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "downloading"
                job_name = job.name

            dest_dir.mkdir(parents=True, exist_ok=True)
            size_map: dict[str, int] = {}

            if direct_urls:
                target_files = explicit_files or list(direct_urls.keys())
            else:
                api = HfApi()
                info = api.model_info(repo_id, files_metadata=True)
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
                    url = direct_urls.get(rel_path) or hf_hub_url(repo_id=repo_id, filename=rel_path)

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
                                            from .toasts import say

                                            self._notify_cb(
                                                say("app"),
                                                say(
                                                    "download_progress",
                                                    name=job_name,
                                                    quant=quant,
                                                ),
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
                from .toasts import say

                self._notify_cb(
                    say("app"),
                    say("download_ready", name=job_name, quant=quant),
                    100,
                )

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
                from .toasts import say

                self._notify_cb(say("app"), say("download_failed", name=job_name), None)
