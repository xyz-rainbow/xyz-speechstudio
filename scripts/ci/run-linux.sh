#!/usr/bin/env bash
# Homelab / k3s CI entrypoint (Linux). Mirrors .github/workflows/ci.yml jobs.
# macOS is intentionally not run here; keep writing portable Rust/TS/Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== frontend =="
npm ci
npm run build

echo "== python =="
python3 -m pip install --upgrade pip
python3 -m pip install pydantic fastapi httpx huggingface_hub pytest
python3 -m compileall -q backend
python3 -m pytest -q

echo "== rust (linux) =="
cd src-tauri
cargo check --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --locked
echo "CI linux OK"
