# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Persistence — save/load engine state with .blend files.

Engine state is serialised as JSON into a Scene custom property
(``scene["bexpeng_data"]``) so it survives file save/load.
"""

from __future__ import annotations

import json

import bpy
from bpy.app.handlers import persistent

from .api import get_engine

_PROP_KEY = "bexpeng_data"


@persistent
def _save_handler(dummy) -> None:
    """``save_pre`` handler — persist engine state into the scene."""
    engine = get_engine()
    data = engine.to_dict()
    # Store in the active scene (or first scene as fallback)
    target_scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    if target_scene:
        target_scene[_PROP_KEY] = json.dumps(data)


@persistent
def _load_handler(dummy) -> None:
    """``load_post`` handler — restore engine state from the scene, then sync the UI."""
    from .operators import sync_scene_ui_list

    engine = get_engine()

    raw = None
    for scene in bpy.data.scenes:
        raw = scene.get(_PROP_KEY)
        if raw is not None:
            break

    if raw is not None:
        try:
            data = json.loads(raw)
            engine.load_dict(data)
        except Exception:
            engine.clear()
    else:
        engine.clear()

    # Sync the Blender UI collection to reflect the (now authoritative) engine
    # state.  Without this, props.expressions retains stale rows from the
    # previous session and the panel appears correct until the first Refresh.
    for scene in bpy.data.scenes:
        sync_scene_ui_list(scene)


def register():
    bpy.app.handlers.save_pre.append(_save_handler)
    bpy.app.handlers.load_post.append(_load_handler)


def unregister():
    if _save_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_handler)
    if _load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_handler)
