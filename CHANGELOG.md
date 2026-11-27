# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-11-27

### Added

- Windows SAPI 5 / Loquendo catalog engine (`sapi5_engine.py`) with 32-bit, 64-bit, and OneCore voice discovery, regional dialect labels, and a Models rescan action.

### Fixed

- Fish Speech 1.5 synthesis follows the active model. A Chatterbox-tagged voice profile only provides the reference clip and no longer raises `Engine 'chatterbox' is not connected`.
- Fish Speech is no longer marked runtime-ready solely because a CrispASR binary exists.
- Live Captions stream installed CrispASR STT models and pass `model_id` on the captions socket.
- WASAPI process-loopback capture retries initialization and does not block the UI thread on the websocket connect.
- Application quit forces process exit if WebView2 teardown stalls. The captions overlay opens at the bottom of the primary monitor. The window picker is portaled above the subtitles card.
- Chained playback no longer stops after the first Kokoro section, and the gap between Qwen sections is removed by preloading the next chunk.
- F5-TTS Spanish finishes synthesis. The worker reads the reference clip with soundfile instead of TorchCodec, and preloads the bundled cuDNN so a path that contains brackets does not abort the first convolution.

## [0.2.0] - 2026-11-26

### Added

- Persistent CrispASR `--server` VRAM manager (`crispasr.py`, `supervisor.py`, `main.py`) keeping C++ TTS models warm in VRAM across Play chunks & requests (`Eject` + mutual GPU eviction + `POST /api/tts/cancel` Stop action + `spoken_disclaimer=false` with `marking_attestation` + CLI `-l <lang>` propagation).
- Real CPU formant **eSpeak NG** engine (`backend/orchestrator/espeak_engine.py`, `espeakng-loader` in `requirements-core.txt`), automatic GGUF v3 packing for all 54 **Kokoro** voices (`ef_dora`, `em_alex`, `em_santa`, EN US/UK, FR, DE, IT, PT, JA, ZH, HI), **Chatterbox Multilingual** catalog entry, and `KittenTTS 2 Mini` direct ONNX multilingual inference (`voices_<lang>.npz` + `vocab.json`).
- Unified Python TTS environment (`.venvs/pytts` / `installer/requirements-pytts.txt`) verified with Coqui XTTS v2, F5-TTS Spanish (`F5TTS_Base` + automatic `<=11s` reference clip & transcript matching), Fish Speech 1.5 (`v1.5.1`), and KittenTTS 2 Mini, plus per-model `CrispASR | Python` runtime selector on dual-runtime cards in `ModelsView.tsx`.
- Reference audio pipeline (`backend/orchestrator/audio_prep.py`): automatic 24 kHz mono conversion for cloning, inline Play/Pause reference audio preview, long-reference warning (>15s) with non-destructive **Trim to 12s** (`POST /api/profiles/{id}/trim`), engine profile counters `(0)/(1)` and automatic `Ready` status on all inline clone engines.
- Synthesize Play UI polish: shared loading-bar / `<ChunkedAudioPlayer>` slot, red/rose animated **Stop** button cancelling backend generation, continuous breathing glow + 3-bar equalizer in `FloatingPlaybackIsland.tsx`, cleaner card titles without `(CrispASR)`/`(Legacy Python)`, and download toast notifications restricted to start (0%) and completion (100%).
- Installer rebrand to **Rainbow Technology** (`Program Files\Rainbow Technology\Speech Studio`), hidden PowerShell setup window (`runhidden` + `-WindowStyle Hidden`), and unified `setup-env.ps1` bootstrap (`core` + `pytts`).
- Sentence- and word-aware TTS section chunking (`backend/orchestrator/chunking.py`) with Settings toggle and numeric slider + compact presets (`180 / 300 / 500` chars), progressive background prefetching on Play, ephemeral `data/tmp/play_session/` temp cleanup, Smart Save concatenation into `outputs_dir`, custom Smoked Glass `ChunkedAudioPlayer.tsx` (timeline buffer, seek, volume/mute, cyclic speed `0.75x–3x`), and lime-green `FloatingPlaybackIsland.tsx` when navigating away from `Synthesize`.
- Native CrispASR voice-cloning catalog models (`Chatterbox Turbo`, `CosyVoice3 0.5B`, `IndexTTS 1.5`, `Orpheus 3B`), Whisper/Canary/SenseVoice/Qwen3-TTS CrispASR routing (`crispasr.py`), `Ready` / `Not ready` Model Hub detection with default `Ready` filter and optional official CrispASR GGUF conversion hook, plus architecture research in `docs/crispasr-research.md`.
- Explicit clear (`×`) buttons in `TranscriberView`, `ProfilesView`, and `SubtitlesView`, plus persistent tab state across navigation.

