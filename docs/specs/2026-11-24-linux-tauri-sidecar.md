# Spec: Linux Tauri build and cross-platform sidecar

Date: 2026-11-24

## 1. Context & Goal

GitHub issues [#12](https://github.com/xyz-rainbow/xyz-speechstudio/issues/12) and [#13](https://github.com/xyz-rainbow/xyz-speechstudio/issues/13): build and run Speech Studio on Ubuntu 24.04 without breaking Windows (`mientras no se rompa en windows`).

Problems:

- Unconditional `windows` / `windows-core` dependencies broke `cargo check` on Linux.
- Sidecar hard-coded `.venvs/core/Scripts/python.exe` and Win32 Job Objects.
- Python `WorkerSupervisor.venv_python` was Windows-only.

## 2. Decisions

- Gate Windows APIs behind `#[cfg(windows)]`; keep every Tauri command registered with Linux/macOS stubs returning clear errors where needed.
- Unix orchestrator lifecycle: `CommandExt::process_group(0)` and `kill(-pgid)` on shutdown; Windows Job Object path unchanged.
- `BackendInfo` exposes `live_captions_supported` and `read_selection_supported` for UI gating.
- CI adds `rust-linux` on `ubuntu-24.04` with Tauri apt deps; Windows `cargo check` job renamed `rust-windows`.

## 3. Out of scope (still Windows-only)

- Live captions (WASAPI process loopback).
- Read-selection hotkey (UI Automation).
- Inno Setup installer and `setup-env.ps1` venv bootstrap.

## 4. Verification

- `cargo check` / `cargo clippy` in `src-tauri` on Ubuntu 24.04 (CI).
- `cargo check` on `windows-latest` (CI).
- `npm run build`, `pytest -q`, `python -m compileall backend`.