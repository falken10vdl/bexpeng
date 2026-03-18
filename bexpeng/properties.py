# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender property groups for the expression engine UI."""

import bpy


def _on_active_index_changed(self, context):
    """Populate the bottom edit fields when the active list item changes."""
    idx = self.active_expression_index
    if 0 <= idx < len(self.expressions):
        item = self.expressions[idx]
        self.edit_name = item.param_name
        self.edit_value = item.raw_value


class BEXPENG_ExpressionItem(bpy.types.PropertyGroup):
    """A single expression entry shown in the UI list."""

    param_name: bpy.props.StringProperty(
        name="Parameter",
        description="Name of the parameter",
    )
    expression: bpy.props.StringProperty(
        name="Expression",
        description="Expression that computes this parameter's value",
    )
    value_str: bpy.props.StringProperty(
        name="Value",
        description="Current evaluated value (display only)",
        default="—",
    )
    raw_value: bpy.props.StringProperty(
        name="Raw Value",
        description="User-facing value string: a number, or '= expr' for expressions",
        default="0",
    )


class BEXPENG_SceneProperties(bpy.types.PropertyGroup):
    """Scene-level properties for bexpeng."""

    expressions: bpy.props.CollectionProperty(type=BEXPENG_ExpressionItem)
    active_expression_index: bpy.props.IntProperty(
        name="Active Expression",
        update=_on_active_index_changed,
    )

    # Bottom edit / add fields
    edit_name: bpy.props.StringProperty(
        name="Name",
        description="Parameter name to add or edit",
    )
    edit_value: bpy.props.StringProperty(
        name="Value",
        description="Number, quoted string literal, or start with '=' for an expression (e.g. '= a * 2')",
        default="0",
    )


classes = (
    BEXPENG_ExpressionItem,
    BEXPENG_SceneProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bexpeng = bpy.props.PointerProperty(type=BEXPENG_SceneProperties)


def unregister():
    del bpy.types.Scene.bexpeng
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
