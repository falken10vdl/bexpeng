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
        self.edit_expression = item.expression
        self.edit_description = item.description


class BEXPENG_ExpressionItem(bpy.types.PropertyGroup):
    """A single expression entry shown in the UI list."""

    param_name: bpy.props.StringProperty(
        name="Parameter",
        description="Name of the parameter",
    )
    expression: bpy.props.StringProperty(
        name="Expression",
        description="Expression that computes this parameter's value (a literal number, quoted string, or formula)",
    )
    value_str: bpy.props.StringProperty(
        name="Value",
        description="Current evaluated value (display only)",
        default="—",
    )
    description: bpy.props.StringProperty(
        name="Description",
        description="Optional human-readable description of this parameter",
        default="",
    )
    observer_count: bpy.props.IntProperty(
        name="Observers",
        description="Number of observers currently attached to this parameter",
        default=0,
        min=0,
    )
    dep_count: bpy.props.IntProperty(
        name="Dependents",
        description="Number of parameters whose expressions reference this parameter",
        default=0,
        min=0,
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
    edit_expression: bpy.props.StringProperty(
        name="Expression",
        description='A number (e.g. 3.0), a quoted string (e.g. "Beam A"), or a formula referencing other parameters (e.g. storey_height - 0.3)',
        default="0",
    )
    edit_description: bpy.props.StringProperty(
        name="Description",
        description="Optional human-readable description for this parameter",
        default="",
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
