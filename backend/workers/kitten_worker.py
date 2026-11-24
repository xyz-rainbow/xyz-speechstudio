"""KittenTTS 2 Mini isolated ONNX worker."""

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

parser = argparse.ArgumentParser(description="KittenTTS 2 Mini isolated worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DEFAULT_VOICES = [
    "expr-voice-2-m",
    "expr-voice-2-f",
    "expr-voice-3-m",
    "expr-voice-3-f",
    "expr-voice-4-m",
    "expr-voice-4-f",
    "expr-voice-5-m",
    "expr-voice-5-f",
]

state: dict = {
    "model": None,
    "model_dir": "",
    "port": 0,
    "pid": os.getpid(),
}


class LoadRequest(BaseModel):
    model_dir: str


class SynthRequest(BaseModel):
    text: str
    lang: str = "English"
    voice: Optional[str] = None
    out_path: str


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        json.dumps(
            {
                "port": state["port"],
                "worker": "kitten",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    state["model"] = None


app = FastAPI(title="KittenTTS Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "kitten",
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

    try:
        from kittentts import KittenTTS

        onnxs = sorted(model_dir.rglob("*.onnx"))
        if onnxs:
            try:
                state["model"] = KittenTTS(str(onnxs[0]))
            except TypeError:
                state["model"] = KittenTTS()
        else:
            state["model"] = KittenTTS()
        state["model_dir"] = str(model_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KittenTTS load failed: {exc}") from exc

    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    model = state["model"]
    if model is None:
        raise HTTPException(status_code=400, detail="KittenTTS model is not loaded yet.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")

    voice = (req.voice or "").strip() or DEFAULT_VOICES[0]
    t0 = time.perf_counter()
    try:
        audio = model.generate(text, voice=voice)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KittenTTS synthesis failed: {exc}") from exc

    sr = 24000
    elapsed = time.perf_counter() - t0
    out_p = Path(req.out_path)
    _save_pcm16_wav(out_p, audio, sr)
    dur = len(audio) / float(sr) if sr else 0.0
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
