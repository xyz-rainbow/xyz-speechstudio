"""Versioned reference voice packs (xyz-Ioquendo and future Persona cards).

Packs ship audio + transcript pairs for existing clone engines (Qwen3-TTS).
They are not a new TTS worker. Uninstall never removes engine weights or
user profiles under profiles/.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

PACK_ID_XYZ_IOQUENDO = "xyz-ioquendo"
PACK_DISPLAY_NAME = "xyz-Ioquendo"
PACK_VERSION = "1.0.0-vertical"
MANIFEST_SCHEMA = "speechstudio.voice_pack.v1"

# Stable dependency: Qwen3-TTS 1.7B Base Q4_K_M (existing engine, not a new worker).
REQUIRED_ENGINE = "qwen"
REQUIRED_MODEL_ID = "qwen3-1.7b-base"
REQUIRED_QUANT_ID = "Q4_K_M"

VOICE_ID_PREFIX = "pack:"

_REPO_ROOT = Path(__file__).absolute().parents[2]
DEFAULT_BUNDLE_DIR = _REPO_ROOT / "packs" / "xyz-ioquendo"


@dataclass(frozen=True)
class PackVoice:
    id: str
    slug: str
    name: str
    locale: str
    language: str
    gender: str
    audio_relpath: str
    text_relpath: str
    audio_sha256: str
    text_sha256: str
    duration_s: Optional[float]
    format: str
    size_bytes: int
    provenance: dict[str, Any]

    @property
    def profile_id(self) -> str:
        return f"{VOICE_ID_PREFIX}{self.id}"


@dataclass(frozen=True)
class PackManifest:
    pack_id: str
    name: str
    version: str
    schema: str
    engine: str
    required_model_id: str
    required_quant_id: str
    voices: list[PackVoice]
    excluded: list[dict[str, Any]]
    warnings: list[str]

    def voice_by_id(self, voice_id: str) -> Optional[PackVoice]:
        clean = voice_id.removeprefix(VOICE_ID_PREFIX)
        for voice in self.voices:
            if voice.id == clean or voice.profile_id == voice_id or voice.slug == clean:
                return voice
        return None

    def voices_for_locale(self, locale_or_lang: Optional[str]) -> list[PackVoice]:
        return [
            voice
            for voice in self.voices
            if _matches_locale_filter(voice.locale, voice.language, locale_or_lang)
        ]


def slugify_voice_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    if slug:
        return slug
    # Non-Latin display names (Arabic, Amharic, CJK, …): stable short hash, not "voice".
    digest = hashlib.sha256(unicodedata.normalize("NFC", name).encode("utf-8")).hexdigest()[:12]
    return f"v-{digest}"


def stable_voice_id(pack_id: str, locale: str, name: str) -> str:
    return f"{pack_id}/{locale}/{slugify_voice_name(name)}"


def _language_label(locale: str) -> str:
    primary = (locale or "en").split("-")[0].lower()
    mapping = {
        "af": "Afrikaans",
        "am": "Amharic",
        "ar": "Arabic",
        "az": "Azerbaijani",
        "bg": "Bulgarian",
        "bn": "Bengali",
        "bs": "Bosnian",
        "ca": "Catalan",
        "cmn": "Chinese (Mandarin)",
        "cs": "Czech",
        "cy": "Welsh",
        "da": "Danish",
        "de": "German",
        "el": "Greek",
        "en": "English",
        "es": "Spanish",
        "et": "Estonian",
        "eu": "Basque",
        "fa": "Persian",
        "fi": "Finnish",
        "fil": "Filipino",
        "fr": "French",
        "ga": "Irish",
        "gl": "Galician",
        "gu": "Gujarati",
        "he": "Hebrew",
        "hi": "Hindi",
        "hr": "Croatian",
        "hu": "Hungarian",
        "hy": "Armenian",
        "id": "Indonesian",
        "is": "Icelandic",
        "it": "Italian",
        "ja": "Japanese",
        "jv": "Javanese",
        "ka": "Georgian",
        "kk": "Kazakh",
        "km": "Khmer",
        "kn": "Kannada",
        "ko": "Korean",
        "lo": "Lao",
        "lt": "Lithuanian",
        "lv": "Latvian",
        "mk": "Macedonian",
        "ml": "Malayalam",
        "mn": "Mongolian",
        "mr": "Marathi",
        "ms": "Malay",
        "mt": "Maltese",
        "my": "Burmese",
        "nb": "Norwegian",
        "ne": "Nepali",
        "nl": "Dutch",
        "pl": "Polish",
        "ps": "Pashto",
        "pt": "Portuguese",
        "ro": "Romanian",
        "ru": "Russian",
        "si": "Sinhala",
        "sk": "Slovak",
        "sl": "Slovenian",
        "so": "Somali",
        "sq": "Albanian",
        "sr": "Serbian",
        "su": "Sundanese",
        "sv": "Swedish",
        "sw": "Swahili",
        "ta": "Tamil",
        "te": "Telugu",
        "th": "Thai",
        "tr": "Turkish",
        "uk": "Ukrainian",
        "ur": "Urdu",
        "uz": "Uzbek",
        "vi": "Vietnamese",
        "wuu": "Chinese (Wu)",
        "yue": "Chinese (Cantonese)",
        "zh": "Chinese",
        "zu": "Zulu",
    }
    return mapping.get(primary, primary.upper())


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def estimate_mp3_duration_s(path: Path) -> Optional[float]:
    """Best-effort MP3 duration without optional deps. Prefer ffprobe when packaging."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 4:
        return None
    i = 0
    if data.startswith(b"ID3") and len(data) >= 10:
        size = (
            ((data[6] & 0x7F) << 21)
            | ((data[7] & 0x7F) << 14)
            | ((data[8] & 0x7F) << 7)
            | (data[9] & 0x7F)
        )
        i = 10 + size
    while i + 4 < len(data):
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            break
        i += 1
    else:
        return None
    version = (data[i + 1] >> 3) & 3
    bitrate_idx = (data[i + 2] >> 4) & 0xF
    sample_idx = (data[i + 2] >> 2) & 3
    channel = (data[i + 3] >> 6) & 3
    br_table = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    sr_table = [44100, 48000, 32000, 0]
    br = br_table[bitrate_idx] * 1000
    sr = sr_table[sample_idx]
    if not br or not sr:
        return None
    side = 17 if version == 3 and channel == 3 else 32 if version == 3 else 9 if channel == 3 else 17
    xing = i + 4 + side
    if data[xing : xing + 4] in (b"Xing", b"Info") and xing + 8 <= len(data):
        import struct

        flags = struct.unpack(">I", data[xing + 4 : xing + 8])[0]
        off = xing + 8
        if flags & 1 and off + 4 <= len(data):
            frames = struct.unpack(">I", data[off : off + 4])[0]
            spf = 1152 if version == 3 else 576
            if frames > 0:
                return round(frames * spf / float(sr), 3)
    audio_bytes = max(0, len(data) - i)
    return round(audio_bytes * 8 / float(br), 3)


