# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Adopted the Rainbow Technology proprietary license (all rights reserved). Contributions are assigned to Rainbow Technology as described in LICENSE.
- Fixed README badges: native GitHub CI badge, static license/platform badges, and removed the release badge (no installable release yet).

## [0.1.0] - 2026-11-24

Initial public repository for Speech Studio, a Windows Tauri 2 desktop app for local TTS, voice cloning, and transcription.

### Added

- Desktop app (React + TypeScript + Rust sidecar + Python orchestrator) with Qwen3-TTS voice profiles, faster-whisper file transcription, model catalog, optional OpenAI-compatible local API, tray, read-selection hotkey, and VRAM meter.
- Bilingual README and contributing guides (`README.md` / `README.es.md`, `CONTRIBUTING.md` / `CONTRIBUTING.es.md`) with a language switch.
- Contributor Covenant 2.1 (`CODE_OF_CONDUCT.md`, `CODE_OF_CONDUCT.es.md`), `SECURITY.md`, issue and pull request templates, and `.github/FUNDING.yml`.
- CI workflow (frontend build, Python compile and tests, Windows `cargo check`), Dependabot, tag-based GitHub Releases, and automatic release notes (`.github/release.yml`).
- Lightweight tests for i18n key parity, default settings, catalog ids, and version alignment.
