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
from .groups import GroupManager, ROOT_GROUP_ID


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


def sync_group_ui_list(scene):
    """Synchronise the groups UI collection in *scene* with the GroupManager.

    Builds a flat, DFS-ordered list from ``GroupManager.list_groups()``, honouring
    each group's ``is_expanded`` flag so that collapsed sub-trees are hidden.
    Returns ``True`` when the collection changed.
    """
    props = getattr(scene, "bexpeng", None)
    if props is None:
        return False

    gm = GroupManager.get_instance()
    all_groups = gm.list_groups()  # DFS order, with tree_depth / has_children

    # Capture current UI state keyed by group_id so it survives a full rebuild.
    expanded_state = {item.group_id: item.is_expanded for item in props.groups}
    selected_state = {item.group_id: item.selected for item in props.groups}

    # Build the visible list: skip rows whose ancestor is collapsed.
    collapsed_ids: set = set()
    visible = []
    for g in all_groups:
        if g["parent_id"] in collapsed_ids:
            collapsed_ids.add(g["id"])
            continue
        visible.append(g)
        if not expanded_state.get(g["id"], True):
            collapsed_ids.add(g["id"])

    # Early-exit when nothing changed.
    old_snapshot = [
        (
            item.group_id,
            item.name,
            item.tree_depth,
            item.has_children,
            item.is_expanded,
            item.selected,
        )
        for item in props.groups
    ]
    new_snapshot = [
        (
            g["id"],
            g["name"],
            g["tree_depth"],
            g["has_children"],
            expanded_state.get(g["id"], True),
            selected_state.get(g["id"], False),
        )
        for g in visible
    ]
    if old_snapshot == new_snapshot:
        return False

    # Preserve the active group across the rebuild.
    active_id = None
    idx = props.active_group_index
    if 0 <= idx < len(props.groups):
        active_id = props.groups[idx].group_id

    props.groups.clear()
    for g in visible:
        item = props.groups.add()
        item.group_id = g["id"]  # set before name so the update callback is safe
        item.name = g["name"]  # fires _on_group_name_changed (idempotent no-op)
        item.parent_id = g["parent_id"]
        item.tree_depth = g["tree_depth"]
        item.has_children = g["has_children"]
        item.is_expanded = expanded_state.get(g["id"], True)
        item.selected = selected_state.get(g["id"], False)

    props.active_group_index = -1
    if active_id is not None:
        for i, item in enumerate(props.groups):
            if item.group_id == active_id:
                props.active_group_index = i
                break

    return True


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
        item = props.expressions[idx]
        name = item.param_name
        param_id = item.param_id
        engine = ParametricEngine.get_instance()
        try:
            engine.remove_parameter(name)
        except ParameterStillReferencedError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        except ParameterHasDependentsError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        GroupManager.get_instance().remove_param_from_all_groups(param_id)
        sync_ui_list(context)
        props.active_expression_index = min(idx, len(props.expressions) - 1)
        return {"FINISHED"}


class BEXPENG_OT_add_group(bpy.types.Operator):
    """Add a new group (child of the active group, or a root group if none is active)"""

    bl_idname = "bexpeng.add_group"
    bl_label = "Add Group"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        gm = GroupManager.get_instance()
        parent_id = ""
        idx = props.active_group_index
        if 0 <= idx < len(props.groups):
            parent_id = props.groups[idx].group_id
        gm.add_group("Group", parent_id)
        sync_group_ui_list(context.scene)
        return {"FINISHED"}


