"""Download and verify the engine's model files listed in models/manifest.json.

Usage (from the repo root):
    backend\\.venv\\Scripts\\python.exe -I scripts\\fetch_models.py [--models-dir models]

Only the pinned URLs in the manifest are used. Every download and every extracted
file is checked against its SHA-256; on any mismatch nothing is installed.
Standard library only, so it runs before the app's dependencies matter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIES = 3
CHUNK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, expected_sha256: str) -> None:
    if not url.startswith("https://"):
        raise SystemExit(f"Refusing non-HTTPS model URL: {url}")
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"  downloading {url.rsplit('/', 1)[-1]} (attempt {attempt})")
            with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as out:  # noqa: S310 — https only, checked above
                shutil.copyfileobj(response, out, CHUNK)
            actual = sha256_of(target)
            if actual != expected_sha256:
                target.unlink(missing_ok=True)
                raise SystemExit(f"Checksum mismatch for {url}: got {actual}")
            return
        except OSError as exc:
            target.unlink(missing_ok=True)
            if attempt == RETRIES:
                raise SystemExit(f"Download failed: {url}: {exc}") from exc
            time.sleep(2**attempt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models-dir", type=Path, default=REPO_ROOT / "models")
    args = parser.parse_args()
    models_dir: Path = args.models_dir.resolve()
    manifest = json.loads((models_dir / "manifest.json").read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        downloads: dict[str, Path] = {}  # one download per source URL
        for model in manifest["models"]:
            target = models_dir / model["file"]
            if target.is_file() and sha256_of(target) == model["sha256"]:
                print(f"ok      {model['name']} ({model['file']}) already installed")
                continue

            source = model["source"]
            if source["type"] != "pypi-wheel":
                raise SystemExit(f"Unknown source type {source['type']!r} for {model['name']}")
            archive = downloads.get(source["url"])
            if archive is None:
                archive = Path(tmp) / f"source-{len(downloads)}.zip"
                download(source["url"], archive, source["sha256"])
                downloads[source["url"]] = archive

            staged = Path(tmp) / model["file"]
            with zipfile.ZipFile(archive) as wheel, staged.open("wb") as out:
                out.write(wheel.read(source["member"]))
            if sha256_of(staged) != model["sha256"]:
                raise SystemExit(f"Checksum mismatch for extracted {model['name']}")
            shutil.move(str(staged), target)
            print(f"install {model['name']} -> {target}")

    print("All models installed and verified.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
