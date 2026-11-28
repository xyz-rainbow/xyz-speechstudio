# Speech Studio — Roadmap

## Plan de estabilización y soporte multiplataforma

Las decisiones posteriores del usuario establecen una reorganización profunda, núcleo Rust, CrispASR principal, Python opcional autocontenido e instaladores multiplataforma que funcionen sin Python instalado. El diseño y los criterios de aceptación están en [la especificación de arquitectura](specs/2026-11-27-desktop-runtime-architecture.md).

Actualizado el 28 de noviembre de 2026. El estado de implementación de esta sesión está detallado en [continuidad-qwen.md](roadmap/continuidad-qwen.md); las secciones posteriores a «Historial anterior a v0.2.1» son archivo histórico y no describen necesariamente el código actual.

## Prioridad actual

1. Model Hub, variantes y unificación GGUF: Qwen, Chatterbox, IndexTTS, CosyVoice3, Orpheus, Kokoro (`cstr/kokoro-82m-GGUF`) y Piper (`LocalAI-Community/piper-voices-GGUF`) unificados y cubiertos por pruebas automatizadas multi-variante y borrado seguro sin romper archivos compartidos; `compute_type` de Faster-Whisper seleccionable en selector y tarjetas; `post_quantize` (Fish int8/int4), Parakeet/Moonshine ONNX y F5 no-GGUF bloqueados honestamente hasta soporte real de runtime.
2. `xyz-Ioquendo`, VoiceDesign y Perfiles: pack `xyz-ioquendo` desacoplado de pesos Qwen, voces por locale y síntesis real verificada con CrispASR `qwen3-tts` (Álvaro en CPU); recorte de perfiles a 12 s con alineación de texto por palabras y conservación de `ref_original_text` + `ref_original_path`; Qwen VoiceDesign (`--instruct`, preview y guardado en Perfiles) implementado y probado; [GPT-SoVITS](app/gpt-sovits.md) documentado solo como diseño.
3. Persona (UI, instalación verificada con SHA-256, adaptación por motor y servicio `services/persona/` para k3s) integrado en el orquestador (`persona_routes.py`) con suite completa en verde; pendiente únicamente desplegar en k3s y publicar audios con consentimiento.
4. Reproducción larga por tramos, STT y accesibilidad: aborto al cambiar voz/modelo, tests reales de sesión multi-tramo + WAV concatenado, `/api/stt/cancel`, `role="dialog"` / `aria-modal` / `aria-label` y paridad `en`/`es` completos; pendiente escucha prolongada en WebView empaquetado, Live Captions y hotkey por sistema.
5. Empaquetado e instaladores multiplataforma: gestionado en paralelo por el agente de plataforma ([platform-delivery-matrix.md](roadmap/platform-delivery-matrix.md)).