class BEXPENG_OT_remove_group(bpy.types.Operator):
    """Remove the active group (parameters are kept; children are promoted to its parent)"""

    bl_idname = "bexpeng.remove_group"
    bl_label = "Remove Group"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        idx = props.active_group_index
        if idx < 0 or idx >= len(props.groups):
            self.report({"WARNING"}, "No group selected")
            return {"CANCELLED"}
        group_id = props.groups[idx].group_id
        try:
            GroupManager.get_instance().remove_group(group_id)
        except (KeyError, ValueError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        sync_group_ui_list(context.scene)
        props.active_group_index = min(idx, len(props.groups) - 1)
        return {"FINISHED"}


class BEXPENG_OT_toggle_group_expand(bpy.types.Operator):
    """Expand or collapse a group in the tree"""

    bl_idname = "bexpeng.toggle_group_expand"
    bl_label = "Toggle Group Expand"

    group_id: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.bexpeng
        for item in props.groups:
            if item.group_id == self.group_id:
                item.is_expanded = not item.is_expanded
                break
        sync_group_ui_list(context.scene)
        return {"FINISHED"}


class BEXPENG_OT_assign_params(bpy.types.Operator):
    """Assign checked parameters to every checked group"""

    bl_idname = "bexpeng.assign_params"
    bl_label = "Assign"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        group_ids = [item.group_id for item in props.groups if item.selected]
        param_ids = [item.param_id for item in props.expressions if item.selected]
        if not group_ids:
            self.report({"WARNING"}, "No groups checked")
            return {"CANCELLED"}
        if not param_ids:
            self.report({"WARNING"}, "No parameters checked")
            return {"CANCELLED"}
        GroupManager.get_instance().assign(group_ids, param_ids)
        return {"FINISHED"}


class BEXPENG_OT_deassign_params(bpy.types.Operator):
    """Remove checked parameters from every checked group"""

    bl_idname = "bexpeng.deassign_params"
    bl_label = "Deassign"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.bexpeng
        group_ids = [item.group_id for item in props.groups if item.selected]
        param_ids = [item.param_id for item in props.expressions if item.selected]
        if not group_ids:
            self.report({"WARNING"}, "No groups checked")
            return {"CANCELLED"}
        if not param_ids:
            self.report({"WARNING"}, "No parameters checked")
            return {"CANCELLED"}
        GroupManager.get_instance().deassign(group_ids, param_ids)
        return {"FINISHED"}


class BEXPENG_OT_select_all_params(bpy.types.Operator):
    """Select / deselect all parameters in Area 2.\n\nAlt-click to invert the current selection instead"""

    bl_idname = "bexpeng.select_all_params"
    bl_label = "Select All Parameters"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(
        items=[
            (
                "TOGGLE",
                "Toggle",
                "Select all, or deselect all if all are already selected",
            ),
            ("INVERT", "Invert", "Invert the current selection"),
        ],
        default="TOGGLE",
    )

    def invoke(self, context, event):
        if event.alt:
            self.action = "INVERT"
        else:
            self.action = "TOGGLE"
        return self.execute(context)

    def execute(self, context):
        items = context.scene.bexpeng.expressions
        if self.action == "INVERT":
            for item in items:
                item.selected = not item.selected
        else:  # TOGGLE
            all_selected = all(item.selected for item in items)
            for item in items:
                item.selected = not all_selected
        return {"FINISHED"}


class BEXPENG_OT_select_all_groups(bpy.types.Operator):
    """Select / deselect all groups in Area 1.\n\nAlt-click to invert the current selection instead"""

    bl_idname = "bexpeng.select_all_groups"
    bl_label = "Select All Groups"
    bl_options = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(
        items=[
            (
                "TOGGLE",
                "Toggle",
                "Select all, or deselect all if all are already selected",
            ),
            ("INVERT", "Invert", "Invert the current selection"),
        ],
        default="TOGGLE",
    )

    def invoke(self, context, event):
        if event.alt:
            self.action = "INVERT"
        else:
            self.action = "TOGGLE"
        return self.execute(context)

    def execute(self, context):
        items = context.scene.bexpeng.groups
        if self.action == "INVERT":
            for item in items:
                item.selected = not item.selected
        else:  # TOGGLE
            all_selected = all(item.selected for item in items)
            for item in items:
                item.selected = not all_selected
        return {"FINISHED"}


classes = (
    BEXPENG_OT_new_parameter,
    BEXPENG_OT_save_edit,
    BEXPENG_OT_remove_parameter,
    BEXPENG_OT_add_group,
    BEXPENG_OT_remove_group,
    BEXPENG_OT_toggle_group_expand,
    BEXPENG_OT_assign_params,
    BEXPENG_OT_deassign_params,
    BEXPENG_OT_select_all_params,
    BEXPENG_OT_select_all_groups,
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
