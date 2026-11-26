"""KittenTTS 2 Mini isolated ONNX worker (multilingual, CPU/ONNX Runtime)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import tempfile
import time
import urllib.request
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

HF_REPO_RAW = "https://huggingface.co/KittenML/kitten-tts-2-mini/resolve/main"

ESPEAK_LANG_MAP: dict[str, str] = {
    "es": "es",
    "spanish": "es",
    "en": "en-us",
    "english": "en-us",
    "de": "de",
    "german": "de",
    "fr": "fr-fr",
    "french": "fr-fr",
    "it": "it",
    "italian": "it",
    "pt": "pt-br",
    "portuguese": "pt-br",
    "ru": "ru",
    "russian": "ru",
    "hi": "hi",
    "hindi": "hi",
    "da": "da",
    "fi": "fi",
    "ja": "ja",
    "ko": "ko",
    "nl": "nl",
    "sv": "sv",
    "sw": "sw",
    "tr": "tr",
}

VOICES_BY_LANG: dict[str, list[str]] = {
    "es": ["lucia", "carmen", "javier", "diego", "eleanor", "martha", "serena", "iris", "grace", "edith", "diana", "otis", "vincent"],
    "en": ["eleanor", "martha", "serena", "iris", "grace", "edith", "diana", "otis", "vincent", "max", "danny"],
    "de": ["lena", "greta", "jonas", "felix", "eleanor", "martha", "serena", "iris"],
    "fr": ["camille", "chloe", "manon", "louis", "antoine", "julien", "mathis", "etienne"],
    "it": ["chiara", "giulia", "matteo", "lorenzo", "eleanor", "martha"],
    "pt": ["beatriz", "camila", "rafael", "thiago", "eleanor", "martha"],
    "ru": ["anastasia", "elena", "dmitri", "ivan", "eleanor", "martha"],
    "nl": ["sanne", "fenna", "daan", "bram", "joris"],
    "tr": ["elif", "zeynep"],
}

DEFAULT_VOICES = VOICES_BY_LANG["es"]

state: dict = {
    "session": None,
    "vocab": None,
    "voice_packs": {},
    "phonemizers": {},
    "model_dir": "",
    "port": 0,
    "pid": os.getpid(),
}


class LoadRequest(BaseModel):
    model_dir: str


class SynthRequest(BaseModel):
    text: str
    lang: str = "Spanish"
    voice: Optional[str] = None
    out_path: str
    speed: float = 1.0


def _lang_iso(lang: Optional[str]) -> str:
    raw = (lang or "es").strip().lower()
    if raw in ESPEAK_LANG_MAP:
        mapped = ESPEAK_LANG_MAP[raw]
        return "en" if mapped.startswith("en") else mapped.split("-")[0]
    return raw[:2] if len(raw) >= 2 else "en"


def _ensure_espeak_ascii() -> None:
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    ascii_dir = Path(tempfile.gettempdir()) / "ss_espeak_ng"
    ascii_data = ascii_dir / "espeak-ng-data"
    if not (ascii_data / "phontab").is_file():
        shutil.copytree(espeakng_loader.get_data_path(), ascii_data, dirs_exist_ok=True)
    src_lib = Path(espeakng_loader.get_library_path())
    ascii_lib = ascii_dir / src_lib.name
    if not ascii_lib.is_file():
        ascii_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_lib, ascii_lib)
    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = str(ascii_lib)
    os.environ["PHONEMIZER_ESPEAK_DATA_PATH"] = str(ascii_data)
    EspeakWrapper.set_library(str(ascii_lib))
    EspeakWrapper.set_data_path(str(ascii_data))


def _ensure_asset(model_dir: Path, filename: str) -> Path:
    dest = model_dir / filename
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF_REPO_RAW}/{filename}"
    tmp = dest.with_name(dest.name + ".part")
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
        tmp.write_bytes(data)
        tmp.replace(dest)
        return dest
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Failed downloading KittenTTS asset {filename}: {exc}") from exc


def _get_voice_pack(model_dir: Path, iso: str):
    import numpy as np

    key = f"voices_{iso}.npz"
    if key in state["voice_packs"]:
        return state["voice_packs"][key]
    try:
        npz_path = _ensure_asset(model_dir, key)
    except Exception:
        npz_path = _ensure_asset(model_dir, "voices_en.npz")
    pack = np.load(str(npz_path))
    state["voice_packs"][key] = pack
    return pack


def _get_phonemizer(iso: str):
    from phonemizer.backend import EspeakBackend

    if iso not in state["phonemizers"]:
        espeak_code = ESPEAK_LANG_MAP.get(iso, iso)
        state["phonemizers"][iso] = EspeakBackend(
            language=espeak_code,
            preserve_punctuation=True,
            with_stress=True,
        )
    return state["phonemizers"][iso]


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
    state["session"] = None
    state["voice_packs"].clear()
    state["phonemizers"].clear()


app = FastAPI(title="KittenTTS Worker", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "worker": "kitten",
        "device": args.device,
        "pid": state["pid"],
        "loaded": state["session"] is not None,
        "model_dir": state["model_dir"],
    }


@app.post("/load")
def load_model(req: LoadRequest):
    t0 = time.perf_counter()
    model_dir = Path(req.model_dir)
    if state["session"] is not None and state["model_dir"] == str(model_dir):
        return {"loaded": True, "cached": True, "elapsed_s": 0.0}

    try:
        import onnxruntime as ort

        _ensure_espeak_ascii()
        vocab_path = _ensure_asset(model_dir, "vocab.json")
        vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
        onnxs = sorted(model_dir.rglob("*.onnx"))
        if not onnxs:
            onnx_path = _ensure_asset(model_dir, "kitten_tts_2_mini.onnx")
        else:
            onnx_path = onnxs[0]

        state["session"] = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        state["vocab"] = vocab
        state["model_dir"] = str(model_dir)
        state["voice_packs"].clear()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KittenTTS load failed: {exc}") from exc

    return {"loaded": True, "cached": False, "elapsed_s": round(time.perf_counter() - t0, 3)}


@app.post("/synthesize")
def synthesize(req: SynthRequest):
    import numpy as np

    sess = state["session"]
    vocab = state["vocab"]
    if sess is None or vocab is None:
        raise HTTPException(status_code=400, detail="KittenTTS model is not loaded yet.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Input text is empty.")

    iso = _lang_iso(req.lang)
    model_dir = Path(state["model_dir"])
    t0 = time.perf_counter()
    try:
        pack = _get_voice_pack(model_dir, iso)
        keys = list(pack.keys())
        req_voice = (req.voice or "").strip().lower()
        chosen = req_voice if req_voice in keys else keys[0]
        ref_s = pack[chosen]

        phonemizer = _get_phonemizer(iso)
        phonemes = phonemizer.phonemize([text])[0].strip()
        ids = [0] + [int(vocab[ch]) for ch in phonemes if ch in vocab] + [0]
        if len(ids) <= 2:
            raise RuntimeError(f"Could not phonemize input for language '{iso}'.")

        style = (
            ref_s[min(len(ids), ref_s.shape[0] - 1)][None, :].astype(np.float32)
            if ref_s.ndim == 2
            else ref_s.reshape(1, -1).astype(np.float32)
        )
        audio = sess.run(
            None,
            {
                "input_ids": np.array([ids], dtype=np.int64),
                "style": style,
                "speed": np.array([float(req.speed or 1.0)], dtype=np.float32),
            },
        )[0].squeeze()
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
        "voice": chosen,
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
