# Known issues

- No `LICENSE` file has been published yet.
- There is no `requirements.txt` / venv bootstrap script. The three Windows venvs (`.venvs\core`, `.venvs\qwen`, `.venvs\stt`) must be created by hand. The Qwen worker imports `qwentts_cpp`, which is not pinned in this repository.
- Packaged installers (MSI / NSIS) are not built. The Tauri shell expects the source tree and those local venvs; they are not bundled in `tauri.conf.json`.
- Live Captions has a floating overlay window. Per-app WASAPI loopback capture and live transcription are not wired up yet.
- The Models catalog can list Coqui XTTS v2, NVIDIA Parakeet TDT, and Moonshine Base ONNX, but the only inference workers in the tree are Qwen (TTS) and faster-whisper (STT). There is no `xtts_worker.py`.
- GitHub Sponsors for `xyz-rainbow` may not be enabled (the sponsors URL currently redirects to the organization profile). Funding links in `.github/FUNDING.yml` still include Patreon, Ko-fi, Buy Me a Coffee, and PayPal.
