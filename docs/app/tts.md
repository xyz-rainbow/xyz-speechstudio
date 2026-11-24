# TTS

## Ahora

Synthesize elige motor según el modelo activo y su contrato `capabilities` (`install_mode`, `voice_mode`, `languages`).

- **Clone profiles** (`qwen`, `xtts`): perfiles de voz + idiomas del motor. Qwen vía `qwen_worker.py` (`.spk`/`.rvq`); XTTS vía `xtts_worker.py` (wav de referencia).
- **Built-in voices** (`piper`, `kokoro`, …): sin selector de perfil; CTA “Instalar en Modelos” si falta pack/runtime. Idiomas = `capabilities ∩ ready` (`installed_languages` / checkpoint). Papelera opcional para quitar un pack de idioma.
- **CrispASR** (preferido): si existe `runtime/bin/crispasr(.exe)` o `CRISPASR_BIN`, Piper y F5 GGUF F16 sintetizan por CLI (`--backend piper|f5-tts`). Ver [runtime/bin/README.md](../../runtime/bin/README.md) y `scripts/fetch-crispasr.ps1`.
- El desplegable Glass agrupa `Local` (instalados) y `Externo` (endpoints). Play → WAV temporal; Save → historial.
- `POST /v1/audio/speech` repite la misma síntesis (API local en Ajustes). Ver [endpoints.md](endpoints.md).
- GPU/CPU: `tts_device`. El supervisor puede expulsar workers; Live Captions pide confirmación.

## Acordado

- Runtime preferido: [CrispASR](https://github.com/CrispStrobe/CrispASR) para backends C++. Python en `runtime/envs/` solo donde CrispASR no cubre (XTTS, Fish tooling, Kitten2-mini si hace falta).
- Los pesos de XTTS no van en el repo (Coqui Public Model License).

## Pendiente

- Validar síntesis real XTTS; migrar más STT/TTS a CrispASR; Kokoro cuando haya GGUF de voz en disco. Ver [modelos.md](modelos.md).
