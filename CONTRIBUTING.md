**English** | [Español](CONTRIBUTING.es.md)

# Contributing to xyz-speechstudio

Thanks for taking the time to contribute. Windows desktop app (Tauri 2 + React/TypeScript + Python FastAPI workers) for local TTS and transcription.

## License and contributions

By opening an issue or sending a pull request you accept the contribution clause in [LICENSE](LICENSE): you assign to Rainbow Technology all rights in your contribution, or, if that assignment is not effective, you grant a perpetual, irrevocable, exclusive license, and you warrant that you have the right to contribute it.

Please do not open a public issue for a security vulnerability; use the repository Security advisory form if it is available.

## Development setup

Windows is the primary target platform. Ubuntu 24.04 is supported for building the Tauri shell and running the Python backend (see **Linux (Ubuntu 24.04)** in [README.md](README.md)). Follow **Requirements**, **Installation**, and **Development** to clone the repo, create the three `.venvs/` environments, and run `npm run tauri dev`.

Useful checks before you push:

```powershell
npm run build
python -m compileall backend
pytest -q
```

CI runs the frontend build and Python compile + pytest on Ubuntu, `cargo check` of `src-tauri` on Windows, and `cargo check` + `cargo clippy` on Ubuntu 24.04 with the Tauri apt dependencies.

## Pull requests

1. Create a topic branch from the default branch (`main`).
2. Keep the change focused.
3. Update [CHANGELOG.md](CHANGELOG.md) and add a line to `docs/logs/YYYY-MM.md` when the change is user-visible or touches process or docs.
4. Never commit secrets, API keys, or private data.
5. Wait for CI to go green when the repository has workflows. Maintainers squash-merge into the default branch.
