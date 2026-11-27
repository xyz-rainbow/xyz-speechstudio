from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from . import chunking, downloader, external_providers, history, profiles, updates
from .config import (
    APP_ROOT,
    DEFAULT_PROFILES_DIR,
    DEFAULT_TMP_DIR,
    RUNTIME_JSON_PATH,
    AppSettings,
    load_settings,
    reject_public_bind_without_token,
    resolved_models_dir,
    resolved_outputs_dir,
    save_settings,
)
from .supervisor import (
    InsufficientVramError,
    LiveCaptionsProtectedError,
    WorkerHandle,
    WorkerSupervisor,
    query_nvidia_vram,
)

supervisor = WorkerSupervisor()
runtime_info = {"port": 0, "pid": os.getpid(), "host": "127.0.0.1"}


class CaptionsLockRequest(BaseModel):
    active: bool


class LoadQwenRequest(BaseModel):
    model_id: Optional[str] = None
    device: Optional[Literal["gpu", "cpu"]] = None
    force_stop_captions: bool = False


class DownloadModelRequest(BaseModel):
    model_id: str
    quant_id: Optional[str] = None


class HfInspectRequest(BaseModel):
    url: str


class HfInstallRequest(BaseModel):
    repo_id: str
    name: str
    kind: Literal["tts", "stt"] = "stt"
    files: list[str]


class UrlInstallRequest(BaseModel):
    source: Literal["huggingface", "modelscope", "direct"] = "huggingface"
    repo_id: str
    name: str
    kind: Literal["tts", "stt"] = "stt"
    files: list[str]
    direct_urls: dict[str, str] = {}
    crispasr_ready: bool = False
    crispasr_backend: Optional[str] = None
    convert_to_gguf: bool = False
    convert_script: Optional[str] = None


class LocalImportRequest(BaseModel):
    source_path: str
    name: str
    kind: Literal["tts", "stt"] = "stt"


class LoadSttRequest(BaseModel):
    model_id: Optional[str] = None
    device: Optional[Literal["gpu", "cpu"]] = None
    force_stop_captions: bool = False


class CreateProfileRequest(BaseModel):
    name: str
    language: str = "Spanish"
    engine: Literal[
        "qwen",
        "xtts",
        "f5",
        "fish",
        "chatterbox",
        "chatterbox-turbo",
        "cosyvoice3-tts",
        "orpheus",
        "indextts",
    ] = "qwen"
    ref_audio_path: str = ""
    ref_text: str = ""
    build_voice: bool = True
    force_stop_captions: bool = False


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    engine: Optional[
        Literal[
            "qwen",
            "xtts",
            "f5",
            "fish",
            "chatterbox",
            "chatterbox-turbo",
            "cosyvoice3-tts",
            "orpheus",
            "indextts",
        ]
    ] = None
    ref_audio_path: Optional[str] = None
    ref_text: Optional[str] = None
    rebuild_voice: bool = False
    force_stop_captions: bool = False


class TrimProfileRequest(BaseModel):
    max_seconds: float = 12.0


class ModelRuntimeRequest(BaseModel):
    runtime: Literal["crispasr", "python"]


class SynthesizeRequest(BaseModel):
    profile_id: str
    text: str
    language: Optional[str] = None
    voice: Optional[str] = None
    mode: Literal["play", "wav"] = "play"
    seed: int = -1
    force_stop_captions: bool = False


class TranscribeFileRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
    model_id: Optional[str] = None


class SaveAsRequest(BaseModel):
    dest_path: str


class UpdateCurrentRequest(BaseModel):
    current: str = ""


class SpeechRequest(BaseModel):
    model: str = "qwen3-1.7b"
    input: str
    voice: str = "mario"
    response_format: str = "wav"
    language: Optional[str] = None
    seed: int = -1


def fire_toast(title: str, message: str, progress: Optional[int] = None) -> None:
    from .toasts import deliver

    deliver(title, message, progress)


download_manager = downloader.DownloadManager(notify_cb=fire_toast)


def _verify_local_api_access(request: Request, settings: AppSettings) -> None:
    if not settings.api_endpoint_enabled:
        raise HTTPException(status_code=403, detail="Local API endpoint is turned OFF in Settings.")
    token = settings.api_bearer_token.strip()
    if token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="Invalid or missing Bearer token.")


def _require_bearer_for_non_loopback(request: Request, settings: AppSettings) -> None:
    """When bound on 0.0.0.0, LAN clients must present the configured Bearer token.

    Loopback UI (Tauri → 127.0.0.1) stays unauthenticated so the tray/badge keep working.
    """
    client = (request.client.host if request.client else "") or ""
    if client in {"127.0.0.1", "::1", "localhost"}:
        return
    token = settings.api_bearer_token.strip()
    auth = request.headers.get("authorization", "")
    if not token or auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token.")


def _find_endpoint(settings: AppSettings, ep_id: str) -> external_providers.ExternalEndpointConfig:
    for ep in settings.external_endpoints:
        if ep.id == ep_id:
            return ep
    raise HTTPException(status_code=404, detail=f"External endpoint not found: {ep_id}")


def resolve_qwen_gguf(settings: AppSettings, model_id: Optional[str] = None) -> tuple[Path, Path, str]:
    try:
        return downloader.resolve_qwen_paths(settings, model_id=model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def ensure_qwen_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.tts_device
    target_req = model_id or settings.active_tts_model
    talker, codec, resolved_id = resolve_qwen_gguf(settings, model_id=target_req)

    existing = supervisor.active_workers.get("qwen")
    if existing and existing.process.poll() is None and existing.device == dev and existing.model_id == resolved_id:
        return existing

    if existing and existing.process.poll() is None:
        supervisor.eject("qwen")

    total_mib, free_mib = query_nvidia_vram()
    vram_est = 1600 if "0.6b" in resolved_id else 3300
    supervisor.ensure_vram_or_evict(
        target_family="qwen",
        device=dev,
        vram_est_mib=vram_est,
        free_vram_mib=free_mib,
        total_vram_mib=total_mib,
        force_stop_captions=force_stop_captions,
    )

    handle = supervisor.spawn_worker(
        family="qwen",
        model_id=resolved_id,
        device=dev,
        vram_est_mib=vram_est,
    )
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/load",
            json={"talker_path": str(talker), "codec_path": str(codec)},
        )
        if resp.status_code >= 400:
            supervisor.eject("qwen")
            raise HTTPException(status_code=500, detail=f"Qwen worker load failed: {resp.text}")
    return handle


def ensure_xtts_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.tts_device
    requested = model_id or settings.active_tts_model
    if not requested or not str(requested).startswith("xtts"):
        requested = "xtts-v2"
    try:
        model_dir, resolved_id = downloader.resolve_xtts_dir(settings, model_id=requested)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    existing = supervisor.active_workers.get("xtts")
    if (
        existing
        and existing.process.poll() is None
        and existing.device == dev
        and existing.model_id == resolved_id
    ):
        return existing

    if existing and existing.process.poll() is None:
        supervisor.eject("xtts")

    total_mib, free_mib = query_nvidia_vram()
    vram_est = 2300
    supervisor.ensure_vram_or_evict(
        target_family="xtts",
        device=dev,
        vram_est_mib=vram_est,
        free_vram_mib=free_mib,
        total_vram_mib=total_mib,
        force_stop_captions=force_stop_captions,
    )

    handle = supervisor.spawn_worker(
        family="xtts",
        model_id=resolved_id,
        device=dev,
        vram_est_mib=vram_est,
    )
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/load",
            json={"model_dir": str(model_dir)},
        )
        if resp.status_code >= 400:
            supervisor.eject("xtts")
            raise HTTPException(status_code=500, detail=f"XTTS worker load failed: {resp.text}")
    return handle


