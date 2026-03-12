# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender operators for managing parameters and expressions."""

import bpy

from .api import get_engine
from . import parser as expr_parser


def _sync_ui_list(context):
    """Synchronise the UI collection with the engine state."""
    props = context.scene.bexpeng
    props.expressions.clear()
    engine = get_engine()
    for name, value in engine.list_parameters().items():
        item = props.expressions.add()
        item.param_name = name
        expr = engine.get_expression(name)
        item.expression = expr if expr else ""
        item.value_str = str(value) if value is not None else "—"
        item.raw_value = (
            f"= {expr}" if expr else (str(value) if value is not None else "0")
        )

    # Keep bottom edit fields in sync with current selection
    idx = props.active_expression_index
    if 0 <= idx < len(props.expressions):
        item = props.expressions[idx]
        props.edit_name = item.param_name
        props.edit_value = item.raw_value


class BEXPENG_OT_init_add(bpy.types.Operator):
    """Clear the edit fields to prepare for adding a new parameter"""

    bl_idname = "bexpeng.init_add"
    bl_label = "Add Parameter"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        props.edit_name = ""
        props.edit_value = "0"
        props.active_expression_index = -1
        return {"FINISHED"}


class BEXPENG_OT_save_edit(bpy.types.Operator):
    """Save the name/value fields and propagate changes to the engine"""

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
        idx = props.active_expression_index
        old_name = (
            props.expressions[idx].param_name
            if 0 <= idx < len(props.expressions)
            else None
        )

        # Handle rename: remove the old parameter first
        if old_name and old_name != name and engine.has_parameter(old_name):
            engine.unregister_parameter(old_name)

        if value_str.startswith("="):
            expr = value_str[1:].strip()
            if not expr:
                self.report({"WARNING"}, "Expression cannot be empty after '='")
                return {"CANCELLED"}
            valid, err = expr_parser.validate_expression(expr)
            if not valid:
                self.report({"ERROR"}, f"Invalid expression: {err}")
                return {"CANCELLED"}
            if not engine.has_parameter(name):
                engine.register_parameter(name, 0.0)
            try:
                engine.register_expression(name, expr)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        else:
            try:
                value = float(value_str) if value_str else 0.0
            except ValueError:
                self.report(
                    {"WARNING"},
                    "Value must be a number, or start with '=' for an expression",
                )
                return {"CANCELLED"}
            if engine.has_parameter(name):
                if engine.has_expression(name):
                    engine.unregister_expression(name)
                engine.set_value(name, value)
            else:
                engine.register_parameter(name, value)

        _sync_ui_list(context)

        # Re-select the saved parameter
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
        engine.unregister_parameter(name)
        _sync_ui_list(context)
        props.active_expression_index = min(idx, len(props.expressions) - 1)
        return {"FINISHED"}


class BEXPENG_OT_refresh(bpy.types.Operator):
    """Refresh the expression list from the engine"""

    bl_idname = "bexpeng.refresh"
    bl_label = "Refresh"

    def execute(self, context):
        engine = get_engine()
        engine._solve()
        _sync_ui_list(context)
        return {"FINISHED"}


classes = (
    BEXPENG_OT_init_add,
    BEXPENG_OT_save_edit,
    BEXPENG_OT_remove_parameter,
    BEXPENG_OT_refresh,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
