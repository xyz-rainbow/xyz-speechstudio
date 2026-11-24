"""Route live caption audio to whichever STT source is selected."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from .config import DEFAULT_TMP_DIR, load_settings
from .downloader import BUILTIN_BY_ID
from .external_providers import transcribe_external
from .supervisor import supervisor

PARTIAL_SECONDS = 1.0
PAUSE_SECONDS = 0.4
MIN_SPEECH_SECONDS = 0.3
SAMPLE_RATE = 16000


def _rms(pcm: bytes) -> float:
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    step = 4 if count > 400 else 1
    total = 0.0
    seen = 0
    for index in range(0, count, step):
        sample = int.from_bytes(pcm[index * 2 : index * 2 + 2], "little", signed=True) / 32768.0
        total += sample * sample
        seen += 1
    return (total / seen) ** 0.5


def _wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    return buf.getvalue()


def _language(value: str) -> Optional[str]:
    text = (value or "").strip()
    if not text or text.lower() == "auto":
        return None
    return text


async def _send(ws: WebSocket, kind: str, text: str) -> None:
    if not text and kind != "error":
        return
    await ws.send_text(json.dumps({"type": kind, "text": text}, ensure_ascii=False))


def _selected_local_is_runnable() -> Optional[str]:
    settings = load_settings()
    if settings.stt_source != "local":
        return None
    entry = BUILTIN_BY_ID.get(settings.active_stt_model)
    if entry and entry.get("kind") == "stt" and not entry.get("runtime_supported", True):
        return (
            f"{entry.get('name', settings.active_stt_model)} is in the catalog, "
            "but this build can only run faster-whisper locally."
        )
    return None


async def _proxy_local(ws: WebSocket) -> None:
    blocked = _selected_local_is_runnable()
    if blocked:
        await _send(ws, "error", blocked)
        return
    try:
        from .main import ensure_stt_loaded

        handle = await asyncio.to_thread(ensure_stt_loaded)
    except Exception as exc:
        await _send(ws, "error", str(exc))
        return
    supervisor.live_captions_active = True
    uri = f"ws://127.0.0.1:{handle.port}/stream"
    try:
        async with websockets.connect(uri, max_size=2**22) as upstream:
            async def client_to_worker() -> None:
                while True:
                    message = await ws.receive()
                    if message.get("type") == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        await upstream.send(message["text"])
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def worker_to_client() -> None:
                async for incoming in upstream:
                    if isinstance(incoming, bytes):
                        await ws.send_bytes(incoming)
                    else:
                        await ws.send_text(incoming)

            done, pending = await asyncio.wait(
                {
                    asyncio.create_task(client_to_worker()),
                    asyncio.create_task(worker_to_client()),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect):
                    await _send(ws, "error", f"STT stream failed: {exc}")
    except Exception as exc:
        await _send(ws, "error", f"STT stream failed: {exc}")


async def _run_endpoint(ws: WebSocket) -> None:
    settings = load_settings()
    ep = next((item for item in settings.external_endpoints if item.id == settings.active_stt_endpoint_id), None)
    if ep is None or ep.kind != "stt":
        await _send(ws, "error", "Select an STT endpoint in Models first.")
        return
    supervisor.live_captions_active = True
    language = "auto"
    pcm = bytearray()
    speech = False
    last_voice = 0.0
    last_partial = 0.0
    loop = asyncio.get_running_loop()

    async def transcribe(kind: str, payload: bytes) -> None:
        if len(payload) < int(SAMPLE_RATE * MIN_SPEECH_SECONDS) * 2:
            return
        wav = _wav_bytes(payload)
        path = DEFAULT_TMP_DIR / "captions-endpoint.wav"
        DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)

        def run() -> str:
            path.write_bytes(wav)
            try:
                return str(transcribe_external(ep, path, _language(language)).get("text") or "").strip()
            finally:
                try:
                    path.unlink()
                except OSError:
                    pass

        try:
            text = await asyncio.to_thread(run)
        except Exception as exc:
            await _send(ws, "error", str(exc))
            return
        await _send(ws, kind, text)

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text"):
                try:
                    body = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if body.get("type") == "start":
                    language = str(body.get("language") or "auto")
                elif body.get("type") == "stop":
                    if speech and pcm:
                        await transcribe("final", bytes(pcm))
                    break
                continue
            chunk = message.get("bytes")
            if not chunk:
                continue
            pcm.extend(chunk)
            now = loop.time()
            if _rms(chunk) >= 0.015:
                speech = True
                last_voice = now
                if last_partial == 0.0:
                    last_partial = now
            if not speech:
                if len(pcm) > SAMPLE_RATE * 2:
                    del pcm[:-SAMPLE_RATE]
                continue
            seconds = len(pcm) / (SAMPLE_RATE * 2)
            if now - last_partial >= PARTIAL_SECONDS and seconds >= MIN_SPEECH_SECONDS:
                last_partial = now
                await transcribe("partial", bytes(pcm))
            elif now - last_voice >= PAUSE_SECONDS and seconds >= MIN_SPEECH_SECONDS:
                await transcribe("final", bytes(pcm))
                pcm.clear()
                speech = False
                last_partial = 0.0
            if len(pcm) > SAMPLE_RATE * 20 * 2:
                del pcm[: SAMPLE_RATE * 5 * 2]
    except WebSocketDisconnect:
        return


async def handle_caption_socket(ws: WebSocket) -> None:
    settings = load_settings()
    try:
        if settings.stt_source == "endpoint":
            await _run_endpoint(ws)
        else:
            await _proxy_local(ws)
    finally:
        supervisor.live_captions_active = False
