# TTS

## Ahora

Synthesize elige motor según el modelo activo y su contrato `capabilities` (`install_mode`, `voice_mode`, `languages`). El ID activo puede incluir una cuantización instalada, que se resuelve al cargar los pesos.

- **Clone profiles** (`qwen`, `xtts`, motores CrispASR compatibles): perfiles de voz + idiomas del motor. El audio original (`ref_original_path`) y la transcripción original (`ref_original_text`) se conservan intactos; al recortar a 12 s se alinea `ref_text` por frontera de palabra y se restaura ambos al pulsar «Restaurar audio original».
- **Qwen VoiceDesign & xyz-Ioquendo**: `VoiceDesignModal` permite diseñar una voz con `--instruct` en `qwen3-1.7b-voicedesign`, escuchar la muestra y guardarla en Perfiles para clonar con Qwen Base Q4/Q8. El pack `xyz-ioquendo` provee referencias internas no editables (`pack:xyz-ioquendo/...`) filtradas por locale y desacopladas de los pesos Qwen.
- **Built-in voices** (`piper`, `kokoro`, `espeak`, `sapi5`, `kitten`): Piper y Kokoro operan unificados en GGUF sobre CrispASR; KittenTTS distingue `.onnx` INT8 e INT4 al cargar. Idiomas = `capabilities ∩ ready`.
- **CrispASR** (preferido): servidor persistente para los backends compatibles; cuando `qwen3-tts` usa `VoiceDesign --instruct` se invoca el CLI cancelable.
- El desplegable Glass agrupa `Local` (mostrando variantes instaladas) y `Externo`. Cambiar de texto, voz o modelo aborta cualquier sesión por tramos anterior, incrementa el token de generación y evita mezcla de chunks o fugas de estado.
- `POST /v1/audio/speech` repite la misma síntesis (API local en Ajustes). Ver [endpoints.md](endpoints.md).
- GPU/CPU: `tts_device`. El supervisor puede expulsar workers; Live Captions pide confirmación.

## Acordado

- Runtime preferido: [CrispASR](https://github.com/CrispStrobe/CrispASR) para backends C++. Python en `runtime/envs/` solo donde CrispASR no cubre (XTTS, Fish, F5 no-GGUF, Kitten, o futuro [GPT-SoVITS](gpt-sovits.md)).
- Los pesos de XTTS no van en el repo (Coqui Public Model License).

## Pendiente

- Prueba interactiva prolongada en WebView de escritorio (Tauri empaquetado sin Vite) cubriendo pausa/reanudación con Kokoro y latencia GPU fría vs caliente en varios idiomas.
