"""Package the build interpreter and core dependencies for offline installation.

Run using a dedicated Python build environment backed by python-build-standalone.
The resulting runtime uses its own standard library and site-packages.
"""

import argparse
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


def package_runtime(destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    base = Path(sys.base_prefix)
    source_packages = Path(sysconfig.get_path("purelib"))
    # Standalone builds include their relocation metadata and shared libraries.
    if not (base / "BUILD").exists() and not (base / "PYTHON.json").exists():
        raise RuntimeError("Use a uv-managed standalone Python build to package the runtime.")
    shutil.copytree(base, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), symlinks=True)
    relative_packages = Path("Lib/site-packages") if sys.platform == "win32" else Path(f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    shutil.copytree(source_packages, destination / relative_packages, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    python = destination / ("python.exe" if sys.platform == "win32" else "bin/python3")
    subprocess.run([str(python.resolve()), "-I", "-c", "import fastapi, uvicorn, httpx, espeakng_loader, multipart, faster_whisper"], check=True)
    print("Standalone core runtime ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    package_runtime(parser.parse_args().output)
