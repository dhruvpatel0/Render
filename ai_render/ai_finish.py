"""AI finish: geometry-locked photoreal refinement through fal.

The path-traced render stays the source of truth. The model sees it together
with exact depth and edge maps from the 3D scene (a ControlNet union), so it may
add texture, softness and realism but not move geometry. Afterwards:

1. only pixels inside the allowed mask are kept (everything else is the render),
2. a verifier compares edges before and after and rejects drifted results.

The FAL_KEY stays on the server. This module never logs or returns it.
"""
import io
import json
import os
import time
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage

from . import edit as E

ENDPOINT = os.environ.get("AI_FINISH_ENDPOINT", "fal-ai/flux-general/inpainting")
# ControlNet union weights. Verify on the first real run that fal accepts this path.
UNION_PATH = os.environ.get("AI_FINISH_UNION", "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro")

STYLE = ("professional architectural interior photograph, natural materials with real texture, "
         "soft realistic light and shadow, accurate reflections, full-frame camera, 24mm lens, "
         "photorealistic, high detail")


def key_state():
    """'present' or 'absent'. Never the value."""
    return "present" if os.environ.get("FAL_KEY") else "absent"


def edge_map(depth, index):
    """Exact edges from the scene: depth discontinuities plus object boundaries."""
    d = depth.astype(np.float32)
    gd = np.hypot(ndimage.sobel(d, 0), ndimage.sobel(d, 1))
    gd = gd > max(0.02, np.percentile(gd, 92))
    ob = (ndimage.maximum_filter(index, 3) != ndimage.minimum_filter(index, 3))
    return ((gd | ob) * 255).astype(np.uint8)


def _canny_like(img):
    g = np.asarray(Image.fromarray(img).convert("L"), np.float32)
    m = np.hypot(ndimage.sobel(g, 0), ndimage.sobel(g, 1))
    return m > np.percentile(m, 90)


def edge_agreement(before, after, region):
    """Share of the base render's strong edges inside `region` that are still
    present (within 2 px) after the AI step. 1.0 = nothing moved."""
    a, b = _canny_like(before) & region, _canny_like(after)
    if a.sum() < 50:
        return 1.0
    near = ndimage.binary_dilation(b, iterations=2)
    return float((a & near).sum() / a.sum())


def build_arguments(image, depth, edges, mask, prompt, seed, strength, encode):
    """Arguments for fal-ai/flux-general/inpainting (schema read 2026-10-31)."""
    h, w = image.shape[:2]
    scale = 1024 / max(w, h)
    size = {"width": int(round(w * scale / 16) * 16), "height": int(round(h * scale / 16) * 16)}
    dep = Image.fromarray((np.clip(depth, 0, 1) * 255).astype(np.uint8)).convert("RGB")
    return {
        "prompt": f"{prompt}, {STYLE}" if prompt else STYLE,
        "image_url": encode(Image.fromarray(image), "png"),
        "mask_url": encode(Image.fromarray((mask * 255).astype(np.uint8)).convert("RGB"), "png"),
        "strength": strength,
        "seed": seed,
        "image_size": size,
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "output_format": "png",
        "controlnet_unions": [{
            "path": UNION_PATH,
            "controls": [
                {"control_image_url": encode(dep, "png"), "control_mode": "depth", "conditioning_scale": 0.7},
                {"control_image_url": encode(Image.fromarray(edges).convert("RGB"), "png"),
                 "control_mode": "canny", "conditioning_scale": 0.6},
            ],
        }],
    }


def _download(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return np.array(Image.open(io.BytesIO(r.read())).convert("RGB"))


class FalFinisher:
    """Calls fal. `client` is injectable so tests never touch the network."""

    def __init__(self, client=None, download=_download, log_dir=None):
        if client is None:
            import fal_client as client
        self.client, self.download, self.log_dir = client, download, log_dir

    def __call__(self, image, depth, index, mask, prompt="", seed=7, strength=0.35, min_agreement=0.85):
        edges = edge_map(depth, index)
        args = build_arguments(image, depth, edges, mask, prompt, seed, strength, self.client.encode_image)
        handle = self.client.submit(ENDPOINT, arguments=args)
        request_id = getattr(handle, "request_id", None)
        if self.log_dir:  # keep queue request ids, as fal recommends
            os.makedirs(self.log_dir, exist_ok=True)
            with open(os.path.join(self.log_dir, "fal_requests.jsonl"), "a") as f:
                f.write(json.dumps({"t": time.time(), "endpoint": ENDPOINT, "request_id": request_id}) + "\n")
        out = handle.get()
        gen = self.download(out["images"][0]["url"])
        if gen.shape[:2] != image.shape[:2]:
            gen = np.array(Image.fromarray(gen).resize((image.shape[1], image.shape[0]), Image.LANCZOS))
        result = E.composite(image, gen, mask.astype(bool))
        agree = edge_agreement(image, result, mask.astype(bool))
        accepted = agree >= min_agreement
        return {"image": result if accepted else image, "accepted": accepted, "edge_agreement": agree,
                "request_id": request_id, "seed": out.get("seed", seed)}


def finish_mask(index):
    """Whole-frame finish, minus things the AI should not repaint: windows/sky and light fixtures."""
    from .scene import SEMANTIC
    keep_out = np.isin(index, [SEMANTIC["window"], SEMANTIC["outside"], SEMANTIC["lights"]])
    return ~ndimage.binary_dilation(keep_out, iterations=2)


def cached(finisher, cache_dir):
    """Wrap a finisher so the same input never costs a second request."""
    import hashlib
    os.makedirs(cache_dir, exist_ok=True)

    def run(image, depth, index, mask, **kw):
        h = hashlib.sha1(image.tobytes() + np.packbits(mask).tobytes() + json.dumps(
            [kw, ENDPOINT, UNION_PATH], sort_keys=True).encode()).hexdigest()[:20]
        png, meta = os.path.join(cache_dir, h + ".png"), os.path.join(cache_dir, h + ".json")
        if os.path.exists(meta):
            m = json.load(open(meta))
            return {**m, "image": np.array(Image.open(png).convert("RGB"))}
        r = finisher(image, depth, index, mask, **kw)
        Image.fromarray(r["image"]).save(png)
        json.dump({k: v for k, v in r.items() if k != "image"}, open(meta, "w"))
        return r
    return run
