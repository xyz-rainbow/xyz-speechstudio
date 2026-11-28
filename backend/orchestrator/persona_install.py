"""Validated download, integrity verification, and non-destructive local install for remote Personas."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel

from . import audio_adaptation, profiles
from .config import DEFAULT_TMP_DIR

DEFAULT_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MiB
ALLOWED_AUDIO_FORMATS = frozenset({"wav", "mp3", "flac", "ogg", "m4a"})
_PERSONA_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class PersonaInstallError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RemotePersonaInstallRequest(BaseModel):
    persona_id: str
    name: str
    language: str = "Spanish"
    engine: str = "qwen"
    ref_text: str = ""
    library_url: str
    download_url: str
    sha256: str
    audio_format: str = "wav"
    expected_size_bytes: Optional[int] = None
    auth_header: Optional[str] = None


class RemotePersonaInstallResult(BaseModel):
    profile: profiles.VoiceProfile
    persona_id: str
    sha256: str
    size_bytes: int
    audio_format: str
    name_disambiguated: bool
    original_name: str


_install_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress: dict[str, Any] = {
    "phase": "idle",
    "persona_id": "",
    "downloaded": 0,
    "total": 0,
    "error_code": None,
}


def get_install_progress() -> dict[str, Any]:
    with _progress_lock:
        return dict(_progress)


def _set_progress(
    phase: str,
    *,
    persona_id: str = "",
    downloaded: int = 0,
    total: int = 0,
    error_code: Optional[str] = None,
) -> dict[str, Any]:
    snapshot = {
        "phase": phase,
        "persona_id": persona_id,
        "downloaded": downloaded,
        "total": total,
        "error_code": error_code,
    }
    with _progress_lock:
        _progress.update(snapshot)
    return snapshot


def validate_persona_id(persona_id: str) -> str:
    pid = (persona_id or "").strip()
    if not pid or ".." in pid or not _PERSONA_ID_RE.match(pid):
        raise PersonaInstallError(
            "invalid_id",
            f"Invalid persona_id '{persona_id}'. Expected 1..128 characters [A-Za-z0-9._-] without '..'.",
            status_code=400,
        )
    return pid


def _origin_key(parsed) -> tuple[str, str, int]:
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise PersonaInstallError("disallowed_url", f"Malformed port in URL: {exc}", status_code=400) from exc
    if port is None:
        port = 443 if scheme == "https" else 80
    return (scheme, host, port)


def validate_library_url(library_url: str) -> str:
    raw = (library_url or "").strip()
    if not raw:
        raise PersonaInstallError(
            "invalid_library_url",
            "Configured Persona library URL is empty.",
            status_code=400,
        )
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise PersonaInstallError(
            "invalid_library_url",
            f"Persona library URL must use http:// or https:// with a valid host: '{raw}'.",
            status_code=400,
        )
    if parsed.username or parsed.password:
        raise PersonaInstallError(
            "invalid_library_url",
            "Embedded credentials in Persona library URL are not allowed.",
            status_code=400,
        )
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc}{path}"


def validate_download_url(download_url: str, library_url: str) -> str:
    base_url = validate_library_url(library_url)
    base_parsed = urlparse(base_url)

    raw = (download_url or "").strip()
    if not raw:
        raise PersonaInstallError("disallowed_url", "Download URL is empty.", status_code=400)
    if raw.startswith("//"):
        raise PersonaInstallError(
            "disallowed_url",
            "Protocol-relative download URLs are not allowed.",
            status_code=400,
        )

    candidate = f"{base_url}{raw}" if raw.startswith("/") else raw
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise PersonaInstallError(
            "disallowed_url",
            f"Download URL scheme or host is not allowed: '{raw}'.",
            status_code=400,
        )
    if parsed.username or parsed.password:
        raise PersonaInstallError(
            "disallowed_url",
            "Embedded credentials in download URL are not allowed.",
            status_code=400,
        )
    if _origin_key(parsed) != _origin_key(base_parsed):
        raise PersonaInstallError(
            "disallowed_url",
            f"Download URL origin '{parsed.scheme}://{parsed.netloc}' does not match configured library '{base_parsed.scheme}://{base_parsed.netloc}'.",
            status_code=400,
        )
    return candidate


def validate_audio_format(audio_format: str) -> str:
    fmt = (audio_format or "").strip().lower().lstrip(".")
    if fmt not in ALLOWED_AUDIO_FORMATS:
        raise PersonaInstallError(
            "unsupported_audio_format",
            f"Unsupported audio format '{audio_format}'. Allowed: {', '.join(sorted(ALLOWED_AUDIO_FORMATS))}.",
            status_code=400,
        )
    return fmt


def validate_sha256(expected_sha256: str) -> str:
    raw = (expected_sha256 or "").strip()
    if raw.lower().startswith("sha256:"):
        raw = raw[7:].strip()
    if not _SHA256_RE.match(raw):
        raise PersonaInstallError(
            "invalid_sha256",
            "A valid 64-character hexadecimal SHA-256 digest is required before downloading.",
            status_code=400,
        )
    return raw.lower()


def detect_audio_magic(header: bytes) -> Optional[str]:
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


def resolve_non_colliding_name(
    requested_name: str,
    existing_profiles: list[profiles.VoiceProfile],
) -> tuple[str, bool]:
    clean = (requested_name or "").strip()
    if not clean:
        raise PersonaInstallError("invalid_name", "Persona name is required.", status_code=400)
    existing_lower = {p.name.strip().lower() for p in existing_profiles if p.name.strip()}
    if clean.lower() not in existing_lower:
        return clean, False
    candidate = f"{clean} (Persona)"
    idx = 2
    while candidate.lower() in existing_lower:
        candidate = f"{clean} (Persona {idx})"
        idx += 1
    return candidate, True


def _emit(
    progress_cb: Optional[Callable[[dict[str, Any]], None]],
    phase: str,
    *,
    persona_id: str = "",
    downloaded: int = 0,
    total: int = 0,
    error_code: Optional[str] = None,
) -> None:
    snap = _set_progress(
        phase,
        persona_id=persona_id,
        downloaded=downloaded,
        total=total,
        error_code=error_code,
    )
    if progress_cb is not None:
        progress_cb(snap)


def install_remote_persona(
    req: RemotePersonaInstallRequest,
    *,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    timeout_s: float = 60.0,
    staging_root: Optional[Path] = None,
    transport: Optional[httpx.BaseTransport] = None,
    progress_cb: Optional[Callable[[dict[str, Any]], None]] = None,
) -> RemotePersonaInstallResult:
    """
    Download and verify a remote Persona audio reference, store it atomically, and create
    a local VoiceProfile without overwriting any existing personal profile.
    """
    if not _install_lock.acquire(blocking=False):
        raise PersonaInstallError(
            "busy",
            "Another Persona installation is already in progress.",
            status_code=409,
        )

    stage_dir: Optional[Path] = None
    pid = (req.persona_id or "").strip()
    downloaded = 0
    expected_total = int(req.expected_size_bytes or 0)

    try:
        _emit(progress_cb, "validating", persona_id=pid, downloaded=0, total=expected_total)

        pid = validate_persona_id(req.persona_id)
        requested_name = (req.name or "").strip()
        if not requested_name:
            raise PersonaInstallError("invalid_name", "Persona name is required.", status_code=400)

        canonical_engine = audio_adaptation.canonical_engine_name(req.engine)
        if not audio_adaptation.engine_supports_cloning(canonical_engine):
            raise PersonaInstallError(
                "invalid_engine",
                f"Engine '{req.engine}' does not support cloned voice profiles.",
                status_code=400,
            )

        base_url = validate_library_url(req.library_url)
        target_url = validate_download_url(req.download_url, base_url)
        fmt = validate_audio_format(req.audio_format)
        expected_hash = validate_sha256(req.sha256)

        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if req.expected_size_bytes is not None and req.expected_size_bytes > max_bytes:
            raise PersonaInstallError(
                "file_too_large",
                f"Declared Persona audio size ({req.expected_size_bytes} bytes) exceeds limit ({max_bytes} bytes).",
                status_code=413,
            )

        stage_base = staging_root or (DEFAULT_TMP_DIR / "persona_install")
        stage_base.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix=f"persona-{pid}-", dir=stage_base))
        part_path = stage_dir / f"{pid}.{fmt}.part"
        staged_audio = stage_dir / f"{pid}.{fmt}"

        headers: dict[str, str] = {"Accept": "*/*"}
        if req.auth_header and req.auth_header.strip():
            headers["Authorization"] = req.auth_header.strip()

        hasher = hashlib.sha256()
        header_bytes = bytearray()

        with httpx.Client(follow_redirects=False, timeout=timeout_s, transport=transport) as client:
            current_url = target_url
            redirects = 0
            while True:
                try:
                    stream_ctx = client.stream("GET", current_url, headers=headers)
                    resp = stream_ctx.__enter__()
                except PersonaInstallError:
                    raise
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    raise PersonaInstallError(
                        "network_error",
                        f"Failed to connect to Persona server: {exc}",
                        status_code=502,
                    ) from exc
                except httpx.TransportError as exc:
                    raise PersonaInstallError(
                        "network_error",
                        f"Network error downloading Persona audio: {exc}",
                        status_code=502,
                    ) from exc

                try:
                    if resp.status_code in _REDIRECT_STATUSES:
                        location = resp.headers.get("location", "").strip()
                        if not location:
                            raise PersonaInstallError(
                                "http_error",
                                f"Redirect HTTP {resp.status_code} missing Location header.",
                                status_code=502,
                            )
                        redirects += 1
                        if redirects > 3:
                            raise PersonaInstallError(
                                "http_error",
                                "Too many redirects while downloading Persona audio.",
                                status_code=502,
                            )
                        next_url = urljoin(current_url, location)
                        current_url = validate_download_url(next_url, base_url)
                        continue

                    if resp.status_code in (401, 403):
                        raise PersonaInstallError(
                            "auth_required",
                            f"Authentication required by Persona server (HTTP {resp.status_code}).",
                            status_code=resp.status_code,
                        )
                    if resp.status_code != 200:
                        raise PersonaInstallError(
                            "http_error",
                            f"Persona server returned HTTP {resp.status_code}.",
                            status_code=502 if resp.status_code >= 500 else resp.status_code,
                        )

                    raw_cl = resp.headers.get("content-length")
                    content_length: Optional[int] = None
                    if raw_cl is not None:
                        try:
                            content_length = int(raw_cl)
                        except ValueError:
                            content_length = None
                    if content_length is not None and content_length > max_bytes:
                        raise PersonaInstallError(
                            "file_too_large",
                            f"Remote audio Content-Length ({content_length} bytes) exceeds limit ({max_bytes} bytes).",
                            status_code=413,
                        )

                    expected_total = content_length if content_length is not None else expected_total
                    _emit(
                        progress_cb,
                        "downloading",
                        persona_id=pid,
                        downloaded=0,
                        total=expected_total,
                    )

                    with part_path.open("wb") as stream_file:
                        try:
                            for chunk in resp.iter_bytes(chunk_size=65536):
                                if not chunk:
                                    continue
                                downloaded += len(chunk)
                                if downloaded > max_bytes:
                                    raise PersonaInstallError(
                                        "file_too_large",
                                        f"Downloaded audio exceeds maximum allowed size ({max_bytes} bytes).",
                                        status_code=413,
                                    )
                                if len(header_bytes) < 32:
                                    need = 32 - len(header_bytes)
                                    header_bytes.extend(chunk[:need])
                                hasher.update(chunk)
                                stream_file.write(chunk)
                                _emit(
                                    progress_cb,
                                    "downloading",
                                    persona_id=pid,
                                    downloaded=downloaded,
                                    total=expected_total,
                                )
                        except PersonaInstallError:
                            raise
                        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.StreamError) as exc:
                            raise PersonaInstallError(
                                "truncated_response",
                                f"Download interrupted before completion: {exc}",
                                status_code=502,
                            ) from exc
                        except httpx.TransportError as exc:
                            raise PersonaInstallError(
                                "network_error",
                                f"Transport error during Persona download: {exc}",
                                status_code=502,
                            ) from exc

                        stream_file.flush()
                        os.fsync(stream_file.fileno())
                    break
                finally:
                    stream_ctx.__exit__(None, None, None)

        if downloaded == 0:
            raise PersonaInstallError(
                "truncated_response",
                "Remote Persona audio response body was empty.",
                status_code=502,
            )
        if content_length is not None and downloaded != content_length:
            raise PersonaInstallError(
                "truncated_response",
                f"Downloaded {downloaded} bytes, expected Content-Length {content_length} bytes.",
                status_code=502,
            )
        if req.expected_size_bytes is not None and downloaded != req.expected_size_bytes:
            raise PersonaInstallError(
                "truncated_response",
                f"Downloaded {downloaded} bytes, expected {req.expected_size_bytes} bytes.",
                status_code=502,
            )

        _emit(
            progress_cb,
            "verifying",
            persona_id=pid,
            downloaded=downloaded,
            total=downloaded,
        )

        detected_fmt = detect_audio_magic(bytes(header_bytes))
        if detected_fmt != fmt:
            raise PersonaInstallError(
                "unsupported_audio_format",
                f"Downloaded payload signature ({detected_fmt or 'unknown'}) does not match declared audio format '{fmt}'.",
                status_code=422,
            )

        actual_hash = hasher.hexdigest().lower()
        if actual_hash != expected_hash:
            raise PersonaInstallError(
                "sha256_mismatch",
                f"SHA-256 mismatch: expected {expected_hash}, got {actual_hash}.",
                status_code=422,
            )

        os.replace(part_path, staged_audio)

        _emit(
            progress_cb,
            "creating_profile",
            persona_id=pid,
            downloaded=downloaded,
            total=downloaded,
        )

        safe_name, disambiguated = resolve_non_colliding_name(
            requested_name,
            profiles.list_profiles(),
        )
        created_profile = profiles.create_profile(
            name=safe_name,
            language=(req.language or "").strip() or "Spanish",
            engine=canonical_engine,
            ref_audio_path=str(staged_audio),
            ref_text=req.ref_text,
        )

        _emit(
            progress_cb,
            "done",
            persona_id=pid,
            downloaded=downloaded,
            total=downloaded,
        )
        return RemotePersonaInstallResult(
            profile=created_profile,
            persona_id=pid,
            sha256=actual_hash,
            size_bytes=downloaded,
            audio_format=fmt,
            name_disambiguated=disambiguated,
            original_name=requested_name,
        )
    except PersonaInstallError as exc:
        _emit(
            progress_cb,
            "failed",
            persona_id=pid,
            downloaded=downloaded,
            total=expected_total,
            error_code=exc.code,
        )
        raise
    finally:
        if stage_dir is not None:
            shutil.rmtree(stage_dir, ignore_errors=True)
        _install_lock.release()
