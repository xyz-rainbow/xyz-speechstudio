# Modelos

## Ahora

La pestaña Models separa TTS y STT. Cada grupo tiene expulsión de todos los workers del grupo y expulsión de uno. Las tarjetas salen del catálogo de `backend/orchestrator/downloader.py` más los modelos propios guardados en el registro local.

Se puede descargar una cuantización, cancelar la descarga, borrar lo instalado e inspeccionar un repo de Hugging Face por id o URL. El progreso puede avisar con un toast.

Qué puede cargar el runtime hoy:

| Id | Motor | Carga |
| --- | --- | --- |
| Qwen3-TTS 1.7B Base y CustomVoice | `qwen` | Sí |
| faster-whisper tiny, base, small, medium, large-v3-turbo | `faster-whisper` | Sí |
| XTTS v2 | `xtts` | Sí, si el checkpoint y `.venvs/xtts` existen. El entorno no se ha creado |
| Parakeet TDT 0.6B v3 | `onnx-asr` | No |
| Moonshine Base | `onnx-asr` | No |

La carpeta de modelos es `data/models/`, o la ruta que se elija en Ajustes. También se puede apuntar a un GGUF que ya exista, como `Z:\[🤖] [Models]\tts\qwen3-1.7b`.

Antes de cargar, el supervisor mira la VRAM libre. Si el modelo no cabe en la VRAM total detectada, lo rechaza. Si Live Captions está activo, no expulsa el STT sin una confirmación.

## Pendiente

Crear `.venvs/xtts` y descargar el checkpoint de XTTS. Parakeet y Moonshine siguen sin worker: sus tarjetas pueden descargarse y no entran en GPU.
