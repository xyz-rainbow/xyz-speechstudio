#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_PYTTS=false
WITH_CUDA=false
for argument in "$@"; do
  case "$argument" in
    --with-pytts) WITH_PYTTS=true ;;
    --cuda) WITH_CUDA=true ;;
    --help)
      printf '%s\n' 'Usage: bash installer/setup-env.sh [--with-pytts] [--cuda]' \
        'Installs Python 3.12 core and STT environments with uv.' \
        '--with-pytts also installs the Python voice cloning engines.' \
        '--cuda includes NVIDIA libraries for Linux STT.'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'uv is required. Install uv and run this script again.' >&2
  exit 1
fi

install_environment() {
  local name="$1"
  local destination="$ROOT/runtime/envs/$name"
  local python="$destination/bin/python"
  local requirements="$ROOT/installer/requirements-$name.txt"
  printf 'Preparing %s\n' "$name"
  if [[ ! -x "$python" ]]; then
    uv venv --python 3.12 "$destination"
  fi
  if [[ "$name" == pytts ]]; then
    uv pip install --python "$python" torch torchaudio --torch-backend=auto
  fi
  if [[ "$name" == stt && "$WITH_CUDA" == false ]]; then
    requirements="$ROOT/installer/requirements-stt-cpu.txt"
  fi
  uv pip install --python "$python" -r "$requirements"
}

install_environment core
install_environment stt
if [[ "$WITH_PYTTS" == true ]]; then
  install_environment pytts
fi
printf '%s\n' 'Speech Studio environments are ready under runtime/envs.'
