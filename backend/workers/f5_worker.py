"""F5-TTS isolated worker for safetensors/pt checkpoints."""

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
from typing import Optional

parser = argparse.ArgumentParser(description="F5-TTS isolated worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

state: dict = {
    "tts": None,
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
    ref_text: str = ""
    out_path: str
    seed: int = -1


def _save_pcm16_wav(path: Path, audio, sr: int) -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(audio, dtype=np.float32).squeeze()
    clipped = np.clip(arr, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _find_ckpt_and_vocab(model_dir: Path) -> tuple[Path, Optional[Path]]:
    ckpts = sorted(
        list(model_dir.rglob("*.safetensors")) + list(model_dir.rglob("*.pt"))
    )
    if not ckpts:
        raise FileNotFoundError(f"No F5-TTS checkpoint (.safetensors/.pt) found in {model_dir}")
    vocabs = sorted(model_dir.rglob("*vocab*.txt"))
    return ckpts[0], (vocabs[0] if vocabs else None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        json.dumps(
            {
                "port": state["port"],
                "worker": "f5",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    state["tts"] = None


app = FastAPI(title="F5-TTS Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "f5",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["tts"] is not None,
        "model_dir": state["model_dir"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    t0 = time.perf_counter()
    model_dir = Path(req.model_dir)
    if state["tts"] is not None and state["model_dir"] == str(model_dir):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}

    try:
        import torch
        from f5_tts.api import F5TTS

        ckpt_file, vocab_file = _find_ckpt_and_vocab(model_dir)
        dev = "cuda" if (args.device == "gpu" and torch.cuda.is_available()) else "cpu"
        kwargs: dict = {
            "model": "F5TTS_v1_Base",
            "ckpt_file": str(ckpt_file),
            "device": dev,
        }
        if vocab_file is not None:
            kwargs["vocab_file"] = str(vocab_file)
        state["tts"] = F5TTS(**kwargs)
        state["model_dir"] = str(model_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"F5-TTS load failed: {exc}") from exc

    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    tts = state["tts"]
    if tts is None:
        raise HTTPException(status_code=400, detail="F5-TTS model is not loaded yet.")
    speaker = Path(req.speaker_wav)
    if not speaker.is_file():
        raise HTTPException(status_code=404, detail=f"Reference audio not found: {speaker}")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")

    t0 = time.perf_counter()
    try:
        wav, sr, _ = tts.infer(
            ref_file=str(speaker),
            ref_text=req.ref_text.strip(),
            gen_text=text,
            seed=req.seed if req.seed >= 0 else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"F5-TTS synthesis failed: {exc}") from exc

    elapsed = time.perf_counter() - t0
    out_p = Path(req.out_path)
    _save_pcm16_wav(out_p, wav, int(sr))
    dur = len(wav) / float(sr) if sr else 0.0
    rtf = (elapsed / dur) if dur > 0 else 0.0
    return {
        "out_path": str(out_p),
        "duration_s": round(dur, 3),
        "sr": int(sr),
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
