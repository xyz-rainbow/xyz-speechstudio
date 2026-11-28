## Learned User Preferences

- Prefers Spanish for conversation; code, identifiers, commits, and technical names stay English; keep Spanish docs Spanish where they already are, and README.md in English.
- Often wants the agent to refine or improve the prompt before implementing large features, and to give realistic feedback with alternatives and phased plans.
- Prefers building the Windows `.exe` at the end of a completed phase or plan, not mid-work.
- Expects the end-user installer to be the Inno Setup UI, not a raw PowerShell install tab.
- Prefers moving away from a project-root `.venv` toward managed runtime envs (`runtime/envs` / installer-managed venvs).
- Prefers CI on personal k3s runners to avoid burning GitHub-hosted minutes; keep macOS in k3s CI while treating macOS shipping as later; still code with Windows, Linux, and macOS in mind.
- Before large feature work: review open PR comments, merge related PRs in the agreed order, then continue; commit/push when explicitly asked.
- When the checkout is shared with other agents: check `git status` before editing, preserve others’ changes, and coordinate before touching shared hubs (`src/App.tsx`, `backend/orchestrator/main.py`) or out-of-scope modules.
- Destacados TTS should reflect real language coverage (drop engines from featured if English-only); for Kitten keep KittenTTS 2 and mini, not nano/pico/0.8.
- TTS capabilities (languages, quantization, voice_mode, install_mode) belong in the backend catalog as source of truth shared by Destacados Hub and Synthesize—not hardcoded in React.
- Prefers CrispASR as the multi-backend speech runtime path (TTS workers and STT) where applicable.
- CrispASR downloads/installer should cover CUDA and CPU builds and work with the GPU/CPU selector.

## Learned Workspace Facts

- Workspace `N:\` is **xyz-speechstudio** (Speech Studio); the same tree is also used from `Z:\[🛠️] [Tools]\xyz-speech-studio`.
- Stack is Tauri 2 + React/TypeScript + Rust shell with a Python FastAPI orchestrator; publisher Rainbow Technology; working tree targets 0.2.3.
- Remote is `github.com/xyz-rainbow/xyz-speechstudio`.
- Primary platform is Windows 10/11 x64; Ubuntu 24.04 can build/run shell + Python backend for TTS/STT; Live Captions (WASAPI loopback) and UI Automation read-selection are Windows-focused.
- Speech runtimes include CrispASR (CUDA + CPU under `runtime/bin`), unified `pytts`, and native eSpeak NG; dual-runtime cards exist for engines such as Qwen3-TTS and F5-TTS.
- Windows packaging is Inno Setup (`Setup.exe`); bootstrap uses `installer/setup-env.ps1`, `uv`, and Python 3.12 with `runtime/envs` / requirements splits.
- Preferred CI lives under `ci/k3s` rather than GitHub-hosted runners.
- Local API binding to `0.0.0.0` requires a non-empty `api_bearer_token`.
- Featured TTS direction includes engines such as F5, Kokoro, Fish, XTTS, Qwen, eSpeak NG, and Piper, with language/quant metadata driving Hub and Synthesize UX.
- Agent branches for this repo commonly use the `agent/` prefix.
