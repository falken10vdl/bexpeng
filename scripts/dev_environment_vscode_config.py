"""Setup bexpeng development environment and configure VS Code.

One-off setup (run once):
1. Install the bexpeng addon in Blender at least once so that the expected
   addon directory path exists (Edit → Preferences → Add-ons → Install…).
2. Run this script via the VS Code task
   "Configure bexpeng/vscode development environment", or directly:

       blender --background --python scripts/dev_environment_vscode_config.py

   This replaces the installed addon copy with a symlink pointing to the
   ``bexpeng/`` package inside this repo, so every code change is immediately
   active the next time Blender loads the addon.  It also writes
   ``.vscode/settings.json`` with the path mappings the VS Code debugger
   needs to resolve remote runtime paths back to your local source files.

   Re-run this script if you move the repo or upgrade Blender.

Per-session workflow:
1. Run the VS Code task "Launch Blender interactively" to open Blender's GUI
   with debugpy listening on port 5678.
2. Run the "Interactive+debugger" launch configuration (F5) to attach the
   debugger.  Breakpoints set in ``bexpeng/`` source files will now be hit.
3. To restart Blender after editing code, use Bonsai's operator
   (F3 → type ``bim.restart_blender``).  Then press F5 again to re-attach.

For automated testing:
- Run the VS Code task "Run Blender+testing" to execute the test suite
  headlessly.  The task completes when Blender prints ``Blender quit``.
- Use the "Pytest+debugger" launch configuration (F5) to attach mid-test.
"""

import json
import shutil
import sys
from pathlib import Path

import bpy

# repo root  →  …/bexpengDevel/
repo_root = Path(__file__).resolve().parent.parent
# The Blender-loadable package lives one level in.
addon_source = repo_root / "bexpeng"

major, minor, _ = bpy.app.version
blender_version = f"{major}.{minor}"

if sys.platform == "win32":
    blender_config = (
        Path.home() / f"AppData/Roaming/Blender Foundation/Blender/{blender_version}"
    )
elif sys.platform == "darwin":
    blender_config = (
        Path.home() / f"Library/Application Support/Blender/{blender_version}"
    )
else:
    blender_config = Path.home() / f".config/blender/{blender_version}"

install_path = blender_config / "scripts/addons/bexpeng"

assert install_path.exists() or install_path.is_symlink(), (
    f"bexpeng not found at expected path: {install_path}\n"
    "Make sure the addon is installed in Blender before running this script."
)

if install_path.is_symlink():
    current_target = install_path.resolve()
    if current_target == addon_source.resolve():
        print(f"Symlink already correct: {install_path} -> {addon_source}")
    else:
        print(f"Relinking: {install_path} -> {addon_source} (was -> {current_target})")
        install_path.unlink()
        install_path.symlink_to(addon_source, target_is_directory=True)
else:
    print(f"Replacing installed copy with symlink: {install_path} -> {addon_source}")
    shutil.rmtree(install_path)
    install_path.symlink_to(addon_source, target_is_directory=True)

settings_path = repo_root / ".vscode" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
settings.update(
    {
        "bexpeng.localRoot": addon_source.as_posix(),
        "bexpeng.remoteRoot": install_path.as_posix(),
        "bexpeng.blenderPath": Path(bpy.app.binary_path).parent.as_posix(),
    }
)
settings_path.write_text(json.dumps(settings, indent=2) + "\n")

print("\n\nbexpeng/VSCode development environment configured successfully!\n")
print(f"  localRoot  : {addon_source}")
print(f"  remoteRoot : {install_path}")
