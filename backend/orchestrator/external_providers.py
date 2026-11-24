from __future__ import annotations

import subprocess
import time
import wave
from pathlib import Path
from typing import Literal, Optional

import httpx
from pydantic import BaseModel


class ExternalEndpointConfig(BaseModel):
    id: str
    name: str
    kind: Literal["tts", "stt"]
    protocol: Literal["openai", "elevenlabs", "deepgram"]
    base_url: str
    api_key: str = ""
    model: str
    voice: str = ""


def default_external_endpoints() -> list[ExternalEndpointConfig]:
    return [
        ExternalEndpointConfig(
            id="groq-stt",
            name="Groq Whisper Turbo",
            kind="stt",
            protocol="openai",
            base_url="https://api.groq.com/openai/v1",
            api_key="",
            model="whisper-large-v3-turbo",
            voice="",
        ),
        ExternalEndpointConfig(
            id="openai-stt",
            name="OpenAI Whisper",
            kind="stt",
            protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="",
            model="whisper-1",
            voice="",
        ),
        ExternalEndpointConfig(
            id="deepgram-stt",
            name="Deepgram Nova-3",
            kind="stt",
            protocol="deepgram",
            base_url="https://api.deepgram.com/v1",
            api_key="",
            model="nova-3",
            voice="",
        ),
        ExternalEndpointConfig(
            id="custom-stt",
            name="Custom STT API",
            kind="stt",
            protocol="openai",
            base_url="http://127.0.0.1:8000/v1",
            api_key="",
            model="whisper-1",
            voice="",
        ),
        ExternalEndpointConfig(
            id="openai-tts",
            name="OpenAI TTS",
            kind="tts",
            protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="",
            model="gpt-4o-mini-tts",
            voice="alloy",
        ),
        ExternalEndpointConfig(
            id="elevenlabs-tts",
            name="ElevenLabs",
            kind="tts",
            protocol="elevenlabs",
            base_url="https://api.elevenlabs.io/v1",
            api_key="",
            model="eleven_multilingual_v2",
            voice="21m00Tcm4TlvDq8ikWAM",
        ),
        ExternalEndpointConfig(
            id="custom-tts",
            name="Custom TTS API",
            kind="tts",
            protocol="openai",
            base_url="http://127.0.0.1:8000/v1",
            api_key="",
            model="tts-1",
            voice="default",
        ),
    ]


def _transcode_to_wav(raw_bytes: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_bytes[:4] == b"RIFF":
        out_path.write_bytes(raw_bytes)
        return
    tmp_src = out_path.with_suffix(".src_audio")
    tmp_src.write_bytes(raw_bytes)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(tmp_src), "-ar", "24000", "-ac", "1", str(out_path)],
            check=True,
            creationflags=creationflags,
        )
    finally:
        tmp_src.unlink(missing_ok=True)


def synthesize_external(
    ep: ExternalEndpointConfig,
    text: str,
    language: Optional[str],
    out_path: Path,
) -> dict:
    base = ep.base_url.rstrip("/")
    t0 = time.perf_counter()

    with httpx.Client(timeout=120.0) as client:
        if ep.protocol == "elevenlabs":
            voice_id = (ep.voice or "21m00Tcm4TlvDq8ikWAM").strip()
            headers = {"Accept": "audio/mpeg", "Content-Type": "application/json"}
            if ep.api_key.strip():
                headers["xi-api-key"] = ep.api_key.strip()
            resp = client.post(
                f"{base}/text-to-speech/{voice_id}",
                headers=headers,
                json={"text": text, "model_id": ep.model},
            )
            resp.raise_for_status()
            _transcode_to_wav(resp.content, out_path)
        else:
            headers = {"Content-Type": "application/json"}
            if ep.api_key.strip():
                headers["Authorization"] = f"Bearer {ep.api_key.strip()}"
            payload = {
                "model": ep.model,
                "input": text,
                "voice": ep.voice or "alloy",
                "response_format": "wav",
            }
            resp = client.post(f"{base}/audio/speech", headers=headers, json=payload)
            resp.raise_for_status()
            _transcode_to_wav(resp.content, out_path)

    elapsed = time.perf_counter() - t0
    with wave.open(str(out_path), "rb") as wf:
        sr = wf.getframerate()
        dur = wf.getnframes() / float(sr) if sr > 0 else 0.0
    rtf = (elapsed / dur) if dur > 0 else 0.0
    return {
        "out_path": str(out_path),
        "duration_s": round(dur, 3),
        "sr": sr,
        "elapsed_s": round(elapsed, 3),
        "rtf": round(rtf, 3),
    }


