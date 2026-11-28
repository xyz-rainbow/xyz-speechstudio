# Live Captions

Los subtítulos usan el STT elegido en Modelos (faster-whisper local, CrispASR STT si hay binario, o endpoint externo).

## Captura por sistema

| SO | Mecanismo | Requisitos | Estado |
| --- | --- | --- | --- |
| **Windows** | WASAPI process loopback (`VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK` + árbol de procesos) → 16 kHz mono s16le | App con audio real | Código listo; sesión real Edge/Discord aún por confirmar en cada máquina |
| **Linux** | `pactl list sink-inputs` + `parec --monitor-stream=<index>` 16 kHz mono | `pulseaudio-utils` / PipeWire | Código listo; sesión PipeWire/Pulse real pendiente |
| **macOS** | `ffmpeg -f avfoundation` sobre dispositivo de **loopback virtual compartido** (p. ej. BlackHole) | BlackHole (o similar) + `ffmpeg` | Código listo; **no** captura por aplicación; el selector ofrece «System loopback» (pid 0) y ventanas solo como contexto UX |

`live_captions_supported` es verdadero en Win/Linux/macOS para que la pestaña muestre errores de captura en vez del aviso genérico de plataforma.

## Flujo

```text
Captura nativa (WASAPI / parec / ffmpeg)
        │
        ▼
Rust  frames 100 ms  (16 kHz mono s16le)
        │  ws://{orquestador}/api/captions/stream
        ▼
orquestador  (stt_source al conectar)
        ├─ local     proxy worker STT  o  CrispASR clip STT
        └─ endpoint  WAV temporal + transcribe_external
        │
        ▼
JSON partial | final | error | status
        │
        ▼
evento Tauri "caption"  →  overlay + pestaña Subtitles
```

### Arranque (anti-carrera)

1. UI prepara STT / overlay.
2. Llama `start_live_captions` (hilo nativo).
3. **No** marca `running` ni `captions/lock` hasta recibir `{"type":"status","text":"started"}` (emitido tras WASAPI/`parec`/`ffmpeg` + WebSocket `start`).
4. Si llega `error` o timeout (~12 s), UI limpia, para captura y no deja la sesión “activa”.

### Partial vs final

| Tipo | Cuándo | UI |
| --- | --- | --- |
| `partial` | ~1 s con voz (RMS) | Línea viva; overlay en itálica |
| `final` | ~400 ms de pausa tras ≥0.3 s de voz | Historial (sin duplicar consecutivos); overlay sólido |
| `error` | fallo captura/STT | Toast / texto error; `running=false` |
| `status` | `started` | Solo lifecycle UI |

Silencio: no emite partial/final. Parar: `stop_live_captions` + `captions/lock=false`. Cambiar fuente/STT: solo aplica en la **siguiente** sesión.

## Comprobado en código (2026-11-28)

- Race UI: `SubtitlesView` espera `status=started` antes de `setRunning(true)`.
- Emit `started` en `audio_capture/{windows,linux,macos}.rs` tras el `start` del socket.
- Overlay distingue partial / final / error.
- `pytest tests/test_captions_helpers.py` (RMS/WAV/idioma).
- Sesión con audio real: **no** verificada en este agente (Windows/Linux/macOS desktop).

## Pendiente

- Sesión real Windows (Edge/Discord) y Linux PipeWire.
- macOS con BlackHole instalado.
- Parakeet/Moonshine en vivo cuando el runtime CrispASR STT esté completo.
