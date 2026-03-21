#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a release zip for the bexpeng Blender addon.

The zip bundles asteval and networkx inside bexpeng/libs/ so users
don't need to pip-install anything into Blender's Python.

Usage:
    python build_release.py          # -> dist/bexpeng-0.1.0.zip
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDON_DIR = ROOT / "bexpeng"
DIST_DIR = ROOT / "dist"
LIBS_STAGE = ROOT / "_libs_stage"

# Read version from __init__.py bl_info
VERSION = "0.9.0"
for line in (ADDON_DIR / "__init__.py").read_text().splitlines():
    if '"version"' in line:
        # e.g.  "version": (0, 1, 0),
        parts = line.split("(")[1].split(")")[0].split(",")
        VERSION = ".".join(p.strip() for p in parts)
        break

ZIP_NAME = f"bexpeng-{VERSION}.zip"


def pip_download_libs():
    """Download pure-Python wheels for asteval and networkx."""
    if LIBS_STAGE.exists():
        shutil.rmtree(LIBS_STAGE)
    LIBS_STAGE.mkdir()

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(LIBS_STAGE),
            "--no-deps",
            "--only-binary=:all:",
            "asteval",
            "networkx",
        ]
    )


def build_zip():
    DIST_DIR.mkdir(exist_ok=True)
    zip_path = DIST_DIR / ZIP_NAME

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add addon source files
        for py_file in sorted(ADDON_DIR.glob("*.py")):
            arcname = f"bexpeng/{py_file.name}"
            zf.write(py_file, arcname)

        # 2. Add bundled libraries under bexpeng/libs/
        for root, dirs, files in os.walk(LIBS_STAGE):
            # Skip dist-info, __pycache__, bin, tests
            dirs[:] = [
                d
                for d in dirs
                if not d.endswith(".dist-info")
                and d != "__pycache__"
                and d != "bin"
                and d != "tests"
            ]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = Path(root) / f
                rel = full.relative_to(LIBS_STAGE)
                arcname = f"bexpeng/libs/{rel}"
                zf.write(full, arcname)

    print(f"Built {zip_path}  ({zip_path.stat().st_size / 1024:.0f} KB)")
    return zip_path


def main():
    print(f"Building bexpeng v{VERSION} release addon...")
    print("Downloading dependencies...")
    pip_download_libs()
    print("Creating zip...")
    zip_path = build_zip()

    # Cleanup
    shutil.rmtree(LIBS_STAGE)

    # List contents
    print(f"\nContents of {zip_path.name}:")
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            print(f"  {info.filename}  ({info.file_size} bytes)")

    print(
        f"\nDone! Install in Blender: Edit → Preferences → Add-ons → Install → {zip_path.name}"
    )


if __name__ == "__main__":
    main()
