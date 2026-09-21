"""Pure NumPy math for Textur Decomposer.

This module deliberately contains **no Blender imports** so the core
perspective-rectification routines can be unit tested with plain Python.

The approach follows the same idea as the original TexturDecomposer-c#
tool: four 2D points (a perspective trapezoid) are mapped onto the unit
square, and the source image is resampled through that homography.

References
----------
* Homography / DLT: Hartley & Zisserman, "Multiple View Geometry",
  and the widely used `findHomography` implementations.
* Bilinear sampling: standard image-warping practice.
"""

import numpy as np

# Unit-square target corners in the same order used by the addon:
# 0 = bottom-left, 1 = bottom-right, 2 = top-right, 3 = top-left.
UNIT_SQUARE = np.array(
    [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float64
)


def content_size(resolution, aspect):
    """Pixel size of a rectangle of the given ``aspect`` fitted in a square.

    The longest side fills ``resolution``; the shorter side is scaled
    proportionally.
    """
    if aspect >= 1.0:
        return resolution, max(1, int(round(resolution / aspect)))
    return max(1, int(round(resolution * aspect))), resolution


def content_offset(resolution, content_x, content_y, placement="CENTER"):
    """Top-left pixel offset of the content inside the square canvas.

    ``placement`` is ``LEFT`` / ``CENTER`` / ``RIGHT`` and is applied along the
    padded axis (horizontally when the content is narrower than the square,
    otherwise vertically: LEFT = bottom, RIGHT = top).
    """
    dx = resolution - content_x
    dy = resolution - content_y
    x0 = y0 = 0
    if dx > 0:
        if placement == "LEFT":
            x0 = 0
        elif placement == "RIGHT":
            x0 = dx
        else:
            x0 = dx // 2
    if dy > 0:
        if placement == "LEFT":
            y0 = 0
        elif placement == "RIGHT":
            y0 = dy
        else:
            y0 = dy // 2
    return x0, y0


def paste_padded(content, resolution, pad_rgba, placement="CENTER"):
    """Place ``content`` (H, W, 4) on a square canvas filled with ``pad_rgba``."""
    height, width = content.shape[0], content.shape[1]
    if height == resolution and width == resolution:
        return content
    out = np.empty((resolution, resolution, 4), dtype=np.float32)
    out[:] = np.asarray(pad_rgba, dtype=np.float32)
    x0, y0 = content_offset(resolution, width, height, placement)
    out[y0:y0 + height, x0:x0 + width] = content
    return out


def find_homography(src_pts, dst_pts):
    """Return the 3x3 homography mapping four ``src_pts`` onto four ``dst_pts``.

    Uses the direct linear transform (DLT). Both inputs are 4x2 sequences of
    (x, y) coordinates.
    """
    src = np.asarray(src_pts, dtype=np.float64).reshape(4, 2)
    dst = np.asarray(dst_pts, dtype=np.float64).reshape(4, 2)

    a = np.zeros((8, 8), dtype=np.float64)
    b = np.zeros(8, dtype=np.float64)
    for i in range(4):
        x, y = src[i]
        u, v = dst[i]
        a[2 * i] = (x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y)
        a[2 * i + 1] = (0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y)
        b[2 * i] = u
        b[2 * i + 1] = v

    h = np.linalg.solve(a, b)
    return np.array(
        [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]],
        dtype=np.float64,
    )


def transform_points(h, pts):
    """Apply homography ``h`` to an Nx2 array of points.

    Returns ``(mapped_xy, w)`` where ``w`` is the (homogeneous) denominator.
    """
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    homo = np.concatenate([pts, np.ones((pts.shape[0], 1))], axis=1)
    out = homo @ h.T
    w = out[:, 2:3]
    safe = np.where(np.abs(w) < 1e-12, 1e-12, w)
    return out[:, :2] / safe, out[:, 2]


def pixel_grid(res_x, res_y):
    """Return the unit-square coordinates of every output texel centre.

    Result is an ``(res_y, res_x, 2)`` array where row 0 is ``v = 0`` (the
    bottom of the texture in Blender's bottom-up image convention).
    """
    us = (np.arange(res_x, dtype=np.float64) + 0.5) / float(res_x)
    vs = (np.arange(res_y, dtype=np.float64) + 0.5) / float(res_y)
    grid = np.empty((res_y, res_x, 2), dtype=np.float64)
    grid[..., 0] = us[None, :]
    grid[..., 1] = vs[:, None]
    return grid


def resample_homography(src_img, h, res_x, res_y, nearest=False):
    """Resample ``src_img`` (H, W, 4), bottom-up RGBA, through homography ``h``.

    ``h`` must map unit-square coordinates to source-image UV coordinates
    (0..1, v measured from the bottom). Texels whose source coordinate falls
    outside the image are written as fully transparent.

    Set ``nearest=True`` for a fast, low-quality pass (used while an
    interactive transform is in progress).
    """
    src_img = np.asarray(src_img, dtype=np.float32)
    height, width = src_img.shape[0], src_img.shape[1]

    grid = pixel_grid(res_x, res_y)
    flat = grid.reshape(-1, 2)
    src_uv, w = transform_points(h, flat)
    src_uv = src_uv.reshape(res_y, res_x, 2)
    w = w.reshape(res_y, res_x)

    valid = (np.abs(w) > 1e-12) & (w > 0.0)
    valid &= (src_uv[..., 0] >= 0.0) & (src_uv[..., 0] <= 1.0)
    valid &= (src_uv[..., 1] >= 0.0) & (src_uv[..., 1] <= 1.0)

    px = np.clip(src_uv[..., 0] * (width - 1), 0.0, width - 1)
    py = np.clip(src_uv[..., 1] * (height - 1), 0.0, height - 1)

    if nearest:
        xi = np.rint(px).astype(np.int64)
        yi = np.rint(py).astype(np.int64)
        np.clip(xi, 0, width - 1, out=xi)
        np.clip(yi, 0, height - 1, out=yi)
        out = src_img[yi, xi].copy()
        out[~valid] = 0.0
        return out.astype(np.float32)

    x0 = np.floor(px).astype(np.int64)
    y0 = np.floor(py).astype(np.int64)
    fx = (px - x0)[..., None]
    fy = (py - y0)[..., None]
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    x0 = np.clip(x0, 0, width - 1)
    y0 = np.clip(y0, 0, height - 1)

    c00 = src_img[y0, x0]
    c10 = src_img[y0, x1]
    c01 = src_img[y1, x0]
    c11 = src_img[y1, x1]

    top = c00 * (1.0 - fx) + c10 * fx
    bottom = c01 * (1.0 - fx) + c11 * fx
    out = top * (1.0 - fy) + bottom * fy

    out[~valid] = 0.0
    out = np.clip(out, 0.0, 1.0)
    return out.astype(np.float32)