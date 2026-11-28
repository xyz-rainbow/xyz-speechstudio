# Matriz de entrega multiplataforma (runtime / instaladores / Update)

Propietario de este eje: agente de escritorio (Tauri/Rust, runtime, instaladores, Update, CI).  
Model Hub / TTS / Persona: otro agente — no revertir su trabajo; coordinar `main.py` y `App.tsx`.

Actualizado: 28 de noviembre de 2026. «Compila en CI» ≠ «soporte declarado».

## Objetivo de producto

Persona sin Python/Node/Rust/modelos: instalar → abrir sin Vite → descargar modelo → TTS/STT → Save → Update conservando datos.

## Fase 1 — Runtime y arranque

| Ítem | Estado | Evidencia |
| --- | --- | --- |
| Runtime interno `runtime/python` en Setup Windows | OK Setup + install limpia | Payload Inno incluye `runtime/python`; smoke_boot OK; portable `/PORTABLE=1` 2026-11-28 |
| Sin `.venv` de raíz para usuarios finales | OK en código | Sidecar: `runtime/python` → `runtime/envs/core` → `.venvs/core` |
| Docs instalador sin exigir uv en destino | OK | `installer/README.md`; `setup-env.ps1` marcado DEV/REPAIR |
| CrispASR CPU obligatorio en payload | OK Setup + install | `runtime/bin/cpu/crispasr.exe` en artefacto e install portable |
| CUDA opcional verificada | OK en Inno | Tarea post-install + `fetch-crispasr.ps1` |
| Datos vs caché vs recursos RO | OK unit + portable | `paths.py` / `paths.rs`; portable crea `data/` junto al exe |
| Unicode / espacios / corchetes | OK unit | `tests/test_paths.py` + Rust `paths::` |
| Migración legado `app/data` | Informe only | `migrate_legacy_app_data`; sin move automático |
| Anti-huérfanos | OK smoke post-quit | Job Object + `crispasr` atexit eject; tras cerrar install portable: `check_orphan_speech_processes.ps1` = 0 |
| Smoke sin Vite | OK en build previo `0.2.3`; pendiente revalidar binario actual | Build actual `speech-studio.exe` (`66890420…7a2a`); en build previo `50da2b1b…17de1` portable → `/health` 200, `openapi` `0.2.3`, `32` modelos, pack + TTS/Save WAV + reinicio sin Vite |
| Setup `0.2.3` local (artefacto) | Recompilado (`8e1ec34d…d0f7`); clean/upgrades validados en `fa4e3482…9a88` | Actual `SpeechStudio_0.2.3_Setup.exe` `91,012,572` bytes, SHA-256 `8e1ec34d5bf2d9f627e3ea9de8f3fdfe356cb92079f01734e470aff5ea04d0f7`; clean `/PORTABLE=1` y upgrades `0.2.1`/`0.2.2 -> 0.2.3` validados en `fa4e3482…9a88` |
| Release pública `v0.2.2` (GitHub) | Parcial / pre-fix | Contiene `SpeechStudio_0.2.2_Setup.exe` antiguo (`24dbc9e8…`, `94 MB`), `Speech.Studio.0.2.2_amd64.deb` (`83e19341…`; nombre con punto distinto al `SpeechStudio_…` de `release.yml`), `SHA256SUMS.txt` y sin `.dmg` |
| Expulsión VRAM | Otro agente | Coordinar orquestador |

### Fase 2 — Escritorio (avance)

| Ítem | Estado | Evidencia |
| --- | --- | --- |
| macOS captions no afirman captura por app | OK código | Entrada «System loopback (shared virtual device)» pid 0; capture ignora PID de ventana |
| Docs live-captions macOS | Actualizado | `docs/app/live-captions.md` |
| Prueba voz real Win/Linux | Pendiente | Requiere escritorio interactivo |

## Matriz por plataforma (no declarar verde sin evidencia)

| Capacidad | Windows | Ubuntu 24.04 | macOS Intel | macOS Apple Silicon |
| --- | --- | --- | --- | --- |
| Instalador nativo | Setup Inno (artefacto local/CI) | `.deb` workflow | `.dmg` workflow | `.dmg` workflow |
| Arranque limpio sin Vite | OK portable `0.2.3` + std silent `0.2.2` (`openapi` `0.2.3`, `/health` 200) | Pendiente en limpio | Pendiente | Pendiente |
| TTS | OK eSpeak `0.2.3` en install limpia + Save WAV; Qwen CrispASR Q8+`xyz-Ioquendo` en tree | Pendiente | Pendiente | Pendiente |
| STT | `crispasr.exe --help` OK + `/api/stt/cancel` 200 en install limpia; STT real en repo (`ggml-base.bin`) | Pendiente | Pendiente | Pendiente |
| Subtítulos | WASAPI (código); prueba voz real pendiente | pactl/parec (código) | Dispositivo virtual; no afirmar captura por app | Igual |
| Atajo lectura | UIA (código); prueba foco pendiente | Primary selection | Unsupported / permiso TBD | Unsupported / permiso TBD |
| Save audio | OK install limpia `0.2.3` (WAV `7.16s`, `315,656` B, ruta sanitizada) | Pendiente | Pendiente | Pendiente |
| Update salto real | OK módulo (`23` tests) + salto real portable `0.2.1 -> 0.2.3` y `0.2.2 -> 0.2.3` conservando `settings.json` + `profiles.json` | Pendiente | Firma/notarización: **bloqueo credenciales** | Igual |
| Firma | N/A Inno | N/A | **Bloqueo: credenciales Apple** | **Bloqueo: credenciales Apple** |

## Bloqueos conocidos

1. Credenciales de firma/notarización macOS del editor.
2. Salto Update entre **dos releases publicadas distintas** (falta); reinstall same-version Inno sobre DIR existente **sí** conserva `%LOCALAPPDATA%\Speech Studio\settings.json` + profiles (2026-11-28).
3. Q4 weights no están requisito del runtime; el smoke TTS del pack xyz-Ioquendo usó Q8 local.

## Próximos cierres verificables

1. Install en perfil/ruta Unicode (espacios/corchetes) no-portable; confirmar datos en `%LOCALAPPDATA%\Speech Studio`.
2. Cerrar app con CrispASR cargado (TTS real) y re-verificar cero huérfanos.
3. Salto Update entre dos Setup publicados conservando `settings.json` / profiles.
4. Ejecutar workflow `build-installers` en runners k3s/ARC cuando estén disponibles; no publicar sin smoke.
