import argparse
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

if args.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

from fastapi import FastAPI
import uvicorn
from qwentts_cpp import QwenTTS

MODEL_DIR = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b")
TALKER_GGUF = MODEL_DIR / "qwen-talker-1.7b-base-Q8_0.gguf"
CODEC_GGUF = MODEL_DIR / "qwen-tokenizer-12hz-Q8_0.gguf"
MARIO_DIR = MODEL_DIR / "mario-new-tts"
SPK_PATH = MARIO_DIR / "mario.spk"
RVQ_PATH = MARIO_DIR / "mario.rvq"
REF_TXT_PATH = MARIO_DIR / "mario-new-tts.txt"

state = {"tts": None, "vref": None, "ref_text": None, "port": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(json.dumps({"port": state["port"], "worker": "qwen", "device": args.device}), flush=True)
    yield
    if state["tts"] is not None:
        state["tts"].close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "worker": "qwen", "device": args.device, "loaded": state["tts"] is not None}


@app.post("/load")
def load_model():
    t0 = time.perf_counter()
    if state["tts"] is None:
        tts = QwenTTS(TALKER_GGUF, CODEC_GGUF)
        vref = tts.load_voice_ref(SPK_PATH, RVQ_PATH)
        ref_text = REF_TXT_PATH.read_text(encoding="utf-8").strip()
        state["tts"] = tts
        state["vref"] = vref
        state["ref_text"] = ref_text
    return {"loaded": True, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synth")
def synth():
    if state["tts"] is None:
        load_model()
    t0 = time.perf_counter()
    tts = state["tts"]
    vref = state["vref"]
    audio, sr = tts.synthesize(
        text="Prueba de fase cero completada.",
        lang="spanish",
        ref_spk_emb=vref.ref_spk_emb,
        ref_codes=vref.ref_codes,
        ref_text=state["ref_text"],
        seed=42,
    )
    elapsed = time.perf_counter() - t0
    dur = len(audio) / float(sr)
    return {"duration_s": round(dur, 3), "sr": sr, "elapsed_s": round(elapsed, 3)}


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    state["port"] = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=state["port"], log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    import asyncio
    asyncio.run(server.serve(sockets=[sock]))
