"""Catalog capability contract (Fase 1) — pure helpers, no I/O except uninstall."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

InstallMode = Literal["shared_weights", "per_language_checkpoint", "voices_pack"]
VoiceMode = Literal["clone_profile", "builtin_voices"]
QuantPolicy = Literal["gguf", "checkpoint", "onnx", "binary", "post_quantize"]

INSTALL_MODES: tuple[InstallMode, ...] = (
    "shared_weights",
    "per_language_checkpoint",
    "voices_pack",
)
VOICE_MODES: tuple[VoiceMode, ...] = ("clone_profile", "builtin_voices")
QUANT_POLICIES: tuple[QuantPolicy, ...] = (
    "gguf",
    "checkpoint",
    "onnx",
    "binary",
    "post_quantize",
)

# Defaults by engine when BUILTIN_MODELS omit explicit capabilities.
_ENGINE_DEFAULTS: dict[str, dict[str, Any]] = {
    "qwen": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"],
    },
    "chatterbox": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "ru", "ar", "hi", "nl", "pl", "tr"],
    },
    "cosyvoice3-tts": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["en", "zh", "ja", "ko", "de", "fr", "ru", "es", "it"],
    },
    "orpheus": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "gguf",
        "languages": ["en", "de"],
    },
    "indextts": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "gguf",
        "languages": ["zh", "en"],
    },
    "xtts": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": [
            "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "hu", "ko", "ja", "hi",
        ],
    },
    "f5-tts": {
        "install_mode": "per_language_checkpoint",
        "voice_mode": "clone_profile",
        "quant_policy": "checkpoint",
        "languages": [],  # filled per variant
    },
    "fish-audio": {
        "install_mode": "shared_weights",
        "voice_mode": "clone_profile",
        "quant_policy": "post_quantize",
        "languages": ["en", "zh", "ja", "de", "fr", "es", "ko", "ar", "ru", "nl", "it", "pl", "pt"],
    },
    "kokoro": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": ["en", "es", "fr", "hi", "it", "ja", "pt", "zh"],
    },
    "piper": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": ["es", "en", "de", "fr", "it", "pt", "ru", "nl", "pl"],
    },
    "espeak": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": ["es", "en", "de", "fr", "it", "pt", "ru", "nl", "pl"],
    },
    "sapi5": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "binary",
        "languages": ["all", "es-ES", "en-US"],
    },
    "kitten": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": [
            "en", "de", "es", "it", "pt", "ru", "hi", "fr", "da", "fi", "ja", "ko", "nl", "sv", "sw", "tr",
        ],
    },
    "faster-whisper": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "checkpoint",
        "languages": [],
    },
    "parakeet": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": [],
    },
    "moonshine": {
        "install_mode": "shared_weights",
        "voice_mode": "builtin_voices",
        "quant_policy": "onnx",
        "languages": ["en"],
    },
}


class ModelCapabilities(BaseModel):
    install_mode: InstallMode = "shared_weights"
    voice_mode: VoiceMode = "clone_profile"
    quant_policy: QuantPolicy = "checkpoint"
    languages: list[str] = Field(default_factory=list)


def defaults_for_engine(engine: str) -> ModelCapabilities:
    raw = _ENGINE_DEFAULTS.get(engine, {})
    return ModelCapabilities(
        install_mode=raw.get("install_mode", "shared_weights"),
        voice_mode=raw.get("voice_mode", "clone_profile"),
        quant_policy=raw.get("quant_policy", "checkpoint"),
        languages=list(raw.get("languages", [])),
    )


def capabilities_from_spec(spec: dict[str, Any]) -> ModelCapabilities:
    """Merge explicit catalog fields with engine defaults."""
    base = defaults_for_engine(str(spec.get("engine", "")))
    langs = spec.get("languages")
    if langs is None:
        langs = base.languages
    return ModelCapabilities(
        install_mode=spec.get("install_mode", base.install_mode),
        voice_mode=spec.get("voice_mode", base.voice_mode),
        quant_policy=spec.get("quant_policy", base.quant_policy),
        languages=[str(x) for x in langs],
    )


def resolve_quant(quants: list[Any], quant_id: Optional[str] = None) -> Any | None:
    """Pick a quant option by id, else recommended, else first."""
    if not quants:
        return None
    if quant_id:
        for q in quants:
            qid = q.id if hasattr(q, "id") else q.get("id")
            if qid == quant_id:
                return q
    for q in quants:
        rec = q.recommended if hasattr(q, "recommended") else q.get("recommended", False)
        if rec:
            return q
    return quants[0]


def languages_for_engine(engine: str, spec: dict[str, Any] | None = None) -> list[str]:
    if spec is not None:
        return capabilities_from_spec(spec).languages
    return defaults_for_engine(engine).languages


def is_language_ready(
    family_id: str,
    language: str,
    installed_languages: dict[str, list[str]],
) -> bool:
    ready = installed_languages.get(family_id) or []
    return language in ready


def resolve_install_target(
    *,
    install_mode: InstallMode,
    family_id: str,
    model_id: str,
    language: Optional[str],
) -> dict[str, str]:
    """Describe what an Install click should download for this mode."""
    if install_mode == "per_language_checkpoint":
        if not language:
            raise ValueError("language is required for per_language_checkpoint installs")
        return {
            "mode": install_mode,
            "family_id": family_id,
            "model_id": model_id,
            "language": language,
            "unit": "language_checkpoint",
        }
    if install_mode == "voices_pack":
        if not language:
            raise ValueError("language is required for voices_pack installs")
        return {
            "mode": install_mode,
            "family_id": family_id,
            "model_id": model_id,
            "language": language,
            "unit": "voice_pack",
        }
    return {
        "mode": install_mode,
        "family_id": family_id,
        "model_id": model_id,
        "language": language or "",
        "unit": "shared_weights",
    }


def uninstall_language_pack(
    *,
    models_root: Path,
    install_mode: InstallMode,
    family_id: str,
    language: str,
    catalog_specs: list[dict[str, Any]],
) -> list[str]:
    """
    Remove on-disk language units. Returns deleted paths (as strings).

    - per_language_checkpoint: delete install dirs of catalog entries whose
      languages list is exactly that language (or contains only it as primary).
    - voices_pack: delete voice pack files matching the language under the family dir.
    - shared_weights: no-op (remove whole model via existing delete).
    """
    deleted: list[str] = []
    lang = language.strip().lower()
    if not lang:
        raise ValueError("language is required")

    if install_mode == "shared_weights":
        return deleted

    if install_mode == "per_language_checkpoint":
        for spec in catalog_specs:
            if spec.get("family_id") != family_id:
                continue
            caps = capabilities_from_spec(spec)
            if caps.install_mode != "per_language_checkpoint":
                continue
            langs = [x.lower() for x in caps.languages]
            # Match variants tagged for this language (e.g. f5-tts-spanish → ["es"]).
            if lang not in langs:
                continue
            if len(langs) > 1 and langs != [lang]:
                # Multi-lang shared checkpoint: skip (use full model remove).
                continue
            for name in spec.get("dir_names", [spec["id"]]):
                target = models_root / "tts" / name
                if target.is_dir():
                    import shutil

                    shutil.rmtree(target, ignore_errors=True)
                    deleted.append(str(target))
        return deleted

    # voices_pack
    family_dir = models_root / "tts" / family_id
    if not family_dir.is_dir():
        return deleted
    patterns = [
        f"voices_{lang}.npz",
        f"voices_{lang}.bin",
        f"voices/{lang}",
    ]
    # Kokoro-style voice prefix: e=es, a=en-US, etc. — leave file wipe to Fase 2 mapping;
    # here remove obvious packs and lang subdirs.
    for pat in patterns:
        path = family_dir / pat
        if path.is_file():
            path.unlink(missing_ok=True)
            deleted.append(str(path))
        elif path.is_dir():
            import shutil

            shutil.rmtree(path, ignore_errors=True)
            deleted.append(str(path))
    # Piper locale folders: es/es_ES/...
    for child in family_dir.iterdir():
        if child.is_dir() and (
            child.name == lang or child.name.startswith(f"{lang}_") or child.name.startswith(f"{lang}-")
        ):
            import shutil

            shutil.rmtree(child, ignore_errors=True)
            deleted.append(str(child))
    return deleted


def resolve_runtime_envs_root(app_root: Path) -> Path:
    """Canonical runtime/envs with legacy .venvs read fallback."""
    canonical = app_root / "runtime" / "envs"
    legacy = app_root / ".venvs"
    if canonical.is_dir():
        return canonical
    if legacy.is_dir():
        return legacy
    return canonical
