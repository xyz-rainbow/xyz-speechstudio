import argparse
import asyncio
import glob
import json
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--device", choices=["gpu", "cpu"], default="gpu")
args = parser.parse_args()

# Ensure nvidia/*/bin DLLs inside this venv are discoverable by CTranslate2 on Windows
site_pkgs = Path(sys.prefix) / "Lib" / "site-packages"
nvidia_bins = glob.glob(str(site_pkgs / "nvidia" / "*" / "bin"))
for b in nvidia_bins:
    if os.path.isdir(b):
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(b)
        os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

from fastapi import FastAPI
import uvicorn
from faster_whisper import WhisperModel

TEST_WAV = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b\mario-new-tts\test-1-saludo.wav")
MODEL_CACHE = Path(r"N:\data\models\stt")
state = {"model": None, "port": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(json.dumps({"port": state["port"], "worker": "stt", "device": args.device}), flush=True)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "worker": "stt", "device": args.device, "loaded": state["model"] is not None}


@app.post("/load")
def load_model():
    t0 = time.perf_counter()
    if state["model"] is None:
        MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        dev = "cuda" if args.device == "gpu" else "cpu"
        ctype = "int8_float16" if args.device == "gpu" else "int8"
        state["model"] = WhisperModel(
            "base",
            device=dev,
            compute_type=ctype,
            download_root=str(MODEL_CACHE),
        )
    return {"loaded": True, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/transcribe")
def transcribe():
    if state["model"] is None:
        load_model()
    t0 = time.perf_counter()
    segments, info = state["model"].transcribe(str(TEST_WAV), language="es")
    text = " ".join(s.text.strip() for s in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    state["port"] = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=state["port"], log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[sock]))
