# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Public API re-exports for bexpeng.

External addons access the engine via the Singleton class method::

    from bexpeng.engine import ParametricEngine

    engine = ParametricEngine.get_instance()
    engine.set_parameter("wall_length", "5.0")
    engine.attach("wall_length", lambda name: ...)

To replace the instance (e.g. on file load)::

    ParametricEngine.reset_instance()
"""

from .engine import (
    CyclicDependencyError,
    ExpressionSyntaxError,
    ParameterHasDependentsError,
    ParameterStillReferencedError,
    ParametricEngine,
)

__all__ = [
    "ParametricEngine",
    "CyclicDependencyError",
    "ExpressionSyntaxError",
    "ParameterStillReferencedError",
    "ParameterHasDependentsError",
]
