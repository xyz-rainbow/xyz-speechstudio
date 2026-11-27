"""F5-TTS isolated worker for safetensors/pt checkpoints."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import sys
import tempfile
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


def _preload_cudnn() -> None:
    """Map the wheel's cuDNN plugins before torch's loader runs.

    cuDNN resolves sibling DLLs from the module path. A path that contains
    brackets (this repo lives under ``[🛠️]``) makes that lookup return an
    invalid handle, and the first convolution aborts with
    ``Cannot load symbol cudnnGetVersion``. Loading the DLLs by absolute path
    first keeps the already-mapped plugins.
    """
    if os.name != "nt":
        return
    libdir = Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
    if not libdir.is_dir():
        return
    import ctypes

    try:
        os.add_dll_directory(str(libdir))
    except OSError:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for dll in sorted(libdir.glob("cudnn*.dll")):
        kernel32.LoadLibraryExW(str(dll), None, 0x00001100)


def _use_soundfile_loader() -> None:
    """TorchAudio 2.9+ reads clips through TorchCodec, which needs FFmpeg shared libraries."""
    import soundfile as sf
    import torch
    import torchaudio
    import f5_tts.infer.utils_infer as utils_infer

    def _sf_load(uri, *l_args, **l_kwargs):
        data, sr = sf.read(str(uri), always_2d=True, dtype="float32")
        return torch.from_numpy(data.T.copy()), int(sr)

    torchaudio.load = _sf_load
    utils_infer.torchaudio.load = _sf_load


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


def _detect_model_arch(model_dir: Path, ckpt_file: Path) -> str:
    ckpt_low = ckpt_file.name.lower()
    dir_low = model_dir.name.lower()
    if "1200000" in ckpt_low or "spanish" in dir_low or ("base" in ckpt_low and "v1" not in ckpt_low):
        return "F5TTS_Base"
    return "F5TTS_v1_Base"


def _trim_text_proportionally(ref_text: str, keep_ratio: float) -> str:
    txt = ref_text.strip()
    if not txt or keep_ratio >= 0.99:
        return txt
    target_chars = max(16, int(len(txt) * keep_ratio))
    if len(txt) <= target_chars:
        return txt
    cut = txt[:target_chars]
    last_space = cut.rfind(" ")
    if last_space > 8:
        cut = cut[:last_space]
    return cut.rstrip(" ,;:") + "."


def _prepare_short_ref(speaker: Path, ref_text: str, max_seconds: float = 11.0) -> tuple[Path, str]:
    import numpy as np
    import soundfile as sf

    info = sf.info(str(speaker))
    duration = float(info.duration or 0.0)
    if duration <= 12.2 or duration <= 0.0:
        return speaker, ref_text

    stat = speaker.stat()
    key = hashlib.sha1(f"{speaker.resolve()}|{stat.st_mtime_ns}|{max_seconds}".encode("utf-8")).hexdigest()[:12]
    clip_dir = Path(tempfile.gettempdir()) / "ss_f5_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_path = clip_dir / f"{key}_11s.wav"

    if not clip_path.is_file():
        data, sr = sf.read(str(speaker), always_2d=True, dtype="float32")
        mono = data.mean(axis=1)
        if sr != 24000:
            n_out = max(1, int(round(len(mono) * 24000.0 / float(sr))))
            mono = np.interp(
                np.linspace(0.0, max(0, len(mono) - 1), n_out),
                np.arange(len(mono)),
                mono,
            ).astype(np.float32)
            sr = 24000
        max_frames = int(round(max_seconds * sr))
        _save_pcm16_wav(clip_path, mono[:max_frames], sr)

    trimmed_text = _trim_text_proportionally(ref_text, max_seconds / duration) if ref_text.strip() else ""
    return clip_path, trimmed_text


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
        _preload_cudnn()
        import torch
        from f5_tts.api import F5TTS

        _use_soundfile_loader()

        ckpt_file, vocab_file = _find_ckpt_and_vocab(model_dir)
        dev = "cuda" if (args.device == "gpu" and torch.cuda.is_available()) else "cpu"
        kwargs: dict = {
            "model": _detect_model_arch(model_dir, ckpt_file),
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
        _use_soundfile_loader()
        # An empty transcript makes F5 download openai/whisper-large-v3-turbo.
        ref_text = req.ref_text.strip() or "Referencia."
        ref_clip, matched_ref_text = _prepare_short_ref(speaker, ref_text)
        wav, sr, _ = tts.infer(
            ref_file=str(ref_clip),
            ref_text=matched_ref_text,
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
