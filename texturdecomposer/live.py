"""Live update handlers (no viewport overlay).

While a projection plane is being transformed the output texture is refreshed
with the fast (nearest-neighbour) pass, throttled to a fixed rate. A debounced
timer then runs the final, full-quality pass once the plane stops moving.
"""

import time

import bpy

from . import extraction

_depsgraph_handle = None
_registered = False
_updating = False

_prev_matrices = {}
_pending = {}       # object name -> (object, last-change time)
_last_fast = {}     # object name -> last fast-update time

_TOLERANCE = 1e-5
_FAST_INTERVAL = 0.05   # ~20 fast updates / second
_FINAL_DELAY = 0.3      # seconds of no movement before the final pass
_TICK_INTERVAL = 0.15


def _matrices_equal(a, b):
    return all(abs(x - y) < _TOLERANCE for x, y in zip(a, b))


def _flat_matrix(obj):
    return tuple(value for row in obj.matrix_world for value in row)


def fast_update(proj_obj, force=False):
    """Cheap nearest-neighbour refresh, rate limited."""
    now = time.perf_counter()
    if not force and now - _last_fast.get(proj_obj.name, 0.0) < _FAST_INTERVAL:
        return
    _last_fast[proj_obj.name] = now
    extraction.update_output(proj_obj, nearest=True)


def request_final(proj_obj, delay=_FINAL_DELAY):
    """Mark ``proj_obj`` for a full-quality pass after it stops moving."""
    _pending[proj_obj.name] = (proj_obj, time.perf_counter())
    _ensure_timer()


def finalize(proj_obj):
    """Run the full-quality extraction now."""
    _pending.pop(proj_obj.name, None)
    extraction.commit_texture(proj_obj, pack=proj_obj.td_proj.auto_commit)


def _ensure_timer():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=_TICK_INTERVAL)


def _tick():
    global _updating
    now = time.perf_counter()
    due = [name for name, (_, changed) in _pending.items()
           if now - changed >= _FINAL_DELAY]
    if due:
        _updating = True
        try:
            for name in due:
                entry = _pending.pop(name, None)
                if entry is None:
                    continue
                obj = entry[0]
                try:
                    extraction.commit_texture(
                        obj, pack=obj.td_proj.auto_commit)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            _updating = False
    return _TICK_INTERVAL if _pending else None


def depsgraph_update(scene, depsgraph=None):
    global _updating
    if _updating:
        return
    if getattr(scene, "td", None) is None:
        return

    for obj in scene.objects:
        props = obj.td_proj
        if not props.is_projector or props.source_object is None:
            continue
        flat = _flat_matrix(obj)
        previous = _prev_matrices.get(obj.name)
        if previous is not None and _matrices_equal(previous, flat):
            continue
        _prev_matrices[obj.name] = flat
        try:
            fast_update(obj)
        except Exception:  # noqa: BLE001
            pass
        request_final(obj)


def register_handlers():
    global _depsgraph_handle, _registered
    if _registered:
        return
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update)
    _depsgraph_handle = depsgraph_update
    _registered = True


def unregister_handlers():
    global _depsgraph_handle, _registered
    if not _registered:
        return
    if _depsgraph_handle is not None \
            and _depsgraph_handle in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handle)
    _depsgraph_handle = None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _pending.clear()
    _prev_matrices.clear()
    _last_fast.clear()
    _registered = False