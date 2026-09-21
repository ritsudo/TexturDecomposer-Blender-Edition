"""Extraction: turn a projection plane + source photo into a rectified texture.

Fast path
---------
While a projection plane is being moved the addon re-extracts with nearest
neighbour sampling (``nearest=True``) so the viewport stays responsive. When
the plane stops moving a final, full-quality bilinear pass is run by
``live.py`` (and by the explicit *Save Texture* operator).
"""

import bpy
import numpy as np
from mathutils import Vector

from . import tdmath

_SOURCE_CACHE = {}

# Padding used when the output is fitted into a square (see ``pad_color``).
_PAD_COLORS = {
    "TRANSPARENT": (0.0, 0.0, 0.0, 0.0),
    "WHITE": (1.0, 1.0, 1.0, 1.0),
    "BLACK": (0.0, 0.0, 0.0, 1.0),
}


def clear_cache(image_name=None):
    """Drop cached source pixels (all, or one image)."""
    if image_name is None:
        _SOURCE_CACHE.clear()
    else:
        _SOURCE_CACHE.pop(image_name, None)


def get_source_array(image):
    """Return the source image as an (H, W, 4) float32 array, bottom-up.

    Blender stores ``Image.pixels`` row-major starting at the bottom-left,
    which matches the (u, v) convention used throughout this addon.
    """
    key = image.name
    cached = _SOURCE_CACHE.get(key)
    if cached is not None and cached.shape[0] == image.size[1] \
            and cached.shape[1] == image.size[0]:
        return cached

    width, height = image.size
    if width == 0 or height == 0:
        return None
    buf = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(buf)
    arr = buf.reshape(height, width, 4)
    _SOURCE_CACHE[key] = arr
    return arr


def projection_origin(proj_obj):
    """World-space projection centre, or ``None`` for parallel projection."""
    props = proj_obj.td_proj
    mode = props.origin_mode

    if mode == "PARALLEL":
        return None
    if mode == "EMPTY":
        if props.origin_object is not None:
            return props.origin_object.matrix_world.translation.copy()
        return None

    camera = bpy.context.scene.camera
    if camera is not None:
        return camera.matrix_world.translation.copy()
    return None


