# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""UI panel for the Blender Expression Engine."""

import bpy


class BEXPENG_UL_expression_list(bpy.types.UIList):
    """UIList showing registered parameters and their expressions."""

    bl_idname = "BEXPENG_UL_expression_list"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property, index
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.param_name, icon="DOT")
            if item.expression:
                row.label(text=f"= {item.expression}")
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

        # Expression list
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
        col.operator("bexpeng.remove_parameter", icon="REMOVE", text="")
        col.operator("bexpeng.remove_expression", icon="X", text="")
        col.separator()
        col.operator("bexpeng.refresh", icon="FILE_REFRESH", text="")

        # Add parameter section
        box = layout.box()
        box.label(text="Add Parameter", icon="ADD")
        row = box.row(align=True)
        row.prop(props, "new_param_name", text="Name")
        row.prop(props, "new_param_value", text="Value")
        box.operator("bexpeng.add_parameter", icon="CHECKMARK")

        # Add expression section
        box = layout.box()
        box.label(text="Set Expression", icon="SCRIPT")
        box.prop(props, "new_expr_param", text="Target")
        box.prop(props, "new_expr_text", text="Expr")
        box.operator("bexpeng.add_expression", icon="CHECKMARK")


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
