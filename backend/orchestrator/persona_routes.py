"""FastAPI routes for Persona remote install and non-destructive profile switching."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import audio_adaptation, persona_install, profiles, voice_packs
from .config import load_settings, resolved_models_dir

router = APIRouter(tags=["persona"])


def _local_persona_entries() -> list[tuple[dict, Path]]:
    models_dir = Path(resolved_models_dir(load_settings()))
    installed = voice_packs.load_installed(models_dir)
    entries: list[tuple[dict, Path]] = []
    if installed:
        version = str(installed.get("version") or voice_packs.PACK_VERSION)
        for voice in installed.get("voices") or []:
            audio_p = Path(str(voice.get("audio_path") or ""))
            text_p = Path(str(voice.get("text_path") or ""))
            if not audio_p.is_file():
                continue
            ref_text = text_p.read_text(encoding="utf-8", errors="replace").strip() if text_p.is_file() else ""
            slug = str(voice.get("slug") or "")
            loc = str(voice.get("locale") or "")
            audio_key = f"{loc}--{slug}" if loc else slug
            entries.append((
                {
                    "id": f"local:{voice['id']}",
                    "slug": slug,
                    "version": version,
                    "name": str(voice["name"]),
                    "language": str(voice.get("language") or voice_packs._language_label(loc)),
                    "locale": loc,
                    "origin": "prebuilt",
                    "description": f"Voz lista para clonar con Qwen3-TTS, F5, Chatterbox y XTTS ({loc}).",
                    "author": "Speech Studio · xyz-Ioquendo",
                    "tags": [voice_packs.PACK_ID_XYZ_IOQUENDO, loc, "local"],
                    "ref_text": ref_text,
                    "audio": {
                        "format": str(voice.get("format") or audio_p.suffix.lstrip(".") or "mp3"),
                        "sample_rate_hz": 24000,
                        "channels": 1,
                        "duration_s": float(voice.get("duration_s") or 6.0),
                        "sha256": str(voice.get("audio_sha256") or ""),
                        "size_bytes": audio_p.stat().st_size,
                        "preview_url": f"/api/persona/local-audio/{audio_key}",
                        "local_path": str(audio_p),
                    },
                    "consent": {
                        "speaker_consent_confirmed": True,
                        "provenance_type": "pack_reference",
                        "provenance_note": str((voice.get("provenance") or {}).get("note") or "Included local voice reference."),
                        "license": "proprietary-pack",
                        "attribution": "Speech Studio",
                    },
                    "recommended_engines": ["qwen", "f5", "chatterbox", "xtts"],
                    "created_at": "2026-11-28T00:00:00Z",
                    "updated_at": "2026-11-28T00:00:00Z",
                },
                audio_p.resolve(),
            ))
    if entries:
        return entries

    bundle_dir = voice_packs.DEFAULT_BUNDLE_DIR
    try:
        manifest_path = voice_packs.default_bundle_manifest_path(bundle_dir)
        manifest = voice_packs.load_manifest(manifest_path)
    except FileNotFoundError:
        return []
    for v in manifest.voices:
        audio_p = (bundle_dir / v.audio_relpath).resolve()
        text_p = (bundle_dir / v.text_relpath).resolve()
        if not audio_p.is_file():
            audio_p = (bundle_dir / "voices" / v.audio_relpath).resolve()
            text_p = (bundle_dir / "voices" / v.text_relpath).resolve()
        if not audio_p.is_file():
            continue
        ref_text = text_p.read_text(encoding="utf-8", errors="replace").strip() if text_p.is_file() else ""
        entries.append((
            {
                "id": f"local:{v.id}",
                "slug": v.slug,
                "version": manifest.version,
                "name": v.name,
                "language": v.language,
                "locale": v.locale,
                "origin": "prebuilt",
                "description": f"Voz lista para clonar con Qwen3-TTS, F5, Chatterbox y XTTS ({v.locale}).",
                "author": "Speech Studio · xyz-Ioquendo",
                "tags": [manifest.pack_id, v.locale, "local"],
                "ref_text": ref_text,
                "audio": {
                    "format": v.format,
                    "sample_rate_hz": 24000,
                    "channels": 1,
                    "duration_s": float(v.duration_s or 6.0),
                    "sha256": v.audio_sha256,
                    "size_bytes": audio_p.stat().st_size,
                    "preview_url": f"/api/persona/local-audio/{v.slug}",
                    "local_path": str(audio_p),
                },
                "consent": {
                    "speaker_consent_confirmed": True,
                    "provenance_type": "pack_reference",
                    "provenance_note": str(v.provenance.get("note") or "Included local voice reference."),
                    "license": "proprietary-pack",
                    "attribution": "Speech Studio",
                },
                "recommended_engines": ["qwen", "f5", "chatterbox", "xtts"],
                "created_at": "2026-11-28T00:00:00Z",
                "updated_at": "2026-11-28T00:00:00Z",
            },
            audio_p,
        ))
    return entries


@router.get("/api/persona/local-catalog")
def get_local_persona_catalog():
    items = [rec for rec, _path in _local_persona_entries()]
    return {"items": items, "total": len(items)}


@router.get("/api/persona/local-audio/{voice_slug}")
def get_local_persona_audio(voice_slug: str):
    if "/" in voice_slug or "\\" in voice_slug or ".." in voice_slug:
        raise HTTPException(status_code=404, detail="Audio not found.")
    for rec, audio_p in _local_persona_entries():
        loc = str(rec.get("locale") or "")
        audio_key = f"{loc}--{rec['slug']}" if loc else str(rec["slug"])
        if (voice_slug == audio_key or voice_slug == rec["slug"]) and audio_p.is_file():
            return FileResponse(audio_p)
    raise HTTPException(status_code=404, detail="Audio not found.")


class SwitchProfileEngineRequest(BaseModel):
    engine: str
    preserve_original: bool = True


@router.post("/api/persona/install-remote")
def install_remote_persona_route(req: persona_install.RemotePersonaInstallRequest):
    try:
        res = persona_install.install_remote_persona(req)
    except persona_install.PersonaInstallError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
        )
    return res.model_dump()


@router.get("/api/persona/install-progress")
def get_remote_persona_progress_route():
    return persona_install.get_install_progress()


@router.post("/api/profiles/{profile_id}/switch-engine")
def switch_profile_engine_route(profile_id: str, req: SwitchProfileEngineRequest):
    if not audio_adaptation.engine_supports_cloning(req.engine):
        raise HTTPException(
            status_code=400,
            detail=f"Engine '{req.engine}' does not support cloned voice profiles.",
        )
    canonical = audio_adaptation.canonical_engine_name(req.engine)
    updated = profiles.switch_profile_engine(
        profile_id,
        canonical,
        preserve_original=req.preserve_original,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"profile": updated.model_dump()}


@router.post("/api/profiles/{profile_id}/restore-original")
def restore_profile_original_route(profile_id: str):
    updated = profiles.restore_original_audio(profile_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Profile or original audio not found.")
    return {"profile": updated.model_dump()}
