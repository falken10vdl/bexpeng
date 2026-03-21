# End-to-end example: two addons sharing parameters

This document walks through a realistic scenario in which two fictitious addons
cooperate through the shared BExpEng engine:

- **StructCalc** owns structural inputs such as storey height and beam span.
- **DrawingGen** subscribes to selected parameters so it can keep its drawing
  annotations in sync.

The example follows the current architecture:

- external addons only need `import bexpeng` and `bexpeng.get_engine()`
- parameters are created or updated with `engine.set_parameter(name, expression)`
- subscriber callbacks receive only the parameter name: `callback(name)`
- callbacks read current state from the engine with `engine.get_value(name)`
- the Blender UI reflects subscription counts and dependent counts separately

No Blender objects or IFC data are created here; the focus is the engine
contract between addons.

---

## The scenario

```text
StructCalc side                     DrawingGen side
----------------------------------  --------------------------------
storey_height   = 3.0               watches storey_height
column_section  = "HEB 200"         watches door_height
beam_span       = 6.0               watches fanlight_h
                                    watches column_section

                BExpEng engine
                ----------------------------------------
                door_height = storey_height - 0.3
                fanlight_h  = storey_height - door_height - 0.05
                total_load  = beam_span * 2.5
```

StructCalc publishes raw values and derived expressions. DrawingGen subscribes
to the parameters it cares about so it can react when those values change.

---

## Step 1 - StructCalc registers its parameters

```python
# structcalc/engine_bridge.py
import bexpeng


def structcalc_register_parameters():
    """Called from StructCalc's addon register() hook."""
    engine = bexpeng.get_engine()

    # Literal values are still expressions.
    engine.set_parameter("storey_height", "3.0")
    engine.set_parameter("beam_span", "6.0")
    engine.set_parameter("column_section", '"HEB 200"')

    # Derived values reference other parameters by name.
    engine.set_parameter("door_height", "storey_height - 0.3")
    engine.set_parameter("fanlight_h", "storey_height - door_height - 0.05")
    engine.set_parameter("total_load", "beam_span * 2.5")

    print("StructCalc registered")
    print("  storey_height =", engine.get_value("storey_height"))
    print("  door_height   =", engine.get_value("door_height"))
    print("  fanlight_h    =", engine.get_value("fanlight_h"))
    print("  total_load    =", engine.get_value("total_load"))
    print("  column_section=", engine.get_value("column_section"))
```

At this point the dependency graph is:

```text
storey_height -> door_height -> fanlight_h
beam_span     -> total_load
column_section
```

`get_dep_count()` would report:

| Parameter | Dependent count |
|---|---|
| `storey_height` | 2 |
| `door_height` | 1 |
| `beam_span` | 1 |
| `column_section` | 0 |
| `fanlight_h` | 0 |
| `total_load` | 0 |

---

## Step 2 - DrawingGen subscribes to the parameters it needs

```python
# drawinggen/engine_bridge.py
import bexpeng


_annotation_data = {
    "storey_height": None,
    "door_height": None,
    "fanlight_h": None,
    "column_section": None,
}


def _sync_annotation(name):
    engine = bexpeng.get_engine()
    _annotation_data[name] = engine.get_value(name)


def _on_storey_height_changed(name):
    _sync_annotation(name)
    print(
        f"DrawingGen: {name} -> "
        f"{_annotation_data[name]:.3f} m"
    )


def _on_door_height_changed(name):
    _sync_annotation(name)
    print(
        f"DrawingGen: {name} -> "
        f"{_annotation_data[name]:.3f} m"
    )


def _on_fanlight_h_changed(name):
    _sync_annotation(name)
    print(
        f"DrawingGen: {name} -> "
        f"{_annotation_data[name]:.3f} m"
    )
    _refresh_elevation_sheet()


def _on_column_section_changed(name):
    _sync_annotation(name)
    print(f'DrawingGen: {name} -> "{_annotation_data[name]}"')


def drawinggen_register_subscriptions():
    """Called from DrawingGen's addon register() hook."""
    engine = bexpeng.get_engine()

    engine.subscribe("storey_height", _on_storey_height_changed)
    engine.subscribe("door_height", _on_door_height_changed)
    engine.subscribe("fanlight_h", _on_fanlight_h_changed)
    engine.subscribe("column_section", _on_column_section_changed)

    # Prime local state from the engine's current values.
    for key in _annotation_data:
        _annotation_data[key] = engine.get_value(key)

    print("DrawingGen subscribed:", _annotation_data)


def drawinggen_unregister_subscriptions():
    """Called from DrawingGen's addon unregister() hook."""
    engine = bexpeng.get_engine()
    engine.unsubscribe("storey_height", _on_storey_height_changed)
    engine.unsubscribe("door_height", _on_door_height_changed)
    engine.unsubscribe("fanlight_h", _on_fanlight_h_changed)
    engine.unsubscribe("column_section", _on_column_section_changed)


def _refresh_elevation_sheet():
    print("  -> refreshing sheet with", _annotation_data)
```

