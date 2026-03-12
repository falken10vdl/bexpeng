#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a GitHub release and upload the bexpeng addon zip.

Requires the GitHub CLI (gh) to be installed and authenticated:
    gh auth login

Usage:
    python upload_release.py                # build + upload
    python upload_release.py --skip-build   # upload existing zip only
    python upload_release.py --draft        # create as draft release
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDON_DIR = ROOT / "bexpeng"
DIST_DIR = ROOT / "dist"

# Read version from __init__.py bl_info
VERSION = "0.1.0"
for line in (ADDON_DIR / "__init__.py").read_text().splitlines():
    if '"version"' in line:
        parts = line.split("(")[1].split(")")[0].split(",")
        VERSION = ".".join(p.strip() for p in parts)
        break

TAG = f"v{VERSION}"
ZIP_NAME = f"bexpeng-{VERSION}.zip"
ZIP_PATH = DIST_DIR / ZIP_NAME


def check_gh():
    """Verify gh CLI is installed and authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("Error: GitHub CLI is not authenticated.")
            print("Run: gh auth login")
            sys.exit(1)
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) is not installed.")
        print("Install it: https://cli.github.com/")
        sys.exit(1)


def check_clean_tree():
    """Warn if there are uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.stdout.strip():
        print("Warning: You have uncommitted changes:")
        print(result.stdout)
        resp = input("Continue anyway? [y/N] ").strip().lower()
        if resp != "y":
            sys.exit(0)


def build():
    """Run build_release.py to create the zip."""
    print(f"Building {ZIP_NAME}...")
    subprocess.check_call([sys.executable, str(ROOT / "build_release.py")])


def create_release(draft: bool):
    """Create a GitHub release with the addon zip attached."""
    if not ZIP_PATH.exists():
        print(f"Error: {ZIP_PATH} not found. Run without --skip-build.")
        sys.exit(1)

    print(f"\nCreating GitHub release {TAG}...")

    notes = (
        f"## BExpEng v{VERSION}\n\n"
        f"Blender Expression Engine — parametric expression system "
        f"for cross-addon parameter linking.\n\n"
        f"### Installation\n"
        f"1. Download `{ZIP_NAME}` below\n"
        f"2. In Blender: **Edit → Preferences → Add-ons → Install…**\n"
        f"3. Select the downloaded zip\n"
        f'4. Enable **"BExpEng — Blender Expression Engine"**\n\n'
        f"Dependencies (asteval, networkx) are bundled — no pip install needed."
    )

    cmd = [
        "gh",
        "release",
        "create",
        TAG,
        str(ZIP_PATH),
        "--title",
        f"BExpEng v{VERSION}",
        "--notes",
        notes,
        "--repo",
        "falken10vdl/bexpeng",
    ]
    if draft:
        cmd.append("--draft")

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("Failed to create release.")
        sys.exit(1)

    print(f"\nRelease {TAG} created successfully!")
    print(f"https://github.com/falken10vdl/bexpeng/releases/tag/{TAG}")


def main():
    parser = argparse.ArgumentParser(description="Upload bexpeng release to GitHub")
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip building the zip"
    )
    parser.add_argument("--draft", action="store_true", help="Create as draft release")
    args = parser.parse_args()

    print(f"bexpeng release uploader — v{VERSION}")
    check_gh()
    check_clean_tree()

    if not args.skip_build:
        build()

    create_release(args.draft)


if __name__ == "__main__":
    main()
