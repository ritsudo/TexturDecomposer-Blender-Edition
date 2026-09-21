"""Operators for the Textur Decomposer addon."""

import os

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from bpy_extras.view3d_utils import region_2d_to_location_3d
from mathutils import Matrix

from . import extraction, geometry, live


def _is_projector(obj):
    return obj is not None and obj.td_proj.is_projector


def _active_projector(context):
    scene = context.scene
    active = scene.td.active_projector
    if _is_projector(active):
        return active
    if _is_projector(context.active_object):
        return context.active_object
    for obj in scene.objects:
        if _is_projector(obj):
            return obj
    return None


class TD_OT_import_image(bpy.types.Operator, ImportHelper):
    bl_idname = "td.import_image"
    bl_label = "Import Source Image"
    bl_description = "Load a photo and place it into the scene as a source plane"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_image = True
    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.exr;*.webp;*.hdr",
        options={"HIDDEN"},
    )
    height: FloatProperty(
        name="World Height",
        description="Height of the imported plane in Blender units",
        default=1.0,
        min=1e-4,
    )
    create_camera: BoolProperty(
        name="Create/Fit Camera",
        description="Create or reposition the scene camera to face the photo",
        default=True,
    )

    def execute(self, context):
        if not self.filepath:
            return {"CANCELLED"}
        try:
            image = bpy.data.images.load(self.filepath, check_existing=True)
        except Exception as error:  # noqa: BLE001
            self.report({"ERROR"}, f"Could not load image: {error}")
            return {"CANCELLED"}

        base = os.path.splitext(os.path.basename(self.filepath))[0]
        try:
            source = geometry.create_source_plane(
                image, name=f"TD_Source_{base}", height=self.height)
        except Exception as error:  # noqa: BLE001
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        if self.create_camera:
            geometry.ensure_camera_facing(source)

        context.scene.td.active_projector = None
        for obj in context.selected_objects:
            obj.select_set(False)
        source.select_set(True)
        context.view_layer.objects.active = source
        self.report({"INFO"}, f"Imported source '{source.name}'")
        return {"FINISHED"}


class TD_OT_add_projection(bpy.types.Operator):
    bl_idname = "td.add_projection"
    bl_label = "Add Projection Plane"
    bl_description = (
        "Create a plane that extracts a rectified texture from the active "
        "source photo")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = geometry.find_source_object(context)
        if source is None:
            self.report({"ERROR"}, "Import a source image first")
            return {"CANCELLED"}
        projector = geometry.create_projection_plane(source)
        for obj in context.selected_objects:
            obj.select_set(False)
        projector.select_set(True)
        context.view_layer.objects.active = projector
        extraction.commit_texture(projector)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class TD_OT_frame_source(bpy.types.Operator):
    bl_idname = "td.frame_source"
    bl_label = "Fit Camera to Source"
    bl_description = "Create/reposition the camera so the source photo fills it"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = geometry.find_source_object(context)
        if source is None:
            self.report({"ERROR"}, "No source image found")
            return {"CANCELLED"}
        geometry.ensure_camera_facing(source)
        return {"FINISHED"}


class TD_OT_extract(bpy.types.Operator):
    bl_idname = "td.extract"
    bl_label = "Update Texture"
    bl_description = "Recompute the rectified texture at full quality"
    bl_options = {"REGISTER"}

    def execute(self, context):
        projector = _active_projector(context)
        if projector is None:
            self.report({"ERROR"}, "No projection plane")
            return {"CANCELLED"}
        extraction.clear_cache()
        if not extraction.commit_texture(projector, pack=False):
            self.report({"ERROR"}, "Extraction failed (check source/camera)")
            return {"CANCELLED"}
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class TD_OT_commit(bpy.types.Operator):
    bl_idname = "td.commit"
    bl_label = "Save Texture"
    bl_description = (
        "Extract at full resolution and store the texture in the image pool")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        projector = _active_projector(context)
        if projector is None:
            self.report({"ERROR"}, "No projection plane")
            return {"CANCELLED"}
        extraction.clear_cache()
        if not extraction.commit_texture(projector):
            self.report({"ERROR"}, "Extraction failed (check source/camera)")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Saved '{projector.td_proj.output_image.name}' to the image pool")
        return {"FINISHED"}


class TD_OT_delete_projection(bpy.types.Operator):
    bl_idname = "td.delete_projection"
    bl_label = "Delete Projection Plane"
    bl_description = "Remove the active projection plane"
    bl_options = {"REGISTER", "UNDO"}

    remove_images: BoolProperty(
        name="Remove Images", default=False,
        description="Also delete the generated output image datablock")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        projector = _active_projector(context)
        if projector is None:
            return {"CANCELLED"}
        image = projector.td_proj.output_image
        bpy.data.objects.remove(projector, do_unlink=True)
        if self.remove_images and image is not None and image.users == 0:
            bpy.data.images.remove(image)
        context.scene.td.active_projector = None
        return {"FINISHED"}


