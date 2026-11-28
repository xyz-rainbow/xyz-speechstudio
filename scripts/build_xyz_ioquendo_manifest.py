#!/usr/bin/env python3
"""Build xyz-Ioquendo manifests from the reference tree (read-only on originals).

Examples:
  python scripts/build_xyz_ioquendo_manifest.py --vertical
  python scripts/build_xyz_ioquendo_manifest.py --source "Z:/.../xyz-Ioquendo" --full
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.orchestrator import voice_packs as vp  # noqa: E402


def ffprobe_duration(path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return round(float(proc.stdout.strip()), 3)
    except ValueError:
        return None


def enrich_durations(manifest: dict, root: Path) -> None:
    for voice in manifest.get("voices") or []:
        audio = root / voice["audio_relpath"]
        probed = ffprobe_duration(audio) if audio.is_file() else None
        if probed is not None:
            voice["duration_s"] = probed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Original xyz-Ioquendo locale tree (read-only).",
    )
    parser.add_argument("--vertical", action="store_true", help="Write vertical-slice manifest from packs/xyz-ioquendo/voices.")
    parser.add_argument("--full", action="store_true", help="Scan --source and write full manifest (excludes benchmark).")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "packs" / "xyz-ioquendo",
        help="Output directory for manifests.",
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.vertical or not args.full:
        data = vp.build_vertical_manifest_from_bundle(out_dir)
        enrich_durations(data, out_dir)
        path = out_dir / "manifest.vertical.v1.json"
        vp.write_manifest(path, data)
        print(json.dumps({"wrote": str(path), "voices": data["voice_count"], "locales": data["locales"]}, ensure_ascii=False))

    if args.full:
        if args.source is None:
            print("--full requires --source", file=sys.stderr)
            return 2
        voices, excluded, warnings = vp.scan_source_tree(args.source)
        data = vp.build_manifest_dict(
            voices=voices,
            excluded=excluded,
            warnings=warnings,
            version="1.0.0-full-draft",
        )
        enrich_durations(data, args.source)
        path = out_dir / "manifest.full.v1.json"
        vp.write_manifest(path, data)
        report = {
            "wrote": str(path),
            "voices": data["voice_count"],
            "excluded": len(excluded),
            "warnings": len(warnings),
            "locales": data["locales"],
            "bytes": sum(v.get("size_bytes", 0) for v in voices),
        }
        print(json.dumps(report, ensure_ascii=False))
        # Never copy originals into the repo from this script.
        print("Originals left untouched; redistributable archive not published.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
