#!/usr/bin/env python3
"""Smoke-check the packaged core runtime without Vite or system Python.

Usage (from a staged payload or installed app root):

  runtime\\python\\python.exe scripts\\smoke_boot_runtime.py
  # or against the repo after packaging into a temp dir

Exits 0 only if the interpreter can import orchestrator deps and resolve data dirs.
Does not download models or require a display.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REQUIRED = ("fastapi", "uvicorn", "httpx", "multipart")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
    if missing:
        print("MISSING", ",".join(missing))
        return 2
    from backend.orchestrator.paths import ensure_user_dirs, resolve_cache_dir, resolve_data_dir

    data = resolve_data_dir(root)
    cache = resolve_cache_dir(root, data_dir=data)
    ensure_user_dirs(data, cache_dir=cache)

    import backend.orchestrator.main as orch_main

    route_paths = set(orch_main.app.openapi().get("paths", {}).keys())
    expected_routes = {
        "/health",
        "/api/persona/install-remote",
        "/api/persona/local-catalog",
        "/api/tts/voice-design/status",
        "/api/voice-packs/{pack_id}",
        "/api/stt/cancel",
        "/api/updates/latest",
    }
    missing_routes = sorted(expected_routes - route_paths)
    if missing_routes:
        print("MISSING_ROUTES", ",".join(missing_routes))
        return 3

    print("ok", f"python={sys.version.split()[0]}", f"data={data}", f"cache={cache}", f"routes={len(route_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
