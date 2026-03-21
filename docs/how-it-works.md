# How BExpEng works

BExpEng is a **shared parametric expression engine** that lives inside
Blender as a regular addon. Any number of other addons can register named
parameters and link them together with Python-style mathematical expressions.
When one value changes the engine automatically recomputes every value that
depends on it, in the correct order, and calls each subscriber callback so
the originating addon can apply the new value back to its own objects.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  External addon  (Bonsai, CAD Sketcher, …)                                  │
│                                                                             │
│    import bexpeng                                                           │
│    engine = bexpeng.get_engine()                                            │
│    engine.set_parameter("wall_length", "2 * construction_line_length")      │
│    engine.subscribe("wall_length", on_wall_updated)                         │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  api.py  (no Blender dep)                                                   │
│    get_engine()    — return the singleton ParametricEngine                  │
│    reset_engine()  — clear state and start fresh (preserves UI hook)        │
│    re-exports: ParametricEngine, CyclicDependencyError,                     │
│                ExpressionSyntaxError, ParameterStillReferencedError,        │
│                ParameterHasDependentsError                                  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  engine.py  (no Blender dep — unit-tested with plain pytest)                │
│                                                                             │
│  class ParametricEngine                                                     │
│    _values          dict[name → Any]       current evaluated values         │
│    _expressions     dict[name → str]       expression strings               │
│    _graph           nx.DiGraph             edge A→B: B depends on A         │
│    _subscribers     dict[name → [cb]]      change listeners                 │
│    _ref_counts      dict[name → int]       active subscriber count          │
│    _aeval           asteval.Interpreter    sandboxed expression evaluator   │
│    bexpeng_panel_update Callable | None       called after every solve()   │
│                                                                             │
│  module-level helpers                                                       │
│    _validate_expression(expr)             AST syntax check                  │
│    _extract_dependencies(expr, names)     AST name-reference scan           │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Blender integration                                                        │
│    __init__.py      addon entry-point, bl_info, re-exports                  │
│    properties.py    PropertyGroups: ExpressionItem, SceneProperties         │
│    operators.py     save_edit, remove_parameter, refresh + sync helper      │
│    panels.py        sidebar panel, UIList                                   │
│    persistence.py   save_pre / load_post handlers (JSON → scene property)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

`engine.py` and `api.py` have no Blender dependency and are fully unit-testable
with plain `pytest`. All Blender-specific code is isolated in the five modules
at the bottom, so the core logic can be tested and reused outside Blender.

---

## Core concepts

### Parameters

A **parameter** is a **name** paired with an **expression**. The expression
is evaluated to produce the parameter's current value. Every parameter always
has an expression — even a plain number like `3.0` or a quoted string like
`"Beam A"` is stored as an expression and evaluated.

Parameters are identified by plain Python-identifier strings (`wall_length`,
`storey_height`, `beam_label`, …). Names must be unique across all addons
because they share one engine instance.

### Expressions