After step 2 the subscription counts are:

| Parameter | Subscription count |
|---|---|
| `storey_height` | 1 |
| `door_height` | 1 |
| `fanlight_h` | 1 |
| `column_section` | 1 |
| `beam_span` | 0 |
| `total_load` | 0 |

In the sidebar panel:

- `#Sub` shows those subscription counts with the linked icon when the count is
  greater than zero
- `#Dep` shows how many expressions depend on each parameter

---

## Step 3 - StructCalc changes a value

The architect increases the storey height from `3.0` m to `3.6` m:

```python
engine = bexpeng.get_engine()
engine.set_parameter("storey_height", "3.6")
```

### What happens inside the engine

1. The expression for `storey_height` is updated.
2. `_solve("storey_height")` re-evaluates `storey_height` and all of its
   transitive dependents in topological order.
3. Each parameter whose value actually changed triggers its own subscribers.

The resulting values are:

| Parameter | New value |
|---|---|
| `storey_height` | `3.6` |
| `door_height` | `3.3` |
| `fanlight_h` | `0.25` |
| `total_load` | `15.0` |

`fanlight_h` does not notify subscribers in this case because its value was
already `0.25`.

### Console output

```text
DrawingGen: storey_height -> 3.600 m
DrawingGen: door_height -> 3.300 m
```

### Important callback behavior

Subscriber callbacks are invoked per parameter as each changed value is solved.
That means a callback for an upstream parameter should not assume all downstream
parameters have already been recomputed.

If DrawingGen needs one "final snapshot" refresh for the whole chain, the most
reliable pattern is to subscribe to the leaf parameter that represents the end
of the update chain, or debounce its own redraw logic.

---

## Step 4 - StructCalc changes the column section label

```python
engine.set_parameter("column_section", '"HEB 240"')
```

Console output:

```text
DrawingGen: column_section -> "HEB 240"
```

String literals participate in the same mechanism as numeric parameters. The
only requirement is that string expressions stay quoted.

---

## Step 5 - StructCalc changes the beam span

```python
engine.set_parameter("beam_span", "8.0")
```

`beam_span` has no subscribers, so no addon callback runs. Its dependent
parameter still recomputes:

```python
engine.get_value("total_load")  # 20.0
```

---

## Step 6 - A third addon subscribes later

Another addon, **CostEst**, can subscribe after the others are already active:

```python
def _on_total_load_changed(name):
    engine = bexpeng.get_engine()
    value = engine.get_value(name)
    print(f"CostEst: {name} changed -> {value} kN/m")


engine = bexpeng.get_engine()
engine.subscribe("total_load", _on_total_load_changed)
```

Now `total_load` shows `#Sub = 1` in the UI. The next call to:

```python
engine.set_parameter("beam_span", "9.0")
```

prints:

```text
CostEst: total_load changed -> 22.5 kN/m
```

---

## Step 7 - Detecting a cycle

If an addon tries to redefine `storey_height` in terms of `door_height`:

```python
engine.set_parameter("storey_height", "door_height + 0.3")
```

the engine rejects it because `door_height` already depends on
`storey_height`.

```text
bexpeng.CyclicDependencyError: Expression 'door_height + 0.3' for
'storey_height' would create a circular dependency.
```

The previous expressions and values remain unchanged.

---

## Step 8 - DrawingGen unregisters cleanly

```python
drawinggen_unregister_subscriptions()
```

After that, the four parameters DrawingGen watched all return to `#Sub = 0`.

This is important because `remove_parameter(name)` refuses to remove a
parameter while its own subscriber count is still non-zero.

---

## Complete runnable script

This script mirrors the steps above and uses only the current public API:

