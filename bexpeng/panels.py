# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bexpeng contributors
"""UI panel for the Blender Expression Engine."""

import bpy

from .operators import sync_scene_ui_list

_AUTO_SYNC_INTERVAL_SECONDS = 0.5


def _auto_sync_timer():
    """Keep panel collections synced without mutating Blender IDs in draw()."""
    try:
        for scene in bpy.data.scenes:
            sync_scene_ui_list(scene)
    except Exception:
        # Keep timer resilient; next tick can still recover.
        pass
    return _AUTO_SYNC_INTERVAL_SECONDS


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
    if not bpy.app.timers.is_registered(_auto_sync_timer):
        bpy.app.timers.register(_auto_sync_timer, first_interval=0.2, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_auto_sync_timer):
        bpy.app.timers.unregister(_auto_sync_timer)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