class TD_OT_set_active(bpy.types.Operator):
    bl_idname = "td.set_active"
    bl_label = "Set Active Projection Plane"
    bl_description = "Make this projection plane the active one"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(default="")

    def execute(self, context):
        obj = bpy.data.objects.get(self.name)
        if not _is_projector(obj):
            return {"CANCELLED"}
        context.scene.td.active_projector = obj
        context.view_layer.objects.active = obj
        extraction.update_output(obj, nearest=False)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class TD_OT_modal_transform(bpy.types.Operator):
    bl_idname = "td.modal_transform"
    bl_label = "Move / Rotate Projection Plane"
    bl_description = (
        "Interactively move, rotate and scale the projection plane with the "
        "mouse while the texture updates live")
    bl_options = {"REGISTER", "UNDO", "GRAB_CURSOR", "BLOCKING"}

    def invoke(self, context, event):
        projector = _active_projector(context)
        if projector is None:
            self.report({"ERROR"}, "No projection plane")
            return {"CANCELLED"}
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"ERROR"}, "Run this from the 3D viewport")
            return {"CANCELLED"}

        context.scene.td.active_projector = projector
        self._object = projector
        self._original = projector.matrix_world.copy()
        self._original_scale = projector.scale.copy()
        self._mode = "TRANSLATE"
        self._region = context.region
        self._rv3d = context.region_data
        # Keep a fixed depth plane for the whole drag so translation is linear.
        self._depth_point = projector.matrix_world.translation.copy()
        self._last_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._last_world = self._mouse_to_world(self._last_mouse)
        self._update_status(context)
        return {"RUNNING_MODAL"}

    def _mouse_to_world(self, mouse):
        return region_2d_to_location_3d(
            self._region, self._rv3d, mouse, self._depth_point)

    def _update_status(self, context):
        hints = {
            "TRANSLATE": "Move: drag mouse",
            "ROTATE": "Rotate: drag mouse (horizontal = yaw, vertical = pitch)",
            "SCALE": "Scale: drag mouse vertically",
        }
        text = (f"Textur Decomposer [{self._mode}] - {hints[self._mode]}  |  "
                "T translate, R rotate, S scale, LMB/Enter apply, Esc cancel")
        context.workspace.status_text_set(text)

    def _apply(self, context):
        live.fast_update(self._object, force=True)
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        obj = self._object
        mouse = (event.mouse_region_x, event.mouse_region_y)

        if event.type == "MOUSEMOVE":
            dx = mouse[0] - self._last_mouse[0]
            dy = mouse[1] - self._last_mouse[1]
            if self._mode == "TRANSLATE":
                world = self._mouse_to_world(mouse)
                obj.location += world - self._last_world
                self._last_world = world
            elif self._mode == "ROTATE":
                center = obj.matrix_world.translation.copy()
                rot = (Matrix.Rotation(dx * 0.01, 4, "Z")
                       @ Matrix.Rotation(dy * 0.01, 4, "X"))
                obj.matrix_world = (
                    Matrix.Translation(center) @ rot
                    @ Matrix.Translation(-center) @ obj.matrix_world)
            elif self._mode == "SCALE":
                factor = max(0.01, 1.0 + dy * 0.005)
                obj.scale *= factor
            self._last_mouse = mouse
            self._apply(context)
            return {"RUNNING_MODAL"}

        if event.type == "T":
            self._mode = "TRANSLATE"
            self._last_world = self._mouse_to_world(mouse)
            self._last_mouse = mouse
            self._update_status(context)
            return {"RUNNING_MODAL"}
        if event.type == "R":
            self._mode = "ROTATE"
            self._last_mouse = mouse
            self._update_status(context)
            return {"RUNNING_MODAL"}
        if event.type == "S":
            self._mode = "SCALE"
            self._last_mouse = mouse
            self._update_status(context)
            return {"RUNNING_MODAL"}

        if event.type in {"LEFTMOUSE", "RET"} and event.value in {
                "PRESS", "RELEASE"}:
            context.workspace.status_text_set(None)
            live.finalize(obj)
            return {"FINISHED"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            obj.matrix_world = self._original
            obj.scale = self._original_scale
            live.finalize(obj)
            context.workspace.status_text_set(None)
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def cancel(self, context):
        context.workspace.status_text_set(None)


class TD_OT_clear_cache(bpy.types.Operator):
    bl_idname = "td.clear_cache"
    bl_label = "Reload Source Pixels"
    bl_description = "Invalidate cached source-image pixels"
    bl_options = {"REGISTER"}

    def execute(self, context):
        extraction.clear_cache()
        return {"FINISHED"}


classes = (
    TD_OT_import_image,
    TD_OT_add_projection,
    TD_OT_frame_source,
    TD_OT_extract,
    TD_OT_commit,
    TD_OT_delete_projection,
    TD_OT_set_active,
    TD_OT_modal_transform,
    TD_OT_clear_cache,
)