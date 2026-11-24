[English](README.md) | **Español**

# Speech Studio

App de escritorio para Windows, local, de síntesis de voz, clonación de voz y transcripción.

[![CI](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml) [![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red?style=flat-square)](LICENSE) [![Windows](https://img.shields.io/badge/platform-Windows-0078d4?style=flat-square&logo=windows&logoColor=white)](https://www.microsoft.com/windows) [![Tauri](https://img.shields.io/badge/Tauri-2-24c8db?style=flat-square&logo=tauri&logoColor=white)](https://tauri.app/) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

Speech Studio es un escritorio [Tauri 2](https://tauri.app/) (React + TypeScript + Rust) con un orquestador FastAPI en Python. Ejecuta **Qwen3-TTS** en local para sintetizar y clonar voces, y **faster-whisper** para transcribir archivos. Windows es la plataforma principal (versión `0.1.0`); **Ubuntu 24.04** puede compilar y ejecutar el shell con el backend Python para desarrollo de TTS/STT. Los subtítulos en vivo, el atajo de lectura con UI Automation y los toasts de Windows siguen siendo solo Windows.

![Banner de Speech Studio](docs/assets/banner.svg)

![Arquitectura: shell Tauri, orquestador y workers](docs/assets/architecture.svg)

![Flujo desde el bootstrap hasta la síntesis](docs/assets/flow.svg)

## Funciones

- **TTS Studio** — sintetiza con un perfil de voz clonado, previsualiza la reproducción y exporta el historial en WAV (guardar, guardar como, mostrar en el Explorador, borrar).
- **Perfiles de voz** — crea perfiles a partir de un audio de referencia y su transcripción; extrae embeddings `.spk` / `.rvq` con el worker de Qwen; transcribe el clip de referencia si hace falta.
- **Transcriptor** — transcribe archivos `.wav`, `.mp3`, `.m4a`, `.flac` o `.opus` con faster-whisper local (tiny, base, small, medium, large-v3-turbo) o con un endpoint STT externo. Devuelve el texto completo y segmentos con marcas de tiempo. El idioma puede detectarse automáticamente.
- **Modelos y endpoints** — el catálogo lleva `capabilities` (modo de instalación, voces, idiomas). **Qwen y faster-whisper cargan hoy.** Coloca [CrispASR](https://github.com/CrispStrobe/CrispASR) en `runtime/bin/crispasr` (`scripts/fetch-crispasr.ps1`) para Piper y F5 GGUF. Coqui XTTS v2 tiene worker en `runtime/envs/xtts`; Parakeet, Moonshine y Fish siguen solo en catálogo hasta su runtime.
- **API local opcional** — compatibles con OpenAI: `POST /v1/audio/speech` y `POST /v1/audio/transcriptions`, con interruptor de encendido, host (`127.0.0.1` o `0.0.0.0`), puerto fijo o dinámico y token Bearer. Escuchar en `0.0.0.0` exige un token no vacío. Ajustes no guarda esa combinación y el orquestador no llega a servirla.
- **Endpoints externos** — plantillas para OpenAI, Groq, ElevenLabs y Deepgram, más URLs propias compatibles con OpenAI. Desde Ajustes puedes probar la conexión y copiar un cURL.
- **Escritorio Windows** — bandeja del sistema (mostrar/ocultar, acceso a subtítulos, expulsar modelos, salir), una sola instancia, cerrar a la bandeja, medidor de VRAM NVIDIA, selectores GPU o CPU, y un atajo global que lee el texto seleccionado con UI Automation (no usa el portapapeles) y lo envía al TTS Studio.
- **Notificaciones** — toasts de Windows opcionales a través de `scripts/notify.ps1` (BurntToast / [xyz-windows-notify](https://github.com/xyz-rainbow/xyz-windows-notify)).
- **Interfaz** — inglés o español (según el idioma de la app), temas claro/oscuro, acentos de color y un fondo ASCII opcional.
- **Overlay de subtítulos en vivo** — la pestaña Subtítulos elige una app y manda su audio (loopback del proceso) al STT seleccionado, local o endpoint. El overlay muestra ese texto. Aún no se ha probado una sesión con audio real.

## Requisitos

- Windows 10 u 11. El sidecar de Rust, el atajo de UI Automation, la bandeja, los toasts y las rutas `runtime\envs\*\Scripts\python.exe` son específicos de Windows.
- [Node.js](https://nodejs.org/) 20+ y npm.
- Rust estable y los [requisitos de Tauri 2 en Windows](https://v2.tauri.app/start/prerequisites/).
- Python 3.11 o posterior, de 64 bits.
- Opcional: una GPU NVIDIA y un controlador reciente (`nvidia-smi` / NVML) para inferencia en GPU y el medidor de VRAM. El modo CPU está soportado.
- Opcional: el módulo de PowerShell [BurntToast](https://github.com/Windos/BurntToast) para los toasts.

Los entornos virtuales salen de [`installer/setup-env.ps1`](installer/setup-env.ps1) (`uv`, Python 3.12) y de los ficheros fijados [`installer/requirements-core.txt`](installer/requirements-core.txt), [`requirements-qwen.txt`](installer/requirements-qwen.txt), [`requirements-stt.txt`](installer/requirements-stt.txt) y [`requirements-xtts.txt`](installer/requirements-xtts.txt). El paquete de Windows es Inno Setup: `installer/Output/SpeechStudio_0.1.0_Setup.exe`. Una instalación limpia en silencio el 24 de noviembre de 2026 dejó la app en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`. `setup-env.ps1` salió con código 0 y creó los `runtime/envs`. Un `/DIR` silencioso hacia otra carpeta se ignoró. El valor por defecto de la plantilla es `{autopf}\XYZ-Productions\Speech Studio`. Los paquetes MSI y NSIS de `tauri build` no instalan Python. Hace falta `uv` en el equipo. Los pesos no van en el instalador.

### Linux (Ubuntu 24.04) — desarrollo

Instala los [requisitos de Tauri en Linux](https://v2.tauri.app/start/prerequisites/), por ejemplo:

```bash
sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

`installer/setup-env.ps1` es solo Windows. En Linux, crea los mismos entornos con `uv` y los requirements (`bin/python`, no `Scripts/python.exe`):

```bash
uv venv --python 3.12 runtime/envs/core
uv pip install --python runtime/envs/core/bin/python -r installer/requirements-core.txt
uv venv --python 3.12 runtime/envs/qwen
uv pip install --python runtime/envs/qwen/bin/python -r installer/requirements-qwen.txt
uv venv --python 3.12 runtime/envs/stt
uv pip install --python runtime/envs/stt/bin/python -r installer/requirements-stt.txt
```

XTTS también necesita PyTorch antes de `installer/requirements-xtts.txt` (`uv pip install --python runtime/envs/xtts/bin/python torch torchaudio torchcodec --torch-backend=auto`, después de `uv venv --python 3.12 runtime/envs/xtts`). Luego `npm install` y `npm run tauri dev`. El sidecar de Rust usa un grupo de procesos en Unix en lugar de los Job Objects de Windows. En Linux, si las notificaciones están activas, se usa `notify-send`. El CI de Linux compila el shell y no genera AppImage ni `.deb`.

## Instalación

```powershell
git clone https://github.com/xyz-rainbow/xyz-speechstudio.git
cd xyz-speechstudio
npm install
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\setup-env.ps1 -AppRoot (Get-Location).Path
```

`setup-env.ps1` es el bootstrap oficial. Necesita [`uv`](https://docs.astral.sh/uv/) y Python 3.12, y crea cuatro entornos en `runtime\envs\` (la app busca `Scripts\python.exe` en Windows):

| Venv | Requirements | Uso |
| --- | --- | --- |
| `runtime\envs\core` | `installer/requirements-core.txt` | Orquestador (`backend.orchestrator.main`) |
| `runtime\envs\qwen` | `installer/requirements-qwen.txt` | Worker TTS de Qwen (`realtimetts-qwen-native`) |
| `runtime\envs\stt` | `installer/requirements-stt.txt` | Worker de faster-whisper |
| `runtime\envs\xtts` | `installer/requirements-xtts.txt` | Coqui XTTS v2 (`coqui-tts==0.28.0` y `six==1.17.0`). Antes se instalan PyTorch, torchaudio y torchcodec con `--torch-backend=auto`. |

Descarga un par GGUF de Qwen3-TTS (talker + tokenizer) y un modelo faster-whisper desde la vista **Modelos**, o colócalos en la carpeta de modelos configurada. Las compilaciones Qwen del catálogo salen de [`Serveurperso/Qwen3-TTS-GGUF`](https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF); las de Whisper, de los repos Systran `faster-whisper-*`. Los pesos de XTTS no van en git (Coqui Public Model License). En este árbol los pesos ya están en disco; una síntesis real puede seguir en validación. Una carga falló una vez porque faltaba `six`, hasta `pip install six` (`six` queda fijado). Parakeet, Moonshine y Fish Audio no cargan.

## Uso

```powershell
npm run tauri dev
```

Arranca la UI de Vite y la ventana de Tauri. El sidecar de Rust lanza el orquestador desde `runtime\envs\core` y escribe `data/tmp/orchestrator.stderr.log`.

1. En **Modelos**, descarga o elige un modelo TTS y uno STT, y carga los workers (GPU o CPU en la barra superior).
2. En **Perfiles**, añade un audio de referencia y su transcripción, y extrae la voz.
3. En **Sintetizar**, elige el perfil, escribe el texto y usa **Reproducir** o **Guardar** (exporta un WAV y lo lista en el historial).
4. En **Transcriptor** puedes transcribir un archivo de audio.

Cerrar la ventana principal la oculta en la bandeja; usa **Salir** en la bandeja para cerrar del todo. La app mantiene una sola instancia y enfoca la ventana existente si la vuelves a abrir.

### API local

En **Ajustes**, activa *Servir API local compatible con OpenAI*. Reinicia la app si cambias el host o el puerto fijo (`0` significa puerto dinámico). Si hay token Bearer, envíalo como `Authorization: Bearer <token>`. Escuchar en `0.0.0.0` exige un token no vacío; esa combinación se rechaza al guardar y antes de que el orquestador escuche.

```powershell
curl.exe -X POST "http://127.0.0.1:<puerto>/v1/audio/speech" `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d "{\"input\":\"Hola\",\"voice\":\"<id-de-perfil>\",\"response_format\":\"wav\"}" `
  --output speech.wav

curl.exe -X POST "http://127.0.0.1:<puerto>/v1/audio/transcriptions" `
  -H "Authorization: Bearer <token>" `
  -F "file=@audio.wav" `
  -F "model=faster-whisper-base"
```

`GET /health` indica si el orquestador está en marcha. La API permanece apagada hasta que actives el ajuste.

## Configuración

Los ajustes se guardan en `data/settings.json` (se crea en la primera ejecución). Claves útiles:

| Clave | Significado |
| --- | --- |
| `language` | Idioma de la UI: `en` o `es` |
| `theme`, `accent` | `dark` / `light` y acento (`cyber`, `emerald`, `amber`, `rose`) |
| `models_dir`, `outputs_dir` | Carpetas propias; vacío equivale a `data/models` y `data/outputs` |
| `tts_device`, `stt_device` | `gpu` o `cpu` |
| `tts_source`, `stt_source` | `local` o `endpoint` |
| `active_tts_model`, `active_stt_model` | Identificadores del catálogo |
| `api_endpoint_enabled`, `api_bind_host`, `api_fixed_port`, `api_bearer_token` | API local |
| `read_hotkey` | Atajo global para «leer la selección» |
| `notifications_enabled` | Toasts de Windows |
| `external_endpoints` | Endpoints TTS/STT guardados |

No subas `data/`, perfiles de voz, claves de API ni pesos de modelos. Están en `.gitignore`.

## Desarrollo

| Comando | Qué hace |
| --- | --- |
| `npm run dev` | Solo la UI de Vite (`http://localhost:1420`) |
| `npm run build` | Comprobación de tipos (`tsc --noEmit`) y build de Vite |
| `npm run tauri dev` | App de escritorio completa |
| `python -m compileall backend` | Comprueba la sintaxis del orquestador y los workers |

Las pruebas ligeras están en `tests/` y se ejecutan en el CI (`pytest`). El árbol `spikes/` guarda experimentos previos y no forma parte del CI.

Consulta [CONTRIBUTING.es.md](CONTRIBUTING.es.md) para las convenciones de las pull requests.

## Documentación

[docs/README.md](docs/README.md) reúne el changelog, la spec de comunidad, los problemas conocidos y el estado vivo de la app en [docs/app/](docs/app/README.md).

## Contribuir

Se aceptan issues, debates y pull requests. Lee [CONTRIBUTING.es.md](CONTRIBUTING.es.md) y el [Código de conducta](CODE_OF_CONDUCT.es.md). Los informes de seguridad van por [SECURITY.md](SECURITY.md), no por issues públicos.

## Patrocinio

Si el proyecto te resulta útil, puedes [patrocinar a xyz-rainbow](https://github.com/sponsors/xyz-rainbow). El resto de plataformas está en [`.github/FUNDING.yml`](.github/FUNDING.yml) (GitHub Sponsors, Patreon, Ko-fi, Buy Me a Coffee, PayPal).

## Licencia

Propietaria — todos los derechos reservados. Copyright (c) 2026 Rainbow Technology (xyz-rainbow).

El código se puede ver y evaluar en este repositorio. Queda prohibido copiarlo, redistribuirlo, sublicenciarlo, publicar forks o trabajos derivados, y cualquier uso comercial o en producción, salvo permiso escrito. Se admiten issues y pull requests. El fork en GitHub solo está permitido para preparar pull requests hacia este repositorio.

Consulta [LICENSE](LICENSE) para el texto completo, incluida la cesión de contribuciones, y [CONTRIBUTING.es.md](CONTRIBUTING.es.md) si quieres enviar un cambio.
