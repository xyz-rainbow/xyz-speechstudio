# Speech Studio — Roadmap

App de escritorio en `N:\` (`Z:\[🛠️] [Tools]\xyz-speech-studio`). Estado contrastado con el código el 24 de noviembre de 2026.

El detalle vivo de cada parte está en [app/](app/README.md). Este archivo solo guarda las fases.

La sesión de Antigravity `5bd7416d` se cortó por cuota al revisar la app. La nota de la release `v0.1.0` está en [releases/v0.1.0.md](releases/v0.1.0.md) y lista lo que aún no funciona.

## Hecho

### Fase 0 — Spikes

Pruebas sueltas en `spikes/`, fuera de la app: NVML, Job Object, workers Qwen y faster-whisper por HTTP en `127.0.0.1:0`.

### Fase 1 — Esqueleto

- Tauri v2, React, Tailwind, sidebar plegable.
- Temas Dark/Light, acentos, `AsciiAmbientPool`, `BorderBeamButton`, `GlassCard`.
- Orquestador FastAPI en `.venvs/core`, sidecar con puerto dinámico y Job Object (`KILL_ON_JOB_CLOSE`).
- Barra de VRAM, toggle GPU/CPU, Settings (rutas, toasts, límite de historial de subtítulos).
- Bandeja del sistema, instancia única y cierre a la bandeja.

### Fase 2 — TTS con Qwen

- `.venvs/qwen` y `qwen_worker.py`.
- Perfiles de voz, importación de Mario, referencia de audio y texto.
- Synthesize: Play, guardar WAV, historial, abrir carpeta y borrar.
- `POST /v1/audio/speech` y toasts de Windows.

### Fase 3 — STT de archivos

- `.venvs/stt` y `stt_worker.py` con faster-whisper y filtro VAD.
- Pestaña Transcriber y auto-transcribir la referencia de un perfil.
- El supervisor protege la VRAM si Live Captions estuviera activo.

### Hotkey

Graba la tecla física (`Alt+Shift+Digit7`, `Super+Slash`), sin traducirla al carácter impreso. Lee el texto seleccionado por UI Automation y no toca el portapapeles. Hace falta al menos un modificador.

## A medias

### Capabilities + CrispASR (ola TTS 2026-11)

- Contrato `capabilities` en catálogo + UI (chips idioma, Synthesize perfiles vs voces builtin).
- Rutas canónicas `runtime/envs/` y `runtime/bin/crispasr`.
- Puente CLI CrispASR para Piper / F5 GGUF cuando el binario está instalado.
- Pendiente: más backends CrispASR (Kokoro GGUF, STT Parakeet/Moonshine), validar XTTS, empaquetar crispasr en el instalador.

### Catálogo de modelos

La pestaña Models descarga desde el catálogo y Hugging Face, con cuantización, progreso y borrado. Qwen y faster-whisper se cargan hoy; Piper/F5 GGUF si hay CrispASR. XTTS tiene worker; Parakeet, Moonshine y Fish siguen con `runtime_supported: false` hasta runtime.

### Overlay

La pestaña Subtitles elige la app, manda el audio al STT elegido y el overlay escucha el evento `caption`. El código está. Falta una sesión con audio de verdad.

## Pendiente

1. **Live Captions.** Confirmar con Edge o Discord que el PCM llega y el texto sale en el overlay. En Linux cada sink-input es una fila y el paro señala `parec` en cuanto publica su pid; una sesión PipeWire o Pulse no se ha oído. Parakeet, Moonshine y Fish Audio siguen con `runtime_supported: false`.
2. **XTTS v2.** `.venvs/xtts` (`coqui-tts==0.28.0` + PyTorch) ya está creado, `xtts_worker.py` está en el árbol y los pesos del checkpoint están en disco. No van en el repo (Coqui Public Model License). Una carga falló una vez porque faltaba `six`, hasta `pip install six`. `six==1.17.0` queda fijado en `requirements-xtts.txt`. Una síntesis real puede seguir en validación.
3. **Parakeet, Moonshine y Fish Audio.** Hace falta cargarlos. Hoy el worker STT solo acepta faster-whisper y el catálogo los marca con `runtime_supported: false`. XTTS no se apaga: sigue en `true`.
4. **Idiomas.** Hay inglés y español. Faltan italiano, francés, alemán, ruso, chino simplificado, portugués, japonés, coreano, árabe con RTL e hindi.
5. **Instalador.** `SpeechStudio_0.1.0_Setup.exe` (Inno Setup) existe. El 24 de noviembre de 2026 se ejecutó en silencio y quedó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`. `setup-env.ps1` salió con código 0 y creó `.venvs/core`, `qwen`, `stt` y `xtts`. `/DIR` en silencio ignoró la ruta pedida. El MSI y el NSIS de `tauri build` no instalan Python. Ver [docs/app/instalador.md](app/instalador.md).
6. **macOS y Linux.** CI enlaza el shell de Linux y hace check en macOS. Falta el paquete (AppImage, `.deb`, bundle de macOS) porque los sidecars de Python no van dentro. El icono de bandeja y los toasts ya están escritos. Esas sesiones de escritorio no se han probado. Ver [docs/app/instalador.md](app/instalador.md).

## Por dónde seguir

Lo siguiente es oír una captura WASAPI real y validar una síntesis real de XTTS (el worker, `.venvs/xtts` y los pesos ya están). Parakeet, Moonshine y Fish Audio siguen con `runtime_supported: false`.