def corner_source_uvs(proj_obj, source_obj, origin):
    """Map the projector's four corners onto the source image UV space.

    Returns a list of four ``(u, v)`` pairs (bottom-left, bottom-right,
    top-right, top-left) or ``None`` if the mapping is degenerate.
    """
    mesh = proj_obj.data
    if len(mesh.vertices) != 4:
        return None

    src_props = source_obj.td_source
    if src_props.width <= 0.0 or src_props.height <= 0.0:
        return None

    mw = source_obj.matrix_world
    normal = (mw.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    normal.normalize()
    plane_point = mw.translation.copy()
    mw_inv = mw.inverted()

    uvs = []
    for vertex in mesh.vertices:
        corner = proj_obj.matrix_world @ vertex.co
        if origin is None:
            # Parallel projection straight along the source plane normal.
            denom = normal.dot(normal)
            t = normal.dot(plane_point - corner) / denom
            hit = corner + normal * t
        else:
            direction = corner - origin
            denom = normal.dot(direction)
            if abs(denom) < 1e-9:
                return None
            t = normal.dot(plane_point - origin) / denom
            if t <= 1e-6:
                return None
            hit = origin + direction * t

        local = mw_inv @ hit
        u = local.x / src_props.width + 0.5
        v = local.y / src_props.height + 0.5
        uvs.append((u, v))
    return uvs


def plane_aspect(proj_obj):
    """Width / height of the projection plane in its own local plane."""
    mesh = proj_obj.data
    if len(mesh.vertices) < 2:
        return 1.0
    xs = [vertex.co.x for vertex in mesh.vertices]
    ys = [vertex.co.y for vertex in mesh.vertices]
    width = (max(xs) - min(xs)) * abs(proj_obj.scale.x)
    height = (max(ys) - min(ys)) * abs(proj_obj.scale.y)
    if width <= 0.0 or height <= 0.0:
        return 1.0
    return width / height


def _content_size(resolution, aspect):
    """Pixel size of the texture content inside the square output."""
    return tdmath.content_size(resolution, aspect)


def _paste_padded(content, resolution, pad_rgba, placement="CENTER"):
    return tdmath.paste_padded(content, resolution, pad_rgba, placement)


def extract_array(source_obj, proj_obj, resolution, nearest=False):
    """Return a rectified (res, res, 4) float32 array, or ``None`` on failure."""
    image = source_obj.td_source.image
    if image is None:
        return None
    source = get_source_array(image)
    if source is None:
        return None

    origin = projection_origin(proj_obj)
    quad = corner_source_uvs(proj_obj, source_obj, origin)
    if quad is None:
        return None

    homography = tdmath.find_homography(tdmath.UNIT_SQUARE, np.array(quad))

    props = proj_obj.td_proj
    if props.aspect_mode == "ORIGINAL":
        content_x, content_y = _content_size(resolution, plane_aspect(proj_obj))
        content = tdmath.resample_homography(
            source, homography, content_x, content_y, nearest=nearest)
        pad = _PAD_COLORS.get(props.pad_color, _PAD_COLORS["TRANSPARENT"])
        return _paste_padded(content, resolution, pad, props.pad_placement)

    return tdmath.resample_homography(
        source, homography, resolution, resolution, nearest=nearest)


def material_region(proj_obj, resolution):
    """UV sub-region of the stored texture that should show on the plane.

    In *Original Ratio* mode the stored image is a padded square; the plane
    must display only the content, stretched back to fill the plane (no
    margins). Returns ``(location, scale)`` in UV space.
    """
    props = proj_obj.td_proj
    if props.aspect_mode != "ORIGINAL":
        return (0.0, 0.0), (1.0, 1.0)

    content_x, content_y = _content_size(resolution, plane_aspect(proj_obj))
    x0, y0 = tdmath.content_offset(
        resolution, content_x, content_y, props.pad_placement)
    location = (x0 / resolution, y0 / resolution)
    scale = (content_x / resolution, content_y / resolution)
    return location, scale


def write_array(image, array):
    """Copy an (H, W, 4) float32 array into a Blender image datablock."""
    image.pixels.foreach_set(
        np.ascontiguousarray(array, dtype=np.float32).ravel())
    image.update()


def _ensure_output_image(proj_obj, resolution):
    output = proj_obj.td_proj.output_image
    if output is not None:
        if output.size[0] != resolution or output.size[1] != resolution:
            try:
                output.scale(resolution, resolution)
            except Exception:
                pass
        return output
    name = unique_image_name(f"{proj_obj.name}_texture")
    output = bpy.data.images.new(name, resolution, resolution, alpha=True)
    output.generated_color = (0.0, 0.0, 0.0, 0.0)
    return output


def unique_image_name(base):
    name = base
    index = 1
    while name in bpy.data.images:
        index += 1
        name = f"{base}.{index:04d}"
    return name


def update_output(proj_obj, nearest=False, pack=False):
    """(Re)write the projection plane's output texture.

    ``nearest=True`` is the fast interactive pass; call with ``nearest=False``
    once the plane has stopped moving for the final quality.
    """
    source_obj = proj_obj.td_proj.source_object
    if source_obj is None or not source_obj.td_source.is_source:
        return False

    resolution = proj_obj.td_proj.resolution
    array = extract_array(source_obj, proj_obj, resolution, nearest=nearest)
    if array is None:
        return False

    output = _ensure_output_image(proj_obj, resolution)
    write_array(output, array)
    if pack:
        try:
            output.pack()
        except Exception:
            pass
    proj_obj.td_proj.output_image = output

    location, scale = material_region(proj_obj, resolution)
    from . import materials
    for slot in proj_obj.material_slots:
        materials.set_material_image(slot.material, output)
        materials.set_material_image_region(slot.material, location, scale)
    return True


def commit_texture(proj_obj, pack=True):
    """Full-quality extraction stored in the scene image pool."""
    return update_output(proj_obj, nearest=False, pack=pack)