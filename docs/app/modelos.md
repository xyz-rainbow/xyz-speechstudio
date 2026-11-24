# Modelos

## Ahora

La pestaña Models separa TTS y STT. Cada grupo tiene expulsión de todos los workers del grupo y expulsión de uno. En modo `Local`, la vista principal muestra **únicamente los modelos ya instalados** (y las descargas activas) junto con el botón `+`. Las tarjetas salen exclusivamente del escaneo dentro de `data/models/` (o la ruta personalizada configurada en Ajustes) y del registro local `custom_models.json` — sin rutas externas hardcodeadas.

Al pulsar `+` se abre `ModelHubModal`, con 3 pestañas paginadas:
- **Destacados**: una tarjeta agrupada por familia (`Qwen3-TTS`, `Coqui XTTS v2`, `Fish Audio`, `F5-TTS` en TTS; `Whisper (CTranslate2)`, `NVIDIA Parakeet v3`, `Moonshine` en STT) con selectores integrados de variante y cuantización.
- **Explorar Hub**: búsqueda en vivo contra Hugging Face con paginación e inspección/selección de archivos antes de descargar.
- **Importar**: descarga desde URL de Hugging Face, ModelScope o enlace directo `.gguf`/`.onnx`, o importación desde una carpeta o archivo local.

Se puede cancelar la descarga, borrar lo instalado e inspeccionar repos o URLs. También se pueden gestionar los modelos desde terminal con `speechstudio --models`, `speechstudio models search`, `speechstudio models download`, `speechstudio models install-url` y `speechstudio models import`. El progreso puede avisar con un toast.

Qué puede cargar el runtime hoy:

| Id | Motor | Carga |
| --- | --- | --- |
| Qwen3-TTS 1.7B Base, 1.7B CustomVoice, 0.6B Base | `qwen` | Sí |
| faster-whisper tiny, base, small, medium, large-v3-turbo | `faster-whisper` | Sí |
| XTTS v2 | `xtts` | Worker, `.venvs/xtts` y pesos en disco. La síntesis real puede seguir en validación. `runtime_supported` sigue en true |
| Fish Audio 1.5 / F5-TTS v1 Base + Spanish / Parakeet TDT 0.6B v3 / Moonshine Base | `fish-audio` / `f5-tts` / `onnx-asr` | No (archivos descargables; worker pendiente). F5 solo ofrece FP16: Q8/GGUF no conviene en flow-matching. ES = variante Spanish, no el base. |

La carpeta de modelos es `data/models/`, o la ruta que se elija en Ajustes.

Antes de cargar, el supervisor mira la VRAM libre. Si el modelo no cabe en la VRAM total detectada, lo rechaza. Si Live Captions está activo, no expulsa el STT sin una confirmación.

## Pendiente

Validar una síntesis real de XTTS (`transformers==4.46.3`, `six`, carga de ref con `soundfile`) y conectar workers para Fish Audio, F5-TTS, Parakeet y Moonshine (`runtime_supported: false`).
