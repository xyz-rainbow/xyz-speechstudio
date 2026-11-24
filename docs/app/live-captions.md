# Live Captions

Los subtítulos usan el STT que esté elegido en Modelos: un faster-whisper local o un endpoint externo. En Windows la captura WASAPI está en el código. En Linux el listado sale de `pactl list sink-inputs` y el audio de `parec --monitor-stream` a 16 kHz mono s16le, con el mismo socket de 100 ms. Ninguna de las dos sesiones se ha oído con audio real.

## Ahora

La pestaña Subtitles lista las ventanas abiertas (también WhatsApp, aunque su ventana WinUI esté oculta en la bandeja) y, además, los procesos que ya tienen sesión de audio. El historial de esa sesión se corta en `captions_max_history` (5–200, por defecto 20).

Rust abre el loopback del árbol de procesos (`PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE`), pasa el mix a 16 kHz mono s16le y manda un frame binario cada 100 ms. El cliente siempre entra por el orquestador:

```text
WASAPI Process Loopback
        │
        ▼
Rust  resample 16 kHz mono s16le
        │  ws://{orquestador}/api/captions/stream
        ▼
orquestador  lee stt_source al conectar
        ├─ local     proxy a ws://127.0.0.1:{stt}/stream
        └─ endpoint  WAV temporal + transcribe_external
        │
        ▼
JSON partial | final | error
        │
        ▼
evento Tauri "caption"  →  overlay y pestaña Subtitles
```

En local, el orquestador carga el modelo activo con `ensure_stt_loaded` (el tamaño elegido, o un directorio Hugging Face que ya tenga `model.bin`) y reenvía el socket. Parakeet y Moonshine siguen en el catálogo con `runtime_supported: false`: el socket responde un error y no cambia a whisper por debajo.

En endpoint, el mismo PCM se junta en ventanas. Cada ventana se escribe como WAV y pasa por `transcribe_external`: OpenAI-compatible (`/audio/transcriptions`) o Deepgram (`/listen`). El archivo es `data/tmp/captions-endpoint.wav` y se borra al terminar la llamada.

Tiempos, en los dos caminos:

1. **Línea viva.** Con voz (RMS cerca de 0.015), cada segundo sale un `partial` y sustituye la frase en pantalla.
2. **Frase cerrada.** Tras unos 400 ms de pausa, y al menos 0.3 s de voz, sale un `final`. El overlay se queda con esa frase. La pestaña la añade al historial y vacía la línea viva.

El worker local usa faster-whisper con `beam_size` 1, `vad_filter`, `condition_on_previous_text` falso y `without_timestamps`. El idioma del mensaje `start` es `auto` salvo que el JSON traiga otro. `POST /transcribe` sigue siendo el de archivos.

`POST /api/captions/lock` marca `live_captions_active` mientras la captura está abierta. Al cerrar el socket el orquestador lo apaga. Salir de la app para la captura.

El overlay (`index.html#/overlay`) escucha el mismo evento. En reposo muestra "—". Se puede fijar, cambiar opacidad y cambiar el tamaño de letra.

Comprobado en esta pasada: `cargo check` del crate Tauri, `tsc --noEmit` del frontend y `py_compile` de `captions.py` y `stt_worker.py`. `websockets` 17.4 ya está en `.venvs/core` y `.venvs/stt`.

## Acordado

El STT de los subtítulos es el de Modelos en el momento de pulsar Iniciar. Cambiar de modelo o de endpoint vale para la siguiente sesión, no a mitad de una.

Un frame de 100 ms son 3200 bytes. El worker local no escribe un WAV. El endpoint sí, porque esas APIs reciben un archivo.

## Acordado

En Linux cada sink-input es una fila. Si un proceso tiene varios, el nombre lleva ` #` y el índice. Al iniciar se captura ese índice si sigue perteneciendo al mismo pid; no se cambia a otro stream del mismo proceso. Parar manda SIGTERM en cuanto el pid de `parec` existe, también si el paro llegó antes de publicarlo. Si faltan `pactl` o `parec`, el error lo dice. macOS sigue sin captura. `live_captions_supported` es verdadero en Linux para que la pestaña muestre ese error en vez del aviso de plataforma. Una sesión PipeWire o PulseAudio no se ha oído.

## Pendiente

- Una sesión real en Windows (Edge, Discord u otra app) que confirme que el PCM no llega en silencio y que el texto aparece en el overlay.
- Una sesión real en Linux con PipeWire o PulseAudio. Desde esta máquina no se ha lanzado `parec`.
- Parakeet y Moonshine no transcriben en vivo hasta que tengan runtime.
