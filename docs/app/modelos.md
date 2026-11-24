# Modelos

## Ahora

La pestaña Models separa TTS y STT. Cada grupo tiene expulsión de todos los workers del grupo y expulsión de uno. En modo `Local`, la vista principal muestra **únicamente los modelos ya instalados** (y las descargas activas) junto con el botón `+`. Las tarjetas salen exclusivamente del escaneo dentro de `data/models/` (o la ruta personalizada configurada en Ajustes) y del registro local `custom_models.json` — sin rutas externas hardcodeadas.

Al pulsar `+` se abre `ModelHubModal`, con 3 pestañas paginadas:
- **Destacados**: familias TTS/STT con chips de idioma según `install_mode` (`shared_weights` | `per_language_checkpoint` | `voices_pack`), variante y cuantización. Badge si aún no hay runtime.
- **Explorar Hub** / **Importar**: Hugging Face, URL o carpeta local.

Cada entrada del catálogo lleva `capabilities` (`install_mode`, `voice_mode`, `quant_policy`, `languages`). Los entornos Python viven en `runtime/envs/` (legacy `.venvs/` se sigue leyendo).

Qué puede cargar el runtime hoy:

| Id | Motor | Carga |
| --- | --- | --- |
| Qwen3-TTS 1.7B / 0.6B | `qwen` | Sí (`qwen_worker`, `runtime/envs/qwen`) |
| faster-whisper * | `faster-whisper` | Sí (`stt_worker`) |
| XTTS v2 | `xtts` | Worker listo; síntesis real puede seguir en validación |
| Piper | `piper` | Sí **si** `runtime/bin/crispasr` está presente (`-m auto`) |
| F5-TTS GGUF F16 | `f5-tts` | Sí con CrispASR; checkpoints por idioma siguen catalog-only |
| Kokoro / eSpeak / Kitten2-mini / Fish | varios | Catálogo + chips; runtime CrispASR/Python pendiente según motor |
| Parakeet / Moonshine | STT | `runtime_supported: false` hasta CrispASR STT |

La carpeta de modelos es `data/models/`, o la ruta de Ajustes. VRAM: el supervisor rechaza si no cabe; Live Captions no se expulsa sin confirmación.

## Pendiente

Validar XTTS de punta a punta; ampliar CrispASR a más TTS/STT; Fish/Kitten2-mini si no hay backend C++.