```python
import bexpeng
from bexpeng import CyclicDependencyError


engine = bexpeng.get_engine()
engine.clear()

log = []
_drawing = {}


def record(message):
    print(message)
    log.append(message)


def sync_drawing(name):
    _drawing[name] = engine.get_value(name)


def on_storey(name):
    sync_drawing(name)
    record(f"[DrawingGen] {name} -> {_drawing[name]}")


def on_door(name):
    sync_drawing(name)
    record(f"[DrawingGen] {name} -> {_drawing[name]}")


def on_fanlight(name):
    sync_drawing(name)
    record(f"[DrawingGen] {name} -> {_drawing[name]}")


def on_column(name):
    sync_drawing(name)
    record(f"[DrawingGen] {name} -> {_drawing[name]}")


def on_total_load(name):
    record(f"[CostEst] {name} -> {engine.get_value(name)}")


# ---------------------------------------------------------------------------
# Step 1: StructCalc registers parameters.
# ---------------------------------------------------------------------------
print("\n=== Step 1: StructCalc registers parameters ===")
engine.set_parameter("storey_height", "3.0")
engine.set_parameter("beam_span", "6.0")
engine.set_parameter("column_section", '"HEB 200"')
engine.set_parameter("door_height", "storey_height - 0.3")
engine.set_parameter("fanlight_h", "storey_height - door_height - 0.05")
engine.set_parameter("total_load", "beam_span * 2.5")

print(f"  storey_height  = {engine.get_value('storey_height')}")
print(f"  beam_span      = {engine.get_value('beam_span')}")
print(f"  column_section = {engine.get_value('column_section')!r}")
print(f"  door_height    = {engine.get_value('door_height')}")
print(f"  fanlight_h     = {engine.get_value('fanlight_h')}")
print(f"  total_load     = {engine.get_value('total_load')}")

print("\n  [check] values after registration")
assert engine.get_value("door_height") == 2.7,          "door_height should be 2.7"
print(f"    door_height == 2.7  ✓")
assert abs(engine.get_value("fanlight_h") - 0.25) < 1e-9, "fanlight_h should be ~0.25"
print(f"    fanlight_h  ≈ 0.25  ✓")
assert engine.get_value("total_load") == 15.0,           "total_load should be 15.0"
print(f"    total_load  == 15.0 ✓")

print("\n  [check] dependency counts (how many expressions reference each param)")
assert engine.get_dep_count("storey_height") == 2
print(f"    dep_count(storey_height) == 2  ✓  (door_height, fanlight_h)")
assert engine.get_dep_count("door_height") == 1
print(f"    dep_count(door_height)   == 1  ✓  (fanlight_h)")
assert engine.get_dep_count("beam_span") == 1
print(f"    dep_count(beam_span)     == 1  ✓  (total_load)")
assert engine.get_dep_count("column_section") == 0
print(f"    dep_count(column_section)== 0  ✓  (leaf)")
assert engine.get_dep_count("fanlight_h") == 0
print(f"    dep_count(fanlight_h)    == 0  ✓  (leaf)")
assert engine.get_dep_count("total_load") == 0
print(f"    dep_count(total_load)    == 0  ✓  (leaf)")

# ---------------------------------------------------------------------------
# Step 2: DrawingGen subscribes.
# ---------------------------------------------------------------------------
print("\n=== Step 2: DrawingGen subscribes ===")
engine.subscribe("storey_height", on_storey)
engine.subscribe("door_height", on_door)
engine.subscribe("fanlight_h", on_fanlight)
engine.subscribe("column_section", on_column)
print("  subscribed to: storey_height, door_height, fanlight_h, column_section")

for key in ("storey_height", "door_height", "fanlight_h", "column_section"):
    _drawing[key] = engine.get_value(key)
print(f"  primed local drawing state: {_drawing}")

print("\n  [check] subscription (ref) counts")
assert engine.get_ref_count("storey_height") == 1
print(f"    ref_count(storey_height)  == 1  ✓")
assert engine.get_ref_count("door_height") == 1
print(f"    ref_count(door_height)    == 1  ✓")
assert engine.get_ref_count("fanlight_h") == 1
print(f"    ref_count(fanlight_h)     == 1  ✓")
assert engine.get_ref_count("column_section") == 1
print(f"    ref_count(column_section) == 1  ✓")
assert engine.get_ref_count("beam_span") == 0
print(f"    ref_count(beam_span)      == 0  ✓  (no subscribers)")
assert engine.get_ref_count("total_load") == 0
print(f"    ref_count(total_load)     == 0  ✓  (no subscribers yet)")

# ---------------------------------------------------------------------------
# Step 3: upstream change propagates.
# ---------------------------------------------------------------------------
print("\n=== Step 3: storey_height changes 3.0 -> 3.6 ===")
print("  (fanlight_h stays at 0.25 — its value does not change — so no callback)")
log.clear()
engine.set_parameter("storey_height", "3.6")
print(f"  callbacks fired: {log}")

print("\n  [check] recomputed values")
assert engine.get_value("storey_height") == 3.6
print(f"    storey_height == 3.6   ✓")
assert abs(engine.get_value("door_height") - 3.3) < 1e-9
print(f"    door_height   ≈ 3.3   ✓")
assert abs(engine.get_value("fanlight_h") - 0.25) < 1e-9
print(f"    fanlight_h    ≈ 0.25  ✓  (unchanged, no callback)")
assert not any("[DrawingGen] fanlight_h" in entry for entry in log)
print(f"    fanlight_h callback NOT fired  ✓")

# ---------------------------------------------------------------------------
# Step 4: string value change.
# ---------------------------------------------------------------------------
print("\n=== Step 4: column_section changes to HEB 240 ===")
engine.set_parameter("column_section", '"HEB 240"')
assert engine.get_value("column_section") == "HEB 240"
print(f"    column_section == 'HEB 240'  ✓")

# ---------------------------------------------------------------------------
# Step 5: silent recompute — beam_span has no subscribers.
# ---------------------------------------------------------------------------
print("\n=== Step 5: beam_span changes 6.0 -> 8.0 (no subscribers) ===")
print("  no addon callbacks will fire, but total_load still recomputes")
engine.set_parameter("beam_span", "8.0")
assert engine.get_value("total_load") == 20.0
print(f"    total_load == 20.0  ✓  (8.0 * 2.5)")

# ---------------------------------------------------------------------------
# Step 6: CostEst subscribes to total_load later.
# ---------------------------------------------------------------------------
print("\n=== Step 6: CostEst subscribes to total_load, then beam_span -> 9.0 ===")
engine.subscribe("total_load", on_total_load)
assert engine.get_ref_count("total_load") == 1
print(f"    ref_count(total_load) == 1  ✓")
engine.set_parameter("beam_span", "9.0")
assert engine.get_value("total_load") == 22.5
print(f"    total_load == 22.5  ✓  (9.0 * 2.5)")

# ---------------------------------------------------------------------------
# Step 7: cycle detection.
# ---------------------------------------------------------------------------
print("\n=== Step 7: cycle detection ===")
print("  attempting: storey_height = door_height + 0.3  (door_height depends on storey_height)")
try:
    engine.set_parameter("storey_height", "door_height + 0.3")
    raise AssertionError("Expected CyclicDependencyError")
except CyclicDependencyError as exc:
    print(f"    CyclicDependencyError raised as expected  ✓")
    print(f"    {exc}")

# ---------------------------------------------------------------------------
# Step 8: clean unregister.
# ---------------------------------------------------------------------------
print("\n=== Step 8: DrawingGen and CostEst unsubscribe ===")
engine.unsubscribe("storey_height", on_storey)
engine.unsubscribe("door_height", on_door)
engine.unsubscribe("fanlight_h", on_fanlight)
engine.unsubscribe("column_section", on_column)
engine.unsubscribe("total_load", on_total_load)

assert engine.get_ref_count("storey_height") == 0
print(f"    ref_count(storey_height) == 0  ✓")
assert engine.get_ref_count("total_load") == 0
print(f"    ref_count(total_load)    == 0  ✓")

print("\n=== All steps completed successfully ===")

```

---

## Key takeaways

| Pattern | Recommendation |
|---|---|
| Ownership | The addon that owns the source data should call `set_parameter()` for that parameter. Other addons should usually subscribe rather than overwrite it. |
| Callback contract | Subscribers are `callback(name)`, then read the latest state with `engine.get_value(name)` or `engine.get_expression(name)`. |
| Registration order | A producing addon should register parameters before a consuming addon relies on them. Consumers can also guard with `engine.get_value(name) is not None`. |
| Strings | String parameters must be quoted Python literals such as `'"HEB 200"'`. |
| Cleanup | Always `unsubscribe()` in your addon's `unregister()` hook so reference counts stay accurate. |
| UI meaning | `#Sub` is active subscriber count; `#Dep` is dependent-expression count. |
| Callback timing | Upstream notifications can happen before downstream values finish recomputing. Subscribe to the right leaf parameter if you need a stable final snapshot. |
| Cycle safety | Catch `CyclicDependencyError` around `set_parameter()`; failed registrations do not partially modify the engine. |
