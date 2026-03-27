# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender operators for managing parameters and expressions."""

import bpy

from .engine import (
    ExpressionSyntaxError,
    ParameterHasDependentsError,
    ParameterRenameError,
    ParameterStillReferencedError,
    ParametricEngine,
)


def sync_scene_ui_list(scene):
    """Synchronise one scene UI collection with the engine state.

    Returns ``True`` when the UI list changed, ``False`` when it was already
    up-to-date.
    """
    props = getattr(scene, "bexpeng", None)
    if props is None:
        return False

    engine = ParametricEngine.get_instance()
    params = engine.list_parameters()

    old_snapshot = [
        (
            item.param_id,
            item.param_name,
            item.expression,
            item.value_str,
            item.observer_count,
            item.dep_count,
            item.description,
        )
        for item in props.expressions
    ]

    new_snapshot = [
        (
            p["id"],
            p["name"],
            p["expression"],
            str(p["value"]) if p["value"] is not None else "—",
            engine.get_observer_count(p["name"]),
            engine.get_dep_count(p["name"]),
            p["description"],
        )
        for p in params
    ]

    if old_snapshot == new_snapshot:
        return False

    # Preserve selection by internal ID (stable across renames)
    selected_id = None
    idx = props.active_expression_index
    if 0 <= idx < len(props.expressions):
        selected_id = props.expressions[idx].param_id

    props.expressions.clear()
    for pid, name, expr, value_str, obs_count, dep_count, desc in new_snapshot:
        item = props.expressions.add()
        item.param_id = pid
        item.param_name = name
        item.expression = expr
        item.value_str = value_str
        item.observer_count = obs_count
        item.dep_count = dep_count
        item.description = desc

    props.active_expression_index = -1
    if selected_id is not None:
        for i, item in enumerate(props.expressions):
            if item.param_id == selected_id:
                props.active_expression_index = i
                break

    idx = props.active_expression_index
    if 0 <= idx < len(props.expressions):
        item = props.expressions[idx]
        props.edit_name = item.param_name
        props.edit_expression = item.expression
        props.edit_description = item.description

    return True


def sync_ui_list(context):
    """Synchronise the active scene UI collection with the engine state."""
    return sync_scene_ui_list(context.scene)


class BEXPENG_OT_new_parameter(bpy.types.Operator):
    """Clear the edit fields to enter a new parameter"""

    bl_idname = "bexpeng.new_parameter"
    bl_label = "New Parameter"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        props.edit_name = ""
        props.edit_expression = "0"
        props.edit_description = ""
        props.active_expression_index = -1
        return {"FINISHED"}


class BEXPENG_OT_save_edit(bpy.types.Operator):
    """Save the name/expression fields — adds a new parameter or updates an existing one"""

    bl_idname = "bexpeng.save_edit"
    bl_label = "Save"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        name = props.edit_name.strip()
        value_str = props.edit_expression.strip()

        if not name:
            self.report({"WARNING"}, "Parameter name cannot be empty")
            return {"CANCELLED"}
        if not name.isidentifier():
            self.report({"WARNING"}, f"'{name}' is not a valid Python identifier")
            return {"CANCELLED"}

        engine = ParametricEngine.get_instance()

        # Capture before any engine call — set_parameter triggers _solve →
        # ui_observer → sync_scene_ui_list, which rewrites
        # props.edit_description from the (not-yet-updated) engine state.
        description = props.edit_description

        # Determine the currently selected parameter (may differ from edit_name)
        selected_id = None
        selected_name = None
        idx = props.active_expression_index
        if 0 <= idx < len(props.expressions):
            selected_id = props.expressions[idx].param_id
            selected_name = props.expressions[idx].param_name

        # Rename if the name field was changed on an existing parameter
        if selected_id is not None and selected_name != name:
            try:
                engine.rename_parameter(selected_name, name)
            except ParameterRenameError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}

        try:
            engine.set_parameter(name, value_str or "0")
        except ExpressionSyntaxError as exc:
            self.report({"ERROR"}, f"Invalid expression: {exc}")
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        engine.set_description(name, description)

        sync_ui_list(context)

        # Re-select by internal ID (stable, even after rename)
        target_id = engine.get_id(name)
        props.active_expression_index = -1
        if target_id is not None:
            for i, item in enumerate(props.expressions):
                if item.param_id == target_id:
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
        engine = ParametricEngine.get_instance()
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
    BEXPENG_OT_new_parameter,
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
    ParametricEngine.get_instance().ui_observer = _ui_post_solve


def unregister():
    engine = ParametricEngine.get_instance()
    if engine.ui_observer is _ui_post_solve:
        engine.ui_observer = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
