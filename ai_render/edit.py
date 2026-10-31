"""Masked, non-destructive edits and the drift verifier."""
import numpy as np
from scipy import ndimage

from .scene import SEMANTIC


def edit_region(index_before, index_after, key, grow_px=6):
    """Pixels an edit to `key` may touch: the object in either version,
    grown a little so contact shadows and soft edges can update."""
    k = SEMANTIC[key]
    m = (index_before == k) | (index_after == k)
    return ndimage.binary_dilation(m, iterations=grow_px)


def composite(before, after, region, feather_px=2):
    """Take `after` inside the region, `before` everywhere else.
    The feather only blends inside the region, so outside stays byte-identical."""
    inner = ndimage.binary_erosion(region, iterations=feather_px)
    dist = ndimage.distance_transform_edt(region)
    alpha = np.clip(dist / max(feather_px, 1), 0, 1)
    alpha[inner] = 1.0
    alpha[~region] = 0.0
    out = before.astype(np.float32) * (1 - alpha[..., None]) + after.astype(np.float32) * alpha[..., None]
    out = np.rint(out).astype(np.uint8)
    out[~region] = before[~region]
    return out


def drift(before, after, region, threshold=6):
    """Share of pixels outside the edit region that changed (0..1)."""
    d = np.abs(before.astype(np.int16) - after.astype(np.int16)).sum(-1) > threshold
    outside = ~region
    return float(d[outside].mean()), d


def diff_image(before, after, region, threshold=6):
    d = np.abs(before.astype(np.int16) - after.astype(np.int16)).sum(-1) > threshold
    grey = (before.mean(-1) * 0.45 + 70).astype(np.uint8)
    out = np.stack([grey] * 3, -1)
    out[d & region] = (60, 170, 140)
    out[d & ~region] = (255, 60, 40)
    return out
