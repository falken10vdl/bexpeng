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

from .engine import ParametricEngine

_PROP_KEY = "bexpeng_data"
_GROUP_PROP_KEY = "bexpeng_groups"


@persistent
def _save_handler(dummy) -> None:
    """``save_pre`` handler — persist engine and group state into the scene."""
    from .groups import GroupManager

    engine = ParametricEngine.get_instance()
    data = engine.to_dict()
    group_data = GroupManager.get_instance().to_dict()
    target_scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    if target_scene:
        target_scene[_PROP_KEY] = json.dumps(data)
        target_scene[_GROUP_PROP_KEY] = json.dumps(group_data)


@persistent
def _load_handler(dummy) -> None:
    """``load_post`` handler — restore engine and group state, then sync the UI."""
    from .groups import GroupManager
    from .operators import sync_group_ui_list, sync_scene_ui_list

    engine = ParametricEngine.get_instance()
    gm = GroupManager.get_instance()

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

    # Load group data
    group_raw = None
    for scene in bpy.data.scenes:
        group_raw = scene.get(_GROUP_PROP_KEY)
        if group_raw is not None:
            break

    if group_raw is not None:
        try:
            group_data = json.loads(group_raw)
            gm.load_dict(group_data)
        except Exception:
            gm.clear()
    else:
        gm.clear()

    # Sync the Blender UI collections to reflect the (now authoritative) state.
    for scene in bpy.data.scenes:
        sync_scene_ui_list(scene)
        sync_group_ui_list(scene)


def register():
    bpy.app.handlers.save_pre.append(_save_handler)
    bpy.app.handlers.load_post.append(_load_handler)


def unregister():
    if _save_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_handler)
    if _load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_handler)
