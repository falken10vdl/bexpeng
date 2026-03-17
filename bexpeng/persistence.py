# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Persistence — save/load engine state with .blend files.

Engine state is serialised as JSON into a Scene custom property
(``scene["bexpeng_data"]``) so it survives file save/load.
"""

from __future__ import annotations

import json
import logging

import bpy

from .api import get_engine, reset_engine

log = logging.getLogger(__name__)

_PROP_KEY = "bexpeng_data"


def _save_handler(dummy) -> None:
    """``save_pre`` handler — persist engine state into the scene."""
    engine = get_engine()
    data = engine.to_dict()
    # Store in the active scene (or first scene as fallback)
    target_scene = bpy.context.scene if bpy.context.scene else bpy.data.scenes[0]
    if target_scene:
        target_scene[_PROP_KEY] = json.dumps(data)
        log.debug("bexpeng: saved engine state to scene '%s'", target_scene.name)


def _load_handler(dummy) -> None:
    """``load_post`` handler — restore engine state from any scene."""
    reset_engine()
    # Search all scenes for the saved data (in case the active scene changed)
    raw = None
    for scene in bpy.data.scenes:
        raw = scene.get(_PROP_KEY)
        if raw is not None:
            log.debug("bexpeng: found saved state in scene '%s'", scene.name)
            break
    if raw is None:
        return
    try:
        data = json.loads(raw)
        engine = get_engine()
        engine.load_dict(data)
        log.info(
            "bexpeng: restored %d parameters, %d expressions",
            len(engine.list_parameters()),
            len(engine.list_expressions()),
        )
    except Exception as exc:
        log.error("bexpeng: failed to restore engine state: %s", exc)


def register():
    bpy.app.handlers.save_pre.append(_save_handler)
    bpy.app.handlers.load_post.append(_load_handler)


def unregister():
    if _save_handler in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_save_handler)
    if _load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_handler)
