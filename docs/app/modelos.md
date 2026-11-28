# Modelos

## Ahora

La pestaña Models separa TTS y STT. En modo `Local`, la vista principal muestra los modelos instalados y las descargas activas. `+` abre Destacados, Explorar Hub e Importar. El catálogo del backend es la fuente de verdad para las capacidades, variantes disponibles e instalación detectada en `data/models/` o la ruta elegida en Ajustes.

Al pulsar `+` se abre `ModelHubModal`, con 3 pestañas paginadas:
- **Destacados**: familias TTS/STT con chips de idioma según `install_mode` (`shared_weights` | `per_language_checkpoint` | `voices_pack`), variante y cuantización. Badge si aún no hay runtime.
- **Explorar Hub** / **Importar**: Hugging Face, URL o carpeta local.

Cada entrada lleva `capabilities` (`install_mode`, `voice_mode`, `quant_policy`, `languages`), `quants`, `installed_quants` e `installed_quant`. Se puede descargar una cuantización adicional sin retirar la anterior. El selector de Featured permite activar una variante compatible y borrarla sin eliminar los ficheros que comparta con otra. La variante activa se guarda como `<model_id>-<quant_id>`; la vista principal conserva esa selección al pulsar Cargar.

Estado de la selección por motor en el árbol de trabajo del 28 de noviembre:

| Id | Motor | Carga |
| --- | --- | --- |
| Qwen3-TTS 1.7B / 0.6B / VoiceDesign | `qwen` | Selección del par talker/tokenizer por cuantización; VoiceDesign (`cstr/qwen3-tts-1.7b-voicedesign-GGUF`) usa CrispASR `--instruct` |
| Chatterbox, IndexTTS, CosyVoice3 | CrispASR | Se pasa el modelo primario y su compañero elegidos; IndexTTS y CosyVoice3 conservan compañeros compartidos al borrar una variante |
| Orpheus y Kokoro | CrispASR | Orpheus (`cstr/orpheus-3b-base-GGUF`) y Kokoro (`cstr/kokoro-82m-GGUF`, F16/Q8_0) en GGUF; ONNX obsoleto ignorado |
| Piper | CrispASR | Unificado a `LocalAI-Community/piper-voices-GGUF` (`medium`/`low`, `quant_policy: "gguf"`); prioridad local antes de caché/HF |
| Fish Speech 1.5 | Python worker | BF16 ejecutable; opciones `int8`/`int4` (`post_quantize`) bloqueadas en catálogo/API hasta soporte de runtime |
| Faster-Whisper | `stt_worker` | INT8, INT8/FP16 y FP16 son modos de cómputo del mismo checkpoint; selector UI y `/api/stt/transcribe` recargan el modo elegido |
| Parakeet / Moonshine | STT ONNX | Sin activación ni promoción falsa: descargables bloqueados hasta soporte de runtime ONNX/CrispASR |
| [GPT-SoVITS](gpt-sovits.md) | Propuesto | Solo diseño arquitectónico; no listado ni instalable |

Al borrar una variante TTS activa, la app selecciona otra instalada si existe y expulsa CrispASR antes de liberar sus ficheros. Al borrar el modelo STT activo, se limpia la selección aunque incluya sufijo de `compute_type`. La variante activa se muestra en la tarjeta de Modelos, los selectores TTS/STT y el resumen de Ajustes.

## Pendiente

1. Validación manual en la app desktop completa (sin Vite) para Chatterbox, IndexTTS y CosyVoice3 en frío con GPU/VRAM limitada y descarga limpia desde cero.
2. Añadir worker Python/CrispASR real para Parakeet ONNX, Moonshine ONNX, F5 no-GGUF y poscuantización INT8/INT4 de Fish antes de habilitarlos en el catálogo.
