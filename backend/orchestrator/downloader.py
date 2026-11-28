from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
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
from .config import DEFAULT_TMP_DIR, AppSettings, resolved_models_dir


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
    available_runtimes: list[str] = Field(default_factory=list)
    active_runtime: str = ""
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    quants: list[QuantOption] = Field(default_factory=list)
    installed: bool = False
    installed_quant: Optional[str] = None
    installed_quants: list[str] = Field(default_factory=list)
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
    crispasr_ready: bool = False
    crispasr_backend: Optional[str] = None
    crispasr_reason: str = ""
    can_convert_gguf: bool = False
    convert_script: Optional[str] = None


class HubModelSummary(BaseModel):
    repo_id: str
    name: str
    author: str = ""
    downloads: int = 0
    likes: int = 0
    tags: list[str] = Field(default_factory=list)
    pipeline_tag: str = ""
    crispasr_ready: bool = False
    crispasr_backend: Optional[str] = None
    crispasr_reason: str = ""


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
        "id": "qwen3-1.7b-voicedesign",
        "name": "Qwen3-TTS 1.7B VoiceDesign",
        "kind": "tts",
        "engine": "qwen",
        "family_id": "qwen3-tts",
        "family_name": "Qwen3-TTS",
        "variant_label": "1.7B VoiceDesign (Prompt)",
        "repo_id": "cstr/qwen3-tts-1.7b-voicedesign-GGUF",
        "dir_names": ["qwen3-1.7b-voicedesign"],
        "description": "Design a synthetic voice from text instructions (pitch, timbre, emotion) via CrispASR --instruct.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "gguf",
        "languages": ["es", "en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "it"],
        "quants": [
            {
                "id": "q8_0",
                "label": "GGUF Q8_0 (Balanced)",
                "disk_mb": 1948,
                "vram_mib": 2600,
                "files": ["qwen3-tts-12hz-1.7b-voicedesign-q8_0.gguf"],
                "recommended": True,
            },
            {
                "id": "f16",
                "label": "GGUF F16 (Full Precision)",
                "disk_mb": 3661,
                "vram_mib": 4400,
                "files": ["qwen3-tts-12hz-1.7b-voicedesign-f16.gguf"],
                "recommended": False,
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
        "description": "Multilingual neural TTS from Fish Audio. Runs on the Python Fish Speech worker, not CrispASR.",
        "runtime_supported": True,
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
            "Runs on isolated Python F5 worker."
        ),
        "runtime_supported": True,
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
        "id": "chatterbox-multilingual-gguf",
        "name": "Chatterbox Multilingual",
        "kind": "tts",
        "engine": "chatterbox",
        "family_id": "chatterbox",
        "family_name": "Chatterbox",
        "variant_label": "Multilingual GGUF (Voice Clone)",
        "repo_id": "cstr/chatterbox-GGUF",
        "dir_names": ["chatterbox-multilingual-gguf", "chatterbox-gguf"],
        "description": "Multilingual zero-shot voice cloning (Spanish, English, etc.) on CrispASR C++.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "ru", "ar", "hi", "nl", "pl", "tr"],
        "quants": [
            {
                "id": "q4_k",
                "label": "GGUF Q4_K (T3 + S3Gen)",
                "disk_mb": 650,
                "vram_mib": 1600,
                "files": ["chatterbox-v3-t3-q4_k.gguf", "chatterbox-v3-s3gen-q4_k.gguf"],
                "recommended": True,
            },
            {
                "id": "q8_0",
                "label": "GGUF Q8_0 (T3 + S3Gen)",
                "disk_mb": 1000,
                "vram_mib": 2100,
                "files": ["chatterbox-v3-t3-q8_0.gguf", "chatterbox-v3-s3gen-q8_0.gguf"],
                "recommended": False,
            },
            {
                "id": "f16",
                "label": "GGUF F16 (T3 + S3Gen)",
                "disk_mb": 1700,
                "vram_mib": 2800,
                "files": ["chatterbox-v3-t3-f16.gguf", "chatterbox-v3-s3gen-f16.gguf"],
                "recommended": False,
            },
        ],
    },
    {
        "id": "chatterbox-turbo-gguf",
        "name": "Chatterbox Turbo",
        "kind": "tts",
        "engine": "chatterbox",
        "family_id": "chatterbox",
        "family_name": "Chatterbox",
        "variant_label": "Turbo EN GGUF (Voice Clone)",
        "repo_id": "cstr/chatterbox-turbo-GGUF",
        "dir_names": ["chatterbox-turbo-gguf"],
        "description": "Fast English flow-matching voice cloning running natively on CrispASR C++.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en"],
        "quants": [
            {
                "id": "q4_k",
                "label": "GGUF Q4_K (T3 + S3Gen)",
                "disk_mb": 560,
                "vram_mib": 1400,
                "files": ["chatterbox-turbo-t3-q4_k.gguf", "chatterbox-turbo-s3gen-q4_k.gguf"],
                "recommended": True,
            },
            {
                "id": "f16",
                "label": "GGUF F16 (T3 + S3Gen)",
                "disk_mb": 1400,
                "vram_mib": 2400,
                "files": ["chatterbox-turbo-t3-f16.gguf", "chatterbox-turbo-s3gen-f16.gguf"],
                "recommended": False,
            },
        ],
    },
    {
        "id": "cosyvoice3-0.5b-gguf",
        "name": "CosyVoice3 0.5B",
        "kind": "tts",
        "engine": "cosyvoice3-tts",
        "family_id": "cosyvoice3",
        "family_name": "CosyVoice3",
        "variant_label": "0.5B GGUF (Cross-Lingual Clone)",
        "repo_id": "cstr/cosyvoice3-0.5b-2512-GGUF",
        "dir_names": ["cosyvoice3-0.5b-gguf"],
        "description": "Cross-lingual zero-shot voice cloning running natively on CrispASR C++.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "zh", "ja", "ko", "de", "fr", "ru", "es", "it"],
        "quants": [
            {
                "id": "q4_k",
                "label": "GGUF Q4_K + Flow Q8_0",
                "disk_mb": 1360,
                "vram_mib": 1800,
                "files": [
                    "cosyvoice3-llm-q4_k.gguf",
                    "cosyvoice3-flow-q8_0.gguf",
                    "cosyvoice3-campplus-f16.gguf",
                    "cosyvoice3-hift-f16.gguf",
                    "cosyvoice3-s3tok-f16.gguf",
                    "cosyvoice3-voices.gguf",
                ],
                "recommended": True,
            },
            {
                "id": "f16",
                "label": "GGUF F16 Full",
                "disk_mb": 2250,
                "vram_mib": 2800,
                "files": [
                    "cosyvoice3-llm-f16.gguf",
                    "cosyvoice3-flow-f16.gguf",
                    "cosyvoice3-campplus-f16.gguf",
                    "cosyvoice3-hift-f16.gguf",
                    "cosyvoice3-s3tok-f16.gguf",
                    "cosyvoice3-voices.gguf",
                ],
                "recommended": False,
            },
        ],
    },
    {
        "id": "indextts-1.5-gguf",
        "name": "IndexTTS 1.5",
        "kind": "tts",
        "engine": "indextts",
        "family_id": "indextts",
        "family_name": "IndexTTS",
        "variant_label": "1.5 GGUF (EN+zh Clone)",
        "repo_id": "cstr/indextts-1.5-GGUF",
        "dir_names": ["indextts-1.5-gguf"],
        "description": "Zero-shot English & Chinese voice cloning on CrispASR C++ (GPT + BigVGAN).",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "zh"],
        "quants": [
            {
                "id": "q8_0",
                "label": "GGUF Q8_0 + BigVGAN",
                "disk_mb": 1050,
                "vram_mib": 2100,
                "files": ["indextts-gpt-q8_0.gguf", "indextts-bigvgan.gguf"],
                "recommended": True,
            },
            {
                "id": "q4_k",
                "label": "GGUF Q4_K + BigVGAN",
                "disk_mb": 720,
                "vram_mib": 1600,
                "files": ["indextts-gpt-q4_k.gguf", "indextts-bigvgan.gguf"],
                "recommended": False,
            },
        ],
    },
    {
        "id": "orpheus-3b-gguf",
        "name": "Orpheus 3B",
        "kind": "tts",
        "engine": "orpheus",
        "family_id": "orpheus",
        "family_name": "Orpheus",
        "variant_label": "3B Base GGUF (EN)",
        "repo_id": "cstr/orpheus-3b-base-GGUF",
        "dir_names": ["orpheus-3b-gguf"],
        "description": "Expressive Llama-3.2-3B + SNAC 24kHz TTS running on CrispASR C++.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "gguf",
        "languages": ["en"],
        "quants": [
            {
                "id": "q4_k",
                "label": "GGUF Q4_K",
                "disk_mb": 1950,
                "vram_mib": 3200,
                "files": ["orpheus-3b-base-q4_k.gguf"],
                "recommended": True,
            },
            {
                "id": "q8_0",
                "label": "GGUF Q8_0",
                "disk_mb": 3400,
                "vram_mib": 4600,
                "files": ["orpheus-3b-base-q8_0.gguf"],
                "recommended": False,
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
        "variant_label": "82M GGUF",
        "repo_id": "cstr/kokoro-82m-GGUF",
        "dir_names": ["kokoro-82m"],
        "description": "Fast multilingual TTS (Kokoro 82M GGUF). All 54 voices resolved via CrispASR.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "gguf",
        "languages": ["en", "es", "fr", "hi", "it", "ja", "pt", "zh"],
        "quants": [
            {
                "id": "f16",
                "label": "GGUF F16",
                "disk_mb": 156,
                "vram_mib": 400,
                "files": ["kokoro-82m-f16.gguf"],
                "recommended": True,
            },
            {
                "id": "q8_0",
                "label": "GGUF Q8_0",
                "disk_mb": 135,
                "vram_mib": 320,
                "files": ["kokoro-82m-q8_0.gguf"],
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
        "variant_label": "GGUF Voices (CrispASR)",
        "repo_id": "LocalAI-Community/piper-voices-GGUF",
        "dir_names": ["piper"],
        "description": "Lightweight VITS GGUF voices running natively on CrispASR.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "gguf",
        "languages": ["es", "en", "de", "fr", "it", "pt", "ru", "nl", "pl"],
        "quants": [
            {
                "id": "medium",
                "label": "GGUF F16 (Medium · ES + EN)",
                "disk_mb": 60,
                "vram_mib": 200,
                "files": ["piper-es_ES-davefx-medium-f16.gguf", "piper-en_US-lessac-medium-f16.gguf"],
                "recommended": True,
            },
            {
                "id": "low",
                "label": "GGUF F16 (Compact · ES)",
                "disk_mb": 30,
                "vram_mib": 160,
                "files": ["piper-es_ES-mls_10246-low-f16.gguf"],
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
        "description": "Tiny formant CPU TTS runtime (no VRAM required).",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": ["es", "en", "de", "fr", "it", "pt", "ru", "nl", "pl"],
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
        "id": "windows-sapi5",
        "name": "Windows SAPI 5",
        "kind": "tts",
        "engine": "sapi5",
        "family_id": "sapi5",
        "family_name": "Windows SAPI 5",
        "variant_label": "32/64-bit + OneCore",
        "repo_id": "local/windows-sapi5",
        "dir_names": [],
        "description": "Native Windows SAPI 5 (32-bit & 64-bit) and OneCore voices — automatically detects Loquendo TTS 7, IVONA, and system voices with all dialects.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": ["all", "es-ES", "en-US"],
        "quants": [
            {
                "id": "native",
                "label": "Windows COM (32/64-bit + OneCore)",
                "disk_mb": 0,
                "vram_mib": 0,
                "files": [],
                "recommended": True,
            },
        ],
    },
    {
        "id": "loquendo-tts7",
        "name": "Loquendo TTS 7",
        "kind": "tts",
        "engine": "sapi5",
        "family_id": "loquendo-tts7",
        "family_name": "Loquendo TTS 7",
        "variant_label": "Windows SAPI 5 · 32/64-bit",
        "repo_id": "local/loquendo-tts7",
        "dir_names": [],
        "description": "Loquendo TTS 7 engine and voices through Windows SAPI 5. Requires an existing licensed installer. Select the engine and voice installers locally, then rescan installed voices.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": [],
        "quants": [{"id": "native", "label": "Windows SAPI 5", "disk_mb": 0, "vram_mib": 0, "files": [], "recommended": True}],
    },
    {
        "id": "xyz-ioquendo",
        "name": "xyz-Ioquendo",
        "kind": "tts",
        "engine": "qwen",
        "family_id": "xyz-ioquendo",
        "family_name": "xyz-Ioquendo",
        "variant_label": "Qwen3 reference pack",
        "repo_id": "local/xyz-ioquendo",
        "dir_names": ["voice-packs/xyz-ioquendo"],
        "description": (
            "Reference voice pack for Qwen3-TTS 1.7B Base Q4_K_M cloning. "
            "Independent of Qwen weights. Not an official Loquendo product; "
            "redistribution pending license review."
        ),
        "runtime_supported": True,
        "install_mode": "voices_pack",
        "voice_mode": "clone_profile",
        "quant_policy": "binary",
        "languages": ["es", "en"],
        "quants": [
            {
                "id": "references",
                "label": "Reference pack (vertical)",
                "disk_mb": 1,
                "vram_mib": 0,
                "files": [],
                "recommended": True,
            }
        ],
        "depends_on_model_id": "qwen3-1.7b-base",
        "depends_on_quant_id": "Q4_K_M",
        "pack_kind": "reference_pack",
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
        "description": "Compact ONNX TTS (16 langs). 0.8/nano/pico excluded.",
        "runtime_supported": True,
        "install_mode": "shared_weights",
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


def _detect_builtin_install(
    entry: dict[str, Any], settings: AppSettings, *, qwen_quant: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[Path], bool, int]:
    """Return (installed, installed_quant, install_dir, external, disk_mb)."""
    models_root = resolved_models_dir(settings)
    mid = entry["id"]
    kind = entry["kind"]
    engine = entry["engine"]

    if mid == "xyz-ioquendo":
        from . import voice_packs

        pack_dir = voice_packs.pack_install_dir(models_root)
        if voice_packs.is_pack_installed(models_root):
            disk_mb = _dir_size_mb(pack_dir) if pack_dir.is_dir() else 1
            return True, "references", pack_dir, False, disk_mb
        return False, None, pack_dir if pack_dir.exists() else None, False, 0

    if engine == "sapi5":
        from . import sapi5_engine

        if mid == "loquendo-tts7":
            from . import loquendo

            return (True, "native", None, False, 0) if loquendo.installed_voices() else (False, None, None, False, 0)
        if sapi5_engine.is_available():
            return True, "native", None, False, 0
        return False, None, None, False, 0

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
            quants = entry["quants"]
            if qwen_quant is None:
                try:
                    saved_quant = json.loads(_meta_file(base_dir).read_text(encoding="utf-8")).get("quant")
                except (OSError, ValueError, AttributeError):
                    saved_quant = None
                quants = sorted(quants, key=lambda q: q["id"] != saved_quant)
            for q in quants:
                if qwen_quant is not None and q["id"] != qwen_quant:
                    continue
                q_files = q.get("files") or []
                if q_files and all((base_dir / f).is_file() for f in q_files):
                    size_mb = sum(
                        max(1, round((base_dir / f).stat().st_size / (1024 * 1024)))
                        for f in q["files"]
                    )
                    return True, q["id"], base_dir, False, size_mb
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
    quant_policy = (entry.get("quant_policy") or "").strip().lower()
    weight_exts = {".gguf"} if quant_policy == "gguf" else {".pth", ".pt", ".safetensors", ".gguf", ".onnx"}
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
        matched_quants = []
        for q in entry.get("quants", []):
            q_files = q.get("files") or []
            if q_files and all((tts_dir / f).is_file() for f in q_files):
                matched_quants.append(q["id"])
        if matched_quants:
            chosen_q = meta_q if meta_q in matched_quants else matched_quants[0]
            return True, chosen_q, tts_dir, False, _dir_size_mb(tts_dir)
        has_quant_files_spec = any(q.get("files") for q in entry.get("quants", []))
        if has_quant_files_spec and quant_policy in ("gguf", "onnx", "post_quantize", "checkpoint"):
            continue
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
    preferred_quant = None
    for entry in BUILTIN_MODELS:
        if entry["engine"] != "qwen":
            continue
        for quant in entry["quants"]:
            if preferred_id == f"{entry['id']}-{quant['id']}":
                preferred_id = entry["id"]
                preferred_quant = quant["id"]
                break
        if preferred_quant is not None:
            break

    order = [BUILTIN_BY_ID[preferred_id]] if BUILTIN_BY_ID.get(preferred_id, {}).get("engine") == "qwen" else []
    for m in BUILTIN_MODELS:
        if m["engine"] == "qwen" and m["id"] != preferred_id:
            order.append(m)

    for entry in order:
        requested_quant = preferred_quant if entry["id"] == preferred_id else None
        install = _detect_builtin_install(entry, settings, qwen_quant=requested_quant)
        if not install[0] and requested_quant is not None:
            # Legacy settings may name a default quant that was never downloaded.
            install = _detect_builtin_install(entry, settings)
        installed, q_id, install_dir, _, _ = install
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
    selected_quant = None
    if entry is None:
        entry = next(
            (candidate for candidate in BUILTIN_MODELS
             if candidate["kind"] == "stt" and model_id.startswith(candidate["id"] + "-")
             and any(model_id == f"{candidate['id']}-{q['id']}" for q in candidate.get("quants", []))),
            None,
        )
        if entry is not None:
            selected_quant = model_id[len(entry["id"]) + 1:]
    if entry and entry["kind"] == "stt":
        installed, q_id, install_dir, _, _ = _detect_builtin_install(entry, settings)
        compute_type: Optional[str] = None
        vram_est = entry["quants"][0]["vram_mib"] if entry.get("quants") else 350
        for q in entry.get("quants", []):
            if q["id"] == (selected_quant or q_id):
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
    """Honor catalog flag; promote genuinely runnable CrispASR GGUF engines when binary is present."""
    engine = (m.get("engine") or "").lower()
    if engine == "sapi5":
        from . import sapi5_engine

        return sapi5_engine.is_available()
    if m.get("runtime_supported", True):
        return True
    mid = (m.get("id") or "").lower()
    quant_policy = (m.get("quant_policy") or "").lower()
    try:
        from .crispasr import CRISPASR_READY_ENGINES, is_available

        if not is_available():
            return False
        # Non-GGUF F5 checkpoints (.pt / .safetensors) require a dedicated Python checkpoint setup.
        if engine in ("f5", "f5-tts") and quant_policy != "gguf":
            return False
        # Parakeet & Moonshine catalog entries currently point to HF ONNX repos while CrispASR requires GGUF
        # and no sherpa/onnx-asr worker is bundled. Do not claim they are runnable until supported.
        if engine == "onnx-asr":
            return False
        if engine in CRISPASR_READY_ENGINES or engine == "kitten":
            return True
    except Exception:
        return False
    return False


def _runtimes_for_model(m: dict, settings: AppSettings) -> tuple[list[str], str]:
    """Return honest (available_runtimes, active_runtime) without exposing CrispASR on unsupported models."""
    engine = (m.get("engine") or "").strip().lower()
    quant_policy = (m.get("quant_policy") or "").strip().lower()
    available: list[str] = []
    if m.get("kind") == "tts":
        if engine == "qwen":
            available = ["crispasr", "python"]
        elif engine in ("f5", "f5-tts"):
            if quant_policy == "gguf":
                available = ["crispasr"]
            elif m.get("runtime_supported"):
                available = ["python"]
            else:
                available = []
        elif engine in ("piper", "kokoro", "chatterbox", "chatterbox-turbo", "cosyvoice3-tts", "indextts", "orpheus"):
            available = ["crispasr"]
        elif engine in ("xtts", "fish-audio", "fish", "kitten"):
            available = ["python"]
        elif engine in ("espeak", "sapi5"):
            available = []
    default_rt = available[0] if available else ""
    preferred = (settings.model_runtimes or {}).get(m["id"], "")
    active = preferred if preferred in available else default_rt
    return available, active


def build_catalog(settings: AppSettings) -> list[CatalogModelEntry]:
    models_root = resolved_models_dir(settings)
    entries: list[CatalogModelEntry] = []

    for m in BUILTIN_MODELS:
        installed, q_id, install_dir, is_ext, disk_mb = _detect_builtin_install(m, settings)
        installed_quants = []
        if m["engine"] == "qwen":
            installed_quants = [
                quant["id"]
                for quant in m["quants"]
                if _detect_builtin_install(m, settings, qwen_quant=quant["id"])[0]
            ]
        elif m["kind"] == "stt" and m["engine"] == "faster-whisper" and installed:
            # CTranslate2 compute types reuse one downloaded checkpoint.
            installed_quants = [q["id"] for q in m.get("quants", []) if q.get("compute_type")]
        elif install_dir and install_dir.is_dir():
            installed_quants = [
                quant["id"]
                for quant in m.get("quants", [])
                if quant.get("files") and all((install_dir / filename).is_file() for filename in quant["files"])
            ]
            if not installed_quants and q_id and not any(q.get("files") for q in m.get("quants", [])):
                installed_quants = [q_id]
        elif q_id:
            installed_quants = [q_id]
        if m["kind"] == "tts" and m["engine"] != "sapi5" and not is_ext and m.get("quants") and any(q.get("files") for q in m["quants"]):
            installed = bool(installed_quants)
            if not installed:
                q_id = None
        quants = [QuantOption(**q) for q in m.get("quants", [])]
        rec_q = next((q for q in quants if q.recommended), quants[0] if quants else None)
        active_q = next((q for q in quants if q.id == q_id), rec_q)
        caps = capabilities_from_spec(m)
        if m["engine"] == "sapi5":
            from . import sapi5_engine

            if m["id"] == "loquendo-tts7":
                from . import loquendo

                langs = loquendo.installed_languages()
            else:
                langs = sapi5_engine.installed_languages()
            if langs:
                caps.languages = langs
        if m["id"] == "xyz-ioquendo":
            from . import voice_packs

            pack_langs = voice_packs.installed_locale_codes(models_root)
            if pack_langs:
                caps.languages = pack_langs
            if installed:
                installed_quants = ["references"]
                q_id = "references"
        avail_rt, active_rt = _runtimes_for_model(m, settings)
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
                available_runtimes=avail_rt,
                active_runtime=active_rt,
                capabilities=caps,
                quants=quants,
                installed=installed,
                installed_quant=q_id,
                installed_quants=installed_quants,
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
        stored_backend = (custom.get("crispasr_backend") or "").strip().lower()
        has_gguf = any(f.lower().endswith(".gguf") for f in files) or (
            cdir.is_dir() and any(cdir.rglob("*.gguf"))
        )
        is_ct2 = kind == "stt" and (
            any(Path(f).name == "model.bin" for f in files) or (cdir / "model.bin").is_file()
        )
        inferred_engine = stored_backend or (
            "faster-whisper" if is_ct2 else ("qwen" if (kind == "tts" and has_gguf) else f"custom-{source}")
        )
        if inferred_engine == "qwen3-tts":
            inferred_engine = "qwen"
        elif inferred_engine == "qwen3":
            inferred_engine = "qwen3-asr"
        is_crispasr_ready = bool(stored_backend) or has_gguf
        voice_mode = (
            "clone_profile"
            if kind == "tts" and inferred_engine in {"qwen", "f5", "f5-tts", "chatterbox", "cosyvoice3-tts", "orpheus", "indextts"}
            else "builtin_voices"
        )
        entries.append(
            CatalogModelEntry(
                id=cid,
                name=custom.get("name", cid),
                kind=kind,
                engine=inferred_engine,
                family_id=cid,
                family_name=custom.get("name", cid),
                variant_label=source,
                repo_id=custom.get("repo_id", source),
                description=f"{source}: {custom.get('repo_id', '')}",
                runtime_supported=is_ct2 or is_crispasr_ready,
                capabilities=capabilities_from_spec(
                    {
                        "engine": inferred_engine,
                        "install_mode": "shared_weights",
                        "voice_mode": voice_mode,
                        "quant_policy": "gguf" if has_gguf else "checkpoint",
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


_CRISPASR_CONVERTERS: dict[str, str] = {
    "qwen3-tts": "models/convert-qwen3-tts-to-gguf.py",
    "f5-tts": "models/convert-f5-tts-to-gguf.py",
    "chatterbox": "models/convert-chatterbox-to-gguf.py",
    "cosyvoice3-tts": "models/convert-cosyvoice3-to-gguf.py",
    "orpheus": "models/convert-orpheus-to-gguf.py",
    "indextts": "models/convert-indextts-to-gguf.py",
    "kokoro": "models/convert-kokoro-to-gguf.py",
    "piper": "models/convert-piper-to-gguf.py",
    "bark": "models/convert-bark-to-gguf.py",
    "dia": "models/convert-dia-to-gguf.py",
    "zonos": "models/convert-zonos-to-gguf.py",
    "csm": "models/convert-csm-to-gguf.py",
    "parler-tts": "models/convert-parler-to-gguf.py",
    "outetts": "models/convert-outetts-to-gguf.py",
    "melotts": "models/convert-melotts-to-gguf.py",
    "pocket-tts": "models/convert-pocket-tts-to-gguf.py",
    "supertonic": "models/convert-supertonic3-to-gguf.py",
    "vibevoice": "models/convert-vibevoice-to-gguf.py",
    "parakeet": "models/convert-parakeet-to-gguf.py",
    "moonshine": "models/convert-moonshine-to-gguf.py",
    "canary": "models/convert-canary-to-gguf.py",
    "sensevoice": "models/convert-sensevoice-to-gguf.py",
    "granite": "models/convert-granite-speech-to-gguf.py",
    "voxtral": "models/convert-voxtral-to-gguf.py",
    "cohere": "models/convert-cohere-asr-to-gguf.py",
    "funasr": "models/convert-funasr-to-gguf.py",
    "paraformer": "models/convert-paraformer-to-gguf.py",
    "wav2vec2": "models/convert-wav2vec2-to-gguf.py",
    "qwen3": "models/convert-qwen3-asr-to-gguf.py",
}

_BACKEND_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("qwen3-tts", "qwen3-tts"),
    ("qwen3_tts", "qwen3-tts"),
    ("qwen3-asr", "qwen3"),
    ("f5-tts", "f5-tts"),
    ("f5_tts", "f5-tts"),
    ("cosyvoice3", "cosyvoice3-tts"),
    ("cosyvoice", "cosyvoice3-tts"),
    ("chatterbox", "chatterbox"),
    ("orpheus", "orpheus"),
    ("indextts", "indextts"),
    ("index-tts", "indextts"),
    ("kokoro", "kokoro"),
    ("piper", "piper"),
    ("bark", "bark"),
    ("dia-tts", "dia"),
    ("nari-labs/dia", "dia"),
    ("zonos", "zonos"),
    ("sesame/csm", "csm"),
    ("csm-1b", "csm"),
    ("parler", "parler-tts"),
    ("outetts", "outetts"),
    ("melotts", "melotts"),
    ("pocket-tts", "pocket-tts"),
    ("supertonic", "supertonic"),
    ("vibevoice", "vibevoice"),
    ("parakeet", "parakeet"),
    ("moonshine", "moonshine"),
    ("canary", "canary"),
    ("sensevoice", "sensevoice"),
    ("granite", "granite"),
    ("voxtral", "voxtral"),
    ("cohere", "cohere"),
    ("funasr", "funasr"),
    ("paraformer", "paraformer"),
    ("wav2vec2", "wav2vec2"),
    ("whisper", "whisper"),
)


def _infer_crispasr_backend(
    repo_id: str,
    *,
    tags: Optional[list[str]] = None,
    files: Optional[list[str]] = None,
    config_json: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    haystack_parts = [repo_id.lower()]
    if tags:
        haystack_parts.extend(str(t).lower() for t in tags)
    if files:
        haystack_parts.extend(str(f).lower() for f in files[:30])
    if config_json:
        for key in ("model_type", "architectures"):
            val = config_json.get(key)
            if isinstance(val, str):
                haystack_parts.append(val.lower())
            elif isinstance(val, list):
                haystack_parts.extend(str(x).lower() for x in val)
    haystack = " ".join(haystack_parts)
    for kw, backend in _BACKEND_KEYWORDS:
        if kw in haystack:
            return backend
    return None


def detect_crispasr_compatibility(
    repo_id: str,
    *,
    files: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    config_json: Optional[dict[str, Any]] = None,
    inspect_files_known: bool = False,
) -> dict[str, Any]:
    from .crispasr import list_compiled_backends

    compiled = list_compiled_backends()
    backend = _infer_crispasr_backend(repo_id, tags=tags, files=files, config_json=config_json)
    low_repo = repo_id.lower()
    low_tags = {str(t).lower() for t in (tags or [])}
    gguf_files = [f for f in (files or []) if f.lower().endswith(".gguf")]
    has_gguf = bool(gguf_files) or ("gguf" in low_repo) or ("gguf" in low_tags)

    if backend and backend in compiled:
        if has_gguf:
            return {
                "crispasr_ready": True,
                "crispasr_backend": backend,
                "crispasr_reason": f"Ready · CrispASR ({backend})",
                "can_convert_gguf": False,
                "convert_script": None,
            }
        if not inspect_files_known and "auto-download" in compiled[backend] and backend in {
            "kokoro",
            "piper",
            "parakeet",
            "moonshine",
            "chatterbox",
            "cosyvoice3-tts",
            "orpheus",
            "indextts",
        }:
            return {
                "crispasr_ready": True,
                "crispasr_backend": backend,
                "crispasr_reason": f"Ready · CrispASR ({backend})",
                "can_convert_gguf": False,
                "convert_script": None,
            }
        script = _CRISPASR_CONVERTERS.get(backend)
        return {
            "crispasr_ready": False,
            "crispasr_backend": backend,
            "crispasr_reason": (
                f"Not ready: falta archivo .gguf para el backend CrispASR '{backend}'"
                + (f" (conversión disponible vía {Path(script).name})." if script else ".")
            ),
            "can_convert_gguf": bool(script),
            "convert_script": script,
        }

    if inspect_files_known and gguf_files:
        return {
            "crispasr_ready": True,
            "crispasr_backend": backend,
            "crispasr_reason": f"Ready · Archivo GGUF detectado ({gguf_files[0]})",
            "can_convert_gguf": False,
            "convert_script": None,
        }

    return {
        "crispasr_ready": False,
        "crispasr_backend": backend,
        "crispasr_reason": (
            "Not ready: arquitectura no implementada en CrispASR o sin archivos .gguf compatibles."
        ),
        "can_convert_gguf": False,
        "convert_script": None,
    }


def search_hf_hub(
    kind: Literal["tts", "stt"],
    query: str = "",
    page: int = 1,
    page_size: int = 6,
    ready_only: bool = True,
) -> HubSearchResponse:
    safe_page = max(1, page)
    safe_size = max(1, min(20, page_size))
    pipeline_tag = "text-to-speech" if kind == "tts" else "automatic-speech-recognition"

    api = HfApi()
    raw_query = query.strip()
    needed = safe_page * safe_size + 1

    candidates: list[Any] = []
    seen_ids: set[str] = set()

    def _collect(search_text: Optional[str], limit: int) -> None:
        for m in api.list_models(
            pipeline_tag=pipeline_tag,
            search=search_text or None,
            sort="downloads",
            limit=limit,
        ):
            rid = getattr(m, "id", "") or ""
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                candidates.append(m)

    if ready_only:
        gguf_q = f"{raw_query} gguf".strip() if raw_query else "gguf"
        _collect(gguf_q, max(needed * 3, 24))
        if len(candidates) < needed and raw_query:
            _collect(raw_query, max(needed * 3, 24))
    else:
        _collect(raw_query, max(needed * 2, 18))

    annotated: list[HubModelSummary] = []
    for m in candidates:
        rid = getattr(m, "id", "") or ""
        parts = rid.split("/", 1)
        author = parts[0] if len(parts) == 2 else ""
        short_name = parts[1] if len(parts) == 2 else rid
        tags = [str(t) for t in (getattr(m, "tags", None) or [])[:8]]
        compat = detect_crispasr_compatibility(rid, tags=tags, inspect_files_known=False)
        if ready_only and not compat["crispasr_ready"]:
            continue
        annotated.append(
            HubModelSummary(
                repo_id=rid,
                name=short_name,
                author=author,
                downloads=int(getattr(m, "downloads", 0) or 0),
                likes=int(getattr(m, "likes", 0) or 0),
                tags=tags[:6],
                pipeline_tag=str(getattr(m, "pipeline_tag", pipeline_tag) or pipeline_tag),
                crispasr_ready=bool(compat["crispasr_ready"]),
                crispasr_backend=compat["crispasr_backend"],
                crispasr_reason=str(compat["crispasr_reason"]),
            )
        )

    start = (safe_page - 1) * safe_size
    page_items = annotated[start : start + safe_size]
    has_more = len(annotated) > start + safe_size
    return HubSearchResponse(
        kind=kind,
        query=raw_query,
        page=safe_page,
        page_size=safe_size,
        has_more=has_more,
        items=page_items,
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

    config_json: Optional[dict[str, Any]] = None
    all_names = [getattr(s, "rfilename", "") or "" for s in siblings]
    if "config.json" in all_names:
        try:
            with httpx.Client(follow_redirects=True, timeout=6.0) as client:
                r = client.get(hf_hub_url(repo_id=repo_id, filename="config.json"))
                if r.status_code < 400:
                    parsed = r.json()
                    if isinstance(parsed, dict):
                        config_json = parsed
        except Exception:
            pass

    compat = detect_crispasr_compatibility(
        repo_id,
        files=all_names,
        tags=[str(t) for t in (getattr(info, "tags", None) or [])],
        config_json=config_json,
        inspect_files_known=True,
    )
    return HfInspectResponse(
        source="huggingface",
        repo_id=repo_id,
        suggested_name=suggested_name,
        suggested_kind=suggested_kind,
        files=files,
        **compat,
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
    compat = detect_crispasr_compatibility(
        f"{owner}/{repo}",
        files=[f.filename for f in files],
        inspect_files_known=True,
    )
    return HfInspectResponse(
        source="modelscope",
        repo_id=f"{owner}/{repo}",
        suggested_name=repo.replace("-", " "),
        suggested_kind="tts" if is_tts else "stt",
        files=files,
        **compat,
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
    compat = detect_crispasr_compatibility(clean, files=[fname], inspect_files_known=True)
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
        **compat,
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


def remove_installed_model(
    settings: AppSettings, model_id: str, quant_id: Optional[str] = None
) -> dict[str, Any]:
    models_root = resolved_models_dir(settings).resolve()
    if model_id == "xyz-ioquendo":
        from . import voice_packs

        result = voice_packs.uninstall_pack(models_root)
        return {
            "removed": bool(result.get("removed")),
            "model_id": model_id,
            "untouched": result.get("untouched") or ["qwen_weights", "user_profiles"],
        }
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

    if quant_id is not None:
        quant = next((q for q in target.quants if q.id == quant_id), None)
        if quant is None or quant_id not in target.installed_quants or not quant.files:
            raise FileNotFoundError(f"Quantization is not installed: {model_id}/{quant_id}")
        other_files = {
            filename
            for other in target.quants
            if other.id != quant_id and other.id in target.installed_quants
            for filename in other.files
        }
        deleted = []
        for filename in quant.files:
            file_path = (install_path / filename).resolve()
            if filename not in other_files and _is_within(file_path, install_path) and file_path.is_file():
                file_path.unlink()
                deleted.append(filename)
        remaining = [q for q in target.installed_quants if q != quant_id]
        meta = _meta_file(install_path)
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                if data.get("quant") == quant_id:
                    data["quant"] = remaining[0] if remaining else None
                    meta.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except (OSError, ValueError, AttributeError):
                pass
        return {"removed": bool(deleted), "model_id": model_id, "quant_id": quant_id, "remaining": remaining}

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

        if not _runtime_supported_for_builtin(entry):
            raise ValueError(
                f"Model {model_id} has no compatible local runtime yet."
            )

        quants = entry.get("quants", [])
        chosen = next((q for q in quants if q["id"] == quant_id), None) or next(
            (q for q in quants if q.get("recommended")), quants[0]
        )
        has_files_key = "files" in chosen
        explicit_files = list(chosen.get("files") or [])
        if has_files_key and not explicit_files:
            if (entry.get("quant_policy") or "").lower() == "post_quantize":
                base_q = next((q for q in quants if q.get("files")), None)
                base_label = base_q["label"] if base_q else "base weights"
                raise ValueError(
                    f"Post-quantize variant '{chosen['id']}' for {model_id} is not supported by the runtime yet; install {base_label} instead."
                )
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
        crispasr_backend: Optional[str] = None,
        convert_to_gguf: bool = False,
        convert_script: Optional[str] = None,
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
                "crispasr_backend": crispasr_backend or "",
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
            engine=crispasr_backend or f"custom-{source}",
            direct_urls=direct_urls or {},
            convert_script=convert_script if convert_to_gguf else None,
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
        convert_script: Optional[str] = None,
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
            args=(job_id, repo_id, dest_dir, explicit_files, engine, quant, direct_urls, ev, convert_script),
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
        convert_script: Optional[str] = None,
    ) -> None:
        part_files: list[Path] = []
        last_milestone = 0
        existed_before = dest_dir.exists()

        try:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "downloading"
                job_name = job.name

            if self._notify_cb:
                from .toasts import say

                self._notify_cb(
                    say("app"),
                    say("download_started", name=job_name, quant=quant),
                    0,
                )

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

                    if part_path.exists():
                        part_path.replace(out_path)

            _meta_file(dest_dir).write_text(
                json.dumps({"repo_id": repo_id, "quant": quant, "files": target_files}, indent=2),
                encoding="utf-8",
            )

            if convert_script:
                with self._lock:
                    self._jobs[job_id].current_file = f"Converting ({Path(convert_script).name})..."
                conv_dir = DEFAULT_TMP_DIR / "converters"
                conv_dir.mkdir(parents=True, exist_ok=True)
                script_path = conv_dir / Path(convert_script).name
                raw_url = f"https://raw.githubusercontent.com/CrispStrobe/CrispASR/main/{convert_script.lstrip('/')}"
                with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                    resp = client.get(raw_url)
                    resp.raise_for_status()
                    script_path.write_text(resp.text, encoding="utf-8")
                gguf_out = dest_dir / f"{dest_dir.name}.gguf"
                run_kwargs: dict = {
                    "cwd": str(dest_dir),
                    "stdin": subprocess.DEVNULL,
                    "capture_output": True,
                    "text": True,
                    "timeout": 1800.0,
                }
                if sys.platform == "win32":
                    run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if hasattr(subprocess, "STARTUPINFO"):
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = subprocess.SW_HIDE
                        run_kwargs["startupinfo"] = si
                proc = subprocess.run(
                    [sys.executable, str(script_path), str(dest_dir), "--outfile", str(gguf_out)],
                    **run_kwargs,
                )
                if proc.returncode != 0 or not gguf_out.is_file():
                    err_tail = (proc.stderr or proc.stdout or "").strip()[-600:]
                    raise RuntimeError(
                        f"GGUF conversion failed ({Path(convert_script).name}): {err_tail or 'missing converter dependencies (torch/gguf)'}"
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
