# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Public API — the interface that external addons (Bonsai, CAD Sketcher, etc.) use.

Usage from another addon::

    import bexpeng

    engine = bexpeng.get_engine()
    engine.register_parameter("construction_line_length", 5.0)
    engine.register_expression("wall_length", "2 * construction_line_length")

    def on_wall_updated(name, value):
        # Apply value back to your IFC/BIM object
        ...

    engine.subscribe("wall_length", on_wall_updated)

    # When a sketch constraint changes:
    engine.set_value("construction_line_length", 7.0)
    # -> on_wall_updated("wall_length", 14.0) is called automatically
"""

from __future__ import annotations

from .engine import CyclicDependencyError, ExpressionError, ParametricEngine

_engine: ParametricEngine | None = None


def get_engine() -> ParametricEngine:
    """Return the singleton ``ParametricEngine`` instance.

    The engine is created lazily on first call.  All addons share the
    same instance within a Blender session.
    """
    global _engine
    if _engine is None:
        _engine = ParametricEngine()
    return _engine


def reset_engine() -> None:
    """Discard the current engine and create a fresh one.

    Primarily used when loading a new ``.blend`` file.
    """
    global _engine
    if _engine is not None:
        _engine.clear()
    _engine = None


__all__ = [
    "get_engine",
    "reset_engine",
    "ParametricEngine",
    "CyclicDependencyError",
    "ExpressionError",
]