### Changed

- Fixed main window size at `880×580` (`resizable: false`, `maximizable: false`), removed redundant top tab title/subtitle headers, and reordered Settings (`General & System` → `Storage Paths` with `outputs_dir` first → `Split Text into Sections` → `Live Captions` → `Appearance` → `Advanced`).

### Fixed

- Fixed Live Captions (`list_audio_apps`) deadlock and app crash on Windows by moving window scanning onto `tauri::async_runtime::spawn_blocking`, skipping Speech Studio's own PID, and skipping hung windows via `IsHungAppWindow`.

- Redesigned local model manager: `Models` shows only installed local models and active downloads with a unified `(+)` modal featuring three paginated tabs — **Featured** (one grouped card per family with inline variant & quantization selectors), **Explore Hub** (live Hugging Face search with file inspection), and **Import** (Hugging Face / ModelScope / direct URLs plus local folder or file import). Added Fish Audio to the catalog metadata.
- Global `speechstudio` terminal CLI (`backend/cli/main.py`, `scripts/speechstudio.cmd`, `scripts/speechstudio`): connects to a running Speech Studio backend via `data/runtime.json` or starts a temporary headless orchestrator that cleans up on exit across Windows, Linux, and macOS (`play`, `status`/`inspect`, `models`, `profiles`, `transcribe`, `config`, `endpoints`, shorthands `--models`/`--status`/`--profiles`/`--config`/`--endpoints`, and `--json`).
- Discord-style paginated 2×2 window picker (`WindowPickerModal.tsx`) for Live Captions with side page arrows, bottom pagination dots, app icons, and live window thumbnail previews across Windows (`PrintWindow`), Linux X11 (`wmctrl` + ImageMagick `import`), and macOS (`CGWindowListCopyWindowInfo` + `screencapture`/`sips`).
- Native cross-platform file & folder picker (`dialogs.rs` via `rfd`) restoring reliable `Select Audio` / folder dialogs without COM parent-HWND stalls.
- Close confirmation popup (`CloseConfirmModal.tsx`) with stacked lime-green **Minimize App** (`Minimizar la App`) and red **Close & Shut Down** (`Cerrar y Apagar`) actions plus optional `"Remember my choice"`, paired with a single-line system autostart (`ON | OFF`) toggle in Settings (`autostart.rs` supporting Windows `Run` + Task Manager `StartupApproved`, Linux `.desktop`, and macOS `LaunchAgents`).
- Unified Glass model dropdowns in Synthesize and Transcriber with `Local` and `External` (`Externo`) sections, provider + model subtitles on external endpoints, automatic `tts_source` / `stt_source` switching, and honest empty-state labels when no local model or external endpoint is configured.
- Created and verified `.venvs/xtts` (`coqui-tts==0.28.0`, `torch==2.15.0+cu132`, `torchaudio==2.11.1+cu132`, `torchcodec==0.17.0+cu132`) with `xtts_worker.py` `/health` check.

### Changed

- Removed hardcoded external model directory scanning (`FALLBACK_QWEN_DIR`), automatic Mario seed profile creation (`ensure_mario_imported`), and the default Mario placeholder text in `Synthesize` so the app begins with zero preloaded models, profiles, or endpoints like a clean fresh install.
- XTTS writes WAV at `output_sample_rate` (24000 Hz for the catalog checkpoint), splits text that would pass the 400-token limit, and returns the worker's 4xx status. The worker does not set `COQUI_TOS_AGREED`.
- XTTS v2 worker (`backend/workers/xtts_worker.py`) and `POST /api/workers/xtts/load`. A profile with engine `xtts` synthesizes from its reference wav. The Synthesize model list enables XTTS and shows profiles of the selected engine. `requirements-xtts.txt` pins `coqui-tts==0.28.0`; `setup-env.ps1` also installs PyTorch with `--torch-backend=auto`. The environment was not created and a synthesis was not heard. Checkpoint weights stay out of the repo (Coqui Public Model License).
- CI links the Linux Tauri shell on Ubuntu 24.04 (`cargo build --locked`, debug) and typechecks macOS (`cargo check` and clippy). There is still no AppImage, `.deb`, or macOS bundle, and those desktops were not launched.
- Linux tray: the primary click shows the main window and still opens the menu. The existing Open Speech Studio item is unchanged. Close-to-tray and quit-stops-backend were already cross-platform. Ubuntu was not tried.
- Linux live captions list playback streams with `pactl` and capture one of them with `parec --monitor-stream` at 16 kHz mono s16le, using the same 100 ms WebSocket protocol as Windows. A PipeWire or PulseAudio session was not heard.
- Linux read-selection uses only the primary selection (`wl-paste --primary`, then `xclip -selection primary`). There is no clipboard fallback. Missing tools show a translated message. A real Wayland or X11 selection was not read from this machine.
- On Linux, `live_captions_supported` and `read_selection_supported` are both true.
- Linux (Ubuntu 24.04) development path: Tauri `cargo check`/`clippy` in CI, Unix Python venv paths (`.venvs/<name>/bin/python`), process-group orchestrator lifecycle, and README/CONTRIBUTING setup notes.
- `BackendInfo` flags `live_captions_supported` and `read_selection_supported` so the UI can disable Windows-only features on other platforms.

