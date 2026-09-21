"""Textur Decomposer - Blender addon.

Recover rectified (square) textures from tilted surfaces photographed in a
static image.  This is the Blender re-implementation of the original
TexturDecomposer-c# tool.

Load an image into the scene, create projection planes, move/rotate/scale
them while the extracted texture updates live, then save the result into
Blender's image pool for reuse or export.
"""

bl_info = {
    "name": "Textur Decomposer",
    "author": "Textur Decomposer contributors",
    "version": (0, 2, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Textur Decomposer",
    "description": (
        "Extract rectified textures from tilted surfaces in photos and store "
        "them in the image pool"),
    "category": "UV",
}

import importlib

import bpy

from . import extraction, geometry, live, materials, operators, properties, ui

_modules = (properties, materials, geometry, extraction, live, operators, ui)

if "bpy" in locals():
    for _module in _modules:
        importlib.reload(_module)

_classes = properties.classes + operators.classes + ui.classes


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    properties.register_props()
    live.register_handlers()


def unregister():
    live.unregister_handlers()
    properties.unregister_props()
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    register()