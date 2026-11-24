**English** | [Español](CONTRIBUTING.es.md)

# Contributing to Speech Studio

Thanks for taking the time to contribute. Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- Open a bug report or a feature request with the issue forms (English or Spanish).
- Start a conversation in [Discussions](https://github.com/xyz-rainbow/xyz-speechstudio/discussions) for questions and ideas.
- Send a pull request against the default branch, `main`.

Do not open a public issue for a security vulnerability. Follow [SECURITY.md](SECURITY.md).

## Development setup

The app is Windows-only today. Follow the **Requirements**, **Installation**, and **Development** sections in [README.md](README.md) to clone the repo, create the three `.venvs\` environments, and run `npm run tauri dev`.

Useful checks before you push:

```powershell
npm run build
python -m compileall backend
pytest -q
```

CI runs the frontend build, Python compile + pytest, and `cargo check` of `src-tauri` on Windows.

## Pull requests

1. Create a topic branch from `main` (for example `fix/transcriber-copy` or `docs/api-examples`).
2. Keep the change focused. Do not mix refactors with bug fixes unless they cannot be split.
3. Update [CHANGELOG.md](CHANGELOG.md) and add a line to `docs/logs/YYYY-MM.md` in the same commit when the change is user-visible or touches process/docs.
4. Keep [README.md](README.md) and [README.es.md](README.es.md) (and the two contributing guides) in sync if you change either one.
5. Never commit secrets, API keys, voice profiles, model weights, or files under `data/`.
6. Wait for CI to go green. Maintainers squash-merge into `main`.

Use the pull request template. Say what you changed, why, and how you tested it.

## Code notes

- Frontend: React 19 + TypeScript + Vite + Tailwind in `src/`. `npm run build` must pass (`tsc --noEmit` and Vite).
- Desktop shell: Rust / Tauri 2 in `src-tauri/`. This crate uses Windows APIs and will not compile on Linux or macOS.
- Backend: Python orchestrator in `backend/orchestrator/` and workers in `backend/workers/`. There is no `requirements.txt` yet; document new runtime dependencies in the README tables.
- In-app copy lives in `src/i18n/locales/en.json` and `es.json`. Keep the same key tree in both files.
- `spikes/` is historical; do not treat those scripts as the supported entrypoint.

## License

The repository does not ship a license file yet. By contributing you agree that your work can be distributed with the project under the license the maintainers later publish.
