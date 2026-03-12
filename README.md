# BExpEng — Blender Expression Engine

A shared parametric expression engine for Blender. Allows addons like
[Bonsai](https://bonsaibim.org/) and
[CAD Sketcher](https://www.cadsketcher.com/) to register named
parameters and expressions so that changing one value automatically
recomputes all dependents — much like a spreadsheet or FreeCAD's
expression engine.

## Features

- **Named parameters** — register values from any addon
- **Expression binding** — attach Python-style expressions to parameters (e.g. `"2 * wall_length"`)
- **Automatic dependency resolution** — topological evaluation order via a directed acyclic graph
- **Cycle detection** — registering a circular dependency raises an error immediately
- **Safe evaluation** — expressions are evaluated with [asteval](https://lmfit.github.io/asteval/), not raw `eval()`
- **Subscriber callbacks** — addons get notified when a value they depend on changes
- **Persistence** — engine state is saved/loaded with `.blend` files
- **UI panel** — sidebar panel in the 3D Viewport for managing parameters

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

## Quick start (API for other addons)

```python
import bexpeng

engine = bexpeng.get_engine()

# Register parameters from different addons
engine.register_parameter("construction_line_length", 5.0)     # from CAD Sketcher
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

## API reference

| Method | Description |
|---|---|
| `get_engine()` | Return the singleton engine instance |
| `engine.register_parameter(name, value=None)` | Register a named parameter |
| `engine.set_value(name, value)` | Set a value and recompute dependents |
| `engine.get_value(name)` | Get the current value |
| `engine.register_expression(name, expr)` | Bind an expression to a parameter |
| `engine.unregister_expression(name)` | Remove an expression |
| `engine.unregister_parameter(name)` | Remove a parameter and its dependents |
| `engine.subscribe(name, callback)` | Register a `(name, value)` callback |
| `engine.unsubscribe(name, callback)` | Remove a callback |
| `engine.list_parameters()` | Dict of all parameter names and values |
| `engine.list_expressions()` | Dict of all expression definitions |
| `engine.get_dependents(name)` | Parameters that depend on *name* |
| `engine.get_dependencies(name)` | Parameters that *name* depends on |
| `engine.to_dict()` / `engine.load_dict(data)` | Serialise / restore state |

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
