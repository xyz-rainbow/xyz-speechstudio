**English** | [Español](README.es.md)

# Speech Studio

Local Windows desktop app for text-to-speech, voice cloning, and transcription — published by **Rainbow Technology**.

[![CI](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml/badge.svg)](https://github.com/xyz-rainbow/xyz-speechstudio/actions/workflows/ci.yml) [![Release v0.2.1](https://img.shields.io/badge/release-v0.2.1-39ff14?style=flat-square)](https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.1) [![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red?style=flat-square)](LICENSE) [![Windows](https://img.shields.io/badge/platform-Windows-0078d4?style=flat-square&logo=windows&logoColor=white)](https://www.microsoft.com/windows) [![Tauri](https://img.shields.io/badge/Tauri-2-24c8db?style=flat-square&logo=tauri&logoColor=white)](https://tauri.app/) [![Python](https://img.shields.io/badge/Python-3.12-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

Speech Studio `v0.2.1` is a [Tauri 2](https://tauri.app/) desktop shell (React + TypeScript + Rust) paired with a Python FastAPI orchestrator, bundled **[CrispASR](https://github.com/CrispStrobe/CrispASR)** (C++/CUDA & CPU, persistent `--server` VRAM mode), a unified **`pytts`** Python environment, and native CPU **eSpeak NG** (`espeakng-loader`). Windows 10/11 (x64) is the primary platform; **Ubuntu 24.04** can build and run the shell plus Python backend for TTS/STT development, while Live Captions, UI Automation read-selection, and Windows toasts remain Windows-only.

![Speech Studio banner](docs/assets/banner.svg)

![Speech Studio interface](docs/assets/screenshot.png)

![Architecture: Tauri shell, orchestrator, and workers](docs/assets/architecture.svg)

![Flow from bootstrap to synthesis](docs/assets/flow.svg)

## Features

- **TTS Studio (`Synthesize`)** — sentence- and word-aware section chunking with progressive background prefetching so long texts start playing faster; shared loading-bar / `<ChunkedAudioPlayer>` slot (timeline buffer, seek, volume/mute, cyclic speed `0.75x–3x`); red/rose **Stop** button cancelling backend generation (`POST /api/tts/cancel`); lime-green `FloatingPlaybackIsland` when navigating to other tabs; Smart Save WAV concatenation into `outputs_dir`; and automatic ephemeral `data/tmp/play_session/` cleanup.
- **Voice profiles (`Profiles`)** — non-destructive 24 kHz mono WAV normalization, inline reference audio Play/Pause preview, warning badge on long clips (`>15s`) with non-destructive **Trim to 12s**, per-engine profile counters `(0)/(1)`, automatic `Ready` status for inline cloning engines, and built-in Parakeet/Whisper reference transcription.
- **Transcriber** — transcribe `.wav`, `.mp3`, `.m4a`, `.flac`, or `.opus` files using local CrispASR **Parakeet TDT 0.6B v3** / **Whisper** (`faster-whisper` also supported) or external STT endpoints, returning full text + timestamped segments with auto language detection and an explicit clear (`×`) action.
- **Live Captions (`Subtitles`)** — Discord-style paginated `2×2` window picker (`WindowPickerModal`), safe window enumeration (`spawn_blocking` + `IsHungAppWindow`), Windows WASAPI process-loopback PCM capture, and an overlay streaming captions from the selected STT backend.
- **Models & Hub** — grouped **Featured** catalog with inline variant/quantization selectors, **Explore Hub** live Hugging Face search with `Ready` compatibility filter, **Import** from Hugging Face / ModelScope / direct URLs / local files, and per-model **`CrispASR | Python`** runtime toggles on dual-runtime cards (`Qwen3-TTS`, `F5-TTS`).
- **Global CLI (`speechstudio`)** — connects to a running backend via `data/runtime.json` or spins up a temporary headless orchestrator (`play`, `status`, `models`, `profiles`, `transcribe`, `config`, `endpoints`, `--json`).
- **Optional OpenAI-compatible Local API & External Endpoints** — `POST /v1/audio/speech` and `POST /v1/audio/transcriptions` (`127.0.0.1` or `0.0.0.0` with required Bearer token), plus presets for OpenAI, Groq, ElevenLabs, and Deepgram with connection testing and cURL snippet generation.
- **Windows desktop shell** — fixed non-resizable `880×580` window, system tray, close confirmation popup (**Minimize App** vs **Close & Shut Down**), single-line system autostart toggle, NVIDIA VRAM meter, GPU/CPU device toggles, global UI Automation read-selection hotkey, persistent tab state, and start (`0%`) / completion (`100%`) download toast alerts via `scripts/notify.ps1`.

### Supported TTS Engines (`v0.2.1`)

10 local TTS engines verified end-to-end with real audio synthesis and NVIDIA Parakeet transcription:

| Runtime | Engines | Notes |
| --- | --- | --- |
| **CrispASR** (C++/CUDA & CPU `--server`) | **Qwen3-TTS** (`1.7B Base`, `0.6B Base`, `CustomVoice`), **Kokoro 82M** (54 voices auto-packed to GGUF v3), **Piper**, **Chatterbox Turbo**, **CosyVoice3 0.5B** | Stays warm in VRAM across Play calls; frees VRAM immediately on **Eject**; `Chatterbox Multilingual`, `F5-TTS GGUF F16`, `IndexTTS 1.5`, and `Orpheus 3B` are also cataloged |
| **Unified `pytts`** (`.venvs/pytts` / `runtime/envs/pytts`) | **Coqui XTTS v2**, **F5-TTS Spanish** (`F5TTS_Base` + automatic `<=11s` reference clip & transcript matching), **Fish Speech 1.5** (`v1.5.1`), **KittenTTS 2 Mini** (ONNX + multilingual `voices_<lang>.npz`) | Runs all four Python engines in a single environment |
| **Native CPU** | **eSpeak NG** (`espeak-ng.dll` via `espeakng-loader` / `ctypes`) | Runs directly inside the `core` orchestrator without external servers |
| **Windows SAPI 5** | **SAPI 5 / Loquendo**, IVONA, and OneCore voices | Uses voices already installed on Windows, including regional dialects |

## Requirements

- Windows 10 or 11 (x64). Inno Setup package: **`SpeechStudio_0.2.1_Setup.exe`** ([GitHub Releases `v0.2.1`](https://github.com/xyz-rainbow/xyz-speechstudio/releases/tag/v0.2.1)), publisher **Rainbow Technology**, default install directory `C:\Program Files\Rainbow Technology\Speech Studio` (plus Portable Mode).
- Bundled CrispASR CUDA (`cuda/`) and CPU (`cpu/`) binaries under `runtime/bin/` (`scripts/fetch-crispasr.ps1`).
- [`uv`](https://docs.astral.sh/uv/) and 64-bit Python 3.12 (for `installer/setup-env.ps1` creating `runtime/envs/core` and `runtime/envs/pytts`).
- From source only: [Node.js](https://nodejs.org/) 20+, Rust stable, and [Tauri 2 Windows prerequisites](https://v2.tauri.app/start/prerequisites/).
- Optional: NVIDIA GPU + driver (`nvidia-smi` / NVML) for GPU acceleration & VRAM meter; [BurntToast](https://github.com/Windos/BurntToast) PowerShell module for desktop toast notifications.

### Linux (Ubuntu 24.04) — development

Install [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for Linux:

```bash
sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

`installer/setup-env.ps1` is Windows-only. On Linux, create `core` and `pytts` with `uv` (`bin/python` instead of `Scripts/python.exe`):

```bash
uv venv --python 3.12 runtime/envs/core
uv pip install --python runtime/envs/core/bin/python -r installer/requirements-core.txt

uv venv --python 3.12 runtime/envs/pytts
uv pip install --python runtime/envs/pytts/bin/python torch torchaudio --torch-backend=auto
uv pip install --python runtime/envs/pytts/bin/python -r installer/requirements-pytts.txt
```

Then run `npm install` and `npm run tauri dev`. On Unix, the Rust sidecar manages a process group instead of Windows Job Objects and uses `notify-send` when notifications are enabled.

## Installation (Windows from Source)

```powershell
git clone https://github.com/xyz-rainbow/xyz-speechstudio.git
cd xyz-speechstudio
npm install
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\setup-env.ps1 -AppRoot (Get-Location).Path
```

`setup-env.ps1` creates the two runtime environments under `runtime\envs\` (local dev trees also detect `.venvs\`):

| Venv | Requirements | Used for |
| --- | --- | --- |
| `runtime\envs\core` | `installer/requirements-core.txt` | Orchestrator (`backend.orchestrator.main`) + native CPU **eSpeak NG** |
| `runtime\envs\pytts` | PyTorch + `installer/requirements-pytts.txt` | Unified Python TTS venv (**XTTS v2**, **F5-TTS**, **Fish Speech 1.5**, **KittenTTS 2 Mini**) |

Model weights are not committed to git and are downloaded cleanly from the in-app **Models** (`+`) modal (`Featured`, `Explore Hub`, `Import`).

## Usage

```powershell
npm run tauri dev
```

1. Open **Models**, click **`+`**, and download a TTS model (for example **Qwen3-TTS**, **Kokoro 82M**, **XTTS v2**, or **F5-TTS Spanish**) and an STT model (**Parakeet TDT 0.6B v3** or **faster-whisper**).
2. Open **Profiles** for voice-cloning models, choose a reference audio clip (with optional inline preview and non-destructive 12s trim), and transcribe/save the profile.
3. Open **Synthesize**, select the model and voice/profile, type or paste text, and click **Play** (or **Stop** to cancel) or **Save** (exports WAV to `outputs_dir`).
4. Open **Transcriber** for audio-to-text, or **Subtitles** to stream Live Captions from a selected desktop app.

Closing the window opens the **Close Confirmation** dialog (**Minimize App** to tray or **Close & Shut Down**). The app enforces a single instance and focuses the active window if launched again.

### Local API

In **Settings**, enable *Serve Local OpenAI-Compatible API* (`127.0.0.1` or `0.0.0.0` with a required Bearer token):

```powershell
curl.exe -X POST "http://127.0.0.1:<port>/v1/audio/speech" `
  -H "Authorization: Bearer <token>" `
  -H "Content-Type: application/json" `
  -d "{\"input\":\"Hello\",\"voice\":\"<profile-id>\",\"response_format\":\"wav\"}" `
  --output speech.wav

curl.exe -X POST "http://127.0.0.1:<port>/v1/audio/transcriptions" `
  -H "Authorization: Bearer <token>" `
  -F "file=@audio.wav" `
  -F "model=parakeet-tdt-0.6b-v3-gguf"
```

## Configuration

Settings live in `data/settings.json` (created on first run):

| Key | Meaning |
| --- | --- |
| `language` | UI language: `en` or `es` |
| `theme`, `accent` | `dark` / `light` and neon accent (`cyber`, `emerald`, `amber`, `rose`) |
| `models_dir`, `outputs_dir` | Custom folders; empty uses `data/models` and `data/outputs` |
| `chunking_enabled`, `chunking_max_chars` | Split long TTS inputs into Play sections (`180 / 300 / 500` presets or slider) |
| `model_runtimes` | Per-model runtime preference (`crispasr` or `python`) on dual-runtime models |
| `tts_device`, `stt_device` | `gpu` or `cpu` |
| `tts_source`, `stt_source` | `local` or `endpoint` |
| `active_tts_model`, `active_stt_model` | Catalog model ids |
| `api_endpoint_enabled`, `api_bind_host`, `api_fixed_port`, `api_bearer_token` | OpenAI-compatible Local API |
| `read_hotkey` | Global UI Automation “read selection” accelerator |
| `notifications_enabled` | Windows toast notifications |
| `external_endpoints` | Saved external TTS/STT endpoint presets |

Do not commit `data/`, voice profiles, API keys, or model weights; they are ignored by `.gitignore`.

## Development

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite UI only (`http://localhost:1420`) |
| `npm run build` | TypeScript check (`tsc --noEmit`) + Vite production bundle |
| `npm run tauri build --no-bundle` | Build `src-tauri/target/release/speech-studio.exe` |
| `.\installer\windows\build.ps1` | Package Inno Setup `installer/Output/SpeechStudio_<ver>_Setup.exe` |
| `python scripts/sync_version.py --check` | Verify synced version across Tauri, npm, Cargo, locales, and Inno Setup |
| `python -m compileall backend` | Syntax-check orchestrator and workers |

## Documentation

- [CHANGELOG.md](CHANGELOG.md) — full change history (`v0.2.1`).
- [docs/releases/v0.2.1.md](docs/releases/v0.2.1.md) — `v0.2.1` release notes.
- [docs/crispasr-research.md](docs/crispasr-research.md) — compatibility research across CrispASR C++ backends and unified `pytts`.
- [docs/README.md](docs/README.md) — community spec, known issues, and app notes.

## Contributing

Issues, discussions, and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). Security reports go through [SECURITY.md](SECURITY.md), not public issues.

## Sponsor

If the project is useful, you can [sponsor xyz-rainbow](https://github.com/sponsors/xyz-rainbow). Other platforms are listed in [`.github/FUNDING.yml`](.github/FUNDING.yml).

## License

Proprietary — all rights reserved. Copyright (c) 2026 Rainbow Technology (xyz-rainbow).

The source may be viewed and evaluated in this repository. Copying, redistribution, sublicensing, published forks, derivative works, and any commercial or production use are prohibited without prior written permission. Issues and pull requests are welcome. A GitHub fork is allowed only to prepare pull requests to this repository.

See [LICENSE](LICENSE) for the full terms, including the contribution assignment, and [CONTRIBUTING.md](CONTRIBUTING.md) if you want to send a change.
