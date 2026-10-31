"""High-level helpers: build a scene for a given look, render it."""
import bpy

from . import scene as S, lighting as L, render as R

DEFAULT = {"moment": "Golden hour", "pendant": True, "cove": True, "kelvin": 3000,
           "sofa": "Linen grey", "rug": "Ivory", "floor": "Oak", "wall": "Warm white", "table": "Walnut"}


def build(state, model_path=None, quality=None):
    """Reset Blender and build the scene for `state` (a DEFAULT-shaped dict)."""
    q = {"width": 1280, "height": 800, "samples": 96, **(quality or {})}
    S.reset()
    info = S.import_model(model_path) if model_path else S.build_sample_room(state)
    L.setup_world(state["moment"])
    if model_path:
        L.add_room_light(S.scene_bounds(), state["pendant"] or state["cove"], state["kelvin"])
    else:
        L.add_interior_lights(state["pendant"], state["cove"], kelvin=state["kelvin"], moment=state["moment"])
    if info.get("camera"):
        S.add_camera(**info["camera"])
    apply_finishes(state, model_path)
    R.configure(q["width"], q["height"], q["samples"])


def apply_finishes(state, model_path=None):
    """For imported models, apply any finish that differs from the model's own."""
    if not model_path:
        return
    for key in ("sofa", "rug", "floor", "wall", "table"):
        if state.get(key) != DEFAULT[key]:
            S.set_finish(key, state[key])
