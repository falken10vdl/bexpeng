"""Run bexpeng test suite from within Blender's Python.

Usage (via VS Code task or directly):
    blender --background --python scripts/run_tests.py
"""

import sys
from pathlib import Path

# Make the repo root importable so pytest can discover tests/ and bexpeng/
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import pytest  # noqa: E402

sys.exit(pytest.main([str(repo_root / "tests"), "-v"]))
