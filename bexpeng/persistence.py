# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Persistence — save/load engine state with .blend files.

Engine state is serialised as JSON into a Scene custom property
(``scene["bexpeng_data"]``) so it survives file save/load.
"""

from __future__ import annotations

import json

import bpy

from .api import get_engine

_PROP_KEY = "bexpeng_data"


def _save_handler(dummy) -> None:
    """``save_pre`` handler — persist engine state into the scene."""
    engine = get_engine()
    data = engine.to_dict()
    # Store in the active scene (or first scene as fallback)
    target_scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    if target_scene:
        target_scene[_PROP_KEY] = json.dumps(data)


def _load_handler(dummy) -> None:
    """``load_post`` handler — restore engine state from any scene."""
    # Search all scenes for explicit serialized state first.
    raw = None
    for scene in bpy.data.scenes:
        raw = scene.get(_PROP_KEY)
        if raw is not None:
            break

    if raw is not None:
        try:
            data = json.loads(raw)
            engine = get_engine()
            engine.load_dict(data)
            return
        except Exception:
            pass

    # Fallback: rebuild engine from persisted scene UI rows. This prevents
    # clearing panel data on file load when _PROP_KEY is absent.
    rebuilt = 0
    try:
        engine = get_engine()
        for scene in bpy.data.scenes:
            props = getattr(scene, "bexpeng", None)
            if props is None:
                continue
            for item in getattr(props, "expressions", []):
                name = (getattr(item, "param_name", "") or "").strip()
                if not name:
                    continue
                expression = item.expression.strip()
                if not expression:
                    expression = "0"
                try:
                    engine.set_parameter(name, expression)
                except Exception:
                    engine._register_parameter(name, 0.0)
                rebuilt += 1
    except Exception:
        pass


def register():
    bpy.app.handlers.save_pre.append(_save_handler)
    bpy.app.handlers.load_post.append(_load_handler)


def unregister():
    if _save_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_handler)
    if _load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_handler)
