"""Fetch and verify an official CrispASR CPU release for Unix packaging."""

import argparse
import hashlib
import json
import platform
import tarfile
import urllib.request
from pathlib import Path


def fetch(destination: Path, tag: str) -> None:
    architecture = {"AMD64": "x86_64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
    if platform.system() == "Darwin":
        name = f"crispasr-macos-{architecture}.tar.gz"
    elif platform.system() == "Linux" and architecture == "x86_64":
        name = "crispasr-linux-x86_64-cpu-legacy.tar.gz"
    else:
        raise RuntimeError("No validated native CPU package for this build platform")
    request = urllib.request.Request(
        f"https://api.github.com/repos/CrispStrobe/CrispASR/releases/tags/{tag}",
        headers={"User-Agent": "SpeechStudio-Packaging"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next(row for row in release["assets"] if row["name"] == name)
    expected = asset.get("digest")
    if not isinstance(expected, str) or not expected.startswith("sha256:"):
        raise RuntimeError("Release asset has no SHA-256 digest")
    url = asset["browser_download_url"]
    if not url.startswith("https://github.com/CrispStrobe/CrispASR/releases/download/"):
        raise RuntimeError("Unexpected release asset URL")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / name
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=180) as response, archive.open("wb") as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            output.write(chunk)
            digest.update(chunk)
    if archive.stat().st_size != asset["size"] or "sha256:" + digest.hexdigest() != expected:
        archive.unlink(missing_ok=True)
        raise RuntimeError("Release asset failed integrity verification")
    with tarfile.open(archive) as package:
        package.extractall(destination / "extracted", filter="data")
    print("Official CPU runtime verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".packaging/native"))
    parser.add_argument("--tag", default="v0.8.55")
    args = parser.parse_args()
    fetch(args.output, args.tag)