def transcribe_external(
    ep: ExternalEndpointConfig,
    audio_path: Path,
    language: Optional[str] = None,
) -> dict:
    base = ep.base_url.rstrip("/")
    lang = language.strip() if language and language.strip() and language.lower() != "auto" else None
    t0 = time.perf_counter()

    with httpx.Client(timeout=180.0) as client:
        if ep.protocol == "deepgram":
            params = {"model": ep.model, "smart_format": "true"}
            if lang:
                params["language"] = lang
            headers = {"Content-Type": "audio/wav"}
            if ep.api_key.strip():
                headers["Authorization"] = f"Token {ep.api_key.strip()}"
            resp = client.post(
                f"{base}/listen",
                params=params,
                headers=headers,
                content=audio_path.read_bytes(),
            )
            resp.raise_for_status()
            data = resp.json()
            alt = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
            text = (alt.get("transcript") or "").strip()
            elapsed = time.perf_counter() - t0
            return {
                "text": text,
                "language": lang or "auto",
                "duration_s": round(float(data.get("metadata", {}).get("duration", 0.0)), 2),
                "elapsed_s": round(elapsed, 3),
                "segments": [{"start": 0.0, "end": 0.0, "text": text}] if text else [],
            }

        headers = {}
        if ep.api_key.strip():
            headers["Authorization"] = f"Bearer {ep.api_key.strip()}"
        form_data = {"model": ep.model, "response_format": "verbose_json"}
        if lang:
            form_data["language"] = lang
        with open(audio_path, "rb") as fh:
            resp = client.post(
                f"{base}/audio/transcriptions",
                headers=headers,
                data=form_data,
                files={"file": (audio_path.name, fh, "application/octet-stream")},
            )
        if resp.status_code == 400 and "response_format" in resp.text:
            form_data["response_format"] = "json"
            with open(audio_path, "rb") as fh:
                resp = client.post(
                    f"{base}/audio/transcriptions",
                    headers=headers,
                    data=form_data,
                    files={"file": (audio_path.name, fh, "application/octet-stream")},
                )
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.perf_counter() - t0
        raw_segs = data.get("segments") or []
        segments = [
            {
                "start": round(float(s.get("start", 0.0)), 2),
                "end": round(float(s.get("end", 0.0)), 2),
                "text": str(s.get("text", "")).strip(),
            }
            for s in raw_segs
            if str(s.get("text", "")).strip()
        ]
        text = (data.get("text") or "").strip()
        if not segments and text:
            segments = [{"start": 0.0, "end": 0.0, "text": text}]
        return {
            "text": text,
            "language": data.get("language") or (lang or "auto"),
            "duration_s": round(float(data.get("duration", 0.0)), 2),
            "elapsed_s": round(elapsed, 3),
            "segments": segments,
        }


def test_external_endpoint(ep: ExternalEndpointConfig) -> dict:
    base = ep.base_url.rstrip("/")
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=12.0) as client:
            if ep.protocol == "elevenlabs":
                headers = {"xi-api-key": ep.api_key.strip()} if ep.api_key.strip() else {}
                resp = client.get(f"{base}/user", headers=headers)
            elif ep.protocol == "deepgram":
                headers = {"Authorization": f"Token {ep.api_key.strip()}"} if ep.api_key.strip() else {}
                resp = client.get(f"{base}/projects", headers=headers)
            else:
                headers = {"Authorization": f"Bearer {ep.api_key.strip()}"} if ep.api_key.strip() else {}
                resp = client.get(f"{base}/models", headers=headers)
        ms = round((time.perf_counter() - t0) * 1000)
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "latency_ms": ms,
            "detail": "OK" if resp.status_code < 400 else resp.text[:220],
        }
    except Exception as exc:
        ms = round((time.perf_counter() - t0) * 1000)
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": ms,
            "detail": str(exc)[:220],
        }
