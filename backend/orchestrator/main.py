from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from . import downloader, external_providers, history, profiles
from .config import (
    APP_ROOT,
    DEFAULT_PROFILES_DIR,
    DEFAULT_TMP_DIR,
    AppSettings,
    load_settings,
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

FALLBACK_QWEN_DIR = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b")
TALKER_NAME = "qwen-talker-1.7b-base-Q8_0.gguf"
CODEC_NAME = "qwen-tokenizer-12hz-Q8_0.gguf"

STT_CATALOG: dict[str, tuple[str, int]] = {
    "faster-whisper-tiny": ("tiny", 250),
    "faster-whisper-base": ("base", 350),
    "faster-whisper-small": ("small", 700),
    "faster-whisper-medium": ("medium", 1500),
    "faster-whisper-large-v3-turbo": ("large-v3-turbo", 2100),
}

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


class LoadSttRequest(BaseModel):
    model_id: Optional[str] = None
    device: Optional[Literal["gpu", "cpu"]] = None
    force_stop_captions: bool = False


class CreateProfileRequest(BaseModel):
    name: str
    language: str = "Spanish"
    engine: Literal["qwen", "xtts"] = "qwen"
    ref_audio_path: str = ""
    ref_text: str = ""
    build_voice: bool = True
    force_stop_captions: bool = False


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    engine: Optional[Literal["qwen", "xtts"]] = None
    ref_audio_path: Optional[str] = None
    ref_text: Optional[str] = None
    rebuild_voice: bool = False
    force_stop_captions: bool = False


class SynthesizeRequest(BaseModel):
    profile_id: str
    text: str
    language: Optional[str] = None
    mode: Literal["play", "wav"] = "play"
    seed: int = -1
    force_stop_captions: bool = False


class TranscribeFileRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
    model_id: Optional[str] = None


class SaveAsRequest(BaseModel):
    dest_path: str


class SpeechRequest(BaseModel):
    model: str = "qwen3-1.7b"
    input: str
    voice: str = "mario"
    response_format: str = "wav"
    language: Optional[str] = None
    seed: int = -1


def fire_toast(title: str, message: str, progress: Optional[int] = None) -> None:
    s = load_settings()
    if not s.notifications_enabled:
        return
    script = APP_ROOT / "scripts" / "notify.ps1"
    if not script.exists():
        return
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Title",
        title,
        "-Message",
        message,
    ]
    if progress is not None:
        cmd.extend(["-Progress", str(max(0, min(100, progress)))])
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(cmd, creationflags=creationflags)
    except Exception:
        pass


download_manager = downloader.DownloadManager(notify_cb=fire_toast)


def _verify_local_api_access(request: Request, settings: AppSettings) -> None:
    if not settings.api_endpoint_enabled:
        raise HTTPException(status_code=403, detail="Local API endpoint is turned OFF in Settings.")
    token = settings.api_bearer_token.strip()
    if token:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {token}":
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
    fire_toast("Speech Studio", f"Voice profile '{updated.name}' ready")
    return updated


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
    profiles.ensure_mario_imported()
    print(json.dumps({"port": runtime_info["port"], "pid": runtime_info["pid"]}), flush=True)
    yield
    supervisor.shutdown_all()


app = FastAPI(title="Speech Studio Local API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.delete("/api/models/{model_id}")
def delete_installed_model(model_id: str):
    s = load_settings()
    # Eject loaded worker if it matches this model before unlinking files on Windows
    qwen_w = supervisor.active_workers.get("qwen")
    if qwen_w and qwen_w.model_id.startswith(model_id):
        supervisor.eject("qwen")
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


@app.post("/api/workers/stt/load")
def load_stt_worker(req: LoadSttRequest):
    ensure_stt_loaded(
        model_id=req.model_id,
        device=req.device,
        force_stop_captions=req.force_stop_captions,
    )
    return supervisor.status_snapshot()


@app.post("/api/workers/eject_group/{group}")
def eject_worker_group(group: str):
    if group == "tts":
        targets = ("qwen", "xtts")
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
    if family not in ("qwen", "stt", "xtts"):
        raise HTTPException(status_code=404, detail=f"Unknown worker family: {family}")
    stopped = supervisor.eject(family)
    if family == "stt" and stopped:
        supervisor.live_captions_active = False
    return {"family": family, "stopped": stopped, **supervisor.status_snapshot()}


@app.post("/api/captions/lock")
def set_captions_lock(req: CaptionsLockRequest):
    supervisor.live_captions_active = req.active
    return {"live_captions_active": supervisor.live_captions_active}


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
    updated = build_qwen_profile(prof, force_stop_captions=force_stop_captions)
    return {"profile": updated.model_dump()}


@app.delete("/api/profiles/{profile_id}")
def delete_profile_route(profile_id: str):
    ok = profiles.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"deleted": True, "id": profile_id}


# --- TTS Synthesis & History ---


def _run_tts(
    *,
    prof: Optional[profiles.VoiceProfile],
    text: str,
    lang: str,
    out_path: Path,
    seed: int,
    force_stop_captions: bool,
) -> tuple[dict, str]:
    settings = load_settings()
    if settings.tts_source == "endpoint":
        ep = _find_endpoint(settings, settings.active_tts_endpoint_id)
        try:
            res = external_providers.synthesize_external(ep, text, lang, out_path)
            return res, ep.name
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"External TTS error ({ep.name}): {exc}")

    if prof is None:
        raise HTTPException(status_code=404, detail="Voice profile not found.")
    if prof.engine != "qwen":
        raise HTTPException(status_code=501, detail="XTTS v2 engine connects in Phase 4.")
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


@app.post("/api/tts/synthesize")
def tts_synthesize(req: SynthesizeRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    settings = load_settings()
    prof = profiles.get_profile(req.profile_id)
    if settings.tts_source == "local" and prof is None:
        raise HTTPException(status_code=404, detail=f"Profile not found: {req.profile_id}")

    lang = (req.language or (prof.language if prof else "Spanish") or "Spanish").strip()

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
    )
    rec = history.add_record(
        profile_id=pid_tag,
        profile_name=speaker_label,
        text=text,
        language=lang,
        file_path=str(out_path),
        duration_s=res["duration_s"],
        sr=res["sr"],
        elapsed_s=res["elapsed_s"],
        rtf=res["rtf"],
    )
    fire_toast("Speech Studio", f"WAV exported ({speaker_label}, {rec.duration_s:.1f}s)")
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
        all_p = [p for p in profiles.list_profiles() if p.engine == "qwen" and p.ready]
        if not all_p:
            raise HTTPException(status_code=404, detail=f"Voice '{req.voice}' not found.")
        prof = all_p[0]

    lang = (req.language or (prof.language if prof else "Spanish") or "Spanish").strip()
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
        target_model = model if model in STT_CATALOG else None
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


def main(port: Optional[int] = None) -> None:
    parser = argparse.ArgumentParser(description="Speech Studio Orchestrator")
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    bind_host = args.host or settings.api_bind_host or "127.0.0.1"
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