An **expression** is a Python-style string evaluated by
[asteval](https://lmfit.github.io/asteval/) — a sandboxed interpreter with no
access to `__builtins__`, file I/O, or other Python built-ins. Standard maths
functions (`sin`, `cos`, `sqrt`, …) are available through asteval's symbol
table.

All three forms below are expressions:

| Expression string | Evaluated value | Type |
|---|---|---|
| `"3.0"` | `3.0` | `float` |
| `'"Beam A"'` | `"Beam A"` | `str` |
| `"2 * construction_line_length"` | computed | `float` |

The unified entry point is `engine.set_parameter(name, expr)`. It creates
the parameter if it does not exist, or updates the expression if it does.

### Dependency graph

Internally the engine maintains a `networkx.DiGraph` where an edge **A → B**
means "B depends on A" (A must be evaluated first).

```
construction_line_length  →  wall_length  →  door_height
storey_height             ↗              →  fanlight_height
```

When you call `set_parameter("construction_line_length", "7.0")` the engine:

1. **Validates** the expression string for Python syntax (raises `ExpressionSyntaxError` if invalid).
2. **Extracts** all referenced parameter names from the expression by walking the AST.
3. **Cycle-checks**: clones the graph, applies the new edges, and tests `nx.is_directed_acyclic_graph`. Raises `CyclicDependencyError` immediately — nothing is changed — if a cycle would be introduced.
4. **Commits**: adds the parameter node if it is new, removes old dependency edges, adds new ones, and stores the expression string.
5. **Solves**: calls `_solve(name)`, which runs `nx.topological_sort` and re-evaluates only *name* and its transitive dependents, in dependency order.
6. **Notifies**: for every parameter whose value changed during step 5, calls every registered subscriber callback.
7. **UI update**: after all notifications, calls `bexpeng_panel_update()` if one is registered (see [Parameter updates](#parameter-updates) below).

### Cycle detection

Before committing a new expression the engine clones the graph, applies the
would-be edges, and checks `nx.is_directed_acyclic_graph`. If the graph would
become cyclic, `CyclicDependencyError` is raised immediately and nothing is
changed.

### Subscribers and the reference counter

An addon calls `engine.subscribe(name, callback)` to be notified when a
parameter value changes. The callback signature is ``callback(name)`` —
it receives only the parameter name. The engine is the single source of
truth: the callback should read the new state by calling
`engine.get_value(name)` and, if needed, `engine.get_expression(name)`.
This avoids any ambiguity about which value or expression is "current" —
there is always exactly one answer and it is in the engine.

Each subscription increments an internal **reference counter** for that
parameter, decremented on `engine.unsubscribe`. The UI panel shows the counter
next to a link icon so you can see at a glance which parameters are actively
consumed by other addons.

Removing a parameter raises `ParameterStillReferencedError` if any subscriber
is still registered for it, preventing one addon from silently destroying a
parameter another addon still depends on. It also raises
`ParameterHasDependentsError` if any other parameter's expression references
it — the exception carries a `dependents` list of those parameter names so
the caller knows exactly what must be removed or rewritten first.

Only when both checks pass (no subscribers, no dependents) does the removal
succeed.

A typical subscriber looks like this:

```python
def on_wall_length_changed(name):
    my_wall.length = engine.get_value(name)
    # optionally: log or display engine.get_expression(name)

engine.subscribe("wall_length", on_wall_length_changed)
```

### Parameter updates

`set_parameter` calls `_solve(name)` after committing the new expression.
`_solve(name)` collects *name* and all parameters that transitively depend on
it (its descendants in the dependency graph), then re-evaluates only those
nodes in topological order. Parameters that are not reachable from *name* are
not touched — if `wall_length` changes, `storey_height` does not need to be
re-evaluated.

For each node that is re-evaluated, if its value actually changed, `_notify()`
calls every registered subscriber callback for that parameter. So an addon
subscribed to `door_height` is notified only when `door_height`'s value
changes, even when the trigger was a change several steps upstream.

`remove_parameter` does not call `_solve()` at all: if a dependent parameter
existed its expression would need to be removed first (raising
`ParameterHasDependentsError`), so by the time removal succeeds there are no
downstream nodes to re-evaluate.
their expressions cleared (they become independent) and retain their last
computed value.

`load_dict` is the one case that does a full solve: all expressions are
registered with solving deferred, and a single `_solve()` (with no root)
runs over the entire graph at the end. This avoids redundant intermediate
passes while restoring a saved parameter table.

Once `_solve()` finishes, the engine calls `bexpeng_panel_update()` if one is
set. This is a single callable slot used exclusively by the Blender UI layer.
Blender's `draw()` callbacks must not write to ID properties, so the panel
cannot refresh itself inline; `bexpeng_panel_update` is the correct hook point
outside any `draw()` call. `operators.py` sets it to `_ui_post_solve` (which
calls `sync_scene_ui_list` for every scene) when the addon loads, and clears
it when the addon unloads. Because the hook fires after every engine mutation —
including mutations made by external addons — the panel always reflects the
current engine state without any polling.

Two special cases keep behaviour correct:

- **Batch reload** (`load_dict`): `bexpeng_panel_update` is set to `None`
  for the duration of the load and fired once at the end, after the full solve.
- **Hard reset** (`reset_engine`): the callable is copied to the new engine
  instance so the UI stays connected across a full engine replacement.

### Persistence

The engine serialises its state to a plain `dict` via `engine.to_dict()` and
restores it with `engine.load_dict(data)`. The format is
`{"expressions": {name: expr}}`. The `persistence.py` module hooks
into Blender's `load_post` and `save_pre` handlers so the parameter table
survives save/load of `.blend` files transparently.

---

## Module reference

```
bexpeng/
├── __init__.py      — Blender addon entry-point; calls register/unregister
├── api.py           — Public surface: get_engine(), reset_engine(), re-exports
├── engine.py        — ParametricEngine class, exception classes, AST helpers
├── operators.py     — Blender operators (add/remove/edit parameters in the UI)
├── panels.py        — Sidebar UI panel (3D Viewport → BExpEng tab)
├── properties.py    — Blender PropertyGroups for scene-level UI state
└── persistence.py   — save_pre / load_post hooks to persist engine state
```

---

### `__init__.py` — Blender addon entry point

Declares the `bl_info` dict that Blender reads to display the addon in
Preferences. Also:

- Ensures bundled libraries (`asteval`, `networkx`) under `bexpeng/libs/` are
  on `sys.path` in release builds.
- Re-exports `get_engine`, `reset_engine`, `ParametricEngine`,
  `CyclicDependencyError`, `ExpressionSyntaxError`,
  `ParameterStillReferencedError`, and `ParameterHasDependentsError` at
  package level so external addons can write `import bexpeng;
  bexpeng.get_engine()` without knowing internal module paths.
- Imports the four Blender sub-modules (`properties`, `operators`, `panels`,
  `persistence`) and delegates `register()` / `unregister()` to each in order
  (reversed for unregister).
- Calls `get_engine()` at the very start of `register()`, **before** any
  sub-module registers. This means the singleton `ParametricEngine` is alive
  from the moment the addon loads, so external addons that also load at
  startup can safely call `bexpeng.get_engine()` in their own `register()`
  without racing against lazy initialisation.

---

### `api.py` — public interface for external addons

The **only file** external addons need to import. It exposes two functions and
re-exports the exception types:

```python
import bexpeng

engine = bexpeng.get_engine()   # always the same singleton
```

**`get_engine() → ParametricEngine`**
Returns the singleton `ParametricEngine`. The engine is created during addon
`register()`; subsequent calls simply return the existing instance. All addons
share the same instance within a Blender session — no need to hold a local
reference.

**`reset_engine() → None`**
Clears state on the current instance and replaces it with a fresh
`ParametricEngine`. Preserves `bexpeng_panel_update` on the new instance so
the UI stays connected. Still available for external callers that need a hard
reset; `persistence.py` no longer calls it on `load_post` — instead it calls
`engine.load_dict()` directly (which calls `clear()` internally).

**Re-exported names available as `bexpeng.<Name>`:**

| Name | Type |
|---|---|
| `ParametricEngine` | class |
| `CyclicDependencyError` | exception |
| `ExpressionSyntaxError` | exception |
| `ParameterStillReferencedError` | exception |
| `ParameterHasDependentsError` | exception |

---

### `engine.py` — the parametric engine

Contains the `ParametricEngine` class, exception classes, and two private
AST helper functions. Has **no Blender dependency** — fully testable with plain pytest.

#### AST helpers (module-level)

**`_validate_expression(expression) → (bool, str)`**
Attempts `ast.parse(expression, mode="eval")`. Returns `(True, "")` on
success or `(False, error_message)` on `SyntaxError`.

**`_extract_dependencies(expression, known_names) → set[str]`**
Walks the AST and collects every `ast.Name` node whose `.id` is in
`known_names`. This is how the engine knows which edges to add to the
dependency graph — without evaluating the expression. Returns an empty set
if parsing fails.

#### Internal state

| Attribute | Type | Purpose |
|---|---|---|
| `_values` | `dict[str, Any]` | Current evaluated value for every parameter |
| `_expressions` | `dict[str, str]` | Expression string for every parameter |
| `_graph` | `nx.DiGraph` | Dependency graph; edge A→B means B depends on A |
| `_subscribers` | `dict[str, list[Callable]]` | Registered callbacks per parameter |
| `_ref_counts` | `dict[str, int]` | Number of active subscribers per parameter |
| `_aeval` | `asteval.Interpreter` | Sandboxed Python expression evaluator |
| `bexpeng_panel_update` | `Callable \| None` | Called once after every `_solve()` completes; used by the Blender UI layer to update the panel |

#### Public methods

| Method | Description |
|---|---|
| `set_parameter(name, expr)` | Create or update a parameter. Validates syntax, cycle-checks, commits graph edges, solves, notifies. |
| `get_value(name)` | Return the current evaluated value, or `None`. |
| `get_expression(name)` | Return the expression string, or `None`. |
| `subscribe(name, callback)` | Register `callback(name)` — called whenever the parameter's value changes. Fetch current state with `get_value`/`get_expression` inside the callback. Increments ref count. |
| `unsubscribe(name, callback)` | Remove callback; decrements ref count. |
| `get_ref_count(name)` | Return number of active subscribers. |
| `get_dep_count(name)` | Return number of parameters whose expressions reference *name*. |
| `remove_parameter(name)` | Remove a parameter. Raises `ParameterStillReferencedError` if subscribed. Raises `ParameterHasDependentsError` (with `.dependents` list) if other parameters reference it in their expressions. |
| `to_dict()` | Serialise to `{"expressions": {name: expr}}`. |
| `load_dict(data)` | Restore from dict; clears first. |
| `clear()` | Reset all internal state. |

#### Private helpers

| Method | Description |
|---|---|
| `_register_parameter(name, value)` | Add a parameter node to `_values`, `_graph`, and `_aeval.symtable`. |
| `_register_expression(name, expr)` | Validate, cycle-check, commit graph edges, store expression, then call `_solve(name)` (unless deferred). |
| `_unregister_expression(name)` | Remove expression and incoming graph edges for a parameter (keeps the node and its last value). |
| `_list_parameters()` | Return a copy of `_values`. Used internally by the UI sync. |
| `_list_expressions()` | Return a copy of `_expressions`. Used internally by the UI sync. |
| `_solve(root=None)` | Re-evaluate *root* and its transitive dependents in topological order; if *root* is `None`, re-evaluate all nodes with an expression. Calls `_notify` for any value that changed. |
| `_notify(name)` | Call all subscribers for a parameter, swallowing callback exceptions. |

#### Exception classes

| Class | Raised when |
|---|---|
| `CyclicDependencyError` | `set_parameter` would introduce a cycle |
| `ExpressionSyntaxError` | Expression string is not valid Python |
| `ParameterStillReferencedError` | `remove_parameter` called while subscribers are registered |
| `ParameterHasDependentsError` | `remove_parameter` called while other parameters reference it in their expressions |

---


### `properties.py` — Blender PropertyGroups

Defines two `bpy.types.PropertyGroup` subclasses registered on
`bpy.types.Scene.bexpeng`:

**`BEXPENG_ExpressionItem`** — one row in the UI list:

| Property | Type | Purpose |
|---|---|---|
| `param_name` | `StringProperty` | parameter name (display only) |
| `expression` | `StringProperty` | expression string (display only) |
| `value_str` | `StringProperty` | current evaluated value as text (display only) |
| `ref_count` | `IntProperty` | number of active subscribers (display only) |
| `dep_count` | `IntProperty` | number of parameters whose expressions reference this one (display only) |

**`BEXPENG_SceneProperties`** — scene-level container:

| Property | Type | Purpose |
|---|---|---|
| `expressions` | `CollectionProperty(BEXPENG_ExpressionItem)` | the list shown in the UI |
| `active_expression_index` | `IntProperty` | currently selected row; triggers `_on_active_index_changed` |
| `edit_name` | `StringProperty` | name field in the bottom edit box |
| `edit_value` | `StringProperty` | expression field in the bottom edit box |

`_on_active_index_changed` — update callback that populates `edit_name` and
`edit_value` from the selected list item whenever the user clicks a row.

---

### `operators.py` — Blender operators

Contains three `bpy.types.Operator` subclasses and the `sync_scene_ui_list`
helper function. Its `register()` attaches `_ui_post_solve` as the engine's
`bexpeng_panel_update`; `unregister()` clears it. This means every time the engine
solves (triggered by `set_parameter` from any addon), all scene UI lists are
synced immediately — no polling timer needed.

**`sync_scene_ui_list(scene)`**
The central reconciliation function. Compares current engine state
(`engine._list_parameters()`, `engine._list_expressions()`) against the
scene's `BEXPENG_SceneProperties.expressions` collection. If they differ it
rebuilds the collection. Preserves the active selection by name. Has a
fallback: if the engine is empty but the scene UI list has persisted rows
(e.g. right after file load before `load_post` ran), it re-registers those
rows into the engine instead of clearing the UI.

**`BEXPENG_OT_save_edit`** (`bexpeng.save_edit`)
Called by the `✓` confirm button in the edit box.
- Reads `props.edit_name` and `props.edit_value`.
- Validates the name is non-empty and a valid Python identifier.
- Calls `engine.set_parameter(name, expr)`.
- Catches `ExpressionSyntaxError` and reports it as a Blender error.
- After success, calls `sync_scene_ui_list` and selects the saved row.

**`BEXPENG_OT_remove_parameter`** (`bexpeng.remove_parameter`)
Called by the `−` button next to the list.
- Looks up the selected parameter name from the active list index.
- Calls `engine.remove_parameter(name)`.
- Catches `ParameterStillReferencedError` and shows it as a Blender warning
  (the parameter is not removed).
- Catches `ParameterHasDependentsError` and shows it as a Blender warning with
  the list of dependent names (the parameter is not removed).
- After success, calls `sync_scene_ui_list` and adjusts the active index.

**`BEXPENG_OT_refresh`** (`bexpeng.refresh`)
Called by the `↺` refresh button.
- Calls `engine._solve()` to recompute all values.
- Then calls `sync_scene_ui_list` to update the display.

---

### `panels.py` — sidebar UI panel

Registers the 3D Viewport sidebar panel under the **BExpEng** tab. UI
refreshes are driven by `bexpeng_panel_update` (registered in
`operators.py`), not a timer.

**`BEXPENG_UL_expression_list`** (UIList)
Each row renders five columns:
1. `param_name` — the parameter identifier
2. `expression` — the expression string
3. `[value_str]` — current evaluated value in brackets
4. ref count with a `LINKED` / `UNLINKED` icon — subscribers; must be zero to remove
5. dep count with a `TRIA_LEFT` icon — parameters that reference this one; must be zero to remove

**`BEXPENG_PT_main_panel`** (Panel, `VIEW_3D > UI > BExpEng`)
Layout:
- Left: `template_list` with `BEXPENG_UL_expression_list`, 5 rows.
- Right column: `−` (remove) and `↺` (refresh) icon buttons.
- Below: a box with the edit row `[name field][=][expression field][✓]`.
  The `=` label is in a sub-row with `scale_x = 0.24` to keep it narrow.

---

### `persistence.py` — save/load handlers

Hooks into two Blender application handlers to persist engine state inside the
`.blend` file.

**`_save_handler`** — registered on `bpy.app.handlers.save_pre`
Called just before Blender writes the file. Calls `engine.to_dict()` and
stores the result as a JSON string in `scene["bexpeng_data"]` on the active
scene.

**`_load_handler`** — registered on `bpy.app.handlers.load_post`
Called after Blender finishes loading a file. Two-stage restore:

1. **Explicit state**: searches all scenes for a `"bexpeng_data"` custom
   property. If found, calls `engine.load_dict(data)` directly (which calls
   `engine.clear()` first). `bexpeng_panel_update` is suppressed during the
   batch reload and fired once at the end so the UI reflects the loaded state.
2. **Fallback**: if no `"bexpeng_data"` key is found, walks all scene
   `BEXPENG_SceneProperties.expressions` collections and calls
   `engine.set_parameter` for each row. This handles files saved before the
   persistence layer existed, and provides resilience if the JSON key is lost.

---

## Full API reference

| Call | Effect |
|---|---|
| `engine.set_parameter(name, expr)` | Create or update a parameter. `expr` can be a literal (`"5.0"`, `'"hello"'`) or a formula (`"2 * wall_length"`). Creates the parameter if it does not exist; updates the expression if it does. Raises `ExpressionSyntaxError` for invalid syntax and `CyclicDependencyError` for circular dependencies. |
| `engine.get_value(name)` | Return the current evaluated value, or `None` if the parameter is unknown. |
| `engine.get_expression(name)` | Return the expression string, or `None` if the parameter is unknown. |
| `engine.subscribe(name, callback)` | Register `callback(name)` — called whenever the parameter's value changes. The engine is the single source of truth: call `engine.get_value(name)` and `engine.get_expression(name)` inside the callback to read current state. Increments the reference counter. |
| `engine.unsubscribe(name, callback)` | Remove a previously registered callback. Decrements the reference counter. |
| `engine.get_ref_count(name)` | Return the current number of active subscribers for a parameter. |
| `engine.get_dep_count(name)` | Return the number of parameters whose expressions reference *name*. |
| `engine.remove_parameter(name)` | Remove a parameter. Raises `ParameterStillReferencedError` if any subscriber is still registered. Raises `ParameterHasDependentsError` (with `.dependents` list) if any other parameter's expression references *name*. Only removes when both checks pass. |
| `engine.to_dict()` | Serialise state to a plain `dict` safe for JSON storage. |
| `engine.load_dict(data)` | Restore from a `dict`; clears current state first. |
| `engine.clear()` | Remove all parameters, expressions, and subscribers. |

---

## Value types and the UI expression field

The right-hand field in the UI panel accepts any valid expression string and
passes it directly to `engine.set_parameter`:

| Typed input | Evaluated value | Type |
|---|---|---|
| `3.14` | `3.14` | `float` |
| `42` | `42.0` | `float` |
| `"Beam A"` | `Beam A` | `str` |
| `'frame_type'` | `frame_type` | `str` |
| `2 * wall_length` | computed | `float` |
| `f"Level {storey:02d}"` | computed | `str` |
| `Beam A` *(no quotes)* | **error** — unquoted non-numeric text is not valid Python |

String values must be quoted exactly like Python string literals.

---

## Error types

| Exception | When raised |
|---|---|
| `bexpeng.CyclicDependencyError` | `set_parameter` would create a circular dependency |
| `bexpeng.ExpressionSyntaxError` | The expression string is not valid Python syntax |
| `bexpeng.ParameterStillReferencedError` | `remove_parameter` called while subscribers are still registered |
| `bexpeng.ParameterHasDependentsError` | `remove_parameter` called while other parameters reference it in their expressions; `.dependents` carries the list of dependent names |

---

## Threading and Blender context

- The engine has **no explicit thread safety**. All calls should be made from
  Blender's main thread (operators, timers, `load_post` handlers).
- Do **not** mutate `Scene` or other Blender ID properties from inside a
  panel's `draw()` method; Blender forbids writes there. Use an
  `app timer` or an operator to apply changes that come from the engine.
  The built-in `panels.py` timer runs every 0.5 s to sync the UI list.