| Fase | Etapas | Criterio de cierre | Estado |
| --- | --- | --- | --- |
| 1. Referencia de Windows (`0.2.3`) | Compilar ejecutable y Setup `0.2.3`. Instalar limpio sin Python/Vite, probar TTS, Save, reinicio y salto real desde `0.2.1` y `0.2.2`. | Setup `0.2.3` identificado por SHA-256; instalación limpia portable y upgrades conservan ajustes y perfiles. | **Recompilado `0.2.3`** (`SpeechStudio_0.2.3_Setup.exe` sha256 `8e1ec34d…d0f7`; `speech-studio.exe` `66890420…7a2a`). Salto real `0.2.1 -> 0.2.3` y `0.2.2 -> 0.2.3` + portable verificado en build anterior `fa4e3482…9a88`; falta repetir smoke portable/UAC sobre `8e1ec34d…d0f7` y STT tras instalar modelo en equipo limpio. |
| 2. Fiabilidad y API | Actualizar pruebas del catálogo y CrispASR. Proteger rutas internas HTTP/WebSocket. Compilar producción Windows `0.2.3`. | Pruebas correctas en Python 3.12, TypeScript, Node y Rust; nombres de archivo sanitizados al guardar WAV. | Verificado localmente tras los últimos arreglos (`py`, Node, `tsc`, Vite, Rust). |
| 3. Subtítulos y atajo | Corregir carrera de inicio y liberación de listeners. Diagnosticar captura, PCM, WebSocket, STT y eventos. Iniciar seguimiento de foco con la aplicación. | Voz conocida produce texto en vista y overlay. Parar y reiniciar funciona. Atajo verificado en primer uso y tras cambiar de ventana. | Código y diagnóstico en árbol; validación visual/audio interactiva pendiente por plataforma. |
| 4. Datos y recuperación | Escrituras atómicas. Serializar cambios de historial y perfiles. Separar recursos, datos y caché por usuario. Sanitizar nombres de archivo de salida. | Interrupciones y operaciones concurrentes preservan datos. Arranque portable verificado; sanitización en Windows verificada. | Implementado guardado atómico, sanitización de `pid_tag` y separación portable/`%LOCALAPPDATA%`; bloqueo multiproceso pendiente. |
| 5. Núcleo multiplataforma | Empaquetar runtime interno y motores en Windows/Linux/macOS. Preparar paquetes con backend y recursos. Declarar capacidades según sistema y hardware. | Instalación limpia en Windows, Ubuntu 24.04 y macOS permite TTS, STT, guardar y reabrir sin Python instalado. | Windows portable `0.2.3` **verificado**; Linux `.deb` (`v0.2.2` subido como `Speech.Studio.0.2.2_amd64.deb`) y macOS `.dmg` pendientes en equipos limpios (bloqueo firma Apple). |
| 6. Interfaz y experiencia | Model Hub, Persona, reproducción TTS por tramos, teclado, foco y estados recuperables. | Paginación Hub estable, cartas compactas, autoplay continuo en Play, `xyz-Ioquendo` separado en Synthesize, Persona operativo local + k3s. | Implementado y probado en backend/Node/build `0.2.3`; falta escucha prolongada interactiva en WebView2 y despliegue k3s real. |
| 7. Distribución | Matriz CI de tres sistemas. Artefactos de prueba. Actualización conservando datos. Notas y documentación alineadas con capacidades verificadas. | Paquetes instalados y probados por sistema. Evidencias de actualización y cierre de procesos. Aprobación de publicación. | Windows `0.2.3` validado localmente; pendiente publicar tag `v0.2.3`, alinear nombre `.deb` y aportar `.dmg` (firma/notarización macOS pendiente). |

La validación de GPU incluye Fish y XTTS en rutas con espacios, Unicode y corchetes. La precarga de cuDNN se ampliará cuando una reproducción identifique el proceso afectado. Los tiempos de carga se medirán por motor en frío y en caliente.

### Evidencias de la primera etapa

- Instalador v0.2.1 local y publicado con el mismo SHA-256, `e79d51b5ca7266ace171942d2f2090a94b77a5dc1cabbefe493b109f52d18a6f`.
- Suite local de Python 3.12.13 con 77 pruebas correctas. Incluye bloqueo HTTP/WebSocket, preservación del archivo ante un reemplazo fallido, 24 escrituras concurrentes de historial y API de voz nativa sin perfiles.
- Compilación TypeScript/Vite y 13 pruebas Rust correctas en Windows. `npx tauri build --no-bundle` genera el ejecutable de producción actualizado. El instalador publicado continúa siendo el de v0.2.1.
- Petición real a `/v1/audio/speech` usando eSpeak CPU devuelve HTTP 200 y WAV mono a 22050 Hz con 2,15 segundos de audio. La prueba usa ajustes temporales en memoria.
- Ajustes, historial y perfiles usan reemplazo atómico. Las operaciones de historial y perfiles se serializan dentro de un proceso. La coordinación entre múltiples procesos y la migración de rutas siguen pendientes.
- Subtítulos libera listeners incluso si la suscripción termina después del desmontaje. La UI marca la sesión antes de arrancar la captura, y un cierre inesperado de WebSocket se comunica como error. El overlay muestra errores. Falta la validación visual y con voz real.
- El seguimiento de foco de Windows arranca con la aplicación. La ventana principal permite redimensionar y maximizar. Falta la prueba interactiva del atajo y del escalado.

El control visual de Windows falla al inicializarse por la interpretación de los corchetes de la ruta del workspace. Debian está registrado en WSL, pero falta preparar sus dependencias de desarrollo y audio. No hay un equipo macOS seleccionado para esta validación. La nueva configuración de CI requiere una ejecución remota para confirmar el resultado en los runners.

La firma y notarización de macOS requieren credenciales del editor. La publicación se realizará tras verificar los paquetes y recibir autorización. Una compilación correcta cubre la construcción. Las pruebas de escritorio y audio deben ejecutarse en cada sistema.

## Historial anterior a v0.2.1

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
