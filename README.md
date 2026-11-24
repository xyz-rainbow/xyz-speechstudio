**English** | [Español](README.es.md)

# Speech Studio

Local Windows desktop app for text-to-speech, voice cloning, and transcription.

[![CI](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml) [![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red?style=flat-square)](LICENSE) [![Windows](https://img.shields.io/badge/platform-Windows-0078d4?style=flat-square&logo=windows&logoColor=white)](https://www.microsoft.com/windows) [![Tauri](https://img.shields.io/badge/Tauri-2-24c8db?style=flat-square&logo=tauri&logoColor=white)](https://tauri.app/) [![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

Speech Studio is a [Tauri 2](https://tauri.app/) desktop shell (React + TypeScript + Rust) with a Python FastAPI orchestrator. It runs **Qwen3-TTS** locally for synthesis and voice profiles, and **faster-whisper** for file transcription. Windows is the primary platform (version `0.1.0`); **Ubuntu 24.04** can build and run the shell plus Python backend for TTS/STT development. Live captions, read-selection UI Automation, and Windows toasts remain Windows-only.

## Features

- **TTS Studio** — synthesize with a cloned voice profile, preview playback, and export WAV history (save, save-as, reveal in Explorer, delete).
- **Voice profiles** — create profiles from reference audio and a transcript; extract `.spk` / `.rvq` embeddings with the Qwen worker; transcribe the reference clip when needed.
- **Transcriber** — transcribe `.wav`, `.mp3`, `.m4a`, `.flac`, or `.opus` files with local faster-whisper (tiny, base, small, medium, large-v3-turbo) or an external STT endpoint. Returns full text plus timestamped segments. Language can be auto-detected.
- **Models & endpoints** — download built-in catalog models from Hugging Face, inspect and install files from a custom repo, switch local vs endpoint sources, and eject TTS or STT workers. The catalog also lists Coqui XTTS v2, NVIDIA Parakeet TDT, and Moonshine Base ONNX; **inference workers in this repo today are Qwen (TTS) and faster-whisper (STT) only**.
- **Optional local API** — OpenAI-compatible `POST /v1/audio/speech` and `POST /v1/audio/transcriptions`, with an on/off switch, bind host (`127.0.0.1` or `0.0.0.0`), fixed or dynamic port, and optional Bearer token.
- **External endpoints** — presets for OpenAI, Groq, ElevenLabs, and Deepgram, plus custom OpenAI-compatible URLs. Test connection and copy a cURL snippet from Settings.
- **Windows desktop shell** — system tray (show/hide, captions shortcut, eject models, exit), single-instance, close-to-tray, NVIDIA VRAM meter, GPU or CPU device selectors, and a global hotkey that reads the selected text via UI Automation (the clipboard is not used) and sends it to TTS Studio.
- **Notifications** — optional Windows toast notifications through `scripts/notify.ps1` (BurntToast / [xyz-windows-notify](https://github.com/xyz-rainbow/xyz-windows-notify)).
- **UI** — English or Spanish (follows the in-app language setting), dark/light themes, accent colors, and an optional ASCII background.
- **Live Captions overlay** — the Subtitles tab picks an app and streams its process-loopback audio to the selected STT (local faster-whisper or an external endpoint). The overlay shows that text. A live capture session has not been tried yet.

## Requirements

- Windows 10 or 11. The Rust sidecar, UI Automation hotkey, tray, toasts, and `.venvs\*\Scripts\python.exe` paths are Windows-specific.
- [Node.js](https://nodejs.org/) 20+ and npm.
- Rust stable and the [Tauri 2 Windows prerequisites](https://v2.tauri.app/start/prerequisites/).
- 64-bit Python 3.11 or newer.
- Optional: an NVIDIA GPU and a recent driver (`nvidia-smi` / NVML) for GPU inference and the VRAM meter. CPU mode is supported.
- Optional: the PowerShell [BurntToast](https://github.com/Windos/BurntToast) module for toasts.

There is no packaged installer and no `requirements.txt` / venv bootstrap script in the repository yet.

### Linux (Ubuntu 24.04) — development

Install [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for Linux, for example:

```bash
sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

Use `.venvs/<name>/bin/python` (not `Scripts/python.exe`). Example for the orchestrator:

```bash
python3 -m venv .venvs/core
.venvs/core/bin/python -m pip install fastapi uvicorn pydantic httpx huggingface_hub
```

Repeat for `.venvs/qwen` and `.venvs/stt`. Then `npm install` and `npm run tauri dev`. The Rust sidecar uses a process group on Unix instead of Windows Job Objects. On Linux, `notify-send` is used when notifications are enabled.

## Installation

```powershell
git clone https://github.com/xyz-rainbow/xyz-speechstudio.git
cd xyz-speechstudio
npm install
```

Create three virtual environments under `.venvs\` (the shell looks for `Scripts\python.exe` on Windows):

| Venv | Used for | Python packages imported by the code |
| --- | --- | --- |
| `.venvs\core` | Orchestrator (`backend.orchestrator.main`) | `fastapi`, `uvicorn`, `pydantic`, `httpx`, `huggingface_hub` |
| `.venvs\qwen` | Qwen TTS worker | `fastapi`, `uvicorn`, `pydantic`, `numpy`, `qwentts_cpp` |
| `.venvs\stt` | faster-whisper worker | `fastapi`, `uvicorn`, `pydantic`, `faster-whisper` |

Example for the orchestrator:

```powershell
py -3 -m venv .venvs\core
.venvs\core\Scripts\python -m pip install fastapi uvicorn pydantic httpx huggingface_hub
```

Repeat for `.venvs\qwen` and `.venvs\stt` with the packages in the table. `qwentts_cpp` is imported as that module name; this repo does not pin a package index or version for it.

Download a Qwen3-TTS GGUF pair (talker + tokenizer) and a faster-whisper model from the in-app **Models** view, or place them in the configured models folder. Built-in Qwen builds come from [`Serveurperso/Qwen3-TTS-GGUF`](https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF); Whisper builds come from the Systran `faster-whisper-*` repos.

## Usage

```powershell
npm run tauri dev
```

This starts the Vite UI and the Tauri window. The Rust sidecar launches the orchestrator from `.venvs\core` and writes `data/tmp/orchestrator.stderr.log`.

1. Open **Models**, download or select a TTS model and an STT model, and load the workers (GPU or CPU from the top bar).
2. Open **Profiles**, add a reference audio file and its transcript, then extract the voice.
3. Open **Synthesize**, pick the profile, enter text, and use **Play** or **Save** (exports a WAV and lists it in history).
4. Open **Transcriber** to transcribe an audio file.

Closing the main window hides it to the tray; use **Exit** in the tray to quit. The app enforces a single instance and focuses the existing window if you start it again.

### Local API

In **Settings**, enable *Serve Local OpenAI-Compatible API*. Restart the app if you change the bind host or the fixed port (`0` means a dynamic port). If a Bearer token is set, send it as `Authorization: Bearer <token>`.

```powershell
curl.exe -X POST "http://127.0.0.1:<port>/v1/audio/speech" `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d "{\"input\":\"Hello\",\"voice\":\"<profile-id>\",\"response_format\":\"wav\"}" `
  --output speech.wav

curl.exe -X POST "http://127.0.0.1:<port>/v1/audio/transcriptions" `
  -H "Authorization: Bearer <token>" `
  -F "file=@audio.wav" `
  -F "model=faster-whisper-base"
```

`GET /health` reports whether the orchestrator is up. The API stays off until the setting is enabled.

## Configuration

Settings are stored in `data/settings.json` (created on first run). Useful keys:

| Key | Meaning |
| --- | --- |
| `language` | UI language: `en` or `es` |
| `theme`, `accent` | `dark` / `light` and neon accent (`cyber`, `emerald`, `amber`, `rose`) |
| `models_dir`, `outputs_dir` | Custom folders; empty means `data/models` and `data/outputs` |
| `tts_device`, `stt_device` | `gpu` or `cpu` |
| `tts_source`, `stt_source` | `local` or `endpoint` |
| `active_tts_model`, `active_stt_model` | Catalog model ids |
| `api_endpoint_enabled`, `api_bind_host`, `api_fixed_port`, `api_bearer_token` | Local API |
| `read_hotkey` | Global accelerator for “read selection” |
| `notifications_enabled` | Windows toasts |
| `external_endpoints` | Saved TTS/STT endpoint configs |

Do not commit `data/`, voice profiles, API keys, or model weights. They are gitignored.

## Development

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite UI only (`http://localhost:1420`) |
| `npm run build` | Typecheck (`tsc --noEmit`) and Vite production build |
| `npm run tauri dev` | Full desktop app |
| `python -m compileall backend` | Syntax-check the orchestrator and workers |

Lightweight tests live in `tests/` and run in CI (`pytest`). The `spikes/` tree holds earlier end-to-end experiments and is not part of CI.

See [CONTRIBUTING.md](CONTRIBUTING.md) for pull request conventions.

## Documentation

[docs/README.md](docs/README.md) indexes the changelog, the community spec, known issues, and the living app notes in [docs/app/](docs/app/README.md).

## Contributing

Issues, discussions, and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Security reports go through [SECURITY.md](SECURITY.md), not public issues.

## Sponsor

If the project is useful, you can [sponsor xyz-rainbow](https://github.com/sponsors/xyz-rainbow). Other platforms are listed in [`.github/FUNDING.yml`](.github/FUNDING.yml) (GitHub Sponsors, Patreon, Ko-fi, Buy Me a Coffee, PayPal).

## License

Proprietary — all rights reserved. Copyright (c) 2026 Rainbow Technology (xyz-rainbow).

The source may be viewed and evaluated in this repository. Copying, redistribution, sublicensing, published forks, derivative works, and any commercial or production use are prohibited without prior written permission. Issues and pull requests are welcome. A GitHub fork is allowed only to prepare pull requests to this repository.

See [LICENSE](LICENSE) for the full terms, including the contribution assignment, and [CONTRIBUTING.md](CONTRIBUTING.md) if you want to send a change.