def ensure_f5_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.tts_device
    entry = _active_tts_catalog_entry(
        settings.model_copy(update={"active_tts_model": model_id or settings.active_tts_model})
    )
    if entry is None or not entry.install_dir:
        raise FileNotFoundError("F5-TTS model is not installed. Download it from Models.")
    resolved_id = entry.id
    model_dir = Path(entry.install_dir)

    existing = supervisor.active_workers.get("f5")
    if existing and existing.process.poll() is None and existing.device == dev and existing.model_id == resolved_id:
        return existing
    if existing and existing.process.poll() is None:
        supervisor.eject("f5")

    total_mib, free_mib = query_nvidia_vram()
    supervisor.ensure_vram_or_evict(
        target_family="f5",
        device=dev,
        vram_est_mib=2400,
        free_vram_mib=free_mib,
        total_vram_mib=total_mib,
        force_stop_captions=force_stop_captions,
    )
    handle = supervisor.spawn_worker(
        family="f5",
        model_id=resolved_id,
        device=dev,
        vram_est_mib=2400,
    )
    with httpx.Client(timeout=240.0) as client:
        resp = client.post(f"http://127.0.0.1:{handle.port}/load", json={"model_dir": str(model_dir)})
        if resp.status_code >= 400:
            supervisor.eject("f5")
            raise HTTPException(status_code=500, detail=f"F5-TTS worker load failed: {resp.text}")
    return handle


def ensure_fish_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.tts_device
    entry = _active_tts_catalog_entry(
        settings.model_copy(update={"active_tts_model": model_id or "fish-speech-1.5"})
    )
    if entry is None or not entry.install_dir:
        raise FileNotFoundError("Fish Speech 1.5 is not installed. Download it from Models.")
    resolved_id = entry.id
    model_dir = Path(entry.install_dir)

    existing = supervisor.active_workers.get("fish")
    if existing and existing.process.poll() is None and existing.device == dev and existing.model_id == resolved_id:
        return existing
    if existing and existing.process.poll() is None:
        supervisor.eject("fish")

    total_mib, free_mib = query_nvidia_vram()
    supervisor.ensure_vram_or_evict(
        target_family="fish",
        device=dev,
        vram_est_mib=2200,
        free_vram_mib=free_mib,
        total_vram_mib=total_mib,
        force_stop_captions=force_stop_captions,
    )
    handle = supervisor.spawn_worker(
        family="fish",
        model_id=resolved_id,
        device=dev,
        vram_est_mib=2200,
    )
    with httpx.Client(timeout=240.0) as client:
        resp = client.post(f"http://127.0.0.1:{handle.port}/load", json={"model_dir": str(model_dir)})
        if resp.status_code >= 400:
            supervisor.eject("fish")
            raise HTTPException(status_code=500, detail=f"Fish worker load failed: {resp.text}")
    return handle


def ensure_kitten_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.tts_device
    entry = _active_tts_catalog_entry(
        settings.model_copy(update={"active_tts_model": model_id or "kitten-tts-2-mini"})
    )
    if entry is None or not entry.install_dir:
        raise FileNotFoundError("KittenTTS 2 Mini is not installed. Download it from Models.")
    resolved_id = entry.id
    model_dir = Path(entry.install_dir)

    existing = supervisor.active_workers.get("kitten")
    if existing and existing.process.poll() is None and existing.device == dev and existing.model_id == resolved_id:
        return existing
    if existing and existing.process.poll() is None:
        supervisor.eject("kitten")

    handle = supervisor.spawn_worker(
        family="kitten",
        model_id=resolved_id,
        device=dev,
        vram_est_mib=250,
    )
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(f"http://127.0.0.1:{handle.port}/load", json={"model_dir": str(model_dir)})
        if resp.status_code >= 400:
            supervisor.eject("kitten")
            raise HTTPException(status_code=500, detail=f"KittenTTS worker load failed: {resp.text}")
    return handle


def ensure_stt_loaded(
    *,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    force_stop_captions: bool = False,
) -> WorkerHandle:
    settings = load_settings()
    dev = device or settings.stt_device
    target_id = model_id or settings.active_stt_model
    model_arg, compute_type, vram_est = downloader.resolve_stt_load_target(settings, target_id)

    existing = supervisor.active_workers.get("stt")
    if existing and existing.process.poll() is None and existing.device == dev:
        if existing.model_id != target_id:
            dl_root = resolved_models_dir(settings) / "stt"
            with httpx.Client(timeout=300.0) as client:
                resp = client.post(
                    f"http://127.0.0.1:{existing.port}/load",
                    json={
                        "model_size": model_arg,
                        "compute_type": compute_type,
                        "download_root": str(dl_root),
                    },
                )
                if resp.status_code >= 400:
                    raise HTTPException(status_code=500, detail=f"STT reload failed: {resp.text}")
            existing.model_id = target_id
            existing.vram_est_mib = vram_est if dev == "gpu" else 0
        return existing

    total_mib, free_mib = query_nvidia_vram()
    supervisor.ensure_vram_or_evict(
        target_family="stt",
        device=dev,
        vram_est_mib=vram_est,
        free_vram_mib=free_mib,
        total_vram_mib=total_mib,
        force_stop_captions=force_stop_captions,
    )

    handle = supervisor.spawn_worker(
        family="stt",
        model_id=target_id,
        device=dev,
        vram_est_mib=vram_est,
    )
    dl_root = resolved_models_dir(settings) / "stt"
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/load",
            json={
                "model_size": model_arg,
                "compute_type": compute_type,
                "download_root": str(dl_root),
            },
        )
        if resp.status_code >= 400:
            supervisor.eject("stt")
            raise HTTPException(status_code=500, detail=f"STT worker load failed: {resp.text}")
    return handle


