# Known issues

- `installer/requirements-core.txt`, `requirements-qwen.txt`, and `requirements-stt.txt` pin the packages used to build the current Windows venvs. `setup-env.ps1` installs them with `uv` into `.venvs/`. That script has not been run on a clean machine. Qwen depends on `realtimetts-qwen-native==0.2.0`.
- `npx tauri build` still emits MSI and NSIS bundles. Those bundles do not install the Python environments. The Inno Setup program `SpeechStudio_0.1.0_Setup.exe` is the installer that does, and it has been compiled but not executed. See [docs/app/instalador.md](../app/instalador.md).
- Live Captions routes WASAPI process-loopback audio to the selected STT (local faster-whisper or an external endpoint). A real capture session has not been tried yet. See [docs/app/live-captions.md](../app/live-captions.md).
- macOS and Linux builds are pending. The tray icon (primary click opens the menu; macOS marks it as a template) and the toasts (`notify-send` on Linux, `osascript` on macOS) are in the source so they can be tried with that future build. Only the Windows executable has been compiled. Toast text follows `settings.language` (`en` or `es`).
- The Models catalog can list Coqui XTTS v2, NVIDIA Parakeet TDT, and Moonshine Base ONNX, but the only inference workers in the tree are Qwen (TTS) and faster-whisper (STT). There is no `xtts_worker.py`.
- GitHub Sponsors for `xyz-rainbow` may not be enabled (the sponsors URL currently redirects to the organization profile). Funding links in `.github/FUNDING.yml` still include Patreon, Ko-fi, Buy Me a Coffee, and PayPal.
