"""Engine audio adaptation rules and non-destructive conversion helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from . import audio_prep


RefTextRequirement = Literal["required", "recommended", "optional", "none"]


@dataclass(frozen=True)
class EngineAudioSpec:
    engine: str
    label: str
    supports_cloning: bool
    target_sample_rate_hz: Optional[int]
    target_channels: Optional[int]
    max_duration_s: Optional[float]
    recommended_duration_s: Optional[tuple[float, float]]
    ref_text_requirement: RefTextRequirement
    notes: str


ENGINE_AUDIO_SPECS: dict[str, EngineAudioSpec] = {
    "qwen": EngineAudioSpec(
        engine="qwen",
        label="Qwen3-TTS",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(6.0, 15.0),
        ref_text_requirement="recommended",
        notes="Normalized to 24 kHz mono 16-bit PCM WAV for CrispASR / Qwen embeddings.",
    ),
    "chatterbox": EngineAudioSpec(
        engine="chatterbox",
        label="Chatterbox",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(5.0, 15.0),
        ref_text_requirement="optional",
        notes="Normalized to 24 kHz mono 16-bit PCM WAV for CrispASR.",
    ),
    "chatterbox-turbo": EngineAudioSpec(
        engine="chatterbox-turbo",
        label="Chatterbox Turbo",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(5.0, 15.0),
        ref_text_requirement="optional",
        notes="Normalized to 24 kHz mono 16-bit PCM WAV for CrispASR.",
    ),
    "cosyvoice3-tts": EngineAudioSpec(
        engine="cosyvoice3-tts",
        label="CosyVoice3",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(5.0, 15.0),
        ref_text_requirement="recommended",
        notes="Normalized to 24 kHz mono 16-bit PCM WAV with paired transcript recommended.",
    ),
    "indextts": EngineAudioSpec(
        engine="indextts",
        label="IndexTTS 1.5",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(5.0, 15.0),
        ref_text_requirement="optional",
        notes="Normalized to 24 kHz mono 16-bit PCM WAV for CrispASR.",
    ),
    "f5": EngineAudioSpec(
        engine="f5",
        label="F5-TTS",
        supports_cloning=True,
        target_sample_rate_hz=24000,
        target_channels=1,
        max_duration_s=12.0,
        recommended_duration_s=(6.0, 11.0),
        ref_text_requirement="required",
        notes="24 kHz mono WAV; references longer than 12s are non-destructively clipped to <=11s.",
    ),
    "xtts": EngineAudioSpec(
        engine="xtts",
        label="XTTS v2",
        supports_cloning=True,
        target_sample_rate_hz=22050,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(6.0, 12.0),
        ref_text_requirement="optional",
        notes="Mono conditioning WAV at 22.05 kHz (worker also resamples 24 kHz clips cleanly).",
    ),
    "fish": EngineAudioSpec(
        engine="fish",
        label="Fish Speech 1.5",
        supports_cloning=True,
        target_sample_rate_hz=44100,
        target_channels=1,
        max_duration_s=None,
        recommended_duration_s=(5.0, 15.0),
        ref_text_requirement="recommended",
        notes="VQGAN reference encoding resamples mono audio to 44.1 kHz.",
    ),
    "kokoro": EngineAudioSpec(
        engine="kokoro",
        label="Kokoro 82M",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Built-in voices only; zero-shot voice cloning is not supported.",
    ),
    "piper": EngineAudioSpec(
        engine="piper",
        label="Piper",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Built-in voices only; zero-shot voice cloning is not supported.",
    ),
    "orpheus": EngineAudioSpec(
        engine="orpheus",
        label="Orpheus 3B",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Cataloged with built-in voice presets only; custom cloning is not supported.",
    ),
    "kitten": EngineAudioSpec(
        engine="kitten",
        label="KittenTTS 2 Mini",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Uses voices_<lang>.npz presets only; custom cloning is not supported.",
    ),
    "espeak": EngineAudioSpec(
        engine="espeak",
        label="eSpeak NG",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Formant synthesizer with built-in voices only.",
    ),
    "sapi5": EngineAudioSpec(
        engine="sapi5",
        label="Windows SAPI 5",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="System voices only; custom audio cloning is not supported.",
    ),
}


def canonical_engine_name(engine: str) -> str:
    low = (engine or "").strip().lower()
    aliases = {
        "f5-tts": "f5",
        "fish-audio": "fish",
        "qwen3-tts": "qwen",
        "cosyvoice3": "cosyvoice3-tts",
    }
    return aliases.get(low, low)


def get_engine_audio_spec(engine: str) -> EngineAudioSpec:
    key = canonical_engine_name(engine)
    if key in ENGINE_AUDIO_SPECS:
        return ENGINE_AUDIO_SPECS[key]
    return EngineAudioSpec(
        engine=key or engine,
        label=engine or "Unknown",
        supports_cloning=False,
        target_sample_rate_hz=None,
        target_channels=None,
        max_duration_s=None,
        recommended_duration_s=None,
        ref_text_requirement="none",
        notes="Cloning support is not verified for this engine.",
    )


def engine_supports_cloning(engine: str) -> bool:
    return get_engine_audio_spec(engine).supports_cloning


def describe_engine_adaptation(
    engine: str,
    audio_info: dict[str, Any],
    *,
    has_ref_text: bool = True,
) -> dict[str, Any]:
    spec = get_engine_audio_spec(engine)
    if not spec.supports_cloning:
        return {
            "engine": spec.engine,
            "label": spec.label,
            "supports_cloning": False,
            "status": "unsupported_no_cloning",
            "target_sample_rate_hz": None,
            "target_channels": None,
            "max_duration_s": None,
            "conversions_needed": [],
            "warnings": [spec.notes],
        }

    fmt = str(audio_info.get("format") or "wav").strip().lower()
    sr = int(audio_info.get("sample_rate") or audio_info.get("sample_rate_hz") or 0)
    ch = int(audio_info.get("channels") or 1)
    dur = float(audio_info.get("duration_s") or 0.0)

    conversions: list[str] = []
    warnings: list[str] = []

    if fmt and fmt != "wav":
        conversions.append(f"Transcode {fmt.upper()} -> 16-bit PCM WAV")
    if ch > 1:
        conversions.append(f"Downmix {ch}ch -> mono (1ch)")
    if spec.target_sample_rate_hz and sr > 0 and sr != spec.target_sample_rate_hz:
        conversions.append(f"Resample {sr} Hz -> {spec.target_sample_rate_hz} Hz")
    if spec.max_duration_s and dur > spec.max_duration_s:
        conversions.append(f"Trim {dur:.1f}s -> <= {spec.max_duration_s:.0f}s (keeps original)")

    if not has_ref_text:
        if spec.ref_text_requirement == "required":
            warnings.append("Reference transcript is required for accurate timing.")
        elif spec.ref_text_requirement == "recommended":
            warnings.append("Reference transcript is recommended for clean alignment.")

    if spec.recommended_duration_s and dur > 0:
        min_d, max_d = spec.recommended_duration_s
        if dur < min_d:
            warnings.append(f"Clip is shorter than the recommended {min_d:.0f}-{max_d:.0f}s range.")
        elif spec.max_duration_s is None and dur > max_d:
            warnings.append(f"Clip exceeds the recommended {min_d:.0f}-{max_d:.0f}s range.")

    return {
        "engine": spec.engine,
        "label": spec.label,
        "supports_cloning": True,
        "status": "needs_conversion" if conversions else "compatible",
        "target_sample_rate_hz": spec.target_sample_rate_hz,
        "target_channels": spec.target_channels,
        "max_duration_s": spec.max_duration_s,
        "conversions_needed": conversions,
        "warnings": warnings,
    }


def adapt_audio_for_engine(
    original_src: Path,
    engine: str,
    output_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """
    Create a derived PCM16 mono WAV copy adapted for `engine` inside `output_dir`,
    never mutating `original_src`.
    """
    src = Path(original_src)
    if not src.is_file():
        raise FileNotFoundError(f"Original reference audio not found: {src}")

    spec = get_engine_audio_spec(engine)
    if not spec.supports_cloning or spec.target_sample_rate_hz is None:
        raise ValueError(f"Engine '{engine}' does not support voice cloning reference audio.")

    target_sr = spec.target_sample_rate_hz
    samples, src_sr, _ = audio_prep._read_pcm_wave(src)
    resampled = audio_prep._resample_linear(samples, src_sr, target_sr)

    if spec.engine == "f5" and len(resampled) > int(math.floor(12.0 * target_sr)):
        cap = int(math.floor(11.0 * target_sr))
        resampled = resampled[:cap]

    output_dir.mkdir(parents=True, exist_ok=True)
    dst = output_dir / f"adapted_{spec.engine}.wav"
    audio_prep._write_pcm16_mono(dst, resampled, target_sr)
    return dst, {
        "engine": spec.engine,
        "duration_s": round(len(resampled) / float(target_sr), 2),
        "sample_rate": target_sr,
        "channels": 1,
        "source_path": str(src),
    }