def build_qwen_profile(prof: profiles.VoiceProfile, force_stop_captions: bool = False) -> profiles.VoiceProfile:
    if not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
        raise HTTPException(status_code=400, detail="Profile needs a valid reference audio file.")
    handle = ensure_qwen_loaded(force_stop_captions=force_stop_captions)
    pdir = DEFAULT_PROFILES_DIR / prof.id
    pdir.mkdir(parents=True, exist_ok=True)
    wav_24k = pdir / "ref_24k.wav"
    spk_p = pdir / "voice.spk"
    rvq_p = pdir / "voice.rvq"

    with httpx.Client(timeout=180.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/extract_ref",
            json={
                "wav_path": prof.ref_audio_path,
                "wav_24k_path": str(wav_24k),
                "spk_path": str(spk_p),
                "rvq_path": str(rvq_p),
            },
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Failed extracting voice ref: {resp.text}")

    updated = profiles.update_profile(
        prof.id,
        ready=True,
        spk_path=str(spk_p),
        rvq_path=str(rvq_p),
    )
    assert updated is not None
    from .toasts import say

    fire_toast(say("app"), say("profile_ready", name=updated.name))
    return updated


PLAY_SESSION_DIR = DEFAULT_TMP_DIR / "play_session"
_play_sessions_lock = threading.Lock()
_play_sessions: dict[str, dict] = {}


def cleanup_play_session() -> None:
    """Delete ephemeral TTS play-session fragments and legacy preview files."""
    with _play_sessions_lock:
        _play_sessions.clear()
    if PLAY_SESSION_DIR.exists():
        for item in PLAY_SESSION_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception:
                pass
    else:
        PLAY_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if DEFAULT_TMP_DIR.exists():
        for old in DEFAULT_TMP_DIR.glob("preview_*.wav"):
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass


def _cleanup_tmp_previews(max_keep: int = 10) -> None:
    DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(DEFAULT_TMP_DIR.glob("preview_*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max_keep:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_settings()
    cleanup_play_session()
    try:
        RUNTIME_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_JSON_PATH.write_text(
            json.dumps(
                {
                    "port": runtime_info["port"],
                    "pid": runtime_info["pid"],
                    "host": runtime_info["host"],
                    "started_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    print(json.dumps({"port": runtime_info["port"], "pid": runtime_info["pid"]}), flush=True)
    yield
    cleanup_play_session()
    try:
        if RUNTIME_JSON_PATH.is_file():
            cur = json.loads(RUNTIME_JSON_PATH.read_text(encoding="utf-8"))
            if cur.get("pid") == runtime_info["pid"]:
                RUNTIME_JSON_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    supervisor.shutdown_all()


app = FastAPI(title="Speech Studio Local API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _update_http(exc: updates.UpdateError) -> HTTPException:
    status = 409 if exc.code in {"no-asset", "already-current", "bad-url", "bad-name", "too-large"} else 502
    return HTTPException(status_code=status, detail=exc.code)


@app.get("/api/toasts/pending")
def pending_toasts():
    from .toasts import drain

    return {"toasts": drain()}


@app.get("/api/updates/latest")
def updates_latest(current: str = "0.0.0", force: bool = False):
    try:
        return updates.check_latest(current, force=force)
    except updates.UpdateError as exc:
        raise _update_http(exc) from exc


@app.post("/api/updates/open")
def updates_open(payload: UpdateCurrentRequest, request: Request):
    _require_bearer_for_non_loopback(request, load_settings())
    try:
        url = updates.open_release_page(payload.current)
    except updates.UpdateError as exc:
        raise _update_http(exc) from exc
    return {"ok": True, "url": url}


@app.post("/api/updates/install")
def updates_install(payload: UpdateCurrentRequest, request: Request):
    _require_bearer_for_non_loopback(request, load_settings())
    try:
        return updates.install_latest(payload.current)
    except updates.UpdateError as exc:
        raise _update_http(exc) from exc


@app.get("/health")
def health():
    return {
        "ok": True,
        "pid": runtime_info["pid"],
        "port": runtime_info["port"],
        "host": runtime_info["host"],
        "app_root": str(APP_ROOT),
    }


@app.get("/api/settings")
def get_settings():
    s = load_settings()
    return {
        "settings": s.model_dump(),
        "resolved_models_dir": str(resolved_models_dir(s)),
        "resolved_outputs_dir": str(resolved_outputs_dir(s)),
        "api_base_url": f"http://127.0.0.1:{runtime_info['port']}",
    }


@app.put("/api/settings")
def update_settings(payload: AppSettings):
    saved = save_settings(payload)
    return {
        "settings": saved.model_dump(),
        "resolved_models_dir": str(resolved_models_dir(saved)),
        "resolved_outputs_dir": str(resolved_outputs_dir(saved)),
        "api_base_url": f"http://127.0.0.1:{runtime_info['port']}",
    }


@app.get("/api/workers")
def get_workers():
    return supervisor.status_snapshot()


@app.post("/api/workers/qwen/load")
def load_qwen_worker(req: LoadQwenRequest):
    ensure_qwen_loaded(
        model_id=req.model_id,
        device=req.device,
        force_stop_captions=req.force_stop_captions,
    )
    return supervisor.status_snapshot()


@app.get("/api/models/catalog")
def get_models_catalog():
    s = load_settings()
    return {
        "models": [m.model_dump() for m in downloader.build_catalog(s)],
        "downloads": [j.model_dump() for j in download_manager.list_jobs()],
        "models_dir": str(resolved_models_dir(s)),
    }


@app.post("/api/models/download")
def download_catalog_model(req: DownloadModelRequest):
    s = load_settings()
    try:
        job = download_manager.start_catalog_download(s, req.model_id, req.quant_id)
        return {"job": job.model_dump()}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/models/downloads/{job_id}/cancel")
def cancel_model_download(job_id: str):
    ok = download_manager.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Download job not found.")
    return {"cancelled": True, "job_id": job_id}


@app.post("/api/models/hf/inspect")
def inspect_hf_model(req: HfInspectRequest):
    try:
        res = downloader.inspect_hf_repo(req.url)
        return res.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/models/hf/install")
def install_hf_model(req: HfInstallRequest):
    if not req.files:
        raise HTTPException(status_code=400, detail="Select at least one model file to download.")
    s = load_settings()
    job = download_manager.start_custom_hf_download(
        s,
        repo_id=req.repo_id,
        name=req.name,
        kind=req.kind,
        selected_files=req.files,
    )
    return {"job": job.model_dump()}


@app.get("/api/models/hub/search")
def search_models_hub(
    kind: Literal["tts", "stt"] = "tts",
    q: str = "",
    page: int = 1,
    page_size: int = 6,
    ready_only: bool = True,
):
    try:
        return downloader.search_hf_hub(
            kind=kind,
            query=q,
            page=page,
            page_size=page_size,
            ready_only=ready_only,
        ).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hub search failed: {exc}")


@app.post("/api/models/url/inspect")
def inspect_url_model(req: HfInspectRequest):
    try:
        return downloader.inspect_model_url(req.url).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/models/url/install")
def install_url_model(req: UrlInstallRequest):
    if not req.files:
        raise HTTPException(status_code=400, detail="Select at least one model file to download.")
    has_gguf = any(f.lower().endswith(".gguf") for f in req.files)
    if not req.crispasr_ready and not has_gguf and not (req.convert_to_gguf and req.convert_script):
        raise HTTPException(
            status_code=400,
            detail=(
                "Este modelo no es compatible directamente con CrispASR (falta un archivo .gguf o "
                "una arquitectura soportada). Activa la conversión GGUF si está disponible o elige un modelo Ready."
            ),
        )
    s = load_settings()
    job = download_manager.start_url_download(
        s,
        source=req.source,
        repo_id=req.repo_id,
        name=req.name,
        kind=req.kind,
        selected_files=req.files,
        direct_urls=req.direct_urls,
        crispasr_backend=req.crispasr_backend,
        convert_to_gguf=req.convert_to_gguf,
        convert_script=req.convert_script,
    )
    return {"job": job.model_dump()}


@app.post("/api/models/local/import")
def import_local_model_route(req: LocalImportRequest):
    s = load_settings()
    try:
        entry = downloader.import_local_model(
            s,
            source_path=req.source_path,
            name=req.name,
            kind=req.kind,
        )
        return {"model": entry.model_dump()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/inspect")
def inspect_app_state():
    s = load_settings()
    total_mib, free_mib = query_nvidia_vram()
    catalog = downloader.build_catalog(s)
    return {
        "health": {
            "ok": True,
            "pid": runtime_info["pid"],
            "port": runtime_info["port"],
            "host": runtime_info["host"],
            "app_root": str(APP_ROOT),
        },
        "vram": {
            "total_mib": total_mib,
            "free_mib": free_mib,
            "used_mib": max(0, total_mib - free_mib),
        },
        "settings": s.model_dump(),
        "resolved_models_dir": str(resolved_models_dir(s)),
        "resolved_outputs_dir": str(resolved_outputs_dir(s)),
        "workers": supervisor.status_snapshot(),
        "models_installed": [m.model_dump() for m in catalog if m.installed],
        "downloads": [j.model_dump() for j in download_manager.list_jobs()],
        "profiles": [p.model_dump() for p in profiles.list_profiles()],
        "history": [h.model_dump() for h in history.list_history()],
        "endpoints": [e.model_dump() for e in s.external_endpoints],
    }


@app.delete("/api/models/{model_id}")
def delete_installed_model(model_id: str):
    s = load_settings()
    # Cancel any active download for this model so file handles are released before rmtree.
    for job in download_manager.list_jobs():
        if job.model_id == model_id and job.status in ("queued", "downloading"):
            download_manager.cancel_job(job.job_id)
            time.sleep(0.2)

    # Eject loaded worker if it matches this model before unlinking files on Windows
    qwen_w = supervisor.active_workers.get("qwen")
    if qwen_w and qwen_w.model_id.startswith(model_id):
        supervisor.eject("qwen")
    xtts_w = supervisor.active_workers.get("xtts")
    if xtts_w and xtts_w.model_id.startswith(model_id):
        supervisor.eject("xtts")
    stt_w = supervisor.active_workers.get("stt")
    if stt_w and stt_w.model_id == model_id:
        supervisor.eject("stt")
        supervisor.live_captions_active = False

    try:
        return downloader.remove_installed_model(s, model_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


class UninstallLanguageRequest(BaseModel):
    family_id: str
    language: str
    install_mode: Literal["shared_weights", "per_language_checkpoint", "voices_pack"] = (
        "per_language_checkpoint"
    )


@app.post("/api/models/uninstall-language")
def uninstall_language_pack(req: UninstallLanguageRequest):
    from .catalog_capabilities import uninstall_language_pack as _uninstall
    from .config import resolved_models_dir
    from .downloader import BUILTIN_MODELS

    if req.install_mode == "shared_weights":
        raise HTTPException(
            status_code=400,
            detail="shared_weights has no per-language uninstall; remove the whole model instead.",
        )
    s = load_settings()
    deleted = _uninstall(
        models_root=resolved_models_dir(s),
        install_mode=req.install_mode,
        family_id=req.family_id,
        language=req.language,
        catalog_specs=BUILTIN_MODELS,
    )
    langs = dict(s.installed_languages)
    ready = [x for x in langs.get(req.family_id, []) if x != req.language]
    if ready:
        langs[req.family_id] = ready
    else:
        langs.pop(req.family_id, None)
    s.installed_languages = langs
    save_settings(s)
    return {"ok": True, "deleted": deleted, "installed_languages": s.installed_languages}


@app.post("/api/models/{model_id}/runtime")
def set_model_runtime(model_id: str, req: ModelRuntimeRequest):
    s = load_settings()
    entry = next((m for m in downloader.build_catalog(s) if m.id == model_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")
    if req.runtime not in entry.available_runtimes:
        raise HTTPException(
            status_code=400,
            detail=f"Runtime '{req.runtime}' is not available for {model_id} (allowed: {entry.available_runtimes})",
        )
    runtimes = dict(s.model_runtimes)
    runtimes[model_id] = req.runtime
    s.model_runtimes = runtimes
    saved = save_settings(s)
    return {"model_id": model_id, "runtime": req.runtime, "settings": saved.model_dump()}


@app.post("/api/workers/xtts/load")
def load_xtts_worker(req: LoadQwenRequest):
    ensure_xtts_loaded(
        model_id=req.model_id,
        device=req.device,
        force_stop_captions=req.force_stop_captions,
    )
    return supervisor.status_snapshot()


@app.post("/api/workers/stt/load")
def load_stt_worker(req: LoadSttRequest):
    from . import crispasr

    s = load_settings()
    target_id = req.model_id or s.active_stt_model
    if crispasr.is_available() and crispasr.stt_backend_for_model(target_id):
        entry = next((m for m in downloader.build_catalog(s) if m.kind == "stt" and m.id == target_id), None)
        if entry is None or not entry.installed:
            raise HTTPException(status_code=404, detail=f"STT model '{target_id}' is not installed.")
        return supervisor.status_snapshot()
    ensure_stt_loaded(
        model_id=target_id,
        device=req.device,
        force_stop_captions=req.force_stop_captions,
    )
    return supervisor.status_snapshot()


@app.post("/api/workers/eject_group/{group}")
def eject_worker_group(group: str):
    if group == "tts":
        targets = ("qwen", "xtts", "f5", "fish", "kitten", "crispasr")
    elif group == "stt":
        targets = ("stt",)
    else:
        raise HTTPException(status_code=404, detail=f"Unknown worker group: {group}")
    ejected = [fam for fam in targets if supervisor.eject(fam)]
    if "stt" in ejected:
        supervisor.live_captions_active = False
    return {"group": group, "ejected": ejected, **supervisor.status_snapshot()}


@app.post("/api/workers/{family}/eject")
def eject_worker(family: str):
    if family not in ("qwen", "stt", "xtts", "f5", "fish", "kitten", "crispasr"):
        raise HTTPException(status_code=404, detail=f"Unknown worker family: {family}")
    stopped = supervisor.eject(family)
    if family == "stt" and stopped:
        supervisor.live_captions_active = False
    return {"family": family, "stopped": stopped, **supervisor.status_snapshot()}


@app.post("/api/captions/lock")
def set_captions_lock(req: CaptionsLockRequest):
    supervisor.live_captions_active = req.active
    return {"live_captions_active": supervisor.live_captions_active}


@app.websocket("/api/captions/stream")
async def captions_stream(ws: WebSocket):
    from .captions import handle_caption_socket

    await ws.accept()
    await handle_caption_socket(
        ws,
        model_id=ws.query_params.get("model_id"),
        supervisor_inst=supervisor,
    )


@app.post("/api/endpoints/{endpoint_id}/test")
def test_endpoint_route(endpoint_id: str):
    s = load_settings()
    ep = _find_endpoint(s, endpoint_id)
    return external_providers.test_external_endpoint(ep)


# --- Voice Profiles ---


@app.get("/api/profiles")
def get_profiles():
    return {"profiles": [p.model_dump() for p in profiles.list_profiles()]}


@app.post("/api/profiles")
def create_profile_route(req: CreateProfileRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Profile name is required.")
    s = load_settings()
    if req.engine == "qwen":
        try:
            resolve_qwen_gguf(s)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    elif req.engine == "xtts":
        try:
            downloader.resolve_xtts_dir(s)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    elif req.engine == "f5":
        if not any(
            m.kind == "tts" and m.engine in ("f5", "f5-tts") and m.installed
            for m in downloader.build_catalog(s)
        ):
            raise HTTPException(status_code=400, detail="F5-TTS model is not installed. Download it from Models.")
    elif req.engine == "fish":
        if not any(
            m.kind == "tts" and m.engine in ("fish", "fish-audio") and m.installed
            for m in downloader.build_catalog(s)
        ):
            raise HTTPException(status_code=400, detail="Fish Speech 1.5 is not installed. Download it from Models.")
    prof = profiles.create_profile(
        name=req.name,
        language=req.language,
        engine=req.engine,
        ref_audio_path=req.ref_audio_path,
        ref_text=req.ref_text,
    )
    if req.build_voice and prof.engine == "qwen" and prof.ref_audio_path:
        prof = build_qwen_profile(prof, force_stop_captions=req.force_stop_captions)
    return {"profile": prof.model_dump()}


@app.put("/api/profiles/{profile_id}")
def update_profile_route(profile_id: str, req: UpdateProfileRequest):
    updated = profiles.update_profile(
        profile_id,
        name=req.name,
        language=req.language,
        engine=req.engine,
        ref_audio_path=req.ref_audio_path,
        ref_text=req.ref_text,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if (req.rebuild_voice or not updated.ready) and updated.engine == "qwen" and updated.ref_audio_path:
        updated = build_qwen_profile(updated, force_stop_captions=req.force_stop_captions)
    return {"profile": updated.model_dump()}


@app.post("/api/profiles/{profile_id}/build")
def build_profile_route(profile_id: str, force_stop_captions: bool = False):
    prof = profiles.get_profile(profile_id)
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if prof.engine in ("xtts", "f5", "f5-tts", "fish", "fish-audio", "chatterbox", "chatterbox-turbo", "cosyvoice3-tts", "indextts", "orpheus"):
        if not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
            raise HTTPException(status_code=400, detail="Profile needs a valid reference audio file.")
        updated = profiles.update_profile(prof.id, ready=True)
        assert updated is not None
        return {"profile": updated.model_dump()}
    updated = build_qwen_profile(prof, force_stop_captions=force_stop_captions)
    return {"profile": updated.model_dump()}


@app.post("/api/profiles/{profile_id}/trim")
def trim_profile_route(profile_id: str, req: TrimProfileRequest):
    max_s = max(3.0, min(30.0, float(req.max_seconds or 12.0)))
    updated = profiles.trim_profile_audio(profile_id, max_seconds=max_s)
    if updated is None:
        raise HTTPException(status_code=404, detail="Profile or reference audio not found.")
    return {"profile": updated.model_dump()}


@app.get("/api/profiles/{profile_id}/audio")
def get_profile_audio(profile_id: str):
    prof = profiles.get_profile(profile_id)
    if prof is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    cand = prof.ref_24k_path or prof.ref_audio_path
    if not cand or not Path(cand).is_file():
        cand = prof.ref_audio_path
    if not cand or not Path(cand).is_file():
        raise HTTPException(status_code=404, detail="Reference audio file missing.")
    return FileResponse(Path(cand), media_type="audio/wav", filename=Path(cand).name)


@app.get("/api/audio/preview")
def preview_local_audio(path: str):
    raw = (path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Audio path is required.")
    fp = Path(raw)
    allowed_exts = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac"}
    if not fp.is_file() or fp.suffix.lower() not in allowed_exts:
        raise HTTPException(status_code=404, detail="Audio file not found or unsupported format.")
    media = "audio/wav" if fp.suffix.lower() == ".wav" else "application/octet-stream"
    return FileResponse(fp, media_type=media, filename=fp.name)


@app.delete("/api/profiles/{profile_id}")
def delete_profile_route(profile_id: str):
    ok = profiles.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"deleted": True, "id": profile_id}


# --- TTS Synthesis & History ---


def _active_tts_catalog_entry(settings) -> Optional[downloader.CatalogModelEntry]:
    mid = (settings.active_tts_model or "").strip()
    if not mid:
        return None
    tts_entries = [entry for entry in downloader.build_catalog(settings) if entry.kind == "tts"]
    for entry in tts_entries:
        if entry.id == mid:
            return entry
    # Quantified ids such as "qwen3-1.7b-base-q4" still need a family match.
    # Exact id wins above so "fish-speech-1.5" cannot bind to a shorter sibling.
    for entry in tts_entries:
        if entry.id.startswith(mid) or mid.startswith(entry.id + "-"):
            return entry
    return None


def _run_crispasr_tts(
    *,
    entry: Optional[downloader.CatalogModelEntry],
    engine: str,
    speaker_name: str,
    text: str,
    lang: str,
    out_path: Path,
    voice: Optional[str] = None,
    ref_audio: Optional[Path] = None,
    ref_text: Optional[str] = None,
    device: str = "gpu",
    force_stop_captions: bool = False,
) -> tuple[dict, str]:
    from . import audio_prep, crispasr

    model_dir = Path(entry.install_dir) if (entry and entry.install_dir) else None
    dev = "cpu" if device == "cpu" else "gpu"
    if dev == "gpu":
        total_mib, free_mib = query_nvidia_vram()
        vram_est = entry.vram_mib if entry and entry.vram_mib > 0 else 1500
        supervisor.ensure_vram_or_evict(
            target_family="crispasr",
            device="gpu",
            vram_est_mib=vram_est,
            free_vram_mib=free_mib,
            total_vram_mib=total_mib,
            force_stop_captions=force_stop_captions,
        )

    prepped_ref = ref_audio
    if ref_audio is not None and ref_audio.is_file():
        dst_24k = ref_audio.with_name(f"{ref_audio.stem}_24k.wav")
        if ref_audio.name in ("ref_24k.wav", "ref_trim_24k.wav"):
            dst_24k = ref_audio
        try:
            prepped_ref, _ = audio_prep.ensure_ref_24k(ref_audio, dst=dst_24k)
        except Exception:
            prepped_ref = ref_audio

    try:
        res = crispasr.synthesize_tts(
            engine=engine,
            text=text,
            out_path=out_path,
            language=lang,
            model_dir=model_dir,
            voice=voice,
            ref_audio=prepped_ref,
            ref_text=ref_text,
            device=dev,
        )
    except InterruptedError as exc:
        raise HTTPException(status_code=499, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CrispASR synthesis failed: {exc}")
    return res, speaker_name


def _call_tts_worker(
    load_fn,
    payload: dict,
    label: str,
    timeout_s: float = 240.0,
) -> dict:
    try:
        handle = load_fn()
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.post(f"http://127.0.0.1:{handle.port}/synthesize", json=payload)
    except (HTTPException, LiveCaptionsProtectedError, InsufficientVramError):
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"{label}: {exc}")
    except subprocess.SubprocessError as exc:
        raise HTTPException(status_code=503, detail=f"{label} environment setup failed: {exc}")
    except (httpx.HTTPError, TimeoutError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"{label} failed: {exc}")

    if resp.status_code >= 400:
        detail = resp.text
        try:
            err_json = resp.json()
            if isinstance(err_json, dict) and err_json.get("detail"):
                detail = str(err_json["detail"])
        except Exception:
            pass
        status = resp.status_code if 400 <= resp.status_code < 500 else 500
        raise HTTPException(status_code=status, detail=f"{label} failed: {detail}")
    return resp.json()


def _prepare_f5_ref(ref_path: Path, ref_text: str, lang: str, settings: AppSettings) -> tuple[Path, str]:
    """Keep F5 reference audio <= 12s with a matched transcript so duration scaling stays accurate."""
    from . import audio_prep, crispasr

    info = audio_prep.probe_audio_info(ref_path)
    duration = float(info.get("duration_s") or 0.0)
    if duration <= 12.2 or duration <= 0.0:
        return ref_path, ref_text

    stat = ref_path.stat()
    max_s = 11.0
    key = hashlib.sha1(f"{ref_path.absolute()}|{stat.st_mtime_ns}|{lang}".encode("utf-8")).hexdigest()[:12]
    clip_dir = Path(tempfile.gettempdir()) / "ss_f5_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_wav = clip_dir / f"{key}_11s.wav"
    clip_txt = clip_dir / f"{key}_11s.txt"

    clip_wav, _ = audio_prep.ensure_ref_24k(ref_path, dst=clip_wav, max_seconds=max_s)
    if clip_txt.is_file():
        cached_txt = clip_txt.read_text(encoding="utf-8").strip()
        if cached_txt:
            return clip_wav, cached_txt

    matched_text = ""
    try:
        parakeet_entry = next(
            (
                m
                for m in downloader.build_catalog(settings)
                if m.kind == "stt" and m.installed and m.install_dir and "parakeet" in m.id.lower()
            ),
            None,
        )
        if parakeet_entry and parakeet_entry.install_dir:
            res = crispasr.transcribe_stt(
                model_id=parakeet_entry.id,
                audio_path=clip_wav,
                model_dir=Path(parakeet_entry.install_dir),
                language=crispasr.language_code(lang),
                device="gpu" if settings.stt_device != "cpu" else "cpu",
                app_root=APP_ROOT,
            )
            matched_text = (res.get("text") or "").strip()
    except Exception:
        matched_text = ""

    if not matched_text and ref_text.strip():
        target_chars = max(16, int(len(ref_text.strip()) * (max_s / duration)))
        cut = ref_text.strip()[:target_chars]
        last_sp = cut.rfind(" ")
        if last_sp > 8:
            cut = cut[:last_sp]
        matched_text = cut.rstrip(" ,;:") + "."

    if matched_text:
        clip_txt.write_text(matched_text, encoding="utf-8")
    return clip_wav, matched_text


def _run_tts(
    *,
    prof: Optional[profiles.VoiceProfile],
    text: str,
    lang: str,
    out_path: Path,
    seed: int,
    force_stop_captions: bool,
    voice: Optional[str] = None,
) -> tuple[dict, str]:
    settings = load_settings()
    if settings.tts_source == "endpoint":
        ep = _find_endpoint(settings, settings.active_tts_endpoint_id)
        try:
            res = external_providers.synthesize_external(ep, text, lang, out_path)
            return res, ep.name
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"External TTS error ({ep.name}): {exc}")

    from . import crispasr

    entry = _active_tts_catalog_entry(settings)
    tts_dev = "cpu" if settings.tts_device == "cpu" else "gpu"
    if entry is not None:
        if entry.engine == "sapi5":
            from . import sapi5_engine

            try:
                res = sapi5_engine.synthesize_tts(
                    text=text,
                    out_path=out_path,
                    language=lang,
                    voice=voice,
                )
                return res, entry.name
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"SAPI 5 / Loquendo failed: {exc}")

        if entry.engine == "espeak":
            from . import espeak_engine

            try:
                res = espeak_engine.synthesize_tts(
                    text=text,
                    out_path=out_path,
                    language=lang,
                    voice=voice,
                )
                return res, entry.name
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"eSpeak NG failed: {exc}")

        model_dir = Path(entry.install_dir) if entry.install_dir else None
        voice_mode = entry.capabilities.voice_mode if entry.capabilities else "clone_profile"
        prefer_crispasr = (entry.active_runtime or "crispasr") != "python"
        if prefer_crispasr and crispasr.supports_engine(entry.engine, model_dir=model_dir, device=tts_dev):
            if voice_mode == "builtin_voices" or (
                entry.engine in ("f5", "f5-tts") and "gguf" in entry.id.lower() and prof is None
            ):
                return _run_crispasr_tts(
                    entry=entry,
                    engine=entry.engine,
                    speaker_name=entry.name,
                    text=text,
                    lang=lang,
                    out_path=out_path,
                    voice=voice,
                    device=tts_dev,
                    force_stop_captions=force_stop_captions,
                )
            if prof is not None and prof.ref_audio_path and Path(prof.ref_audio_path).exists():
                ref_p = Path(prof.ref_24k_path) if prof.ref_24k_path and Path(prof.ref_24k_path).is_file() else Path(prof.ref_audio_path)
                ref_text_eff = prof.ref_text
                if entry.engine in ("f5", "f5-tts"):
                    ref_p, ref_text_eff = _prepare_f5_ref(ref_p, ref_text_eff, lang, settings)
                return _run_crispasr_tts(
                    entry=entry,
                    engine=entry.engine,
                    speaker_name=prof.name,
                    text=text,
                    lang=lang,
                    out_path=out_path,
                    ref_audio=ref_p,
                    ref_text=ref_text_eff,
                    device=tts_dev,
                    force_stop_captions=force_stop_captions,
                )
        if entry.engine == "kitten":
            res = _call_tts_worker(
                lambda: ensure_kitten_loaded(model_id=entry.id, force_stop_captions=force_stop_captions),
                {"text": text, "lang": lang, "voice": voice, "out_path": str(out_path)},
                "KittenTTS",
                timeout_s=180.0,
            )
            return res, entry.name

        # The model picker decides the engine. A Chatterbox-tagged voice profile
        # only supplies the reference clip; it must not reroute Fish Speech.
        if entry.engine in ("fish", "fish-audio"):
            if prof is None or not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
                raise HTTPException(
                    status_code=400,
                    detail="Fish Speech needs a voice profile with a reference audio file.",
                )
            ref_p = (
                Path(prof.ref_24k_path)
                if prof.ref_24k_path and Path(prof.ref_24k_path).is_file()
                else Path(prof.ref_audio_path)
            )
            res = _call_tts_worker(
                lambda: ensure_fish_loaded(model_id=entry.id, force_stop_captions=force_stop_captions),
                {
                    "text": text,
                    "lang": lang,
                    "speaker_wav": str(ref_p),
                    "ref_text": prof.ref_text,
                    "out_path": str(out_path),
                },
                "Fish Speech 1.5",
            )
            return res, prof.name

    if prof is None:
        raise HTTPException(status_code=404, detail="Voice profile not found.")
    if prof.engine == "xtts":
        if not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
            raise HTTPException(status_code=400, detail="Profile needs a valid reference audio file.")
        res = _call_tts_worker(
            lambda: ensure_xtts_loaded(force_stop_captions=force_stop_captions),
            {
                "text": text,
                "lang": lang,
                "speaker_wav": prof.ref_audio_path,
                "out_path": str(out_path),
            },
            "XTTS v2",
        )
        return res, prof.name
    if prof.engine in ("f5", "f5-tts"):
        if not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
            raise HTTPException(status_code=400, detail="Profile needs a valid reference audio file.")
        raw_ref = Path(prof.ref_24k_path) if prof.ref_24k_path and Path(prof.ref_24k_path).is_file() else Path(prof.ref_audio_path)
        clip_ref, matched_ref_text = _prepare_f5_ref(raw_ref, prof.ref_text or "", lang, settings)
        res = _call_tts_worker(
            lambda: ensure_f5_loaded(force_stop_captions=force_stop_captions),
            {
                "text": text,
                "lang": lang,
                "speaker_wav": str(clip_ref),
                "ref_text": matched_ref_text,
                "out_path": str(out_path),
                "seed": seed,
            },
            "F5-TTS",
        )
        return res, prof.name
    if prof.engine in ("fish", "fish-audio"):
        if not prof.ref_audio_path or not Path(prof.ref_audio_path).exists():
            raise HTTPException(status_code=400, detail="Profile needs a valid reference audio file.")
        res = _call_tts_worker(
            lambda: ensure_fish_loaded(force_stop_captions=force_stop_captions),
            {
                "text": text,
                "lang": lang,
                "speaker_wav": prof.ref_audio_path,
                "ref_text": prof.ref_text,
                "out_path": str(out_path),
            },
            "Fish Speech 1.5",
        )
        return res, prof.name
    if prof.engine != "qwen":
        raise HTTPException(status_code=501, detail=f"Engine '{prof.engine}' is not connected.")
    if not prof.ready:
        prof = build_qwen_profile(prof, force_stop_captions=force_stop_captions)
    handle = ensure_qwen_loaded(force_stop_captions=force_stop_captions)
    with httpx.Client(timeout=240.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/synthesize",
            json={
                "text": text,
                "lang": lang,
                "spk_path": prof.spk_path,
                "rvq_path": prof.rvq_path,
                "ref_text": prof.ref_text,
                "out_path": str(out_path),
                "seed": seed,
            },
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {resp.text}")
        return resp.json(), prof.name


@app.get("/api/tts/voices")
def list_tts_builtin_voices(model_id: Optional[str] = None, language: Optional[str] = None):
    from . import crispasr

    s = load_settings()
    if model_id:
        s = s.model_copy(update={"active_tts_model": model_id})
    entry = _active_tts_catalog_entry(s)
    if entry is None:
        return {"voices": []}
    if entry.engine == "sapi5":
        from . import sapi5_engine

        return {"voices": sapi5_engine.list_voices(language=language)}
    if entry.engine == "espeak":
        from . import espeak_engine

        return {"voices": espeak_engine.list_voices(language=language)}
    if entry.engine == "kitten":
        from backend.workers.kitten_worker import VOICES_BY_LANG, _lang_iso

        iso = _lang_iso(language or "Spanish")
        items = VOICES_BY_LANG.get(iso) or VOICES_BY_LANG["en"]
        return {"voices": [{"id": v, "label": f"{v.capitalize()} ({iso})"} for v in items]}
    model_dir = Path(entry.install_dir) if entry.install_dir else None
    return {
        "voices": crispasr.list_builtin_voices(
            entry.engine, model_dir=model_dir, language=language
        )
    }


@app.post("/api/tts/sapi5/refresh")
def refresh_sapi5_voices():
    from . import sapi5_engine

    sapi5_engine.discover_voices(force_refresh=True)
    return {
        "voices": sapi5_engine.list_voices("all"),
        "languages": sapi5_engine.installed_languages(),
    }


def _resolve_tts_context(req: SynthesizeRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    settings = load_settings()
    from . import crispasr

    prof = profiles.get_profile(req.profile_id)
    entry = _active_tts_catalog_entry(settings) if settings.tts_source == "local" else None
    model_dir = Path(entry.install_dir) if entry and entry.install_dir else None
    builtin_ok = entry is not None and (
        entry.engine in ("kitten", "espeak", "sapi5")
        or (
            crispasr.supports_engine(entry.engine, model_dir=model_dir)
            and (
                (entry.capabilities.voice_mode if entry.capabilities else "") == "builtin_voices"
                or (entry.engine in ("f5", "f5-tts") and "gguf" in entry.id.lower())
            )
        )
    )
    if settings.tts_source == "local" and prof is None and not builtin_ok:
        raise HTTPException(status_code=404, detail=f"Profile not found: {req.profile_id}")

    lang = (req.language or (prof.language if prof else "Spanish") or "Spanish").strip()
    if lang.lower() == "auto":
        lang = "Spanish"
    return text, settings, prof, lang


def _concat_wav_files(chunk_paths: list[Path], out_path: Path) -> tuple[float, int]:
    """Concatenate PCM WAV chunks into a single WAV file and return (duration_s, sr)."""
    if not chunk_paths:
        raise HTTPException(status_code=400, detail="No generated chunks to save.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = 0
    params = None
    with wave.open(str(out_path), "wb") as dst:
        for path in chunk_paths:
            with wave.open(str(path), "rb") as src:
                cur_params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                if params is None:
                    params = cur_params
                    dst.setnchannels(params[0])
                    dst.setsampwidth(params[1])
                    dst.setframerate(params[2])
                elif cur_params != params:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Chunk WAV format mismatch: {cur_params} != {params}",
                    )
                frames = src.readframes(src.getnframes())
                dst.writeframes(frames)
                total_frames += src.getnframes()
    sr = params[2] if params else 24000
    return (total_frames / float(sr)) if sr > 0 else 0.0, sr


class TtsPlanRequest(BaseModel):
    text: str
    max_chars: Optional[int] = None
    enabled: Optional[bool] = None


@app.post("/api/tts/plan")
def tts_plan(req: TtsPlanRequest):
    settings = load_settings()
    enabled = settings.tts_chunk_enabled if req.enabled is None else req.enabled
    max_chars = req.max_chars or settings.tts_chunk_max_chars
    cleaned = req.text.strip()
    if not cleaned:
        return {"chunks": []}
    chunks = chunking.split_text_into_chunks(cleaned, max_chars) if enabled else [cleaned]
    return {"chunks": chunks}


@app.post("/api/tts/session/start")
def tts_session_start(req: SynthesizeRequest):
    text, settings, prof, lang = _resolve_tts_context(req)
    cleanup_play_session()
    PLAY_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    chunks = (
        chunking.split_text_into_chunks(text, settings.tts_chunk_max_chars)
        if settings.tts_chunk_enabled
        else [text]
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    session_id = uuid.uuid4().hex[:12]
    with _play_sessions_lock:
        _play_sessions[session_id] = {
            "session_id": session_id,
            "full_text": text,
            "chunks": chunks,
            "generated": {},
            "profile_id": prof.id if prof else "builtin",
            "speaker_label": prof.name if prof else "Speech Studio",
            "language": lang,
            "voice": req.voice,
            "seed": req.seed,
            "force_stop_captions": req.force_stop_captions,
            "sr": 24000,
            "total_elapsed": 0.0,
        }
    return {"session_id": session_id, "chunks": chunks}


@app.post("/api/tts/session/{session_id}/chunk/{index}")
def tts_session_chunk(session_id: str, index: int, force_stop_captions: bool = False):
    if not re.fullmatch(r"[a-f0-9]+", session_id):
        raise HTTPException(status_code=400, detail="Invalid session id.")
    with _play_sessions_lock:
        sess = _play_sessions.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Play session expired.")
        chunks = sess["chunks"]
        if index < 0 or index >= len(chunks):
            raise HTTPException(status_code=404, detail="Chunk index out of range.")
        existing: Optional[Path] = sess["generated"].get(index)
        chunk_text = chunks[index]
        profile_id = sess["profile_id"]
        lang = sess["language"]
        voice = sess["voice"]
        seed = sess["seed"]
        force = force_stop_captions or sess["force_stop_captions"]

    out_path = PLAY_SESSION_DIR / f"{session_id}_chunk_{index:04d}.wav"
    if existing and existing.exists():
        return {
            "index": index,
            "audio_url": f"/api/tts/session/{session_id}/chunk/{index}/audio",
            "duration_s": 0.0,
            "sr": sess["sr"],
            "elapsed_s": 0.0,
            "rtf": 0.0,
        }

    prof = profiles.get_profile(profile_id)
    res, speaker_label = _run_tts(
        prof=prof,
        text=chunk_text,
        lang=lang,
        out_path=out_path,
        seed=seed,
        force_stop_captions=force,
        voice=voice,
    )
    with _play_sessions_lock:
        cur = _play_sessions.get(session_id)
        if cur is not None:
            cur["generated"][index] = out_path
            cur["speaker_label"] = speaker_label
            cur["sr"] = int(res.get("sr") or cur["sr"])
            cur["total_elapsed"] += float(res.get("elapsed_s") or 0.0)
    return {
        "index": index,
        "audio_url": f"/api/tts/session/{session_id}/chunk/{index}/audio",
        "duration_s": res["duration_s"],
        "sr": res["sr"],
        "elapsed_s": res["elapsed_s"],
        "rtf": res["rtf"],
    }


@app.get("/api/tts/session/{session_id}/chunk/{index}/audio")
def get_session_chunk_audio(session_id: str, index: int):
    if not re.fullmatch(r"[a-f0-9]+", session_id) or index < 0:
        raise HTTPException(status_code=400, detail="Invalid chunk reference.")
    fp = PLAY_SESSION_DIR / f"{session_id}_chunk_{index:04d}.wav"
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Chunk audio missing or cleared.")
    return FileResponse(fp, media_type="audio/wav", filename=fp.name)


@app.post("/api/tts/session/{session_id}/save")
def tts_session_save(session_id: str, force_stop_captions: bool = False):
    if not re.fullmatch(r"[a-f0-9]+", session_id):
        raise HTTPException(status_code=400, detail="Invalid session id.")
    with _play_sessions_lock:
        sess = _play_sessions.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Play session expired.")
        chunks = list(sess["chunks"])
        generated = dict(sess["generated"])
        profile_id = sess["profile_id"]
        speaker_label = sess["speaker_label"]
        full_text = sess["full_text"]
        lang = sess["language"]
        voice = sess["voice"]
        seed = sess["seed"]
        force = force_stop_captions or sess["force_stop_captions"]

    prof = profiles.get_profile(profile_id)
    chunk_paths: list[Path] = []
    extra_elapsed = 0.0
    for idx, chunk_text in enumerate(chunks):
        fp = generated.get(idx) or (PLAY_SESSION_DIR / f"{session_id}_chunk_{idx:04d}.wav")
        if not fp.exists():
            res, speaker_label = _run_tts(
                prof=prof,
                text=chunk_text,
                lang=lang,
                out_path=fp,
                seed=seed,
                force_stop_captions=force,
                voice=voice,
            )
            extra_elapsed += float(res.get("elapsed_s") or 0.0)
            with _play_sessions_lock:
                cur = _play_sessions.get(session_id)
                if cur is not None:
                    cur["generated"][idx] = fp
                    cur["speaker_label"] = speaker_label
        chunk_paths.append(fp)

    settings = load_settings()
    out_dir = resolved_outputs_dir(settings)
    ts = time.strftime("%Y%m%d_%H%M%S")
    pid_tag = prof.id if prof else "api"
    fname = f"{ts}_{pid_tag}_{uuid.uuid4().hex[:6]}.wav"
    out_path = out_dir / fname
    dur_s, sr = _concat_wav_files(chunk_paths, out_path)

    with _play_sessions_lock:
        cur = _play_sessions.get(session_id)
        elapsed_total = (cur["total_elapsed"] if cur else 0.0) + extra_elapsed
    rtf = (elapsed_total / dur_s) if dur_s > 0 else 0.0

    rec = history.add_record(
        profile_id=pid_tag,
        profile_name=speaker_label,
        text=full_text,
        language=lang,
        file_path=str(out_path),
        saved_path=str(out_path),
        duration_s=dur_s,
        sr=sr,
        elapsed_s=elapsed_total,
        rtf=rtf,
    )
    from .toasts import say

    fire_toast(say("app"), say("wav_saved", speaker=speaker_label, seconds=f"{rec.duration_s:.1f}"))
    return {
        "mode": "wav",
        "record": rec.model_dump(),
        "saved_path": str(out_path),
        "audio_url": f"/api/tts/history/{rec.id}/audio",
    }


@app.post("/api/tts/session/clear")
def tts_session_clear():
    cleanup_play_session()
    return {"cleared": True}


@app.post("/api/tts/cancel")
def tts_cancel():
    from . import crispasr

    crispasr.server_manager.cancel_active()
    cleanup_play_session()
    return {"cancelled": True}


@app.post("/api/tts/synthesize")
def tts_synthesize(req: SynthesizeRequest):
    text, settings, prof, lang = _resolve_tts_context(req)

    if req.mode == "play":
        _cleanup_tmp_previews()
        fname = f"preview_{uuid.uuid4().hex[:10]}.wav"
        out_path = DEFAULT_TMP_DIR / fname
        res, _ = _run_tts(
            prof=prof,
            text=text,
            lang=lang,
            out_path=out_path,
            seed=req.seed,
            force_stop_captions=req.force_stop_captions,
            voice=req.voice,
        )
        return {
            "mode": "play",
            "audio_url": f"/api/tts/tmp/{fname}",
            "duration_s": res["duration_s"],
            "sr": res["sr"],
            "elapsed_s": res["elapsed_s"],
            "rtf": res["rtf"],
        }

    out_dir = resolved_outputs_dir(settings)
    ts = time.strftime("%Y%m%d_%H%M%S")
    pid_tag = prof.id if prof else "api"
    fname = f"{ts}_{pid_tag}_{uuid.uuid4().hex[:6]}.wav"
    out_path = out_dir / fname
    res, speaker_label = _run_tts(
        prof=prof,
        text=text,
        lang=lang,
        out_path=out_path,
        seed=req.seed,
        force_stop_captions=req.force_stop_captions,
        voice=req.voice,
    )
    rec = history.add_record(
        profile_id=pid_tag,
        profile_name=speaker_label,
        text=text,
        language=lang,
        file_path=str(out_path),
        saved_path=str(out_path),
        duration_s=res["duration_s"],
        sr=res["sr"],
        elapsed_s=res["elapsed_s"],
        rtf=res["rtf"],
    )
    from .toasts import say

    fire_toast(say("app"), say("wav_saved", speaker=speaker_label, seconds=f"{rec.duration_s:.1f}"))
    return {
        "mode": "wav",
        "record": rec.model_dump(),
        "audio_url": f"/api/tts/history/{rec.id}/audio",
    }


@app.get("/api/tts/tmp/{filename}")
def get_tmp_wav(filename: str):
    if not re.fullmatch(r"preview_[a-f0-9]+\.wav", filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    fp = DEFAULT_TMP_DIR / filename
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Temporary audio expired.")
    return FileResponse(fp, media_type="audio/wav", filename=filename)


@app.get("/api/tts/history")
def get_history():
    return {"history": [r.model_dump() for r in history.list_history()]}


@app.get("/api/tts/history/{rec_id}/audio")
def get_history_audio(rec_id: str):
    rec = history.get_record(rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    fp = Path(rec.saved_path) if rec.saved_path and Path(rec.saved_path).exists() else Path(rec.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk.")
    return FileResponse(fp, media_type="audio/wav", filename=fp.name)


@app.post("/api/tts/history/{rec_id}/save_as")
def save_history_as(rec_id: str, req: SaveAsRequest):
    updated = history.set_saved_path(rec_id, req.dest_path)
    if updated is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return {"record": updated.model_dump()}


@app.delete("/api/tts/history/{rec_id}")
def delete_history_item(rec_id: str):
    if not history.delete_record(rec_id):
        raise HTTPException(status_code=404, detail="History record not found.")
    return {"deleted": True, "id": rec_id}


# --- STT File Transcription ---


def _run_stt(audio_path: Path, language: Optional[str] = None, model_id: Optional[str] = None) -> dict:
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {audio_path}")
    settings = load_settings()
    if settings.stt_source == "endpoint":
        ep = _find_endpoint(settings, settings.active_stt_endpoint_id)
        try:
            res = external_providers.transcribe_external(ep, audio_path, language)
            return {**res, "source": "endpoint", "model": ep.name}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"External STT error ({ep.name}): {exc}")

    target_id = (model_id or settings.active_stt_model or "").strip()
    from . import crispasr

    stt_dev = "cpu" if settings.stt_device == "cpu" else "gpu"
    stt_entry = next(
        (m for m in downloader.build_catalog(settings) if m.kind == "stt" and m.id == target_id),
        None,
    )
    stt_dir = Path(stt_entry.install_dir) if (stt_entry and stt_entry.install_dir) else None
    stt_key = (stt_entry.engine if stt_entry else target_id) or target_id
    if (crispasr.stt_backend_for_model(stt_key) or crispasr.stt_backend_for_model(target_id)) and crispasr.is_available(device=stt_dev):
        try:
            res = crispasr.transcribe_stt(
                model_id=stt_key if crispasr.stt_backend_for_model(stt_key) else target_id,
                audio_path=audio_path,
                language=language,
                model_dir=stt_dir,
                device=stt_dev,
            )
            return {**res, "source": "local", "model": target_id}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"CrispASR STT failed: {exc}")

    handle = ensure_stt_loaded(model_id=model_id)
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(
            f"http://127.0.0.1:{handle.port}/transcribe",
            json={"audio_path": str(audio_path), "language": language, "vad_filter": True},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"STT transcribe failed: {resp.text}")
        res = resp.json()
        return {**res, "source": "local", "model": handle.model_id}


@app.post("/api/stt/transcribe")
def stt_transcribe_file(req: TranscribeFileRequest):
    return _run_stt(Path(req.audio_path), language=req.language, model_id=req.model_id)


# --- OpenAI-compatible Local API Endpoints ---


@app.post("/v1/audio/speech")
def openai_speech(request: Request, req: SpeechRequest):
    s = load_settings()
    _verify_local_api_access(request, s)

    text = req.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="'input' must not be empty.")

    prof = profiles.get_profile(req.voice)
    if prof is None and s.tts_source == "local":
        from . import crispasr

        entry = _active_tts_catalog_entry(s)
        model_dir = Path(entry.install_dir) if entry and entry.install_dir else None
        tts_dev = "cpu" if s.tts_device == "cpu" else "gpu"
        builtin_ok = (
            entry is not None
            and crispasr.supports_engine(entry.engine, model_dir=model_dir, device=tts_dev)
            and (
                (entry.capabilities.voice_mode if entry.capabilities else "") == "builtin_voices"
                or (entry.engine in ("f5", "f5-tts") and "gguf" in entry.id.lower())
            )
        )
        if not builtin_ok:
            all_p = [p for p in profiles.list_profiles() if p.ready]
            if not all_p:
                raise HTTPException(
                    status_code=404,
                    detail="No local voice profile found. Create a profile or switch TTS to an external endpoint.",
                )
            prof = all_p[0]

    lang = (req.language or (prof.language if prof else "Spanish") or "Spanish").strip()
    if lang.lower() == "auto":
        lang = "Spanish"
    DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_wav = DEFAULT_TMP_DIR / f"api_{uuid.uuid4().hex[:10]}.wav"
    try:
        _run_tts(
            prof=prof,
            text=text,
            lang=lang,
            out_path=tmp_wav,
            seed=req.seed,
            force_stop_captions=False,
        )
        return Response(content=tmp_wav.read_bytes(), media_type="audio/wav")
    finally:
        tmp_wav.unlink(missing_ok=True)


@app.post("/v1/audio/transcriptions")
async def openai_transcriptions(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: Optional[str] = Form(None),
):
    s = load_settings()
    _verify_local_api_access(request, s)

    DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    tmp_in = DEFAULT_TMP_DIR / f"stt_api_{uuid.uuid4().hex[:10]}{suffix}"
    try:
        tmp_in.write_bytes(await file.read())
        known_stt_ids = {
            m_id
            for m_id, entry in downloader.BUILTIN_BY_ID.items()
            if entry.get("kind") == "stt"
        } | {
            c["id"]
            for c in downloader.load_custom_registry(s)
            if c.get("kind") == "stt"
        }
        target_model = model if model in known_stt_ids else None
        return _run_stt(tmp_in, language=language, model_id=target_model)
    finally:
        tmp_in.unlink(missing_ok=True)


@app.exception_handler(LiveCaptionsProtectedError)
def handle_captions_protected(_, exc: LiveCaptionsProtectedError):
    return JSONResponse(
        status_code=409,
        content={"requires_confirmation": True, "reason": "live_captions_active", "detail": str(exc)},
    )


@app.exception_handler(InsufficientVramError)
def handle_insufficient_vram(_, exc: InsufficientVramError):
    return JSONResponse(status_code=507, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
def handle_missing_file(_, exc: FileNotFoundError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
def handle_unexpected_error(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def main(port: Optional[int] = None) -> None:
    parser = argparse.ArgumentParser(description="Speech Studio Orchestrator")
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    bind_host = args.host or settings.api_bind_host or "127.0.0.1"
    try:
        reject_public_bind_without_token(bind_host, settings.api_bearer_token)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    requested_port = args.port if args.port is not None else settings.api_fixed_port
    runtime_info["host"] = bind_host

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((bind_host, requested_port))
    except OSError:
        sock.bind((bind_host, 0))
    sock.listen(128)
    actual_port = sock.getsockname()[1]
    runtime_info["port"] = actual_port

    config = uvicorn.Config(
        app,
        host=bind_host,
        port=actual_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[sock]))


if __name__ == "__main__":
    main()
