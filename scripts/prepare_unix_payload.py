"""Stage Unix installer resources with a standalone interpreter and native CPU engine."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from package_runtime import package_runtime


def prepare(root: Path, crispasr_dir: Path) -> None:
    payload = root / ".packaging" / "payload"
    if payload.exists():
        raise FileExistsError(f"Payload already exists: {payload}")
    payload.mkdir(parents=True)
    shutil.copytree(root / "backend", payload / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(root / "scripts", payload / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    package_runtime(payload / "runtime" / "python")
    executable = next((path for path in crispasr_dir.rglob("crispasr") if path.is_file()), None)
    if executable is None:
        raise FileNotFoundError("CrispASR executable missing from supplied runtime")
    destination = payload / "runtime" / "bin" / "cpu"
    shutil.copytree(executable.parent, destination)
    subprocess.run([str(destination / "crispasr"), "--list-backends-json"], check=True, stdout=subprocess.DEVNULL)
    print("Unix payload ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--crispasr-dir", type=Path, required=True)
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[1], args.crispasr_dir)
