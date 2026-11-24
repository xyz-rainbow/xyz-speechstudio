from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Tuple

parser = argparse.ArgumentParser(description="Qwen3-TTS isolated worker")
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args, _ = parser.parse_known_args()

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qwentts_cpp import QwenTTS, VoiceRef

state: dict = {
    "tts": None,
    "talker_path": "",
    "codec_path": "",
    "port": 0,
    "pid": os.getpid(),
    "vref_cache": {},  # type: Dict[Tuple[str, str, float], VoiceRef]
}


class LoadRequest(BaseModel):
    talker_path: str
    codec_path: str


class ExtractRefRequest(BaseModel):
    wav_path: str
    wav_24k_path: str
    spk_path: str
    rvq_path: str


class SynthRequest(BaseModel):
    text: str
    lang: str = "spanish"
    spk_path: str
    rvq_path: str
    ref_text: str
    out_path: str
    seed: int = -1


def read_wav_24k_float32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        if wf.getframerate() != 24000 or wf.getnchannels() != 1:
            raise ValueError(f"Expected 24kHz mono WAV at {path}")
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


def save_pcm16_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
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
                "worker": "qwen",
                "device": args.device,
                "pid": state["pid"],
            }
        ),
        flush=True,
    )
    yield
    if state["tts"] is not None:
        try:
            state["tts"].close()
        except Exception:
            pass
        state["tts"] = None


app = FastAPI(title="Qwen3-TTS Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "qwen",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["tts"] is not None,
        "talker_path": state["talker_path"],
        "codec_path": state["codec_path"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    t0 = time.perf_counter()
    if (
        state["tts"] is not None
        and state["talker_path"] == req.talker_path
        and state["codec_path"] == req.codec_path
    ):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}

    if state["tts"] is not None:
        state["tts"].close()
        state["tts"] = None
        state["vref_cache"].clear()

    if not Path(req.talker_path).exists() or not Path(req.codec_path).exists():
        raise HTTPException(status_code=404, detail="GGUF model files not found.")

    state["tts"] = QwenTTS(req.talker_path, req.codec_path)
    state["talker_path"] = req.talker_path
    state["codec_path"] = req.codec_path
    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/extract_ref")
def extract_ref(req: ExtractRefRequest):
    tts: QwenTTS | None = state["tts"]
    if tts is None:
        raise HTTPException(status_code=400, detail="Qwen model is not loaded yet.")

    src = Path(req.wav_path)
    dst_24k = Path(req.wav_24k_path)
    spk_p = Path(req.spk_path)
    rvq_p = Path(req.rvq_path)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Reference audio not found: {src}")

    dst_24k.parent.mkdir(parents=True, exist_ok=True)
    spk_p.parent.mkdir(parents=True, exist_ok=True)

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dst_24k),
        ],
        check=True,
        creationflags=creationflags,
    )

    ref_audio_24k = read_wav_24k_float32(dst_24k)
    vref = tts.save_voice_ref(ref_audio_24k, spk_p, rvq_p)
    mtime = spk_p.stat().st_mtime
    state["vref_cache"][(str(spk_p), str(rvq_p), mtime)] = vref

    return {
        "spk_path": str(spk_p),
        "rvq_path": str(rvq_p),
        "ref_T": vref.ref_T,
        "codebooks": vref.num_codebooks,
        "duration_s": round(len(ref_audio_24k) / 24000.0, 2),
    }


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    tts: QwenTTS | None = state["tts"]
    if tts is None:
        raise HTTPException(status_code=400, detail="Qwen model is not loaded yet.")

    spk_p = Path(req.spk_path)
    rvq_p = Path(req.rvq_path)
    if not spk_p.exists() or not rvq_p.exists():
        raise HTTPException(status_code=404, detail="Voice profile .spk/.rvq files missing.")

    mtime = spk_p.stat().st_mtime
    key = (str(spk_p), str(rvq_p), mtime)
    vref = state["vref_cache"].get(key)
    if vref is None:
        vref = tts.load_voice_ref(spk_p, rvq_p)
        state["vref_cache"][key] = vref

    t0 = time.perf_counter()
    audio, sr = tts.synthesize(
        text=req.text,
        lang=req.lang.lower(),
        ref_spk_emb=vref.ref_spk_emb,
        ref_codes=vref.ref_codes,
        ref_text=req.ref_text,
        seed=req.seed,
    )
    elapsed = time.perf_counter() - t0
    out_p = Path(req.out_path)
    save_pcm16_wav(out_p, audio, sr)
    dur = len(audio) / float(sr)
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
