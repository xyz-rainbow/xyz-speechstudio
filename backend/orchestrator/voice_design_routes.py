"""API routes for Qwen3-TTS VoiceDesign (--instruct preview and saving to a cloning VoiceProfile)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config as cfg
from . import crispasr, downloader, profiles

router = APIRouter(prefix="/api/tts/voice-design", tags=["voice-design"])

_PREVIEW_RE = re.compile(r"^[a-f0-9]{12}$")


class VoiceDesignPreviewRequest(BaseModel):
    instructions: str = Field(..., min_length=3, max_length=600)
    language: str = "Spanish"
    sample_text: str = Field(..., min_length=2, max_length=500)
    device: Optional[Literal["gpu", "cpu"]] = None


class VoiceDesignSaveRequest(BaseModel):
    preview_id: str
    name: str = Field(..., min_length=1, max_length=120)
    language: str = "Spanish"
    sample_text: str = Field(..., min_length=2, max_length=500)
    engine: Literal[
        "qwen",
        "chatterbox",
        "chatterbox-turbo",
        "cosyvoice3-tts",
        "indextts",
        "xtts",
        "f5",
        "fish",
    ] = "qwen"


def _vd_tmp_dir() -> Path:
    d = cfg.DEFAULT_TMP_DIR / "voice_design"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_voicedesign_model(settings: cfg.AppSettings) -> tuple[bool, Optional[Path], Optional[Path], Optional[str]]:
    entry = next(
        (m for m in downloader.build_catalog(settings) if m.id == "qwen3-1.7b-voicedesign"),
        None,
    )
    if entry is None or not entry.installed or not entry.install_dir:
        return False, None, None, None
    mdir = Path(entry.install_dir)
    active_quant = entry.installed_quant or (entry.installed_quants[0] if entry.installed_quants else None)
    q_opt = next((q for q in entry.quants if q.id == active_quant and q.files), None)
    if q_opt is None:
        q_opt = next((q for q in entry.quants if q.id in entry.installed_quants and q.files), None)
    if q_opt and q_opt.files:
        cand = mdir / q_opt.files[0]
        if cand.is_file():
            return True, mdir, cand, q_opt.id
    ggufs = sorted(mdir.glob("*.gguf"))
    if ggufs:
        return True, mdir, ggufs[0], active_quant
    return False, mdir, None, None


@router.get("/status")
def voice_design_status():
    settings = cfg.load_settings()
    installed, mdir, model_path, quant_id = _resolve_voicedesign_model(settings)
    crisp_ok = crispasr.is_available()
    return {
        "installed": installed,
        "crispasr_available": crisp_ok,
        "ready": bool(installed and crisp_ok and model_path is not None),
        "model_id": "qwen3-1.7b-voicedesign",
        "quant_id": quant_id,
        "model_path": str(model_path) if model_path else None,
        "model_dir": str(mdir) if mdir else None,
    }


@router.post("/preview")
def voice_design_preview(req: VoiceDesignPreviewRequest):
    settings = cfg.load_settings()
    installed, mdir, model_path, _ = _resolve_voicedesign_model(settings)
    if not installed or model_path is None:
        raise HTTPException(
            status_code=409,
            detail="Qwen3-TTS 1.7B VoiceDesign is not installed. Download it from Models (+) first.",
        )
    dev = req.device or ("cpu" if settings.tts_device == "cpu" else "gpu")
    if not crispasr.is_available(device=dev):
        raise HTTPException(status_code=503, detail="CrispASR binary is not available for VoiceDesign.")

    pid = uuid.uuid4().hex[:12]
    out_wav = _vd_tmp_dir() / f"vd_{pid}.wav"
    try:
        res = crispasr.synthesize_tts(
            engine="qwen",
            text=req.sample_text.strip(),
            out_path=out_wav,
            language=req.language,
            model_dir=mdir,
            model_path=model_path,
            instruct=req.instructions.strip(),
            device=dev,  # type: ignore[arg-type]
        )
    except InterruptedError as exc:
        out_wav.unlink(missing_ok=True)
        raise HTTPException(status_code=499, detail=str(exc))
    except FileNotFoundError as exc:
        out_wav.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        out_wav.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"VoiceDesign synthesis failed: {exc}")

    return {
        "preview_id": pid,
        "audio_url": f"/api/tts/voice-design/preview/{pid}",
        "duration_s": res.get("duration_s", 0.0),
        "sr": res.get("sr", 24000),
        "elapsed_s": res.get("elapsed_s", 0.0),
    }


@router.get("/preview/{preview_id}")
def get_voice_design_preview(preview_id: str):
    if not _PREVIEW_RE.match(preview_id or ""):
        raise HTTPException(status_code=400, detail="Invalid preview id.")
    wav_path = _vd_tmp_dir() / f"vd_{preview_id}.wav"
    if not wav_path.is_file():
        raise HTTPException(status_code=404, detail="VoiceDesign preview audio not found.")
    return FileResponse(wav_path, media_type="audio/wav", filename=f"voice_design_{preview_id}.wav")


@router.post("/save")
def voice_design_save(req: VoiceDesignSaveRequest):
    if not _PREVIEW_RE.match(req.preview_id or ""):
        raise HTTPException(status_code=400, detail="Invalid preview id.")
    src_wav = _vd_tmp_dir() / f"vd_{req.preview_id}.wav"
    if not src_wav.is_file():
        raise HTTPException(status_code=404, detail="Generate a VoiceDesign preview first before saving.")

    prof = profiles.create_profile(
        name=req.name.strip(),
        language=req.language.strip() or "Spanish",
        engine=req.engine,
        ref_audio_path=str(src_wav),
        ref_text=req.sample_text.strip(),
    )
    return {"profile": prof.model_dump()}
