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
    engine.set_parameter("line_length", "5.0")
    engine.set_parameter("wall_length", "2 * line_length")
    engine.subscribe("wall_length", lambda name, val: print(f"{name} = {val}"))
    engine.set_parameter("line_length", "10.0")   # prints: wall_length = 20.0
"""

bl_info = {
    "name": "BExpEng — Blender Expression Engine",
    "author": "bexpeng contributors",
    "version": (0, 4, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BExpEng",
    "description": "Parametric expression engine for cross-addon parameter linking",
    "category": "System",
    "doc_url": "https://github.com/falken10vdl/bexpeng",
    "tracker_url": "https://github.com/falken10vdl/bexpeng/issues",
}

# Ensure bundled libraries (asteval, networkx) are importable.
# In a release zip they live under bexpeng/libs/.
import os as _os
import sys as _sys

_libs_dir = _os.path.join(_os.path.dirname(__file__), "libs")
if _os.path.isdir(_libs_dir) and _libs_dir not in _sys.path:
    _sys.path.insert(0, _libs_dir)

# Re-export the public API at package level so users can do:
#   import bexpeng; engine = bexpeng.get_engine()
from .api import get_engine, reset_engine  # noqa: E402, F401
from .engine import (
    CyclicDependencyError,
    ExpressionSyntaxError,
    ParameterHasDependentsError,
    ParameterStillReferencedError,
    ParametricEngine,
)  # noqa: E402, F401

from . import properties, operators, panels, persistence  # noqa: E402

_modules = (properties, operators, panels, persistence)


def register():
    get_engine()  # create the singleton before any module registers
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
