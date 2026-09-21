"""Scene geometry helpers: source image planes, projection planes, cameras."""

import math

import bpy
from mathutils import Matrix, Vector

from . import materials


def _mesh_from_quad(name, width, height):
    """Build a single-quad mesh in the local XY plane centred on the origin.

    Vertex order is fixed and relied upon everywhere else:
    0 = bottom-left, 1 = bottom-right, 2 = top-right, 3 = top-left.
    """
    mesh = bpy.data.meshes.new(name)
    hw, hh = width / 2.0, height / 2.0
    verts = [
        (-hw, -hh, 0.0),
        (hw, -hh, 0.0),
        (hw, hh, 0.0),
        (-hw, hh, 0.0),
    ]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()

    uvlayer = mesh.uv_layers.new(name="UVMap")
    uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for i, uv in enumerate(uvs):
        uvlayer.data[i].uv = uv
    return mesh


def _new_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def unique_name(base):
    name = base
    index = 1
    while name in bpy.data.objects:
        index += 1
        name = f"{base}.{index:03d}"
    return name


def create_source_plane(image, name=None, height=1.0, collection=None):
    """Create a textured plane showing ``image`` and tag it as a source."""
    if image is None:
        raise ValueError("create_source_plane requires an image")

    width_px, height_px = image.size
    if width_px == 0 or height_px == 0:
        raise ValueError("source image has no pixel data")

    aspect = float(width_px) / float(height_px)
    width = height * aspect

    name = name or f"TD_Source_{image.name}"
    obj = _new_object(unique_name(name), _mesh_from_quad(name, width, height),
                      collection)
    material = materials.create_image_material(f"{name}_Material", image)
    obj.data.materials.append(material)

    obj.td_source.is_source = True
    obj.td_source.image = image
    obj.td_source.width = width
    obj.td_source.height = height
    return obj


def create_projection_plane(source_obj, resolution=None, name=None,
                            collection=None):
    """Create a projection (projector) quad reading from ``source_obj``."""
    scene = bpy.context.scene
    resolution = resolution or scene.td.default_resolution

    width = source_obj.td_source.width or 1.0
    height = source_obj.td_source.height or 1.0

    name = name or "TD_Projection"
    mesh = _mesh_from_quad(name, width, height)
    obj = _new_object(unique_name(name), mesh, collection)

    output = bpy.data.images.new(
        unique_image_name(f"{obj.name}_texture"), resolution, resolution,
        alpha=True)
    output.generated_color = (0.0, 0.0, 0.0, 0.0)

    material = materials.create_image_material(f"{name}_Material", output)
    obj.data.materials.append(material)

    props = obj.td_proj
    props.source_object = source_obj
    props.output_image = output
    props.resolution = resolution
    props.is_projector = True

    # Place the plane just in front of the source so it does not z-fight with
    # the photo, and make it the active projector.
    normal = (source_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    normal.normalize()
    offset = max(width, height) * 0.02
    obj.matrix_world = Matrix.Translation(
        source_obj.matrix_world.translation + normal * offset)

    scene.td.active_projector = obj
    return obj


def unique_image_name(base):
    name = base
    index = 1
    while name in bpy.data.images:
        index += 1
        name = f"{base}.{index:03d}"
    return name


def find_source_object(context):
    """Best guess for the source plane to use / display in the UI."""
    scene = context.scene
    active = scene.td.active_projector
    if active is not None and active.td_proj.source_object is not None:
        return active.td_proj.source_object
    for obj in context.selected_objects:
        if obj.td_source.is_source:
            return obj
    for obj in scene.objects:
        if obj.td_source.is_source:
            return obj
    return None


def ensure_camera_facing(source_obj, collection=None):
    """Create/frame a camera looking square-on at the source plane.

    A perspective camera is required for the non-affine (true perspective)
    projection mode, so one is created if the scene has none.
    """
    scene = bpy.context.scene
    cam_obj = scene.camera

    normal = (source_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    normal.normalize()
    center = source_obj.matrix_world.translation.copy()

    height = source_obj.td_source.height or 1.0
    lens = 50.0
    sensor = 36.0
    fov = 2.0 * math.atan(sensor / (2.0 * lens))
    distance = (height * 1.15 / 2.0) / max(math.tan(fov / 2.0), 1e-6)
    distance = max(distance, height)

    if cam_obj is None:
        cam_data = bpy.data.cameras.new("TD_Camera")
        cam_obj = bpy.data.objects.new("TD_Camera", cam_data)
        (collection or scene.collection).objects.link(cam_obj)
        scene.camera = cam_obj

    cam_obj.data.lens = lens
    cam_obj.data.sensor_width = sensor
    cam_obj.data.clip_start = max(distance * 1e-4, 1e-4)
    cam_obj.data.clip_end = distance * 100.0
    cam_obj.location = center + normal * distance
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam_obj