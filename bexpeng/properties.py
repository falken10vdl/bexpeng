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


def _on_group_name_changed(self, context):
    """Propagate inline group renames from the UIList to the GroupManager."""
    if not self.group_id:
        return
    from .groups import GroupManager

    try:
        GroupManager.get_instance().rename_group(self.group_id, self.name)
    except KeyError:
        pass


class BEXPENG_GroupItem(bpy.types.PropertyGroup):
    """A single group entry shown in the group-tree UI list."""

    group_id: bpy.props.StringProperty(
        name="Group ID",
        description="Immutable internal identifier (e.g. bxpg0)",
    )
    name: bpy.props.StringProperty(
        name="Group Name",
        description="Display name of this group",
        update=_on_group_name_changed,
    )
    parent_id: bpy.props.StringProperty(
        name="Parent Group ID",
        description="ID of the parent group; empty string for root groups",
    )
    tree_depth: bpy.props.IntProperty(
        name="Tree Depth",
        description="Nesting depth in the group tree (0 = root)",
        default=0,
        min=0,
    )
    has_children: bpy.props.BoolProperty(
        name="Has Children",
        description="True when this group has sub-groups",
        default=False,
    )
    is_expanded: bpy.props.BoolProperty(
        name="Expanded",
        description="Whether the group's children are visible in the tree",
        default=True,
    )
    selected: bpy.props.BoolProperty(
        name="Selected",
        description="Mark this group for Assign/Deassign operations",
        default=False,
    )


class BEXPENG_ExpressionItem(bpy.types.PropertyGroup):
    """A single expression entry shown in the UI list."""

    param_id: bpy.props.StringProperty(
        name="Internal ID",
        description="Immutable internal identifier (e.g. bxp0). Use this to attach observers.",
    )
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
    selected: bpy.props.BoolProperty(
        name="Selected",
        description="Mark this parameter for Assign/Deassign operations",
        default=False,
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

    # Group management
    groups: bpy.props.CollectionProperty(type=BEXPENG_GroupItem)
    active_group_index: bpy.props.IntProperty(
        name="Active Group",
        default=-1,
    )
    param_filter_mode: bpy.props.EnumProperty(
        name="Parameter Filter",
        description="Filter the parameter list by group membership",
        items=[
            ("ALL", "All", "Show all parameters"),
            ("CHECKED", "Checked", "Show only parameters in checked groups"),
            ("ACTIVE", "Active", "Show only parameters in the active group"),
        ],
        default="ALL",
    )


classes = (
    BEXPENG_GroupItem,
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
