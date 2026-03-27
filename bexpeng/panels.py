# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""UI panel for the Blender Expression Engine."""

import bpy
from natsort import natsorted


class BEXPENG_UL_expression_list(bpy.types.UIList):
    """UIList showing registered parameters and their values/expressions."""

    bl_idname = "BEXPENG_UL_expression_list"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property, index
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
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
        sorted_names = natsorted(range(n), key=lambda i: items[i].param_name)
        return flt_flags, sorted_names


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

        # Column headers
        # Outer row: left column holds header + list; right column holds buttons.
        # This ensures the header is constrained to the same width as the list.
        outer = layout.row()
        list_col = outer.column()
        btn_col = outer.column(align=True)

        # Column headers (inside list_col, so they never overlap the buttons)
        header = list_col.row()
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

        # Parameter list
        list_col.template_list(
            "BEXPENG_UL_expression_list",
            "",
            props,
            "expressions",
            props,
            "active_expression_index",
            rows=5,
        )

        # Buttons aligned to the top of the right column
        btn_col.operator("bexpeng.new_parameter", icon="ADD", text="")
        btn_col.operator("bexpeng.remove_parameter", icon="REMOVE", text="")
        # Edit / add entry — always visible at the bottom
        box = layout.box()
        row = box.row(align=True)
        row.prop(props, "edit_name", text="")
        eq = row.row()
        eq.scale_x = 0.24
        eq.label(text="=")
        row.prop(props, "edit_expression", text="")
        row.operator("bexpeng.save_edit", icon="CHECKMARK", text="")
        box.prop(props, "edit_description", text="", placeholder="Description…")


classes = (
    BEXPENG_UL_expression_list,
    BEXPENG_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
