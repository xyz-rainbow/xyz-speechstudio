# STT de archivos

## Ahora

`stt_worker.py` carga faster-whisper y expone:

- `POST /load` con `model_size` y `compute_type`.
- `POST /transcribe` con la ruta de un archivo de audio. Devuelve el texto cuando el archivo entero ha terminado.
- `WebSocket /stream` para PCM 16 kHz mono. Lo usa Live Captions con el modelo que `/load` ya dejó cargado.

El VAD es el de faster-whisper (`vad_filter`, Silero). No hay un segundo motor dentro del worker.

La pestaña Transcriber elige el modelo cargado, manda un archivo y muestra el texto. Profiles usa la misma ruta para rellenar el texto de referencia.

Tamaños que el runtime acepta: `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, en `int8`, `int8_float16` o `float16`. GPU o CPU sale de `stt_device`.

`POST /v1/audio/transcriptions` hace lo mismo para un cliente externo, con la API local apagada por defecto.

## Pendiente

Parakeet y Moonshine están en el catálogo con `runtime_supported: false`. El worker no los carga.

El camino en vivo local no usa `/transcribe`. El detalle, incluido el endpoint externo, está en [live-captions.md](live-captions.md).
