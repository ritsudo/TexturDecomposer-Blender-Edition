"""Material helpers for Textur Decomposer."""

import bpy


def _apply_alpha_mode(material):
    """Make alpha work across EEVEE legacy, EEVEE Next and Cycles."""
    for attr, value in (
        ("blend_method", "BLEND"),
        ("shadow_method", "HASHED"),
        ("surface_render_method", "DITHERED"),
    ):
        if hasattr(material, attr):
            try:
                setattr(material, attr, value)
            except Exception:
                pass
    material.use_backface_culling = False


def create_image_material(name, image):
    """Create (or reuse) an emissive image material with UV remapping.

    A Mapping node sits between the UV coordinates and the image texture so a
    sub-rectangle of the stored (padded) image can be stretched over the plane
    (see :func:`set_material_image_region`).

    Emission is used so the photo / extracted texture is clearly visible
    regardless of scene lighting, mirroring the original tool where the
    background image was drawn unlit.
    """
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (220, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-220, 0)
    mapping.vector_type = "POINT"
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (0, 0)
    tex.image = image
    tex.interpolation = "Linear"
    tex.extension = "CLIP"
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-440, 0)

    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    if "Alpha" in shader.inputs and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], shader.inputs["Alpha"])
    if "Emission Color" in shader.inputs:
        links.new(tex.outputs["Color"], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = 1.0
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    _apply_alpha_mode(material)
    set_material_image_region(material)
    return material


def set_material_image(material, image):
    """Point an existing image material at a different image datablock."""
    if not material or not material.use_nodes:
        return
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE":
            node.image = image


def set_material_image_region(material, location=(0.0, 0.0),
                              scale=(1.0, 1.0)):
    """Select the sub-region of the texture shown on the plane.

    ``location`` / ``scale`` are in UV space: the plane's 0..1 UVs are mapped
    to ``location + uv * scale``. Defaults show the whole image (no margins).
    """
    if not material or not material.use_nodes:
        return
    for node in material.node_tree.nodes:
        if node.type == "MAPPING":
            node.inputs["Location"].default_value = (
                location[0], location[1], 0.0)
            node.inputs["Scale"].default_value = (scale[0], scale[1], 1.0)