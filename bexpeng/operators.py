# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender operators for managing parameters and expressions."""

import bpy

from .api import get_engine
from .engine import (
    ExpressionSyntaxError,
    ParameterHasDependentsError,
    ParameterStillReferencedError,
)


def sync_scene_ui_list(scene):
    """Synchronise one scene UI collection with the engine state.

    Returns ``True`` when the UI list changed, ``False`` when it was already
    up-to-date.
    """
    props = getattr(scene, "bexpeng", None)
    if props is None:
        return False

    engine = get_engine()

    parameters = engine._list_parameters()
    expressions = engine._list_expressions()

    # Build stable snapshots so we only rebuild the Blender collection when
    # the underlying engine state changed.
    old_snapshot = [
        (
            item.param_name,
            item.expression,
            item.value_str,
            item.ref_count,
            item.dep_count,
        )
        for item in props.expressions
    ]

    new_snapshot = []
    for name, value in parameters.items():
        expr = expressions.get(name, "0")
        value_str = str(value) if value is not None else "—"
        new_snapshot.append(
            (
                name,
                expr,
                value_str,
                engine.get_ref_count(name),
                engine.get_dep_count(name),
            )
        )

    if old_snapshot == new_snapshot:
        return False

    selected_name = None
    idx = props.active_expression_index
    if 0 <= idx < len(props.expressions):
        selected_name = props.expressions[idx].param_name

    props.expressions.clear()
    for name, value in parameters.items():
        item = props.expressions.add()
        item.param_name = name
        item.expression = expressions.get(name, "0")
        item.value_str = str(value) if value is not None else "—"
        item.ref_count = engine.get_ref_count(name)
        item.dep_count = engine.get_dep_count(name)

    # Keep selection and edit fields stable if possible.
    props.active_expression_index = -1
    if selected_name is not None:
        for i, item in enumerate(props.expressions):
            if item.param_name == selected_name:
                props.active_expression_index = i
                break

    idx = props.active_expression_index
    if 0 <= idx < len(props.expressions):
        item = props.expressions[idx]
        props.edit_name = item.param_name
        props.edit_value = item.expression

    return True


def sync_ui_list(context):
    """Synchronise the active scene UI collection with the engine state."""
    return sync_scene_ui_list(context.scene)


class BEXPENG_OT_save_edit(bpy.types.Operator):
    """Save the name/expression fields — adds a new parameter or updates an existing one"""

    bl_idname = "bexpeng.save_edit"
    bl_label = "Save"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        name = props.edit_name.strip()
        value_str = props.edit_value.strip()

        if not name:
            self.report({"WARNING"}, "Parameter name cannot be empty")
            return {"CANCELLED"}
        if not name.isidentifier():
            self.report({"WARNING"}, f"'{name}' is not a valid Python identifier")
            return {"CANCELLED"}

        engine = get_engine()

        try:
            engine.set_parameter(name, value_str or "0")
        except ExpressionSyntaxError as exc:
            self.report({"ERROR"}, f"Invalid expression: {exc}")
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        sync_ui_list(context)

        # Select the saved parameter in the list
        for i, item in enumerate(props.expressions):
            if item.param_name == name:
                props.active_expression_index = i
                break

        return {"FINISHED"}


class BEXPENG_OT_remove_parameter(bpy.types.Operator):
    """Remove the selected parameter from the engine"""

    bl_idname = "bexpeng.remove_parameter"
    bl_label = "Remove Parameter"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        idx = props.active_expression_index
        if idx < 0 or idx >= len(props.expressions):
            self.report({"WARNING"}, "No parameter selected")
            return {"CANCELLED"}
        name = props.expressions[idx].param_name
        engine = get_engine()
        try:
            engine.remove_parameter(name)
        except ParameterStillReferencedError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        except ParameterHasDependentsError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        sync_ui_list(context)
        props.active_expression_index = min(idx, len(props.expressions) - 1)
        return {"FINISHED"}


classes = (
    BEXPENG_OT_save_edit,
    BEXPENG_OT_remove_parameter,
)


def _ui_post_solve() -> None:
    """Hook called by the engine after every solve; syncs all scene UI lists."""
    for scene in bpy.data.scenes:
        sync_scene_ui_list(scene)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    get_engine().bexpeng_panel_update = _ui_post_solve


def unregister():
    engine = get_engine()
    if engine.bexpeng_panel_update is _ui_post_solve:
        engine.bexpeng_panel_update = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
