"""Sync or verify the Speech Studio version across all project files.

Single source of truth:
  - By default, reads the version from ``src-tauri/tauri.conf.json``.
  - With ``--version X.Y.Z``, sets that version in all tracked files.
  - With ``--check``, verifies all tracked files match without modifying them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")

TAURI_CONF = ROOT / "src-tauri" / "tauri.conf.json"
PACKAGE_JSON = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
BACKEND_VERSION = ROOT / "backend" / "orchestrator" / "__init__.py"
CARGO_TOML = ROOT / "src-tauri" / "Cargo.toml"
LOCALE_EN = ROOT / "src" / "i18n" / "locales" / "en.json"
LOCALE_ES = ROOT / "src" / "i18n" / "locales" / "es.json"
CONFIG_ISS = ROOT / "installer" / "windows" / "config.iss"
INFO_BEFORE = ROOT / "installer" / "windows" / "texts" / "info_before.txt"
EULA_EN = ROOT / "installer" / "windows" / "texts" / "eula_en.txt"
EULA_ES = ROOT / "installer" / "windows" / "texts" / "eula_es.txt"


def normalize_version(raw: str) -> str:
    ver = raw.strip()
    if ver[:1] in {"v", "V"}:
        ver = ver[1:]
    if not SEMVER_RE.match(ver):
        raise ValueError(f"Invalid version {raw!r}; expected X.Y.Z or X.Y.Z-pre")
    return ver


def read_tauri_version() -> str:
    data = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    return normalize_version(str(data["version"]))


def _sync_json_key(path: Path, keys: tuple[str, ...], value: str, check_only: bool) -> str | None:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    node = data
    for k in keys[:-1]:
        node = node[k]
    current = node.get(keys[-1])
    if current == value:
        return None
    if check_only:
        return f"{path.relative_to(ROOT)}: {'.'.join(keys)} is {current!r}, expected {value!r}"
    node[keys[-1]] = value
    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + trailing, encoding="utf-8")
    return None


def _sync_regex(
    path: Path,
    pattern: re.Pattern[str],
    replacement: str,
    expected_extract: str,
    label: str,
    check_only: bool,
) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = pattern.search(text)
    if not match:
        return f"{path.relative_to(ROOT)}: pattern for {label} not found"
    current = match.group(2)
    if current == expected_extract:
        return None
    if check_only:
        return f"{path.relative_to(ROOT)}: {label} is {current!r}, expected {expected_extract!r}"
    updated = pattern.sub(replacement, text, count=1)
    path.write_text(updated, encoding="utf-8")
    return None


def sync_all(version: str, check_only: bool) -> list[str]:
    errors: list[str] = []

    for err in (
        _sync_json_key(TAURI_CONF, ("version",), version, check_only),
        _sync_json_key(PACKAGE_JSON, ("version",), version, check_only),
        _sync_json_key(PACKAGE_LOCK, ("version",), version, check_only),
        _sync_json_key(PACKAGE_LOCK, ("packages", "", "version"), version, check_only),
        _sync_regex(
            BACKEND_VERSION,
            re.compile(r'(?m)^(__version__ = ")([^"]+)(")'),
            rf"\g<1>{version}\g<3>", version, "backend version", check_only,
        ),
        _sync_json_key(LOCALE_EN, ("app", "phaseBadge"), f"v{version}", check_only),
        _sync_json_key(LOCALE_ES, ("app", "phaseBadge"), f"v{version}", check_only),
        _sync_regex(
            CARGO_TOML,
            re.compile(r'(?ms)(\[package\].*?^version\s*=\s*")([^"]+)(")'),
            rf"\g<1>{version}\g<3>",
            version,
            "[package].version",
            check_only,
        ),
        _sync_regex(
            CONFIG_ISS,
            re.compile(r'(?m)^(\s*#define\s+MyAppVersion\s+")([^"]+)(")'),
            rf"\g<1>{version}\g<3>",
            version,
            "MyAppVersion",
            check_only,
        ),
        _sync_regex(
            INFO_BEFORE,
            re.compile(r"(?m)^(\s*Version\s+\.+:\s*)(\S+)"),
            rf"\g<1>{version}",
            version,
            "Version",
            check_only,
        ),
        _sync_regex(
            EULA_ES,
            re.compile(r"(SPEECH STUDIO v)(\S+)(\s*\[)"),
            rf"\g<1>{version}\g<3>",
            version,
            "EULA ES version",
            check_only,
        ),
        _sync_regex(
            EULA_EN,
            re.compile(r"(SPEECH STUDIO v)(\S+)(\s*\[)"),
            rf"\g<1>{version}\g<3>",
            version,
            "EULA EN version",
            check_only,
        ),
    ):
        if err:
            errors.append(err)

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync or check Speech Studio version across project files.")
    parser.add_argument("--version", help="Target version (e.g. 0.1.1 or v0.1.1). Defaults to tauri.conf.json.")
    parser.add_argument("--check", action="store_true", help="Verify all files match without modifying them.")
    args = parser.parse_args(argv)

    version = normalize_version(args.version) if args.version else read_tauri_version()
    errors = sync_all(version, check_only=args.check)
    if errors:
        for err in errors:
            print(f"[version-mismatch] {err}", file=sys.stderr)
        return 1

    action = "verified" if args.check else "synced"
    print(f"Version {version} {action} across all project files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
