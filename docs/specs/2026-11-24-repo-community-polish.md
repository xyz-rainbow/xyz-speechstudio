# Spec: repository community polish

Date: 2026-11-24

## 1. Context & Goal

Mario asked, literally:

> Ponme bien este repo, en ingles y español el readme segun lang del usuario si es posible, y traduce la descripción, ponle tags, badges, sponsor, etc..

and then:

> Prepara el CI, los issues, el colab para colaboraciones, releases tambien, etc..

The repository `xyz-rainbow/xyz-speechstudio` is a Windows Tauri 2 desktop app (React/TypeScript + Rust sidecar + Python FastAPI workers) for local TTS (Qwen3-TTS) and STT (faster-whisper). It had no README, license, CI, topics, or community files. It is not on the highlighted-repos list.

GitHub cannot pick a README from the browser language, so the deliverable is `README.md` (English) plus `README.es.md` (Spanish) with a language switch at the top, plus community, CI, and release scaffolding that matches the real stack. Documentation must not invent features that are not in the tree.

## 2. Decisions

- 2026-11-24, Mario: bilingual README “según lang del usuario si es posible”; translated description; tags, badges, sponsor.
- 2026-11-24, Mario: CI, issues, collaboration setup, releases.
- 2026-11-24, Code Assist: language switch in the documents themselves (`English | Español`), not a browser-selected README.
- 2026-11-24, Code Assist: `.github/FUNDING.yml` copies the format used by ollama-run / xyz-dashboard (`github: [xyz-rainbow]` plus Patreon, Ko-fi, Buy Me a Coffee, PayPal).
- 2026-11-24, Code Assist: no `LICENSE` file is added (Mario did not choose a license). The README states that none has been published; there is no license badge.
- 2026-11-24, Code Assist: CI is split — frontend build on Ubuntu, Python compile + pytest on Ubuntu, `cargo check` of `src-tauri` on `windows-latest` because the crate uses Windows APIs.
- 2026-11-24, Code Assist: tag-triggered GitHub Release (`v*`) with `.github/release.yml` notes, not release-please and not Tauri installer artifacts (the Python venvs are not bundled).
- 2026-11-24, Code Assist: first GitHub release `v0.1.0` only after this work is squash-merged and CI on `main` is green. The app version is already `0.1.0`.

## 3. Design

- Docs: `README.md`, `README.es.md`, `CONTRIBUTING.md`, `CONTRIBUTING.es.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1) and `CODE_OF_CONDUCT.es.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/logs/`, this spec, `docs/roadmap/known-issues.md`.
- GitHub: issue forms (bug and feature, EN+ES), `config.yml`, `PULL_REQUEST_TEMPLATE.md`, Dependabot (npm, cargo, github-actions), Discussions, basic labels.
- Repo metadata: bilingual description (`EN … · ES …`), 15 topics, no homepage.
- Workflows: `.github/workflows/ci.yml`, `.github/workflows/release.yml`.
- Tests added only as lightweight guards (i18n key parity, default settings, catalog ids, version alignment). No model-backed e2e.

## 4. Risks & Rollback

- Rust CI may fail on `windows-latest` if NVML or Tauri build dependencies are missing on the runner. If that happens, the failure is fixed on the same branch with a follow-up commit (no force-push). Rollback is a revert of the squash commit; no data or production deploy is involved.
- GitHub Sponsors for `xyz-rainbow` may be inactive; the badge is still added as requested and the limitation is recorded in the known issues and the report.
- Enabling Discussions and setting description/topics/labels are repo settings, not branch content. They can be changed later from the GitHub UI or `gh`.

## 5. PR Plan

One documentation and metadata PR against `main`, squash-merged when CI is green. After merge and green CI on `main`, push tag `v0.1.0` so the release workflow publishes the first GitHub Release.

## 6. Acceptance & Tests

- README pair covers what the app is, features that exist, install, usage, configuration, contributing, license, and sponsor, with a language switch and real shields.io badges.
- `pytest -q` and `npm run build` pass locally and in CI. Rust `cargo check` runs on Windows.
- Description, topics, FUNDING.yml, community templates, and Discussions are in place.
- First release `v0.1.0` is created only after CI on `main` is green.

## 7. Out of Scope

- Choosing and adding a license.
- Writing `requirements.txt` or a venv bootstrap script.
- Implementing WASAPI live captions, XTTS/Parakeet/Moonshine workers, or a packaged installer.
- Activating GitHub Sponsors on the organization account (needs Mario in the GitHub billing/sponsors UI).
