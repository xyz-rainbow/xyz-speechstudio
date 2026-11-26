"""Fish Speech 1.5 isolated worker (Firefly-GAN VQGAN + Dual-AR text2semantic)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
    "vq_model": None,
    "vq_sr": 44100,
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


def _ensure_fish_setup():
    import fish_speech
    import soundfile as sf
    import torch
    import torchaudio

    # pyrootutils looks for `.project-root` up from fish_speech package path (namespace pkg has __path__, not __file__).
    pkg_dir = Path(fish_speech.__file__).parent if getattr(fish_speech, "__file__", None) else Path(list(fish_speech.__path__)[0])
    for root_cand in (pkg_dir.parent, pkg_dir):
        marker = root_cand / ".project-root"
        if not marker.exists():
            try:
                marker.write_text("", encoding="utf-8")
            except OSError:
                pass

    def _sf_load(uri, *l_args, **l_kwargs):
        data, sr = sf.read(str(uri), always_2d=True, dtype="float32")
        return torch.from_numpy(data.T.copy()), int(sr)

    torchaudio.load = _sf_load
    return _sf_load


def _save_pcm16_wav(path: Path, audio, sr: int) -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(audio, dtype=np.float32).squeeze()
    clipped = np.clip(arr, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm.tobytes())


def _encode_ref_tokens(speaker: Path, dev: str) -> Path:
    import numpy as np
    import torch
    import torchaudio

    vq_model = state["vq_model"]
    assert vq_model is not None
    sig = hashlib.sha1(f"{speaker}:{speaker.stat().st_mtime_ns}:{speaker.stat().st_size}".encode("utf-8")).hexdigest()[:10]
    cache_npy = speaker.with_name(f"fish_ref_{sig}.npy")
    if cache_npy.is_file() and cache_npy.stat().st_size > 0:
        return cache_npy

    _sf_load = _ensure_fish_setup()
    audio, sr = _sf_load(str(speaker))
    if audio.shape[0] > 1:
        audio = audio.mean(0, keepdim=True)
    target_sr = int(getattr(getattr(vq_model, "spec_transform", None), "sample_rate", 44100))
    audio = torchaudio.functional.resample(audio, sr, target_sr)
    audios = audio[None].to(dev)
    alens = torch.tensor([audios.shape[2]], device=dev, dtype=torch.long)
    with torch.no_grad():
        indices, _ = vq_model.encode(audios, alens)
    if indices.ndim == 3:
        indices = indices[0]
    np.save(str(cache_npy), indices.cpu().numpy())
    return cache_npy


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
    state["vq_model"] = None


app = FastAPI(title="Fish Speech Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "fish",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["vq_model"] is not None,
        "model_dir": state["model_dir"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    t0 = time.perf_counter()
    model_dir = Path(req.model_dir)
    if state["vq_model"] is not None and state["model_dir"] == str(model_dir):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}
    if not (model_dir / "model.pth").is_file():
        raise HTTPException(status_code=404, detail=f"Fish Speech model.pth not found in {model_dir}")
    vq_ckpts = sorted(model_dir.glob("firefly-gan-vq-*.pth"))
    if not vq_ckpts:
        raise HTTPException(status_code=404, detail=f"Fish VQGAN checkpoint missing in {model_dir}")

    try:
        import torch
        import fish_speech.models.vqgan.inference as fv

        _ensure_fish_setup()
        dev = "cuda" if (args.device == "gpu" and torch.cuda.is_available()) else "cpu"
        vq_model = fv.load_model("firefly_gan_vq", str(vq_ckpts[0]), device=dev)
        state["vq_model"] = vq_model
        state["vq_sr"] = int(getattr(getattr(vq_model, "spec_transform", None), "sample_rate", 44100))
        state["model_dir"] = str(model_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fish Speech load failed: {exc}") from exc

    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    vq_model = state["vq_model"]
    if vq_model is None:
        raise HTTPException(status_code=400, detail="Fish Speech model is not loaded yet.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")
    speaker = Path(req.speaker_wav)
    if not speaker.is_file():
        raise HTTPException(status_code=404, detail=f"Reference audio not found: {speaker}")

    import numpy as np
    import torch

    model_dir = Path(state["model_dir"])
    t0 = time.perf_counter()
    out_p = Path(req.out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if (args.device == "gpu" and torch.cuda.is_available()) else "cpu"

    try:
        ref_npy = _encode_ref_tokens(speaker, dev)
        with tempfile.TemporaryDirectory(prefix="fish_") as tmp:
            tmp_dir = Path(tmp)
            cmd = [
                sys.executable,
                "-m",
                "fish_speech.models.text2semantic.inference",
                "--text",
                text,
                "--prompt-text",
                req.ref_text.strip(),
                "--prompt-tokens",
                str(ref_npy),
                "--checkpoint-path",
                str(model_dir),
                "--device",
                dev,
                "--output-dir",
                str(tmp_dir),
            ]
            if dev == "cuda":
                cmd.append("--half")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()[-1200:]
                raise HTTPException(status_code=500, detail=f"Fish text2semantic failed: {err}")

            codes = sorted(tmp_dir.glob("codes_*.npy"))
            if not codes:
                raise HTTPException(status_code=500, detail="Fish text2semantic produced no codes.")

            idx = torch.from_numpy(np.load(str(codes[0]))).to(dev).long()
            if idx.ndim == 2:
                idx = idx[None]
            idx_lens = torch.tensor([idx.shape[2]], device=dev, dtype=torch.long)
            with torch.no_grad():
                fake_aud, _ = vq_model.decode(idx, idx_lens)
            wav_arr = fake_aud[0, 0].float().cpu().numpy()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fish Speech synthesis failed: {exc}") from exc

    sr = int(state["vq_sr"] or 44100)
    _save_pcm16_wav(out_p, wav_arr, sr)
    elapsed = time.perf_counter() - t0
    dur = len(wav_arr) / float(sr) if sr else 0.0
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