def parse_source_stem(stem: str) -> tuple[str, str]:
    """'Álvaro_Hombre_Neuronal' -> ('Álvaro', 'male')."""
    parts = stem.split("_")
    gender = "unknown"
    name_parts: list[str] = []
    for part in parts:
        low = part.lower()
        if low in {"hombre", "male", "man"}:
            gender = "male"
            continue
        if low in {"mujer", "female", "woman"}:
            gender = "female"
            continue
        if low in {"neuronal", "neural", "voice"}:
            continue
        name_parts.append(part)
    name = " ".join(name_parts).strip() or stem
    return name, gender


def pack_install_dir(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> Path:
    return Path(models_dir) / "voice-packs" / pack_id


def installed_marker_path(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> Path:
    return pack_install_dir(models_dir, pack_id) / "installed.json"


def is_pack_installed(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> bool:
    marker = installed_marker_path(models_dir, pack_id)
    if not marker.is_file():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("pack_id") == pack_id and data.get("voices"))


def load_manifest(path: Path) -> PackManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    voices = [
        PackVoice(
            id=item["id"],
            slug=item["slug"],
            name=item["name"],
            locale=item["locale"],
            language=item.get("language") or _language_label(item["locale"]),
            gender=item.get("gender") or "unknown",
            audio_relpath=item["audio_relpath"],
            text_relpath=item["text_relpath"],
            audio_sha256=item["audio_sha256"],
            text_sha256=item["text_sha256"],
            duration_s=item.get("duration_s"),
            format=item.get("format") or "mp3",
            size_bytes=int(item.get("size_bytes") or 0),
            provenance=dict(item.get("provenance") or {}),
        )
        for item in raw.get("voices") or []
    ]
    return PackManifest(
        pack_id=raw["pack_id"],
        name=raw.get("name") or PACK_DISPLAY_NAME,
        version=raw.get("version") or PACK_VERSION,
        schema=raw.get("schema") or MANIFEST_SCHEMA,
        engine=raw.get("engine") or REQUIRED_ENGINE,
        required_model_id=raw.get("required_model_id") or REQUIRED_MODEL_ID,
        required_quant_id=raw.get("required_quant_id") or REQUIRED_QUANT_ID,
        voices=voices,
        excluded=list(raw.get("excluded") or []),
        warnings=list(raw.get("warnings") or []),
    )


def default_bundle_manifest_path(bundle_dir: Optional[Path] = None) -> Path:
    root = bundle_dir or DEFAULT_BUNDLE_DIR
    vertical = root / "manifest.vertical.v1.json"
    if vertical.is_file():
        return vertical
    full = root / "manifest.full.v1.json"
    if full.is_file():
        return full
    raise FileNotFoundError(f"No xyz-Ioquendo manifest under {root}")


def scan_source_tree(
    source_root: Path,
    *,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
    skip_dirs: Iterable[str] = ("benchmark",),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Scan locale folders for audio+transcript pairs. Originals are never modified."""
    skip = {name.lower() for name in skip_dirs}
    voices: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_ids: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}

    if not source_root.is_dir():
        raise FileNotFoundError(f"Source pack root not found: {source_root}")

    for locale_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        locale = locale_dir.name
        if locale.lower() in skip:
            excluded.append({"path": locale, "reason": "benchmark_or_skip_dir"})
            continue
        # BCP47-ish folders: es-ES, en-GB, fil-PH, zh-CN-henan, …
        if not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,16}){0,3}", locale):
            warnings.append(f"Skipping non-locale directory: {locale}")
            excluded.append({"path": locale, "reason": "non_locale_dir"})
            continue

        stems: dict[str, dict[str, Path]] = {}
        for file_path in sorted(locale_dir.iterdir()):
            if not file_path.is_file():
                continue
            ext = file_path.suffix.lower()
            if ext not in {".mp3", ".wav", ".flac", ".txt"}:
                excluded.append({"path": f"{locale}/{file_path.name}", "reason": "unsupported_extension"})
                continue
            stems.setdefault(file_path.stem, {})[ext] = file_path

        for stem, files in sorted(stems.items()):
            audio = files.get(".mp3") or files.get(".wav") or files.get(".flac")
            text = files.get(".txt")
            if audio is None or text is None:
                excluded.append(
                    {
                        "path": f"{locale}/{stem}",
                        "reason": "incomplete_pair",
                        "has_audio": audio is not None,
                        "has_text": text is not None,
                    }
                )
                continue
            if audio.stat().st_size < 1024:
                excluded.append({"path": f"{locale}/{audio.name}", "reason": "audio_too_small"})
                continue
            transcript = text.read_text(encoding="utf-8", errors="replace").strip()
            if not transcript:
                excluded.append({"path": f"{locale}/{text.name}", "reason": "empty_transcript"})
                continue

            name, gender = parse_source_stem(stem)
            slug = slugify_voice_name(name)
            voice_id = f"{pack_id}/{locale}/{slug}"
            if voice_id in seen_ids:
                # Disambiguate rare collisions (same romanized slug) with gender/stem.
                suffix = gender if gender != "unknown" else slugify_voice_name(stem)
                slug = f"{slug}-{suffix}"
                voice_id = f"{pack_id}/{locale}/{slug}"
            audio_hash = sha256_file(audio)
            text_hash = sha256_file(text)
            if voice_id in seen_ids:
                excluded.append(
                    {
                        "path": f"{locale}/{audio.name}",
                        "reason": "duplicate_id",
                        "duplicate_of": seen_ids[voice_id],
                    }
                )
                continue
            if audio_hash in seen_hashes:
                warnings.append(
                    f"Duplicate audio hash for {voice_id} also seen in {seen_hashes[audio_hash]}"
                )
            seen_ids[voice_id] = f"{locale}/{audio.name}"
            seen_hashes[audio_hash] = voice_id

            fmt = audio.suffix.lower().lstrip(".")
            duration = estimate_mp3_duration_s(audio) if fmt == "mp3" else None
            voices.append(
                {
                    "id": voice_id,
                    "slug": slug,
                    "name": name,
                    "locale": locale,
                    "language": _language_label(locale),
                    "gender": gender,
                    "audio_relpath": f"{locale}/{audio.name}",
                    "text_relpath": f"{locale}/{text.name}",
                    "audio_sha256": audio_hash,
                    "text_sha256": text_hash,
                    "duration_s": duration,
                    "format": fmt,
                    "size_bytes": audio.stat().st_size,
                    "provenance": {
                        "type": "synthetic_reference",
                        "generator": "Qwen3-TTS",
                        "note": (
                            "Reference clip synthesized for Speech Studio cloning demos. "
                            "Not an official Loquendo product; naming does not grant third-party rights."
                        ),
                        "source_stem": stem,
                    },
                }
            )
    return voices, excluded, warnings


def build_manifest_dict(
    *,
    voices: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    warnings: list[str],
    version: str = PACK_VERSION,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
) -> dict[str, Any]:
    locales = sorted({v["locale"] for v in voices})
    return {
        "schema": MANIFEST_SCHEMA,
        "pack_id": pack_id,
        "name": PACK_DISPLAY_NAME,
        "version": version,
        "engine": REQUIRED_ENGINE,
        "required_model_id": REQUIRED_MODEL_ID,
        "required_quant_id": REQUIRED_QUANT_ID,
        "voice_count": len(voices),
        "locales": locales,
        "license": {
            "kind": "proprietary-pack",
            "redistribution": "blocked_until_review",
            "disclaimer": (
                "xyz-Ioquendo is an internal Speech Studio pack name. It is not Loquendo TTS, "
                "does not claim affiliation with Nuance/Loquendo, and must not be redistributed "
                "until license and provenance review is complete."
            ),
        },
        "voices": voices,
        "excluded": excluded,
        "warnings": warnings,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_vertical_manifest_from_bundle(bundle_dir: Optional[Path] = None) -> dict[str, Any]:
    root = bundle_dir or DEFAULT_BUNDLE_DIR
    voices_root = root / "voices"
    voices: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    warnings: list[str] = []
    for locale_dir in sorted(p for p in voices_root.iterdir() if p.is_dir()):
        locale = locale_dir.name
        for voice_dir in sorted(p for p in locale_dir.iterdir() if p.is_dir()):
            audio = voice_dir / "audio.mp3"
            text = voice_dir / "transcript.txt"
            if not audio.is_file() or not text.is_file():
                excluded.append({"path": str(voice_dir.relative_to(root)), "reason": "incomplete_pair"})
                continue
            name = voice_dir.name.replace("-", " ").title()
            # Prefer human names for known vertical voices.
            display = {"alvaro": "Álvaro", "alfie": "Alfie"}.get(voice_dir.name.lower(), name)
            voice_id = stable_voice_id(PACK_ID_XYZ_IOQUENDO, locale, display)
            voices.append(
                {
                    "id": voice_id,
                    "slug": slugify_voice_name(display),
                    "name": display,
                    "locale": locale,
                    "language": _language_label(locale),
                    "gender": "male",
                    "audio_relpath": str(audio.relative_to(root)).replace("\\", "/"),
                    "text_relpath": str(text.relative_to(root)).replace("\\", "/"),
                    "audio_sha256": sha256_file(audio),
                    "text_sha256": sha256_file(text),
                    "duration_s": estimate_mp3_duration_s(audio),
                    "format": "mp3",
                    "size_bytes": audio.stat().st_size,
                    "provenance": {
                        "type": "synthetic_reference",
                        "generator": "Qwen3-TTS",
                        "note": (
                            "Vertical-slice reference for Speech Studio. Generated with Qwen3-TTS; "
                            "not an official Loquendo voice and not redistributable pending license review."
                        ),
                        "source_locale": locale,
                    },
                }
            )
    return build_manifest_dict(
        voices=voices,
        excluded=excluded,
        warnings=warnings,
        version=PACK_VERSION,
    )


def install_from_bundle(
    models_dir: Path,
    *,
    bundle_dir: Optional[Path] = None,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
) -> dict[str, Any]:
    """Copy pack files into models/voice-packs/<id>. Does not touch Qwen weights or profiles."""
    root = bundle_dir or DEFAULT_BUNDLE_DIR
    manifest_path = default_bundle_manifest_path(root)
    if not manifest_path.is_file():
        # Generate vertical manifest on the fly when missing.
        data = build_vertical_manifest_from_bundle(root)
        write_manifest(root / "manifest.vertical.v1.json", data)
        manifest_path = root / "manifest.vertical.v1.json"
    manifest = load_manifest(manifest_path)
    dest = pack_install_dir(models_dir, pack_id)
    dest.mkdir(parents=True, exist_ok=True)
    installed_voices: list[dict[str, Any]] = []
    for voice in manifest.voices:
        src_audio = root / voice.audio_relpath
        src_text = root / voice.text_relpath
        if not src_audio.is_file() or not src_text.is_file():
            raise FileNotFoundError(f"Missing pack asset for {voice.id}")
        if sha256_file(src_audio) != voice.audio_sha256:
            raise ValueError(f"Audio hash mismatch for {voice.id}")
        if sha256_file(src_text) != voice.text_sha256:
            raise ValueError(f"Transcript hash mismatch for {voice.id}")
        voice_dest = dest / "voices" / voice.locale / voice.slug
        voice_dest.mkdir(parents=True, exist_ok=True)
        audio_dest = voice_dest / f"audio.{voice.format}"
        text_dest = voice_dest / "transcript.txt"
        shutil.copy2(src_audio, audio_dest)
        shutil.copy2(src_text, text_dest)
        installed_voices.append(
            {
                "id": voice.id,
                "slug": voice.slug,
                "name": voice.name,
                "locale": voice.locale,
                "language": voice.language,
                "gender": voice.gender,
                "audio_path": str(audio_dest),
                "text_path": str(text_dest),
                "audio_sha256": voice.audio_sha256,
                "text_sha256": voice.text_sha256,
                "duration_s": voice.duration_s,
                "format": voice.format,
                "provenance": voice.provenance,
            }
        )
    marker = {
        "pack_id": pack_id,
        "name": manifest.name,
        "version": manifest.version,
        "schema": manifest.schema,
        "engine": manifest.engine,
        "required_model_id": manifest.required_model_id,
        "required_quant_id": manifest.required_quant_id,
        "voices": installed_voices,
    }
    installed_marker_path(models_dir, pack_id).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(manifest_path, dest / "manifest.json")
    return marker


def install_from_source(
    models_dir: Path,
    source_root: Path,
    *,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
) -> dict[str, Any]:
    """Scan a read-only local locale tree and install all valid pairs into models/voice-packs/<id>."""
    src = Path(source_root)
    voices, excluded, warnings = scan_source_tree(src, pack_id=pack_id)
    if not voices:
        raise ValueError(f"No valid audio+transcript voice pairs found under {src}")

    dest = pack_install_dir(models_dir, pack_id)
    dest.mkdir(parents=True, exist_ok=True)
    installed_voices: list[dict[str, Any]] = []
    for item in voices:
        src_audio = src / item["audio_relpath"]
        src_text = src / item["text_relpath"]
        if not src_audio.is_file() or not src_text.is_file():
            raise FileNotFoundError(f"Missing source pack asset for {item['id']}")
        voice_dest = dest / "voices" / item["locale"] / item["slug"]
        voice_dest.mkdir(parents=True, exist_ok=True)
        audio_dest = voice_dest / f"audio.{item['format']}"
        text_dest = voice_dest / "transcript.txt"
        shutil.copy2(src_audio, audio_dest)
        shutil.copy2(src_text, text_dest)
        installed_voices.append(
            {
                "id": item["id"],
                "slug": item["slug"],
                "name": item["name"],
                "locale": item["locale"],
                "language": item["language"],
                "gender": item["gender"],
                "audio_path": str(audio_dest),
                "text_path": str(text_dest),
                "audio_sha256": item["audio_sha256"],
                "text_sha256": item["text_sha256"],
                "duration_s": item.get("duration_s"),
                "format": item["format"],
                "provenance": item["provenance"],
            }
        )

    version = "1.0.0-local"
    marker = {
        "pack_id": pack_id,
        "name": PACK_DISPLAY_NAME,
        "version": version,
        "schema": MANIFEST_SCHEMA,
        "engine": REQUIRED_ENGINE,
        "required_model_id": REQUIRED_MODEL_ID,
        "required_quant_id": REQUIRED_QUANT_ID,
        "source_root": str(src),
        "voices": installed_voices,
    }
    installed_marker_path(models_dir, pack_id).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_dict = build_manifest_dict(
        voices=voices,
        excluded=excluded,
        warnings=warnings,
        version=version,
        pack_id=pack_id,
    )
    write_manifest(dest / "manifest.json", manifest_dict)
    return marker


def repair_pack(models_dir: Path, *, bundle_dir: Optional[Path] = None, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> dict[str, Any]:
    """Re-copy missing/corrupt files from the installed source_root or local bundle without touching Qwen/profiles."""
    if bundle_dir is None:
        existing = load_installed(models_dir, pack_id) or {}
        src_str = str(existing.get("source_root") or "").strip()
        if src_str and Path(src_str).is_dir():
            return install_from_source(models_dir, Path(src_str), pack_id=pack_id)
    return install_from_bundle(models_dir, bundle_dir=bundle_dir, pack_id=pack_id)


def uninstall_pack(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> dict[str, Any]:
    dest = pack_install_dir(models_dir, pack_id)
    removed = False
    if dest.exists():
        shutil.rmtree(dest)
        removed = True
    return {"removed": removed, "path": str(dest), "untouched": ["qwen_weights", "user_profiles"]}


def load_installed(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> Optional[dict[str, Any]]:
    marker = installed_marker_path(models_dir, pack_id)
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _matches_locale_filter(
    voice_locale: str, voice_language: str, locale_or_lang: Optional[str]
) -> bool:
    needle = (locale_or_lang or "").strip().replace("_", "-").lower()
    if not needle or needle in {"all", "all languages", "auto"}:
        return True
    base = needle.split("(", 1)[0].strip()
    loc = (voice_locale or "").lower()
    if loc == needle or loc.startswith(needle + "-") or loc.split("-")[0] == needle:
        return True
    lang_low = (voice_language or "").lower()
    label_low = _language_label(voice_locale).lower()
    return (
        lang_low == needle
        or label_low == needle
        or bool(base and (lang_low == base or label_low == base))
    )


def list_installed_voices(
    models_dir: Path,
    *,
    locale: Optional[str] = None,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
) -> list[dict[str, str]]:
    installed = load_installed(models_dir, pack_id)
    if not installed:
        return []
    voices = installed.get("voices") or []
    out: list[dict[str, str]] = []
    for voice in voices:
        loc = str(voice.get("locale") or "")
        lang = str(voice.get("language") or "")
        if not _matches_locale_filter(loc, lang, locale):
            continue
        out.append(
            {
                "id": f"{VOICE_ID_PREFIX}{voice['id']}",
                "label": f"{voice['name']} ({loc})",
                "locale": loc,
                "name": str(voice["name"]),
                "pack_id": pack_id,
                "kind": "pack_reference",
            }
        )
    return out


def resolve_pack_voice(
    models_dir: Path,
    voice_or_profile_id: str,
    *,
    pack_id: str = PACK_ID_XYZ_IOQUENDO,
) -> Optional[dict[str, Any]]:
    installed = load_installed(models_dir, pack_id)
    if not installed:
        return None
    clean = voice_or_profile_id.removeprefix(VOICE_ID_PREFIX)
    for voice in installed.get("voices") or []:
        if voice.get("id") == clean or voice.get("slug") == clean:
            audio = Path(voice["audio_path"])
            text = Path(voice["text_path"])
            if not audio.is_file() or not text.is_file():
                return None
            return {
                "id": f"{VOICE_ID_PREFIX}{voice['id']}",
                "name": voice["name"],
                "language": voice.get("language") or _language_label(voice.get("locale") or "en"),
                "locale": voice.get("locale") or "",
                "engine": REQUIRED_ENGINE,
                "ref_audio_path": str(audio),
                "ref_text": text.read_text(encoding="utf-8", errors="replace").strip(),
                "ready": True,
                "editable": False,
                "pack_id": pack_id,
                "kind": "pack_reference",
            }
    return None


def as_voice_profile(data: dict[str, Any]):
    """Build a non-persisted VoiceProfile for synth; never written to profiles.json."""
    import time

    from .profiles import VoiceProfile

    now = time.time()
    return VoiceProfile(
        id=str(data["id"]),
        name=str(data["name"]),
        language=str(data.get("language") or "Spanish"),
        engine="qwen",
        ref_audio_path=str(data.get("ref_audio_path") or ""),
        ref_text=str(data.get("ref_text") or ""),
        ready=True,
        created_at=now,
        updated_at=now,
    )


def resolve_profile_like(models_dir: Path, profile_id: str):
    """Resolve user profile id or pack:<voice> into a VoiceProfile-compatible object."""
    if not profile_id:
        return None
    if str(profile_id).startswith(VOICE_ID_PREFIX) or str(profile_id).startswith(f"{PACK_ID_XYZ_IOQUENDO}/"):
        data = resolve_pack_voice(models_dir, profile_id)
        return as_voice_profile(data) if data else None
    return None


def installed_locale_codes(models_dir: Path, pack_id: str = PACK_ID_XYZ_IOQUENDO) -> list[str]:
    installed = load_installed(models_dir, pack_id)
    if not installed:
        return []
    codes: set[str] = set()
    for voice in installed.get("voices") or []:
        loc = str(voice.get("locale") or "")
        if not loc:
            continue
        codes.add(loc.split("-")[0].lower())
    return sorted(codes)


def dependency_status(catalog_entries: Iterable[Any]) -> dict[str, Any]:
    """Report whether required Qwen Q4 weights are present (catalog entries)."""
    installed_q4 = False
    installed_any_qwen_base = False
    for entry in catalog_entries:
        eid = getattr(entry, "id", None) or (entry.get("id") if isinstance(entry, dict) else None)
        if not eid:
            continue
        eid_s = str(eid)
        if not eid_s.startswith(REQUIRED_MODEL_ID):
            continue
        is_installed = bool(getattr(entry, "installed", None) if not isinstance(entry, dict) else entry.get("installed"))
        quants = getattr(entry, "installed_quants", None) if not isinstance(entry, dict) else entry.get("installed_quants")
        quants = list(quants or [])
        if is_installed:
            installed_any_qwen_base = True
        if REQUIRED_QUANT_ID in quants or eid_s.endswith(f"-{REQUIRED_QUANT_ID}"):
            installed_q4 = True
    return {
        "required_model_id": REQUIRED_MODEL_ID,
        "required_quant_id": REQUIRED_QUANT_ID,
        "qwen_base_installed": installed_any_qwen_base,
        "qwen_q4_installed": installed_q4,
        "ready": installed_q4,
    }


def to_persona_records(installed: dict[str, Any]) -> list[dict[str, Any]]:
    """Shape installed pack voices for future Persona cards (stable ids reused)."""
    records: list[dict[str, Any]] = []
    version = installed.get("version") or PACK_VERSION
    for voice in installed.get("voices") or []:
        records.append(
            {
                "id": voice["id"],
                "slug": voice["slug"],
                "version": version,
                "name": voice["name"],
                "language": voice.get("language") or _language_label(voice.get("locale") or "en"),
                "locale": voice.get("locale"),
                "origin": "prebuilt",
                "description": f"{PACK_DISPLAY_NAME} reference voice for Qwen3-TTS cloning.",
                "author": "Speech Studio",
                "tags": [PACK_ID_XYZ_IOQUENDO, voice.get("locale") or "", "pack_reference"],
                "ref_text": Path(voice["text_path"]).read_text(encoding="utf-8", errors="replace").strip()
                if Path(voice["text_path"]).is_file()
                else "",
                "audio": {
                    "format": voice.get("format") or "mp3",
                    "sample_rate_hz": 0,
                    "channels": 1,
                    "duration_s": voice.get("duration_s") or 0,
                    "sha256": voice.get("audio_sha256"),
                    "local_path": voice.get("audio_path"),
                },
                "consent": {
                    "speaker_consent_confirmed": False,
                    "provenance_type": "pack_reference",
                    "provenance_note": (voice.get("provenance") or {}).get("note")
                    or "Synthetic pack reference; redistribution pending license review.",
                    "license": "proprietary-pack",
                    "attribution": PACK_DISPLAY_NAME,
                },
                "recommended_engines": [REQUIRED_ENGINE],
            }
        )
    return records
