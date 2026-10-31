import numpy as np

from ai_render import edit as E
from ai_render.scene import SEMANTIC


def _scene():
    rng = np.random.default_rng(0)
    before = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
    after = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)  # every pixel differs
    idx = np.zeros((60, 80), np.int32)
    idx[20:40, 30:50] = SEMANTIC["sofa"]
    return before, after, idx


def test_outside_region_is_byte_identical():
    before, after, idx = _scene()
    region = E.edit_region(idx, idx, "sofa", grow_px=3)
    out = E.composite(before, after, region)
    assert (out[~region] == before[~region]).all()
    share, _ = E.drift(before, out, region)
    assert share == 0.0


def test_inside_region_takes_new_render():
    before, after, idx = _scene()
    region = E.edit_region(idx, idx, "sofa", grow_px=3)
    out = E.composite(before, after, region, feather_px=2)
    core = idx == SEMANTIC["sofa"]
    assert (out[core] == after[core]).all()


def test_region_covers_object_in_both_versions():
    _, _, idx = _scene()
    moved = np.roll(idx, 5, axis=1)
    region = E.edit_region(idx, moved, "sofa", grow_px=0)
    assert region[idx == SEMANTIC["sofa"]].all() and region[moved == SEMANTIC["sofa"]].all()
