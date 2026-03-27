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
    descriptions = engine._list_descriptions()

    # Build stable snapshots so we only rebuild the Blender collection when
    # the underlying engine state changed.
    old_snapshot = [
        (
            item.param_name,
            item.expression,
            item.value_str,
            item.ref_count,
            item.dep_count,
            item.description,
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
                descriptions.get(name, ""),
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
        item.description = descriptions.get(name, "")

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
        props.edit_expression = item.expression
        props.edit_description = item.description

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
        value_str = props.edit_expression.strip()

        if not name:
            self.report({"WARNING"}, "Parameter name cannot be empty")
            return {"CANCELLED"}
        if not name.isidentifier():
            self.report({"WARNING"}, f"'{name}' is not a valid Python identifier")
            return {"CANCELLED"}

        engine = get_engine()

        # Capture before any engine call — set_parameter triggers _solve →
        # bexpeng_panel_update → sync_scene_ui_list, which rewrites
        # props.edit_description from the (not-yet-updated) engine state.
        description = props.edit_description
        print(
            f"[bexpeng] save_edit: name={name!r} expr={value_str!r} description={description!r}"
        )

        try:
            engine.set_parameter(name, value_str or "0")
        except ExpressionSyntaxError as exc:
            self.report({"ERROR"}, f"Invalid expression: {exc}")
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        print(
            f"[bexpeng] after set_parameter: props.edit_description={props.edit_description!r}"
        )
        print(f"[bexpeng] calling engine.set_description({name!r}, {description!r})")
        engine.set_description(name, description)
        print(
            f"[bexpeng] engine.get_description({name!r}) = {engine.get_description(name)!r}"
        )

        sync_ui_list(context)

        print(
            f"[bexpeng] after sync_ui_list: props.edit_description={props.edit_description!r}"
        )

        # Select the saved parameter
        for i, item in enumerate(props.expressions):
            if item.param_name == name:
                props.active_expression_index = i
                print(f"[bexpeng] item.description after sync = {item.description!r}")
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
