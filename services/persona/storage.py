"""SQLite + atomic local filesystem storage for the k3s Persona service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB
ALLOWED_AUDIO_FORMATS = frozenset({"wav", "mp3", "flac", "ogg", "m4a"})
_SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PersonaServiceError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class PersonaConsentIn(BaseModel):
    speaker_consent_confirmed: bool
    provenance_type: Literal[
        "self_recorded",
        "authorized_actor",
        "synthetic_reference",
        "pack_reference",
    ]
    provenance_note: str = ""
    license: Literal[
        "cc0",
        "cc-by-4.0",
        "personal-non-commercial",
        "proprietary-pack",
        "custom",
    ] = "cc-by-4.0"
    attribution: str = ""


class PersonaMetadataIn(BaseModel):
    id: Optional[str] = None
    slug: Optional[str] = None
    version: str = "1.0.0"
    name: str
    language: str
    locale: str = ""
    origin: Literal["prebuilt", "shared"] = "shared"
    description: str
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    ref_text: str
    consent: PersonaConsentIn
    recommended_engines: list[str] = Field(default_factory=lambda: ["qwen", "xtts", "f5"])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify_persona_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (raw or "").strip().lower()).strip(".-")
    return cleaned[:96] or "persona"


def detect_audio_format(header: bytes) -> Optional[str]:
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "m4a"
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def inspect_audio_bytes(data: bytes, fmt: str) -> tuple[int, int, float]:
    """Return (sample_rate_hz, channels, duration_s); best-effort for WAV without heavy deps."""
    if fmt == "wav":
        try:
            import io

            with wave.open(io.BytesIO(data), "rb") as wf:
                sr = int(wf.getframerate() or 0)
                ch = int(wf.getnchannels() or 1)
                frames = int(wf.getnframes() or 0)
                dur = round(frames / float(sr), 2) if sr > 0 else 0.0
                return sr, ch, dur
        except Exception:
            pass
    return 0, 1, 0.0


class PersonaStore:
    def __init__(self, data_dir: Path, *, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
        self.data_dir = Path(data_dir)
        self.audio_dir = self.data_dir / "audio"
        self.db_path = self.data_dir / "persona.db"
        self.max_upload_bytes = max_upload_bytes
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    version TEXT NOT NULL,
                    name TEXT NOT NULL,
                    language TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    description TEXT NOT NULL,
                    author TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    ref_text TEXT NOT NULL,
                    audio_json TEXT NOT NULL,
                    consent_json TEXT NOT NULL,
                    recommended_engines_json TEXT NOT NULL,
                    audio_filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> dict:
        audio = json.loads(row["audio_json"])
        audio["download_url"] = f"/v1/personas/{row['id']}/audio"
        return {
            "id": row["id"],
            "slug": row["slug"],
            "version": row["version"],
            "name": row["name"],
            "language": row["language"],
            "locale": row["locale"],
            "origin": row["origin"],
            "description": row["description"],
            "author": row["author"],
            "tags": json.loads(row["tags_json"]),
            "ref_text": row["ref_text"],
            "audio": audio,
            "consent": json.loads(row["consent_json"]),
            "recommended_engines": json.loads(row["recommended_engines_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def count_personas(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM personas").fetchone()
            return int(row["cnt"] if row else 0)

    def list_personas(
        self,
        *,
        q: str = "",
        language: Optional[str] = None,
        origin: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM personas ORDER BY updated_at DESC, id ASC").fetchall()
        records = [self._row_to_record(r) for r in rows]

        ql = (q or "").strip().lower()
        lang_l = (language or "").strip().lower()
        origin_l = (origin or "").strip().lower()

        filtered: list[dict] = []
        for rec in records:
            if origin_l and origin_l != "all" and rec["origin"].lower() != origin_l:
                continue
            if lang_l and lang_l != "all":
                rlang = rec["language"].lower()
                rloc = rec["locale"].lower()
                if rlang != lang_l and rloc != lang_l and not rloc.startswith(f"{lang_l}-"):
                    continue
            if ql:
                hay = " ".join(
                    [
                        rec["name"],
                        rec["description"],
                        rec["author"],
                        rec["language"],
                        rec["locale"],
                        *rec["tags"],
                    ]
                ).lower()
                if ql not in hay:
                    continue
            filtered.append(rec)

        total = len(filtered)
        p = max(1, page)
        ps = max(1, min(100, page_size))
        start = (p - 1) * ps
        return {
            "api_version": "v1",
            "items": filtered[start : start + ps],
            "total": total,
            "page": p,
            "page_size": ps,
        }

    def get_persona(self, persona_id: str) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
            return self._row_to_record(row) if row else None

    def get_audio_info(self, persona_id: str) -> Optional[tuple[Path, str, str]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT audio_filename, sha256 FROM personas WHERE id = ?",
                (persona_id,),
            ).fetchone()
        if not row:
            return None
        fp = (self.audio_dir / row["audio_filename"]).resolve()
        if self.audio_dir.resolve() not in fp.parents or not fp.is_file():
            return None
        return fp, str(row["sha256"]), str(row["audio_filename"])

    def create_persona(
        self,
        meta: PersonaMetadataIn,
        audio_bytes: bytes,
        original_filename: str = "reference.wav",
    ) -> dict:
        if not meta.name.strip():
            raise PersonaServiceError("invalid_name", "Persona name is required.", 422)
        if not meta.description.strip():
            raise PersonaServiceError("invalid_description", "Persona description is required.", 422)
        if not meta.ref_text.strip():
            raise PersonaServiceError("invalid_ref_text", "Reference transcript is required.", 422)
        if not meta.consent.speaker_consent_confirmed:
            raise PersonaServiceError(
                "consent_required",
                "speaker_consent_confirmed must be true to publish a Persona.",
                422,
            )
        if not audio_bytes:
            raise PersonaServiceError("empty_audio", "Audio upload is empty.", 422)
        if len(audio_bytes) > self.max_upload_bytes:
            raise PersonaServiceError(
                "file_too_large",
                f"Uploaded audio exceeds limit ({self.max_upload_bytes} bytes).",
                413,
            )

        detected_fmt = detect_audio_format(audio_bytes[:32])
        if detected_fmt not in ALLOWED_AUDIO_FORMATS:
            raise PersonaServiceError(
                "unsupported_audio_format",
                "Audio payload signature is not a supported format (wav/mp3/flac/ogg/m4a).",
                422,
            )

        ext = Path(original_filename or "").suffix.lower().lstrip(".")
        if ext in ALLOWED_AUDIO_FORMATS and ext != detected_fmt:
            raise PersonaServiceError(
                "unsupported_audio_format",
                f"Declared extension '.{ext}' does not match detected audio signature '{detected_fmt}'.",
                422,
            )

        raw_id = (meta.id or meta.slug or slugify_persona_id(meta.name)).strip()
        if ".." in raw_id or not _SAFE_SLUG_RE.match(raw_id):
            raise PersonaServiceError("invalid_id", f"Invalid persona id '{raw_id}'.", 422)

        digest = hashlib.sha256(audio_bytes).hexdigest().lower()
        sr, ch, dur = inspect_audio_bytes(audio_bytes, detected_fmt)
        now = utc_now_iso()

        with self._lock:
            slug = slugify_persona_id(meta.slug or raw_id)
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT id FROM personas WHERE id = ? OR slug = ?",
                    (raw_id, slug),
                ).fetchone()
                if existing:
                    raise PersonaServiceError(
                        "already_exists",
                        f"Persona id or slug '{raw_id}' already exists.",
                        409,
                    )

            audio_filename = f"{raw_id}.{detected_fmt}"
            target_path = self.audio_dir / audio_filename
            temp_path: Optional[Path] = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=self.audio_dir,
                    prefix=f".{raw_id}-",
                    suffix=".part",
                    delete=False,
                ) as tmp:
                    temp_path = Path(tmp.name)
                    tmp.write(audio_bytes)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(temp_path, target_path)
                temp_path = None
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

            audio_spec = {
                "format": detected_fmt,
                "sample_rate_hz": sr,
                "channels": ch,
                "duration_s": dur,
                "sha256": digest,
                "size_bytes": len(audio_bytes),
            }
            author = meta.author.strip() or meta.consent.attribution.strip() or "Contributor"
            locale = meta.locale.strip() or meta.language.strip()

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO personas (
                        id, slug, version, name, language, locale, origin,
                        description, author, tags_json, ref_text, audio_json,
                        consent_json, recommended_engines_json, audio_filename,
                        sha256, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        raw_id,
                        slug,
                        meta.version.strip() or "1.0.0",
                        meta.name.strip(),
                        meta.language.strip(),
                        locale,
                        meta.origin,
                        meta.description.strip(),
                        author,
                        json.dumps([t.strip() for t in meta.tags if t.strip()]),
                        meta.ref_text.strip(),
                        json.dumps(audio_spec),
                        json.dumps(meta.consent.model_dump()),
                        json.dumps(meta.recommended_engines),
                        audio_filename,
                        digest,
                        now,
                        now,
                    ),
                )
                conn.commit()
            created = self.get_persona(raw_id)
            assert created is not None
            return created

    def delete_persona(self, persona_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT audio_filename FROM personas WHERE id = ?",
                (persona_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
            conn.commit()
            fp = self.audio_dir / row["audio_filename"]
            fp.unlink(missing_ok=True)
            return True
