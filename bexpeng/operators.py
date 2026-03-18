# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender operators for managing parameters and expressions."""

import logging

import bpy

from .api import get_engine
from . import parser as expr_parser


log = logging.getLogger(__name__)


def sync_scene_ui_list(scene):
    """Synchronise one scene UI collection with the engine state.

    Returns ``True`` when the UI list changed, ``False`` when it was already
    up-to-date.
    """
    props = getattr(scene, "bexpeng", None)
    if props is None:
        return False

    engine = get_engine()

    parameters = engine.list_parameters()
    expressions = engine.list_expressions()

    # If engine is empty but the scene UI list already has persisted rows,
    # rebuild engine from those rows instead of clearing the UI on sync.
    if not parameters and len(props.expressions):
        rebuilt = 0
        rebuilt_expr = 0
        for item in props.expressions:
            name = (getattr(item, "param_name", "") or "").strip()
            raw_value = (getattr(item, "raw_value", "") or "").strip()
            if not name:
                continue
            if raw_value.startswith("="):
                expr = raw_value[1:].strip()
                if not engine.has_parameter(name):
                    engine.register_parameter(name, 0.0)
                if expr:
                    engine.register_expression(name, expr)
                    rebuilt_expr += 1
            else:
                ok, parsed_value, _ = expr_parser.parse_manual_value(raw_value)
                value = parsed_value if ok else 0.0
                engine.register_parameter(name, value)
            rebuilt += 1
        parameters = engine.list_parameters()
        expressions = engine.list_expressions()

    # Build stable snapshots so we only rebuild the Blender collection when
    # the underlying engine state changed.
    old_snapshot = [
        (
            item.param_name,
            item.expression,
            item.value_str,
            item.raw_value,
            item.ref_count,
        )
        for item in props.expressions
    ]

    new_snapshot = []
    for name, value in parameters.items():
        expr = expressions.get(name)
        value_str = str(value) if value is not None else "—"
        raw_value = (
            f"= {expr}"
            if expr
            else (expr_parser.format_direct_value(value) if value is not None else "0")
        )
        new_snapshot.append(
            (
                name,
                expr if expr else "",
                value_str,
                raw_value,
                engine.get_ref_count(name),
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
        expr = expressions.get(name)
        item.expression = expr if expr else ""
        item.value_str = str(value) if value is not None else "—"
        item.raw_value = (
            f"= {expr}"
            if expr
            else (expr_parser.format_direct_value(value) if value is not None else "0")
        )
        item.ref_count = engine.get_ref_count(name)

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
        props.edit_value = item.raw_value

    return True


def sync_ui_list(context):
    """Synchronise the active scene UI collection with the engine state."""
    return sync_scene_ui_list(context.scene)


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
        idx = props.active_expression_index
        old_name = (
            props.expressions[idx].param_name
            if 0 <= idx < len(props.expressions)
            else None
        )

        if not name:
            self.report({"WARNING"}, "Parameter name cannot be empty")
            return {"CANCELLED"}
        if old_name != name and not name.isidentifier():
            self.report({"WARNING"}, f"'{name}' is not a valid Python identifier")
            return {"CANCELLED"}

        engine = get_engine()

        log.warning(
            "[bexpeng.save_edit] start name=%r old_name=%r value_str=%r",
            name,
            old_name,
            value_str,
        )

        # Handle rename: remove the old parameter first
        if old_name and old_name != name and engine.has_parameter(old_name):
            log.warning(
                "[bexpeng.save_edit] rename: unregister old parameter %r", old_name
            )
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
                log.warning(
                    "[bexpeng.save_edit] create parameter %r with initial value 0.0",
                    name,
                )
                engine.register_parameter(name, 0.0)
            try:
                log.warning(
                    "[bexpeng.save_edit] register expression %r = %r", name, expr
                )
                engine.register_expression(name, expr)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                log.warning(
                    "[bexpeng.save_edit] expression registration failed for %r: %s",
                    name,
                    exc,
                )
                return {"CANCELLED"}
        else:
            ok, value, err = expr_parser.parse_manual_value(value_str)
            if not ok:
                self.report({"WARNING"}, err)
                return {"CANCELLED"}
            if engine.has_parameter(name):
                if engine.has_expression(name):
                    log.warning(
                        "[bexpeng.save_edit] unregister expression for %r before setting direct value",
                        name,
                    )
                    engine.unregister_expression(name)
                log.warning("[bexpeng.save_edit] set_value %r = %r", name, value)
                engine.set_value(name, value)
            else:
                log.warning(
                    "[bexpeng.save_edit] register_parameter %r = %r", name, value
                )
                engine.register_parameter(name, value)

        current_value = engine.get_value(name)
        current_expr = (
            engine.get_expression(name) if engine.has_parameter(name) else None
        )
        subscribers = len(getattr(engine, "_subscribers", {}).get(name, []))
        log.warning(
            "[bexpeng.save_edit] end name=%r value=%r expression=%r subscribers=%d",
            name,
            current_value,
            current_expr,
            subscribers,
        )

        sync_ui_list(context)

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
        sync_ui_list(context)
        props.active_expression_index = min(idx, len(props.expressions) - 1)
        return {"FINISHED"}


class BEXPENG_OT_refresh(bpy.types.Operator):
    """Refresh the expression list from the engine"""

    bl_idname = "bexpeng.refresh"
    bl_label = "Refresh"

    def execute(self, context):
        engine = get_engine()
        engine._solve()
        sync_ui_list(context)
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
