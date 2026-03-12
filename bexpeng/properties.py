# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""Blender property groups for the expression engine UI."""

import bpy


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


class BEXPENG_SceneProperties(bpy.types.PropertyGroup):
    """Scene-level properties for bexpeng."""

    expressions: bpy.props.CollectionProperty(type=BEXPENG_ExpressionItem)
    active_expression_index: bpy.props.IntProperty(name="Active Expression")

    # Fields for adding new entries
    new_param_name: bpy.props.StringProperty(
        name="Name",
        description="Parameter name",
    )
    new_param_value: bpy.props.FloatProperty(
        name="Value",
        description="Initial parameter value",
    )
    new_expr_param: bpy.props.StringProperty(
        name="Target",
        description="Parameter to bind the expression to",
    )
    new_expr_text: bpy.props.StringProperty(
        name="Expression",
        description="Expression string (e.g. '2 * wall_length')",
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
