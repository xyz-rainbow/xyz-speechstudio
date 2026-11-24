# TTS

## Ahora

La pestaña Synthesize habla con Qwen3-TTS a través de `qwen_worker.py`.

- El texto ocupa la sección. El selector de modelo deja elegir las variantes Qwen. `xtts-v2` está en el desplegable y desactivado.
- Play escribe un WAV temporal en `data/tmp/` y lo reproduce.
- Save guarda en el historial. Desde ahí se puede volver a guardar eligiendo carpeta, abrir la carpeta y borrar.
- Un perfil aporta el audio de referencia, el texto de referencia y, si ya se calcularon, `.spk` y `.rvq`.
- La pestaña Profiles crea, edita y borra perfiles. Puede transcribir el audio de referencia con el STT de archivos. Al arrancar, el orquestador importa el perfil de Mario si encuentra sus archivos.
- El motor del perfil acepta `qwen` y `xtts`. Solo `qwen` sintetiza.
- `POST /v1/audio/speech` repite la misma síntesis. Queda apagado hasta activar la API local en Ajustes. Ver [endpoints.md](endpoints.md).
- GPU o CPU sale de `tts_device`. En CPU el worker arranca con `CUDA_VISIBLE_DEVICES=""`.
- Si no cabe en VRAM, el supervisor expulsa a otros workers de GPU. Si Live Captions estuviera activo, pide confirmación antes de expulsar el STT.

## Pendiente

- `xtts_worker.py` y `.venvs/xtts`, para que el perfil XTTS y la opción del selector hagan algo.
- El catálogo ya puede descargar el checkpoint de XTTS. Cargarlo no está conectado. Ver [modelos.md](modelos.md).
