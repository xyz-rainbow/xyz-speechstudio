"""XTTS v2 worker. Imports coqui-tts only when /load runs.

The checkpoint is the one downloaded by the catalog (config.json, model.pth,
vocab.json, speakers_xtts.pth). Synthesis uses the profile reference wav.
A real synthesis has not been run from the machine that added this worker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path

parser = argparse.ArgumentParser(description="XTTS v2 isolated worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

# The catalog download is the license step. This keeps the worker from
# blocking on the Coqui prompt when the checkpoint is already on disk.
os.environ.setdefault("COQUI_TOS_AGREED", "1")

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from xtts_lang import xtts_language

REQUIRED_FILES = ("config.json", "model.pth", "vocab.json", "speakers_xtts.pth")

state: dict = {
    "model": None,
    "config": None,
    "model_dir": "",
    "port": 0,
    "pid": os.getpid(),
}


class LoadRequest(BaseModel):
    model_dir: str


class SynthRequest(BaseModel):
    text: str
    lang: str = "Spanish"
    speaker_wav: str
    out_path: str


def _sample_rate(config: object) -> int:
    audio = getattr(config, "audio", None)
    if isinstance(audio, dict):
        return int(audio.get("sample_rate", 24000))
    return int(getattr(audio, "sample_rate", 24000) or 24000)


def save_pcm16_wav(path: Path, audio, sr: int) -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _load_checkpoint(model_dir: Path):
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    config = XttsConfig()
    config.load_json(str(model_dir / "config.json"))
    model = Xtts.init_from_config(config)
    use_cuda = args.device == "gpu" and torch.cuda.is_available()
    if args.device == "gpu" and not use_cuda:
        raise RuntimeError("XTTS was asked to use the GPU, but CUDA is not available.")
    model.load_checkpoint(
        config,
        checkpoint_dir=str(model_dir),
        use_deepspeed=False,
        eval=True,
    )
    if use_cuda:
        model.cuda()
    return model, config


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        json.dumps(
            {
                "port": state["port"],
                "worker": "xtts",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    state["model"] = None
    state["config"] = None


app = FastAPI(title="XTTS v2 Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "xtts",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["model"] is not None,
        "model_dir": state["model_dir"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    t0 = time.perf_counter()
    model_dir = Path(req.model_dir)
    if state["model"] is not None and state["model_dir"] == str(model_dir):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}

    missing = [name for name in REQUIRED_FILES if not (model_dir / name).is_file()]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"XTTS checkpoint is missing {', '.join(missing)} in {model_dir}.",
        )

    try:
        model, config = _load_checkpoint(model_dir)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"XTTS load failed: {exc}") from exc

    state["model"] = model
    state["config"] = config
    state["model_dir"] = str(model_dir)
    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    model = state["model"]
    config = state["config"]
    if model is None or config is None:
        raise HTTPException(status_code=400, detail="XTTS model is not loaded yet.")

    speaker = Path(req.speaker_wav)
    if not speaker.is_file():
        raise HTTPException(status_code=404, detail=f"Reference audio not found: {speaker}")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    try:
        language = xtts_language(req.lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    t0 = time.perf_counter()
    try:
        outputs = model.synthesize(
            text,
            config,
            speaker_wav=str(speaker),
            language=language,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"XTTS synthesis failed: {exc}") from exc

    wav = outputs["wav"] if isinstance(outputs, dict) else outputs
    sr = _sample_rate(config)
    elapsed = time.perf_counter() - t0
    out_p = Path(req.out_path)
    save_pcm16_wav(out_p, wav, sr)
    dur = len(wav) / float(sr) if sr else 0.0
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
