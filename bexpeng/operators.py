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


class BEXPENG_OT_add_parameter(bpy.types.Operator):
    """Register a new parameter in the expression engine"""

    bl_idname = "bexpeng.add_parameter"
    bl_label = "Add Parameter"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        name = props.new_param_name.strip()
        if not name:
            self.report({"WARNING"}, "Parameter name cannot be empty")
            return {"CANCELLED"}
        if not name.isidentifier():
            self.report({"WARNING"}, f"'{name}' is not a valid Python identifier")
            return {"CANCELLED"}
        engine = get_engine()
        if engine.has_parameter(name):
            self.report({"WARNING"}, f"Parameter '{name}' already exists")
            return {"CANCELLED"}
        engine.register_parameter(name, props.new_param_value)
        _sync_ui_list(context)
        props.new_param_name = ""
        props.new_param_value = 0.0
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


class BEXPENG_OT_add_expression(bpy.types.Operator):
    """Bind an expression to a parameter"""

    bl_idname = "bexpeng.add_expression"
    bl_label = "Set Expression"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        name = props.new_expr_param.strip()
        expr = props.new_expr_text.strip()
        if not name or not expr:
            self.report({"WARNING"}, "Target parameter and expression are required")
            return {"CANCELLED"}

        valid, err = expr_parser.validate_expression(expr)
        if not valid:
            self.report({"ERROR"}, f"Invalid expression: {err}")
            return {"CANCELLED"}

        engine = get_engine()
        try:
            engine.register_expression(name, expr)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        _sync_ui_list(context)
        props.new_expr_param = ""
        props.new_expr_text = ""
        return {"FINISHED"}


class BEXPENG_OT_remove_expression(bpy.types.Operator):
    """Remove the expression from the selected parameter"""

    bl_idname = "bexpeng.remove_expression"
    bl_label = "Remove Expression"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        idx = props.active_expression_index
        if idx < 0 or idx >= len(props.expressions):
            self.report({"WARNING"}, "No parameter selected")
            return {"CANCELLED"}
        name = props.expressions[idx].param_name
        engine = get_engine()
        engine.unregister_expression(name)
        _sync_ui_list(context)
        return {"FINISHED"}


class BEXPENG_OT_set_value(bpy.types.Operator):
    """Update a parameter value and recompute dependents"""

    bl_idname = "bexpeng.set_value"
    bl_label = "Set Value"
    bl_options = {"REGISTER", "UNDO"}

    param_name: bpy.props.StringProperty()
    param_value: bpy.props.FloatProperty()

    def execute(self, context):
        engine = get_engine()
        engine.set_value(self.param_name, self.param_value)
        _sync_ui_list(context)
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
    BEXPENG_OT_add_parameter,
    BEXPENG_OT_remove_parameter,
    BEXPENG_OT_add_expression,
    BEXPENG_OT_remove_expression,
    BEXPENG_OT_set_value,
    BEXPENG_OT_refresh,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
