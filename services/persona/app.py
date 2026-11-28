"""Self-contained Persona Library API service for k3s / Rancher deployment."""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

try:
    from .storage import (
        DEFAULT_MAX_UPLOAD_BYTES,
        PersonaMetadataIn,
        PersonaServiceError,
        PersonaStore,
    )
except ImportError:
    from storage import (  # type: ignore[no-redef]
        DEFAULT_MAX_UPLOAD_BYTES,
        PersonaMetadataIn,
        PersonaServiceError,
        PersonaStore,
    )


_MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
}


def _require_write_auth(authorization: Optional[str], expected_token: str) -> None:
    token = expected_token.strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="Write operations disabled: PERSONA_WRITE_TOKEN is not configured.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=403, detail="Invalid Bearer token.")


def create_app(
    *,
    data_dir: Optional[Path] = None,
    write_token: Optional[str] = None,
    max_upload_bytes: Optional[int] = None,
    cors_origins: Optional[list[str]] = None,
) -> FastAPI:
    resolved_dir = Path(data_dir or os.environ.get("PERSONA_DATA_DIR", "/data"))
    resolved_token = write_token if write_token is not None else os.environ.get("PERSONA_WRITE_TOKEN", "")
    resolved_max_bytes = (
        max_upload_bytes
        if max_upload_bytes is not None
        else int(os.environ.get("PERSONA_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)))
    )
    if cors_origins is None:
        raw_cors = os.environ.get(
            "PERSONA_CORS_ORIGINS",
            "tauri://localhost,http://tauri.localhost,https://tauri.localhost,http://localhost:1420,http://127.0.0.1:1420",
        )
        cors_origins = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]

    store = PersonaStore(resolved_dir, max_upload_bytes=resolved_max_bytes)

    service = FastAPI(title="Speech Studio Persona Library API", version="v1")
    service.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @service.exception_handler(PersonaServiceError)
    def handle_service_error(_request, exc: PersonaServiceError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @service.get("/v1/health")
    def health():
        return {
            "status": "ok",
            "api_version": "v1",
            "personas_count": store.count_personas(),
        }

    @service.get("/v1/personas")
    def list_personas(
        q: str = "",
        language: Optional[str] = None,
        origin: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ):
        return store.list_personas(
            q=q,
            language=language,
            origin=origin,
            page=page,
            page_size=page_size,
        )

    @service.get("/v1/personas/{persona_id}")
    def get_persona(persona_id: str):
        rec = store.get_persona(persona_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="Persona not found.")
        return rec

    @service.get("/v1/personas/{persona_id}/audio")
    def get_persona_audio(persona_id: str):
        info = store.get_audio_info(persona_id)
        if info is None:
            raise HTTPException(status_code=404, detail="Persona audio not found.")
        fp, digest, filename = info
        ext = fp.suffix.lower().lstrip(".")
        return FileResponse(
            fp,
            media_type=_MEDIA_TYPES.get(ext, "application/octet-stream"),
            filename=filename,
            headers={"X-Persona-SHA256": digest},
        )

    @service.post("/v1/personas", status_code=201)
    async def create_persona(
        metadata: str = Form(...),
        audio: UploadFile = File(...),
        authorization: Optional[str] = Header(default=None),
    ):
        _require_write_auth(authorization, resolved_token)
        try:
            meta_obj = PersonaMetadataIn.model_validate(json.loads(metadata))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {exc}") from exc

        chunks: list[bytes] = []
        total = 0
        while True:
            block = await audio.read(65536)
            if not block:
                break
            total += len(block)
            if total > store.max_upload_bytes:
                raise PersonaServiceError(
                    "file_too_large",
                    f"Uploaded audio exceeds limit ({store.max_upload_bytes} bytes).",
                    413,
                )
            chunks.append(block)
        return store.create_persona(
            meta_obj,
            b"".join(chunks),
            original_filename=audio.filename or "reference.wav",
        )

    @service.delete("/v1/personas/{persona_id}")
    def delete_persona(
        persona_id: str,
        authorization: Optional[str] = Header(default=None),
    ):
        _require_write_auth(authorization, resolved_token)
        deleted = store.delete_persona(persona_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Persona not found.")
        return {"deleted": True, "id": persona_id}

    return service


app = create_app() if os.environ.get("PERSONA_AUTOSTART_APP", "") == "1" else None
