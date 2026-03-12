# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""UI panel for the Blender Expression Engine."""

import bpy


class BEXPENG_UL_expression_list(bpy.types.UIList):
    """UIList showing registered parameters and their values/expressions."""

    bl_idname = "BEXPENG_UL_expression_list"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property, index
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.param_name)
            row.label(text=item.raw_value)
            if item.expression:
                row.label(text=f"[{item.value_str}]")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.param_name)


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

        # Parameter list with add / remove / refresh buttons on the right
        row = layout.row()
        row.template_list(
            "BEXPENG_UL_expression_list",
            "",
            props,
            "expressions",
            props,
            "active_expression_index",
            rows=5,
        )

        col = row.column(align=True)
        col.operator("bexpeng.init_add", icon="ADD", text="")
        col.operator("bexpeng.remove_parameter", icon="REMOVE", text="")
        col.separator()
        col.operator("bexpeng.refresh", icon="FILE_REFRESH", text="")

        # Edit / add entry — always visible at the bottom
        box = layout.box()
        row = box.row(align=True)
        row.prop(props, "edit_name", text="Name")
        row.prop(props, "edit_value", text="Value")
        row.operator("bexpeng.save_edit", icon="CHECKMARK", text="")


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
