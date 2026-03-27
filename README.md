# BExpEng — Blender Expression Engine

A shared parametric expression engine for Blender. Allows addons like
[Bonsai](https://bonsaibim.org/) and
[CAD Sketcher](https://www.cadsketcher.com/) to register named
parameters and expressions so that changing one value automatically
recomputes all dependents — much like a spreadsheet or FreeCAD's
expression engine.

## Features

- **Named parameters** — register values from any addon
- **Direct value types** — numbers and quoted string literals (e.g. `"Beam A"`, `'frame_type'`); string values must be quoted in the UI value field
- **Expression binding** — attach Python-style expressions to parameters (e.g. `"2 * wall_length"`)
- **Automatic dependency resolution** — topological evaluation order via a directed acyclic graph
- **Cycle detection** — registering a circular dependency raises an error immediately
- **Safe evaluation** — expressions are evaluated with [asteval](https://lmfit.github.io/asteval/), not raw `eval()`
- **Subscriber callbacks** — addons get notified when a value they depend on changes
- **Persistence** — engine state is saved/loaded with `.blend` files
- **UI panel** — sidebar panel in the 3D Viewport for managing parameters; each row shows a link-status icon (unlinked when no addon has subscribed, linked with a subscription count when one or more addons are bound)

## Installation

### As a Blender addon

1. Download or clone this repository.
2. Install the Python dependencies into Blender's Python:
   ```bash
   # Find Blender's Python (example path — adjust for your system)
   /path/to/blender/4.x/python/bin/python3 -m pip install asteval networkx
   ```
3. In Blender: **Edit → Preferences → Add-ons → Install…** and select the
   `bexpeng/` folder (or zip it first).
4. Enable **"BExpEng — Blender Expression Engine"**.

### For development

```bash
git clone https://github.com/falken10vdl/bexpeng.git
cd bexpeng
pip install -e ".[dev]"
pytest
```

#### VS Code development environment

The repo ships a full VS Code dev environment that symlinks the source tree
directly into Blender, so every edit is live without reinstalling the addon.

**Prerequisites**

- Blender (4.0 or later) available on `PATH`
- `bexpeng` installed in Blender at least once (Edit → Preferences → Add-ons → Install…)  
- `debugpy` available in Blender's Python:
  ```bash
  /path/to/blender/4.x/python/bin/python3 -m pip install debugpy
  ```
- [Bonsai BIM](https://bonsaibim.org/) extension (optional, needed for `bim.restart_blender`)

**One-time setup**

Run the VS Code task **"Configure bexpeng/vscode development environment"**
(Terminal → Run Task), or directly:

```bash
blender --background --python scripts/dev_environment_vscode_config.py
```

This does two things:

1. Replaces the installed addon copy inside Blender's config directory with a
   symlink pointing to `bexpeng/` in this repo, so Blender always loads your
   working tree.
2. Writes `.vscode/settings.json` with the path mappings the debugger needs to
   resolve Blender's runtime paths back to your local source files.

Re-run this script if you move the repo or upgrade Blender.

**Interactive development (with live debugger)**

1. Run the VS Code task **"Launch Blender interactively"** — this opens
   Blender's GUI with debugpy listening on port 5678.
2. In VS Code, run the **"Interactive+debugger"** launch configuration (F5) to
   attach the debugger. Breakpoints in `bexpeng/` source files will now be hit.
3. Edit code, then restart Blender from within Blender using the
   `bim.restart_blender` operator (F3 → type *restart*). Blender relaunches
   and re-opens the debugpy port automatically.
4. Press F5 again to re-attach the debugger.

You do not need to rerun the launch task between restarts — the task stays
running and Blender manages its own restart.

**Automated testing**

Run the VS Code task **"Run Blender+testing"** to execute the test suite
headlessly inside Blender's Python. The task completes when Blender prints
`Blender quit`.

If you need to debug a failing test, use the **"Pytest+debugger"** launch
configuration (F5) — it launches the test task automatically and attaches the
debugger when the port becomes available.

## Quick start (API for other addons)

```python
import bexpeng

engine = bexpeng.get_engine()

# Register parameters from different addons
engine.register_parameter("construction_line_length", 5.0)     # from CAD Sketcher
engine.register_parameter("beam_label", "Beam A")              # string parameter
engine.register_parameter("wall_length")                        # from Bonsai

# Bind an expression: wall_length = 2 × construction_line_length
engine.register_expression("wall_length", "2 * construction_line_length")

# Subscribe to changes
def on_wall_updated(name, value):
    print(f"{name} changed to {value}")
    # Apply back to your IFC object, Blender property, etc.

engine.subscribe("wall_length", on_wall_updated)

# When the sketch changes, update the source parameter:
engine.set_value("construction_line_length", 7.0)
# → prints: wall_length changed to 14.0
```

### More examples

```python
# Wall type thickness derived from another wall type
engine.register_parameter("wall_type_A_thickness", 0.30)
engine.register_expression("wall_type_B_thickness", "wall_type_A_thickness * 0.5")

# Chain expressions
engine.register_parameter("storey_height", 3.0)
engine.register_expression("door_height", "storey_height - 0.3")
engine.register_expression("fanlight_height", "storey_height - door_height - 0.05")
```

## UI panel

The **BExpEng** sidebar panel (3D Viewport → Sidebar → *BExpEng* tab) lets you manage the shared parameter table without writing code.

Each row in the parameter list shows four columns:

| Column | Contents |
|---|---|
| **Name** | Parameter identifier |
| **Expression** | The expression string (a literal or formula) |
| **[Evaluated]** | Current computed value in brackets |
| **Link icon** | See below |

### Link icon and subscription counter

The rightmost column of each row reflects the live subscription state of that parameter:

- **Unlinked icon** — the parameter is defined but no external addon has called `engine.subscribe()` for it yet.
- **Linked icon + count** — one or more addons are actively subscribed; the number shows the total count of registered callbacks across all addons.

### Entering string values

String values **must be quoted** in the *Value* field, exactly like Python string literals:

- `"Beam A"` — double-quoted string
- `'frame_type'` — single-quoted string

Unquoted text is interpreted as a number; entering `Beam A` without quotes will be rejected.

## API reference

| Method | Description |
|---|---|
| `ParametricEngine.get_instance()` | Return the singleton engine instance |
| `ParametricEngine.reset_instance()` | Replace the instance (e.g. on file load), preserving `ui_observer` |
| `engine.set_parameter(name, expression)` | Create or update a parameter with a literal or formula expression |
| `engine.get_value(name)` | Get the current evaluated value |
| `engine.get_expression(name)` | Get the expression string |
| `engine.set_description(name, description)` | Set a human-readable description |
| `engine.get_description(name)` | Get the description |
| `engine.remove_parameter(name)` | Remove a parameter (raises if observers or dependents exist) |
| `engine.attach(name, callback)` | Register a `callback(name)` called when the parameter changes |
| `engine.detach(name, callback)` | Remove a previously attached callback |
| `engine.get_observer_count(name)` | Number of callbacks currently attached to *name* |
| `engine.get_dep_count(name)` | Number of parameters whose expressions reference *name* |
| `engine.notify(name)` | Manually fire all callbacks for *name* |
| `engine.attach_post_load(cb)` | Register a callback fired after every `load_dict()` call |
| `engine.detach_post_load(cb)` | Remove a post-load callback |
| `engine.to_dict()` / `engine.load_dict(data)` | Serialise / restore state |
| `engine.clear()` | Remove all parameters, expressions, and observers |

## Architecture

```
bexpeng/
├── __init__.py       # Blender addon entry point (bl_info, register/unregister)
├── engine.py         # Core ParametricEngine — graph, solver, subscribers
├── parser.py         # AST-based expression parsing and dependency extraction
├── api.py            # Singleton + public API surface
├── operators.py      # Blender operators (add/remove params & expressions)
├── panels.py         # Sidebar UI panel
├── properties.py     # Blender PropertyGroups
└── persistence.py    # Save/load engine state with .blend files
```

**Key design decisions:**

- **Dependency edges point from dependency → dependent** (`A → B` means "B depends on A").
  `networkx.topological_sort` then yields A before B — the correct evaluation order.
- **AST-based parsing** (`ast.walk`) instead of naive string splitting, so `2*x`, `sin(x)`, etc. work correctly.
- **Cycle detection at registration time** — fail fast rather than at solve time.
- **asteval for safe evaluation** — no raw `eval()`, no access to `__builtins__`.

## Dependencies

| Package | License | Purpose |
|---|---|---|
| [asteval](https://pypi.org/project/asteval/) | BSD-3-Clause | Safe expression evaluation |
| [networkx](https://pypi.org/project/networkx/) | BSD-3-Clause | Dependency graph & topological sort |

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
