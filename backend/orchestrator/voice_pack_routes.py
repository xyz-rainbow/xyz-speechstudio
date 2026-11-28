"""FastAPI routes for reference voice packs. Wire from main.py when unlocked:

    from .voice_pack_routes import router as voice_pack_router
    app.include_router(voice_pack_router)
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from .config import load_settings, resolved_models_dir
from . import voice_packs

router = APIRouter(tags=["voice-packs"])


class VoicePackInstallRequest(BaseModel):
    source_dir: Optional[str] = None


def _models_dir() -> Path:
    return Path(resolved_models_dir(load_settings()))


@router.get("/api/voice-packs/{pack_id}")
def voice_pack_status(pack_id: str):
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    from .downloader import build_catalog

    settings = load_settings()
    installed = voice_packs.load_installed(_models_dir(), pack_id)
    dependency = voice_packs.dependency_status(build_catalog(settings))
    return {
        "pack_id": pack_id,
        "name": voice_packs.PACK_DISPLAY_NAME,
        "installed": bool(installed),
        "version": (installed or {}).get("version"),
        "voice_count": len((installed or {}).get("voices") or []),
        "dependency": dependency,
        "disclaimer": (
            "xyz-Ioquendo is not an official Loquendo product; "
            "redistribution is blocked until license review."
        ),
    }


@router.get("/api/voice-packs/{pack_id}/voices")
def voice_pack_voices(pack_id: str, locale: Optional[str] = None):
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    return {
        "voices": voice_packs.list_installed_voices(_models_dir(), locale=locale, pack_id=pack_id)
    }


@router.post("/api/voice-packs/{pack_id}/install")
def voice_pack_install(
    pack_id: str,
    payload: Annotated[Optional[VoicePackInstallRequest], Body()] = None,
):
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    try:
        if payload and payload.source_dir and payload.source_dir.strip():
            return voice_packs.install_from_source(
                _models_dir(),
                Path(payload.source_dir.strip()),
                pack_id=pack_id,
            )
        return voice_packs.install_from_bundle(_models_dir())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/voice-packs/{pack_id}/repair")
def voice_pack_repair(pack_id: str):
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    try:
        return voice_packs.repair_pack(_models_dir())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/voice-packs/{pack_id}")
def voice_pack_uninstall(pack_id: str):
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    return voice_packs.uninstall_pack(_models_dir(), pack_id)


@router.get("/api/voice-packs/{pack_id}/persona-preview")
def voice_pack_persona_preview(pack_id: str):
    """Stable Persona-shaped records for future individual download cards."""
    if pack_id != voice_packs.PACK_ID_XYZ_IOQUENDO:
        raise HTTPException(status_code=404, detail="Unknown voice pack")
    installed = voice_packs.load_installed(_models_dir(), pack_id)
    if not installed:
        return {"items": [], "total": 0}
    items = voice_packs.to_persona_records(installed)
    return {"items": items, "total": len(items)}
