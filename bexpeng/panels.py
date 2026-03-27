# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""UI panel for the Blender Expression Engine."""

import bpy
from natsort import natsorted


class BEXPENG_UL_group_list(bpy.types.UIList):
    """UIList showing groups as an indented, collapsible tree."""

    bl_idname = "BEXPENG_UL_group_list"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property, index
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            # Split: tree name on the left, checkbox pinned to the right.
            split = layout.split(factor=0.85, align=True)
            row = split.row(align=True)

            # Indentation: two BLANK1 icons per depth level for clear nesting.
            for _ in range(item.tree_depth):
                ind = row.row(align=True)
                ind.scale_x = 0.4
                ind.label(text="", icon="BLANK1")
                ind2 = row.row(align=True)
                ind2.scale_x = 0.4
                ind2.label(text="", icon="BLANK1")

            # Expand / collapse toggle
            if item.has_children:
                exp_icon = (
                    "DISCLOSURE_TRI_DOWN"
                    if item.is_expanded
                    else "DISCLOSURE_TRI_RIGHT"
                )
                op = row.operator(
                    "bexpeng.toggle_group_expand",
                    text="",
                    icon=exp_icon,
                    emboss=False,
                )
                op.group_id = item.group_id
            else:
                spacer = row.row(align=True)
                spacer.scale_x = 0.6
                spacer.label(text="", icon="BLANK1")

            # Editable name fills remaining left-column space
            row.prop(item, "name", text="", emboss=False)

            # Checkbox pinned to right column
            split.prop(item, "selected", text="")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)

    def filter_items(self, context, data, propname):
        # sync_group_ui_list already hides collapsed children, so show everything.
        items = getattr(data, propname)
        flt_flags = [self.bitflag_filter_item] * len(items)
        return flt_flags, []


class BEXPENG_UL_expression_list(bpy.types.UIList):
    """UIList showing registered parameters and their values/expressions."""

    bl_idname = "BEXPENG_UL_expression_list"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property, index
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "selected", text="")
            row.label(text=item.param_name)
            row.label(text=item.expression)
            row.label(text=item.value_str)
            ref_col = row.row(align=True)
            ref_col.scale_x = 0.45
            ref_col.label(
                text=str(item.observer_count) if item.observer_count > 0 else "—"
            )
            dep_col = row.row(align=True)
            dep_col.scale_x = 0.45
            dep_col.label(text=str(item.dep_count) if item.dep_count > 0 else "—")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.param_name)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        n = len(items)
        flt_flags = [self.bitflag_filter_item] * n

        # Apply the text filter (typed in the search bar) against both
        # param_name and description — case-insensitive substring match.
        if self.filter_name:
            needle = self.filter_name.lower()
            for i, item in enumerate(items):
                if (
                    needle not in item.param_name.lower()
                    and needle not in item.description.lower()
                ):
                    flt_flags[i] = 0

        # Apply group-membership filter.
        props = context.scene.bexpeng
        mode = props.param_filter_mode

        if mode != "ALL":
            from .groups import GroupManager

            gm = GroupManager.get_instance()
            if mode == "CHECKED":
                checked_gids = [g.group_id for g in props.groups if g.selected]
                visible_ids: set = set()
                for gid in checked_gids:
                    visible_ids.update(gm.get_group_members(gid))
            else:  # ACTIVE
                idx = props.active_group_index
                if 0 <= idx < len(props.groups):
                    visible_ids = gm.get_group_members(props.groups[idx].group_id)
                else:
                    visible_ids = set()
            for i, item in enumerate(items):
                if item.param_id not in visible_ids:
                    flt_flags[i] = 0

        sorted_order = natsorted(range(n), key=lambda i: items[i].param_name)
        return flt_flags, sorted_order


class BEXPENG_PT_main_panel(bpy.types.Panel):
    """Expression Engine — main panel"""

    bl_label = "Expression Engine"
    bl_idname = "BEXPENG_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BExpEng"

    def draw(self, context):
        layout = self.layout
        props = context.scene.bexpeng

        # ─── Area 1: Group tree ───────────────────────────────────────────────
        layout.label(text="Groups")
        outer1 = layout.row()
        list_col1 = outer1.column()
        btn_col1 = outer1.column(align=True)

        list_col1.template_list(
            "BEXPENG_UL_group_list",
            "",
            props,
            "groups",
            props,
            "active_group_index",
            rows=4,
        )
        btn_col1.operator("bexpeng.add_group", icon="ADD", text="")
        btn_col1.operator("bexpeng.remove_group", icon="REMOVE", text="")
        btn_col1.operator(
            "bexpeng.select_all_groups", icon="RESTRICT_SELECT_OFF", text=""
        )

        # ─── Centre row: Assign / Deassign ────────────────────────────────────
        row = layout.row(align=True)
        row.operator("bexpeng.assign_params", text="Assign")
        row.operator("bexpeng.deassign_params", text="Deassign")

        # ─── Area 2: Parameter list ───────────────────────────────────────────
        layout.prop(props, "param_filter_mode", expand=True)

        outer2 = layout.row()
        list_col2 = outer2.column()
        btn_col2 = outer2.column(align=True)

        # Column headers
        header = list_col2.row()
        chk_h = header.row()
        chk_h.scale_x = 0.15
        chk_h.label(text="")
        header.label(text="Name")
        header.label(text="Expression")
        header.label(text="Value")
        ref_h = header.row()
        ref_h.scale_x = 0.45
        ref_h.label(text="#Obs")
        dep_h = header.row()
        dep_h.scale_x = 0.45
        dep_h.label(text="#Dep")
        pad = header.row()
        pad.scale_x = 0.12
        pad.label(text="")

        list_col2.template_list(
            "BEXPENG_UL_expression_list",
            "",
            props,
            "expressions",
            props,
            "active_expression_index",
            rows=5,
        )
        btn_col2.operator("bexpeng.new_parameter", icon="ADD", text="")
        btn_col2.operator("bexpeng.remove_parameter", icon="REMOVE", text="")
        btn_col2.operator(
            "bexpeng.select_all_params", icon="RESTRICT_SELECT_OFF", text=""
        )

        # ─── Area 3: Parameter detail ─────────────────────────────────────────
        box = layout.box()
        row = box.row(align=True)
        row.prop(props, "edit_name", text="")
        eq = row.row()
        eq.scale_x = 0.24
        eq.label(text="=")
        row.prop(props, "edit_expression", text="")
        row.operator("bexpeng.save_edit", icon="CHECKMARK", text="")
        box.prop(props, "edit_description", text="", placeholder="Description…")

        # Group membership display
        idx = props.active_expression_index
        if 0 <= idx < len(props.expressions):
            from .groups import GroupManager

            item = props.expressions[idx]
            gm = GroupManager.get_instance()
            group_ids = gm.get_param_groups(item.param_id)
            if group_ids:
                names = " · ".join(gm.get_group_name(gid) or gid for gid in group_ids)
                box.label(text=f"Groups: {names}")
            else:
                box.label(text="Groups: —")


classes = (
    BEXPENG_UL_group_list,
    BEXPENG_UL_expression_list,
    BEXPENG_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
