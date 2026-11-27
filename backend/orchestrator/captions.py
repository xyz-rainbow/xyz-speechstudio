"""Route live caption audio to whichever STT source is selected."""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from . import crispasr, downloader
from .config import APP_ROOT, DEFAULT_TMP_DIR, load_settings
from .external_providers import transcribe_external

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
    entry = downloader.BUILTIN_BY_ID.get(settings.active_stt_model)
    if entry and entry.get("kind") == "stt" and not entry.get("runtime_supported", True):
        return (
            f"{entry.get('name', settings.active_stt_model)} is in the catalog, "
            "but this build cannot run it locally."
        )
    return None


async def _proxy_local(ws: WebSocket, supervisor_inst=None) -> None:
    if supervisor_inst is None:
        from .main import supervisor as supervisor_inst
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
    supervisor_inst.live_captions_active = True
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


async def _run_endpoint(ws: WebSocket, supervisor_inst=None) -> None:
    if supervisor_inst is None:
        from .main import supervisor as supervisor_inst
    settings = load_settings()
    ep = next((item for item in settings.external_endpoints if item.id == settings.active_stt_endpoint_id), None)
    if ep is None or ep.kind != "stt":
        await _send(ws, "error", "Select an STT endpoint in Models first.")
        return
    supervisor_inst.live_captions_active = True
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


async def _run_crispasr_local(
    ws: WebSocket,
    *,
    model_id: str,
    model_dir: Optional[Path],
    device: str,
    supervisor_inst=None,
) -> None:
    """Stream incoming 16 kHz mono PCM frames into CrispASR STT without blocking WS drain."""
    if supervisor_inst is None:
        from .main import supervisor as supervisor_inst
    supervisor_inst.live_captions_active = True
    language = "auto"
    pcm = bytearray()
    speech = False
    last_voice = 0.0
    last_partial = 0.0
    loop = asyncio.get_running_loop()
    transcribe_lock = asyncio.Lock()
    inflight: set[asyncio.Task] = set()

    async def run_clip(kind: str, payload: bytes) -> None:
        if len(payload) < int(SAMPLE_RATE * 0.35) * 2:
            return
        async with transcribe_lock:
            wav = _wav_bytes(payload)
            DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(tempfile.gettempdir()) / f"ss_cap_{uuid.uuid4().hex[:10]}.wav"

            def _exec() -> str:
                tmp_path.write_bytes(wav)
                try:
                    res = crispasr.transcribe_stt(
                        model_id=model_id,
                        audio_path=tmp_path,
                        model_dir=model_dir,
                        language=language,
                        device="cpu" if device == "cpu" else "gpu",
                        app_root=APP_ROOT,
                    )
                    return str(res.get("text") or "").strip()
                finally:
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

            try:
                text = await asyncio.to_thread(_exec)
                if text:
                    await _send(ws, kind, text)
            except WebSocketDisconnect:
                return
            except Exception as exc:
                try:
                    await _send(ws, "error", str(exc))
                except Exception:
                    pass

    def schedule_clip(kind: str, payload: bytes) -> None:
        task = asyncio.create_task(run_clip(kind, payload))
        inflight.add(task)
        task.add_done_callback(inflight.discard)

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
                        await run_clip("final", bytes(pcm))
                    if inflight:
                        await asyncio.gather(*list(inflight), return_exceptions=True)
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    break
                continue
            chunk = message.get("bytes")
            if not chunk:
                continue
            pcm.extend(chunk)
            now = loop.time()
            if _rms(chunk) >= 0.008:
                speech = True
                last_voice = now
                if last_partial == 0.0:
                    last_partial = now
            if not speech:
                if len(pcm) > SAMPLE_RATE * 2:
                    del pcm[:-SAMPLE_RATE]
                continue
            seconds = len(pcm) / (SAMPLE_RATE * 2)
            if now - last_partial >= 1.2 and seconds >= 0.35 and not transcribe_lock.locked():
                last_partial = now
                schedule_clip("partial", bytes(pcm))
            elif now - last_voice >= 0.55 and seconds >= 0.35:
                snapshot = bytes(pcm)
                pcm.clear()
                speech = False
                last_partial = 0.0
                schedule_clip("final", snapshot)
            if len(pcm) > SAMPLE_RATE * 20 * 2:
                del pcm[: SAMPLE_RATE * 5 * 2]
    except WebSocketDisconnect:
        return
    finally:
        for task in list(inflight):
            if not task.done():
                task.cancel()


async def handle_caption_socket(
    ws: WebSocket,
    model_id: Optional[str] = None,
    supervisor_inst=None,
) -> None:
    if supervisor_inst is None:
        from .main import supervisor as supervisor_inst
    settings = load_settings()
    try:
        if settings.stt_source == "endpoint":
            await _run_endpoint(ws, supervisor_inst=supervisor_inst)
        else:
            installed_stt = [m for m in downloader.build_catalog(settings) if m.kind == "stt" and m.installed]
            target = (model_id or settings.active_stt_model or "").strip()
            entry = next((m for m in installed_stt if m.id == target), None)
            if entry is None and installed_stt:
                entry = installed_stt[0]
            if entry is not None and crispasr.is_available() and crispasr.stt_backend_for_model(entry.id):
                await _run_crispasr_local(
                    ws,
                    model_id=entry.id,
                    model_dir=Path(entry.install_dir) if entry.install_dir else None,
                    device=settings.stt_device,
                    supervisor_inst=supervisor_inst,
                )
            else:
                await _proxy_local(ws, supervisor_inst=supervisor_inst)
    finally:
        supervisor_inst.live_captions_active = False
