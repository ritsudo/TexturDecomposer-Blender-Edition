"""Datablocks / properties for the Textur Decomposer addon."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)


class TDSourceProps(bpy.types.PropertyGroup):
    """Stored on an object that acts as a source photo backdrop."""

    is_source: BoolProperty(
        name="Is Source Image",
        description="This object is a Textur Decomposer source image",
        default=False,
    )
    image: PointerProperty(
        name="Image",
        description="Source image datablock",
        type=bpy.types.Image,
    )
    width: FloatProperty(
        name="World Width",
        description="World-space width of the source plane",
        default=1.0,
        min=1e-4,
    )
    height: FloatProperty(
        name="World Height",
        description="World-space height of the source plane",
        default=1.0,
        min=1e-4,
    )


def _schedule_texture_update(self, context):
    """Re-extract the owning projection plane when a setting changes."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    try:
        from . import live
    except Exception:  # noqa: BLE001 - during registration/teardown
        return
    for obj in scene.objects:
        if obj.td_proj != self:
            continue
        if not obj.td_proj.is_projector:
            return
        live.fast_update(obj, force=True)
        live.request_final(obj)
        return


class TDProjectionProps(bpy.types.PropertyGroup):
    """Stored on every projection-plane object."""

    is_projector: BoolProperty(
        name="Is Projection Plane",
        description="This object extracts a rectified texture",
        default=False,
    )
    source_object: PointerProperty(
        name="Source",
        description="Source image plane this projector reads from",
        type=bpy.types.Object,
        update=_schedule_texture_update,
    )
    output_image: PointerProperty(
        name="Output Image",
        description="Image datablock holding the rectified texture",
        type=bpy.types.Image,
    )
    resolution: IntProperty(
        name="Resolution",
        description="Resolution (longest side) of the square output texture",
        default=1024,
        min=16,
        max=8192,
        update=_schedule_texture_update,
    )
    aspect_mode: EnumProperty(
        name="Output Shape",
        items=(
            ("SQUARE", "Square",
             "Stretch the sampled region to fill the whole square texture"),
            ("ORIGINAL", "Original Ratio",
             "Keep the projection plane's width/height ratio and fit it into "
             "the square by its longest side, padding the rest"),
        ),
        default="SQUARE",
        update=_schedule_texture_update,
    )
    pad_color: EnumProperty(
        name="Padding",
        description="Fill colour for the unused part of the square",
        items=(
            ("TRANSPARENT", "Transparent", "Leave the padding transparent"),
            ("WHITE", "White", "Fill the padding with white"),
            ("BLACK", "Black", "Fill the padding with black"),
        ),
        default="TRANSPARENT",
        update=_schedule_texture_update,
    )
    pad_placement: EnumProperty(
        name="Placement",
        description=(
            "Where the rectangle sits inside the square, along the padded "
            "axis (LEFT = content at the left/bottom, RIGHT = right/top)"),
        items=(
            ("LEFT", "Left", "Add the margin on the right side"),
            ("CENTER", "Center", "Add margins on both sides"),
            ("RIGHT", "Right", "Add the margin on the left side"),
        ),
        default="CENTER",
        update=_schedule_texture_update,
    )
    origin_mode: EnumProperty(
        name="Projection Origin",
        items=(
            ("CAMERA", "Scene Camera",
             "Cast rays from the scene camera through the plane corners"),
            ("EMPTY", "Object",
             "Cast rays from a chosen object (empty) through the plane corners"),
            ("PARALLEL", "Parallel",
             "Project corners straight along the source plane normal (affine)"),
        ),
        default="CAMERA",
        update=_schedule_texture_update,
    )
    origin_object: PointerProperty(
        name="Origin Object",
        description="Projection centre used in Object mode",
        type=bpy.types.Object,
        update=_schedule_texture_update,
    )
    auto_commit: BoolProperty(
        name="Auto Finalize",
        description=(
            "Run the full-quality extraction (and pack the image) once the "
            "plane stops moving"),
        default=True,
    )


class TDSceneProps(bpy.types.PropertyGroup):
    active_projector: PointerProperty(
        name="Active Projection Plane",
        description="Projection plane currently being edited",
        type=bpy.types.Object,
    )
    default_resolution: IntProperty(
        name="Default Resolution",
        description="Resolution used for newly created projection planes",
        default=1024,
        min=16,
        max=8192,
    )


classes = (TDSourceProps, TDProjectionProps, TDSceneProps)


def register_props():
    bpy.types.Object.td_source = PointerProperty(type=TDSourceProps)
    bpy.types.Object.td_proj = PointerProperty(type=TDProjectionProps)
    bpy.types.Scene.td = PointerProperty(type=TDSceneProps)


def unregister_props():
    del bpy.types.Object.td_source
    del bpy.types.Object.td_proj
    del bpy.types.Scene.td