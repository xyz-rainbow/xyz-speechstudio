# TTS

## Ahora

La pestaña Synthesize habla con Qwen3-TTS a través de `qwen_worker.py`.

- El texto arranca vacío (`""`) sin placeholder ni texto precargado. El selector desplegable Glass agrupa `Local` (exclusivamente los modelos TTS instalados en `data/models/` o en la ruta configurada) y `Externo` debajo (endpoints TTS configurados con subtítulo de proveedor + modelo, mostrando estado vacío si aún no hay ninguno). En modo `Local`, el desplegable de perfiles muestra solo los del motor elegido; en modo `Externo`, se oculta el selector de perfil local.
- Play escribe un WAV temporal en `data/tmp/` y lo reproduce (también disponible desde terminal con `speechstudio play "texto" --out salida.wav`).
- Save guarda en el historial. Desde ahí se puede volver a guardar eligiendo carpeta, abrir la carpeta y borrar.
- Un perfil aporta el audio de referencia, el texto de referencia y, si ya se calcularon, `.spk` y `.rvq`.
- La pestaña Profiles crea, edita y borra perfiles. Puede transcribir el audio de referencia con el STT de archivos. No se crea ningún perfil pre-cargado al instalar.
- El motor del perfil acepta `qwen` y `xtts`. Qwen sintetiza con `.spk` y `.rvq`. XTTS sintetiza con el wav de referencia del perfil, a través de `xtts_worker.py`.
- `POST /v1/audio/speech` repite la misma síntesis. Queda apagado hasta activar la API local en Ajustes. Ver [endpoints.md](endpoints.md).
- GPU o CPU sale de `tts_device`. En CPU el worker arranca con `CUDA_VISIBLE_DEVICES=""`.
- Si no cabe en VRAM, el supervisor expulsa a otros workers de GPU. Si Live Captions estuviera activo, pide confirmación antes de expulsar el STT.

## Acordado

- Los pesos de XTTS no van en el repo. La descarga del catálogo es el paso de licencia (Coqui Public Model License, uso no comercial). El worker carga el checkpoint local y no define `COQUI_TOS_AGREED`.

## Pendiente

- Descargar el checkpoint de XTTS v2 desde la pestaña Models y oír una síntesis real (el entorno `.venvs/xtts` ya está creado y verificado en `/health`). Ver [modelos.md](modelos.md).