### Fixed

- Fixed Windows WASAPI process-loopback Live Captions failing with `E_NOTIMPL` on `GetMixFormat()` by initializing `IAudioClient` with an explicit 16 kHz / 48 kHz PCM `WAVEFORMATEX` and `AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`.
- Fixed tray Exit button and clean process/tray teardown (`shutdown_and_exit`), plus Linux/macOS CLI playback (`paplay`/`pw-play`/`aplay`/`ffplay`/`afplay`) and POSIX process-group cleanup.
- Linux live captions keep one row per sink-input. A process with several streams is chosen by that stream's index, and stop signals `parec` as soon as its process id is published. A PipeWire or PulseAudio session was not heard.

### Changed

- `windows` / `windows-core` are Windows-only Cargo dependencies; `selection`, `audio_capture`, and sidecar Job Objects are gated with stubs on Linux/macOS.

## [0.1.0] - 2026-11-24

Initial public repository for Speech Studio, a Windows Tauri 2 desktop app for local TTS, voice cloning, and transcription.

### Added

- Desktop app (React + TypeScript + Rust sidecar + Python orchestrator) with Qwen3-TTS voice profiles, faster-whisper file transcription, model catalog, optional OpenAI-compatible local API, tray, read-selection hotkey, and VRAM meter.
- Bilingual README and contributing guides (`README.md` / `README.es.md`, `CONTRIBUTING.md` / `CONTRIBUTING.es.md`) with a language switch.
- Contributor Covenant 2.1 (`CODE_OF_CONDUCT.md`, `CODE_OF_CONDUCT.es.md`), `SECURITY.md`, issue and pull request templates, and `.github/FUNDING.yml`.
- CI workflow (frontend build, Python compile and tests, Windows `cargo check`), Dependabot, tag-based GitHub Releases, and automatic release notes (`.github/release.yml`).
- Lightweight tests for i18n key parity, default settings, catalog ids, and version alignment.
- Live captions channel: one Windows process tree is captured and sent to the selected STT (local faster-whisper or an external endpoint). Window picker includes titled windows and hidden WinUI tray windows.
- Desktop toasts follow `settings.language` (`en` or `es`) for play, save, delete, captions, profiles, transcription, model load, eject, and remove.
- Inno Setup installer under `installer/windows/`, using the xyz-installer artwork. Default directory is `Program Files\XYZ-Productions\Speech Studio`. `setup-env.ps1` can create the `core`, `qwen`, and `stt` uv environments.
- Physical-key read hotkey (`KeyboardEvent.code` plus modifiers).

### Changed

- Adopted the Rainbow Technology proprietary LICENSE. Contributions are assigned to Rainbow Technology as described in that file.
- Set package, crate, and project license metadata to that LICENSE. README badges say Proprietary.

### Does not work yet

- A real WASAPI live-caption session has not been heard.
- XTTS v2, Parakeet, and Moonshine do not run.
- The Inno Setup program has not been installed on a clean machine. The XTTS environment is not created. Tauri MSI and NSIS bundles do not install Python.
- macOS and Linux builds do not exist. Tray and toasts for those systems are untested.
- UI languages other than English and Spanish are absent.

The Windows release workflow builds and attaches `SpeechStudio_0.1.0_Setup.exe`. That program has not been installed on a clean machine.

The published note for this tag is [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md).
