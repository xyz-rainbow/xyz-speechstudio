from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

parser = argparse.ArgumentParser(description="faster-whisper isolated STT worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

# Ensure nvidia/*/bin DLLs inside this venv are discoverable by CTranslate2 on Windows.
# Use Path.iterdir() instead of glob.glob() because bracket chars ([🛠️]) break glob wildcards.
nvidia_root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
if nvidia_root.is_dir():
    for pkg_dir in nvidia_root.iterdir():
        bin_dir = pkg_dir / "bin"
        if bin_dir.is_dir():
            bin_str = str(bin_dir)
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(bin_str)
            os.environ["PATH"] = bin_str + os.pathsep + os.environ.get("PATH", "")

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import uvicorn
from fastapi import FastAPI, HTTPException
from faster_whisper import WhisperModel
from pydantic import BaseModel

state: dict = {
    "model": None,
    "model_size": "",
    "compute_type": "",
    "port": 0,
    "pid": os.getpid(),
}


class LoadSttRequest(BaseModel):
    model_size: str = "base"
    compute_type: Optional[str] = None
    download_root: str = ""


class TranscribeRequest(BaseModel):
    audio_path: str
    language: Optional[str] = None
    vad_filter: bool = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        json.dumps(
            {
                "port": state["port"],
                "worker": "stt",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    state["model"] = None


app = FastAPI(title="STT Worker (faster-whisper)", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "stt",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["model"] is not None,
        "model_size": state["model_size"],
        "compute_type": state["compute_type"],
    }


@app.post("/load")
def load_model(req: LoadSttRequest):
    t0 = time.perf_counter()
    ctype = req.compute_type or ("int8_float16" if args.device == "gpu" else "int8")
    if (
        state["model"] is not None
        and state["model_size"] == req.model_size
        and state["compute_type"] == ctype
    ):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}

    state["model"] = None
    dev = "cuda" if args.device == "gpu" else "cpu"
    dl_root = Path(req.download_root) if req.download_root else None
    if dl_root:
        dl_root.mkdir(parents=True, exist_ok=True)

    state["model"] = WhisperModel(
        req.model_size,
        device=dev,
        compute_type=ctype,
        download_root=str(dl_root) if dl_root else None,
    )
    state["model_size"] = req.model_size
    state["compute_type"] = ctype
    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/transcribe")
def transcribe(req: TranscribeRequest):
    model: WhisperModel | None = state["model"]
    if model is None:
        raise HTTPException(status_code=400, detail="STT model is not loaded yet.")

    audio_p = Path(req.audio_path)
    if not audio_p.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {audio_p}")

    lang = req.language.strip() if req.language and req.language.strip() and req.language.lower() != "auto" else None
    t0 = time.perf_counter()
    segments_iter, info = model.transcribe(
        str(audio_p),
        language=lang,
        vad_filter=req.vad_filter,
    )
    segments = [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segments_iter
        if s.text.strip()
    ]
    full_text = " ".join(s["text"] for s in segments).strip()
    elapsed = time.perf_counter() - t0

    return {
        "text": full_text,
        "language": info.language,
        "duration_s": round(float(info.duration), 2),
        "elapsed_s": round(elapsed, 3),
        "segments": segments,
    }


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    state["port"] = sock.getsockname()[1]
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=state["port"],
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[sock]))
