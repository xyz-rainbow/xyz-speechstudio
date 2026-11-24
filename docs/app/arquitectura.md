# Arquitectura

## Ahora

Speech Studio es una ventana Tauri. Rust arranca el orquestador Python y lo mete en un Job Object de Windows con `KILL_ON_JOB_CLOSE`. Al cerrar la app, el orquestador y los workers hijos mueren con ella.

```text
React  --invoke-->  Rust (Tauri)
React  --HTTP---->  orquestador  .venvs/core   127.0.0.1
orquestador --HTTP->  worker Qwen  .venvs/qwen
orquestador --HTTP->  worker XTTS  .venvs/xtts
orquestador --HTTP->  worker STT   .venvs/stt
```

Cada worker abre `127.0.0.1:0`, escribe `{"port": N}` por stdout y el supervisor se queda con ese puerto. Cargar un modelo es arrancar ese proceso. Descargarlo es matarlo, y la VRAM vuelve al driver.

Entornos que existen en disco, fuera de git:

| Entorno | Proceso | Listo |
| --- | --- | --- |
| `.venvs/core` | `backend.orchestrator.main` | Sí |
| `.venvs/qwen` | `backend/workers/qwen_worker.py` | Sí |
| `.venvs/stt` | `backend/workers/stt_worker.py` | Sí |
| `.venvs/xtts` | `backend/workers/xtts_worker.py` | Sí (`coqui-tts==0.28.0` + PyTorch CUDA) |

El supervisor nombra la familia `xtts` en `/api/workers` con `script_ready` y `venv_ready` verdaderos.

Rust también lee la VRAM con NVML, muestra el icono de bandeja, registra el hotkey global y puede abrir la ventana `overlay`.

## Acordado

Rust captura el audio y lo entrega al orquestador en `/api/captions/stream`. El orquestador lo pasa al worker STT local o al endpoint STT elegido. El detalle está en [live-captions.md](live-captions.md).

## Pendiente

- Probar una captura WASAPI real. El canal está escrito y no se ha oído todavía.
- Descargar los pesos de XTTS v2 desde Models y oír una síntesis real.
