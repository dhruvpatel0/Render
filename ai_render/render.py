"""Path-traced render + exact passes (depth, normals, object masks)."""
import os
import numpy as np
import OpenEXR
import bpy
from PIL import Image

from .scene import SEMANTIC

ID_COLORS = {1: (39, 174, 96), 2: (47, 128, 237), 3: (86, 204, 242), 4: (107, 91, 210),
             5: (255, 230, 128), 6: (242, 153, 74), 7: (235, 87, 87), 8: (255, 79, 163),
             9: (0, 179, 164), 10: (187, 107, 217), 11: (155, 225, 93), 12: (255, 255, 255),
             13: (60, 80, 50)}


def configure(width=1280, height=800, samples=96, threads=0):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.seed = 0
    sc.cycles.use_animated_seed = False
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 4
    sc.cycles.glossy_bounces = 4
    sc.cycles.transmission_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 1.0
    sc.render.threads_mode = "FIXED" if threads else "AUTO"
    if threads:
        sc.render.threads = threads
    sc.render.resolution_x = width
    sc.render.resolution_y = height
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    vl = sc.view_layers[0]
    vl.use_pass_z = True
    vl.use_pass_normal = True
    vl.use_pass_object_index = True
    vl.use_pass_material_index = True
    sc.render.image_settings.media_type = "MULTI_LAYER_IMAGE"
    sc.render.image_settings.file_format = "OPEN_EXR_MULTILAYER"
    sc.render.image_settings.color_depth = "32"


def _read_exr(path):
    f = OpenEXR.File(path, separate_channels=True)
    ch = {}
    for part in f.parts:
        for name, c in part.channels.items():
            ch[name] = np.asarray(c.pixels, dtype=np.float32)
    return ch


def _find(ch, pass_name, comps):
    out = []
    for c in comps:
        key = next(k for k in ch if k.endswith(f"{pass_name}.{c}"))
        out.append(ch[key])
    return np.stack(out, -1) if len(out) > 1 else out[0]


def tonemap(lin, exposure):
    """Exposure + ACES filmic curve + sRGB encode. Deterministic, so a fixed
    exposure gives byte-identical pixels wherever the linear values match."""
    x = lin * exposure
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
    s = np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)
    return (np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)


def auto_exposure(lin, idx, key=0.20):
    lum = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    inside = (idx != SEMANTIC["window"]) & (idx != SEMANTIC["outside"]) & (idx != SEMANTIC["lights"])
    vals = lum[inside & (lum > 1e-6)]
    logavg = float(np.exp(np.mean(np.log(vals + 1e-6))))
    return key / logavg


def auto_white_balance(lin, idx, strength=0.55):
    """Pull the white ceiling part-way to neutral, like a photographer's grey card.
    Partial, so golden hour still reads warm."""
    m = idx == SEMANTIC["ceiling"]
    if m.sum() < 100:
        return np.ones(3, np.float32)
    mean = lin[m].mean(0) + 1e-6
    lum = float(mean @ np.array([0.2126, 0.7152, 0.0722]))
    return np.power(lum / mean, strength).astype(np.float32)


def render(out_dir, name="beauty", exposure=None, wb=None, passes=True, key=0.20, wb_strength=0.55):
    """Render the current scene. Returns dict with arrays and the exposure used."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    exr = os.path.join(out_dir, f"{name}.exr")
    sc.render.filepath = exr
    bpy.ops.render.render(write_still=True)
    ch = _read_exr(exr)
    rgb = _find(ch, "Combined", "RGB")
    idx = np.rint(_find(ch, "Object Index", "X")).astype(np.int32)
    if wb is None:
        wb = auto_white_balance(rgb, idx, wb_strength)
    rgb = rgb * wb
    if exposure is None:
        exposure = auto_exposure(rgb, idx, key)
    img = tonemap(rgb, exposure)
    Image.fromarray(img).save(os.path.join(out_dir, f"{name}.png"))
    res = {"image": img, "index": idx, "exposure": exposure, "wb": wb, "linear": rgb,
           "matindex": np.rint(_find(ch, "Material Index", "X")).astype(np.int32)}
    z = _find(ch, "Depth", "Z")
    zz = np.clip(z, 0, 12)
    near, far = np.percentile(zz, 1), np.percentile(zz, 99)
    dep = 1 - np.clip((zz - near) / (far - near + 1e-6), 0, 1)
    res["depth"] = dep
    if passes:
        Image.fromarray((dep * 255).astype(np.uint8)).save(os.path.join(out_dir, f"{name}_depth.png"))
        n = _find(ch, "Normal", "XYZ")
        Image.fromarray(((n * 0.5 + 0.5).clip(0, 1) * 255).astype(np.uint8)).save(os.path.join(out_dir, f"{name}_normal.png"))
        ids = np.zeros(idx.shape + (3,), np.uint8)
        for k, col in ID_COLORS.items():
            ids[idx == k] = col
        Image.fromarray(ids).save(os.path.join(out_dir, f"{name}_ids.png"))
        mdir = os.path.join(out_dir, "masks")
        os.makedirs(mdir, exist_ok=True)
        for key, k in SEMANTIC.items():
            m = idx == k
            if m.any():
                Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(mdir, f"{name}_{key}.png"))
    os.remove(exr)
    return res
