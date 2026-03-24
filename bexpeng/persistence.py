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
    print(
        f"[bexpeng] _save_handler: persisting {list(data.get('expressions', {}).keys())}"
    )
    # Store in the active scene (or first scene as fallback)
    target_scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    if target_scene:
        target_scene[_PROP_KEY] = json.dumps(data)
        print(
            f"[bexpeng] _save_handler: wrote bexpeng_data to scene '{target_scene.name}'"
        )


@persistent
def _load_handler(dummy) -> None:
    """``load_post`` handler — restore engine state from the scene, then sync the UI."""
    from .operators import sync_scene_ui_list

    print("[bexpeng] _load_handler: START")
    engine = get_engine()
    print(
        f"[bexpeng] _load_handler: engine before load has params: {list(engine._list_parameters().keys())}"
    )

    raw = None
    for scene in bpy.data.scenes:
        raw = scene.get(_PROP_KEY)
        if raw is not None:
            print(
                f"[bexpeng] _load_handler: found bexpeng_data in scene '{scene.name}'"
            )
            break

    if raw is None:
        print(
            "[bexpeng] _load_handler: no bexpeng_data found in any scene — clearing engine"
        )

    if raw is not None:
        try:
            data = json.loads(raw)
            print(
                f"[bexpeng] _load_handler: loading expressions: {list(data.get('expressions', {}).keys())}"
            )
            engine.load_dict(data)
            print(
                f"[bexpeng] _load_handler: engine after load_dict: {list(engine._list_parameters().keys())}"
            )
        except Exception as exc:
            print(
                f"[bexpeng] _load_handler: load_dict FAILED ({exc}) — clearing engine"
            )
            engine.clear()
    else:
        engine.clear()

    # Sync the Blender UI collection to reflect the (now authoritative) engine
    # state.  Without this, props.expressions retains stale rows from the
    # previous session and the panel appears correct until the first Refresh.
    for scene in bpy.data.scenes:
        changed = sync_scene_ui_list(scene)
        props = getattr(scene, "bexpeng", None)
        rows = [item.param_name for item in props.expressions] if props else []
        print(
            f"[bexpeng] _load_handler: sync_scene_ui_list scene='{scene.name}' changed={changed} rows={rows}"
        )

    print("[bexpeng] _load_handler: END")


def register():
    bpy.app.handlers.save_pre.append(_save_handler)
    bpy.app.handlers.load_post.append(_load_handler)


def unregister():
    if _save_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_handler)
    if _load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_handler)
