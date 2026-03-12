# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""
BExpEng — Blender Expression Engine
====================================

A shared parametric expression engine for Blender.  Other addons
(Bonsai, CAD Sketcher, …) can register named parameters and
expressions so that changing one value automatically recomputes all
dependents — much like a spreadsheet or FreeCAD's expression engine.

Quick start from another addon::

    import bexpeng

    engine = bexpeng.get_engine()
    engine.register_parameter("line_length", 5.0)
    engine.register_expression("wall_length", "2 * line_length")
    engine.subscribe("wall_length", lambda name, val: print(f"{name} = {val}"))
    engine.set_value("line_length", 10.0)   # prints: wall_length = 20.0
"""

bl_info = {
    "name": "BExpEng — Blender Expression Engine",
    "author": "bexpeng contributors",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BExpEng",
    "description": "Parametric expression engine for cross-addon parameter linking",
    "category": "System",
    "doc_url": "https://github.com/falken10vdl/bexpeng",
    "tracker_url": "https://github.com/falken10vdl/bexpeng/issues",
}

# Re-export the public API at package level so users can do:
#   import bexpeng; engine = bexpeng.get_engine()
from .api import get_engine, reset_engine  # noqa: E402, F401
from .engine import (
    CyclicDependencyError,
    ExpressionError,
    ParametricEngine,
)  # noqa: E402, F401

from . import properties, operators, panels, persistence  # noqa: E402

_modules = (properties, operators, panels, persistence)


def register():
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
