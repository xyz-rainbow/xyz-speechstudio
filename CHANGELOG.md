# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Linux read-selection uses only the primary selection (`wl-paste --primary`, then `xclip -selection primary`). There is no clipboard fallback. Missing tools show a translated message. `read_selection_supported` is true on Linux. A real Wayland or X11 selection was not read from this machine.
- Linux (Ubuntu 24.04) development path: Tauri `cargo check`/`clippy` in CI, Unix Python venv paths (`.venvs/<name>/bin/python`), process-group orchestrator lifecycle, and README/CONTRIBUTING setup notes.
- `BackendInfo` flags `live_captions_supported` and `read_selection_supported` so the UI can disable Windows-only features on other platforms.

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
