"""Fish Speech 1.5 isolated worker."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path

parser = argparse.ArgumentParser(description="Fish Speech 1.5 isolated worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

state: dict = {
    "model_dir": "",
    "loaded": False,
    "port": 0,
    "pid": os.getpid(),
}


class LoadRequest(BaseModel):
    model_dir: str


class SynthRequest(BaseModel):
    text: str
    lang: str = "Spanish"
    speaker_wav: str
    ref_text: str = ""
    out_path: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        json.dumps(
            {
                "port": state["port"],
                "worker": "fish",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    state["loaded"] = False


app = FastAPI(title="Fish Speech Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "fish",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["loaded"],
        "model_dir": state["model_dir"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    model_dir = Path(req.model_dir)
    if not (model_dir / "model.pth").is_file():
        raise HTTPException(status_code=404, detail=f"Fish Speech model.pth not found in {model_dir}")
    state["model_dir"] = str(model_dir)
    state["loaded"] = True
    return {"loaded": True, "cached": True, "elapsed_s": 0.0}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    if not state["loaded"]:
        raise HTTPException(status_code=400, detail="Fish Speech model is not loaded yet.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    speaker = Path(req.speaker_wav)
    if not speaker.is_file():
        raise HTTPException(status_code=404, detail=f"Reference audio not found: {speaker}")

    model_dir = Path(state["model_dir"])
    vq_ckpts = sorted(model_dir.glob("firefly-gan-vq-*.pth"))
    if not vq_ckpts:
        raise HTTPException(status_code=404, detail=f"Fish VQGAN checkpoint missing in {model_dir}")

    t0 = time.perf_counter()
    out_p = Path(req.out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if args.device == "gpu" else "cpu"

    with tempfile.TemporaryDirectory(prefix="fish_") as tmp:
        tmp_dir = Path(tmp)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "fish_speech.models.text2semantic.inference",
                "--text",
                text,
                "--prompt-text",
                req.ref_text.strip(),
                "--prompt-tokens",
                str(speaker),
                "--checkpoint-path",
                str(model_dir),
                "--device",
                dev,
                "--output-dir",
                str(tmp_dir),
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[-1200:]
            raise HTTPException(status_code=500, detail=f"Fish text2semantic failed: {err}")

        codes = sorted(tmp_dir.glob("codes_*.npy"))
        if not codes:
            raise HTTPException(status_code=500, detail="Fish text2semantic produced no codes.")

        proc2 = subprocess.run(
            [
                sys.executable,
                "-m",
                "fish_speech.models.vqgan.inference",
                "-i",
                str(codes[0]),
                "--checkpoint-path",
                str(vq_ckpts[0]),
                "--device",
                dev,
                "-o",
                str(out_p),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc2.returncode != 0 or not out_p.is_file():
            err = (proc2.stderr or proc2.stdout or "").strip()[-1200:]
            raise HTTPException(status_code=500, detail=f"Fish vqgan failed: {err}")

    elapsed = time.perf_counter() - t0
    with wave.open(str(out_p), "rb") as wf:
        sr = wf.getframerate()
        dur = wf.getnframes() / float(sr) if sr else 0.0
    rtf = (elapsed / dur) if dur > 0 else 0.0
    return {
        "out_path": str(out_p),
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(rtf, 3),
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
