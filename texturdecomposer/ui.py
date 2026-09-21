"""Sidebar UI for the Textur Decomposer addon."""

import bpy


def _active_projector(scene):
    obj = scene.td.active_projector
    if obj is not None and obj.td_proj.is_projector:
        return obj
    return None


class TD_PT_main(bpy.types.Panel):
    bl_label = "Textur Decomposer"
    bl_idname = "TD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Textur Decomposer"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        td = scene.td

        col = layout.column(align=True)
        col.operator("td.import_image", icon="IMAGE_DATA")
        col.operator("td.add_projection", icon="MESH_PLANE")
        col.operator("td.frame_source", icon="CAMERA_DATA")

        layout.separator()
        box = layout.box()
        box.label(text="Projection Planes", icon="OUTLINER_OB_EMPTY")
        projectors = [obj for obj in scene.objects if obj.td_proj.is_projector]
        if not projectors:
            box.label(text="None yet", icon="INFO")
        for obj in projectors:
            row = box.row(align=True)
            icon = "RADIOBUT_ON" if obj is td.active_projector \
                else "RADIOBUT_OFF"
            operator = row.operator(
                "td.set_active", text=obj.name, icon=icon, emboss=False)
            operator.name = obj.name
            row.label(text="", icon="CHECKMARK" if obj.td_proj.output_image
                      and obj.td_proj.output_image.has_data else "BLANK1")


class TD_PT_settings(bpy.types.Panel):
    bl_label = "Active Projection"
    bl_idname = "TD_PT_settings"
    bl_parent_id = "TD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Textur Decomposer"

    @classmethod
    def poll(cls, context):
        return _active_projector(context.scene) is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        projector = _active_projector(scene)
        props = projector.td_proj

        layout.prop(props, "source_object")
        layout.prop(props, "resolution")
        layout.prop(props, "aspect_mode")
        if props.aspect_mode == "ORIGINAL":
            row = layout.row(align=True)
            row.prop(props, "pad_placement", text="")
            row.prop(props, "pad_color", text="")
        layout.prop(props, "origin_mode")
        if props.origin_mode == "EMPTY":
            layout.prop(props, "origin_object")
        layout.prop(props, "auto_commit")

        layout.separator()
        col = layout.column(align=True)
        col.operator("td.modal_transform", icon="TRANSFORM_MOVE")
        row = layout.row(align=True)
        row.operator("td.extract", icon="FILE_REFRESH")
        row.operator("td.commit", icon="IMAGE_REFERENCE")
        layout.operator("td.delete_projection", icon="TRASH")

        if props.output_image is not None:
            layout.label(text=f"Output: {props.output_image.name}",
                         icon="IMAGE_DATA")
            layout.template_ID(props, "output_image", text="", open="image")

        layout.separator()
        layout.label(
            text="Preview it in the Texture Paint tab", icon="TPAINT_HLT")


class TD_PT_options(bpy.types.Panel):
    bl_label = "Options"
    bl_idname = "TD_PT_options"
    bl_parent_id = "TD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Textur Decomposer"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.td, "default_resolution")
        layout.separator()
        layout.operator("td.clear_cache", icon="FILE_REFRESH")


classes = (TD_PT_main, TD_PT_settings, TD_PT_options)