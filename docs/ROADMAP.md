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

### Catálogo de modelos

La pestaña Models descarga desde el catálogo y desde una URL de Hugging Face, con cuantización, progreso y borrado. El catálogo ya nombra XTTS v2, Parakeet y Moonshine. Solo Qwen y faster-whisper llegan a cargarse.

### Overlay

La pestaña Subtitles elige la app, manda el audio al STT elegido y el overlay escucha el evento `caption`. El código está. Falta una sesión con audio de verdad.

## Pendiente

1. **Live Captions.** Confirmar con Edge o Discord que el PCM llega y el texto sale en el overlay. Parakeet y Moonshine siguen sin runtime.
2. **XTTS v2.** `.venvs/xtts` y `xtts_worker.py`. En Synthesize la opción sigue desactivada. En Perfiles se puede elegir y no sintetiza.
3. **Parakeet y Moonshine.** Hace falta cargarlos en el worker STT (sherpa-onnx). Hoy el worker solo acepta faster-whisper.
4. **Idiomas.** Hay inglés y español. Faltan italiano, francés, alemán, ruso, chino simplificado, portugués, japonés, coreano, árabe con RTL e hindi.
5. **Instalador.** La plantilla Inno Setup ya está en `installer/windows/` con el arte de xyz-installer y destino en Archivos de programa. Falta ejecutar el setup en limpio. `xtts` sigue sin entorno. Ver [docs/app/instalador.md](app/instalador.md).
6. **macOS y Linux.** CI enlaza el shell de Linux y hace check en macOS. Falta el paquete (AppImage, `.deb`, bundle de macOS) porque los sidecars de Python no van dentro. El icono de bandeja y los toasts ya están escritos. Esas sesiones de escritorio no se han probado. Ver [docs/app/instalador.md](app/instalador.md).

## Por dónde seguir

Lo siguiente es oír una captura real. XTTS sigue siendo el motor de después, porque el perfil y el selector ya lo reservan.
