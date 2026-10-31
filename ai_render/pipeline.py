"""High-level helpers: build a scene for a given look, render it."""
import bpy

from . import scene as S, lighting as L, render as R

DEFAULT = {"moment": "Golden hour", "pendant": True, "cove": True, "kelvin": 3000,
           "sofa": "Linen grey", "rug": "Ivory", "floor": "Oak", "wall": "Warm white", "table": "Walnut"}


def build(state, model_path=None, quality=None):
    q = {"width": 1280, "height": 800, "samples": 96, **(quality or {})}
    S.reset()
    info = S.import_model(model_path) if model_path else S.build_sample_room(state)
    L.setup_world(state["moment"])
    L.add_interior_lights(state["pendant"], state["cove"], kelvin=state["kelvin"], moment=state["moment"])
    if info.get("camera"):
        S.add_camera(**info["camera"])
    R.configure(q["width"], q["height"], q["samples"])
