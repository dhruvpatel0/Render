import numpy as np

from ai_render import ai_finish as A
from ai_render import service as S
from ai_render.scene import SEMANTIC
from tests.test_service import fake_renderer, H, W


class FakeFal:
    """Stands in for fal_client: records calls, returns a canned image."""
    def __init__(self, out):
        self.out, self.calls = out, []

    def encode_image(self, img, fmt="jpeg"):
        return f"data:image/{fmt};base64,xx"

    def submit(self, endpoint, arguments):
        self.calls.append((endpoint, arguments))
        return type("H", (), {"request_id": "req-1", "get": lambda s: {"images": [{"url": "u"}], "seed": 7}})()


def _inputs():
    rng = np.random.default_rng(1)
    img = np.zeros((H, W, 3), np.uint8)
    img[:, W // 2:] = 200  # one strong vertical edge
    depth = np.linspace(0, 1, W)[None, :].repeat(H, 0)
    idx = np.full((H, W), SEMANTIC["side"], np.int32)
    return img, depth, idx, rng


def test_arguments_follow_schema():
    img, depth, idx, _ = _inputs()
    fal = FakeFal(img)
    A.FalFinisher(fal, download=lambda u: img)(img, depth, idx, np.ones((H, W), bool))
    endpoint, args = fal.calls[0]
    assert endpoint == A.ENDPOINT
    assert {"prompt", "image_url", "mask_url", "strength", "seed", "controlnet_unions"} <= set(args)
    modes = [c["control_mode"] for c in args["controlnet_unions"][0]["controls"]]
    assert modes == ["depth", "canny"]
    assert args["image_size"]["width"] % 16 == 0


def test_only_mask_changes_and_accepts_when_edges_hold():
    img, depth, idx, _ = _inputs()
    gen = np.clip(img.astype(int) + 9, 0, 255).astype(np.uint8)  # texture-ish change, same edges
    mask = np.zeros((H, W), bool)
    mask[:, :W // 2 + 5] = True
    r = A.FalFinisher(FakeFal(gen), download=lambda u: gen)(img, depth, idx, mask)
    assert r["accepted"] and r["request_id"] == "req-1"
    assert (r["image"][~mask] == img[~mask]).all()


def test_rejects_when_geometry_moves():
    img, depth, idx, _ = _inputs()
    moved = np.zeros_like(img)
    moved[:, W // 4:] = 200  # the edge jumped
    r = A.FalFinisher(FakeFal(moved), download=lambda u: moved)(img, depth, idx, np.ones((H, W), bool))
    assert not r["accepted"] and (r["image"] == img).all()


def test_cache_avoids_second_request(tmp_path):
    img, depth, idx, _ = _inputs()
    fal = FakeFal(img)
    run = A.cached(A.FalFinisher(fal, download=lambda u: img), str(tmp_path))
    run(img, depth, idx, np.ones((H, W), bool), seed=7)
    run(img, depth, idx, np.ones((H, W), bool), seed=7)
    assert len(fal.calls) == 1


def test_edit_after_ai_keeps_rest_of_ai_image():
    calls = []

    def finisher(image, depth, index, mask, **kw):
        calls.append(mask.mean())
        out = image.copy()
        out[mask] = np.clip(out[mask].astype(int) + 3, 0, 255)
        return {"image": out, "accepted": True, "edge_agreement": 1.0}
    p = S.Project("p", fake_renderer(), finisher=finisher)
    p.add_layer("ai", "AI finish: on", {"ai_finish": True})
    ai_base = p.compose()["image"]
    p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})
    out = p.compose()
    assert out["outside_identical"]
    assert (out["image"][~out["edited"]] == ai_base[~out["edited"]]).all()
    assert calls[-1] < 0.5  # the edit's AI pass only covered its own region
