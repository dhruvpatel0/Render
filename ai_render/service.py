"""Projects, edit layers and composition. No Blender here: rendering is
injected, so this logic is fast to test.

Layers are applied in order. Global layers (moment, lights) change the whole
picture, so they set up the base render. Finish layers (sofa, rug, ...) are
masked edits on top of it: only the edited object's region comes from the new
render, every other pixel is kept.
"""
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import edit as E
from .scene import SEMANTIC

DEFAULT = {"moment": "Golden hour", "pendant": True, "cove": True, "kelvin": 3000,
           "sofa": "Linen grey", "rug": "Ivory", "floor": "Oak", "wall": "Warm white", "table": "Walnut"}
GLOBAL_KEYS = {"moment", "pendant", "cove", "kelvin"}
FINISH_KEYS = ["sofa", "rug", "floor", "wall", "table"]
NAMES = {"sofa": "Sofa", "rug": "Rug", "floor": "Floor", "wall": "Back wall", "table": "Coffee table",
         "pendant": "Pendant light", "window": "Window", "art": "Artwork", "ceiling": "Ceiling",
         "side": "Wall", "sidetable": "Side table", "lights": "Light fixture", "outside": "Garden"}
SWATCH = {
    "sofa": {"Linen grey": "#b8b2a7", "Terracotta": "#b0603e", "Forest": "#3f5b47", "Ink blue": "#2e3d5a"},
    "rug": {"Ivory": "#e4dccd", "Sage": "#9ea891", "Rust": "#9f573a", "Charcoal": "#4a4949"},
    "floor": {"Oak": "#b78a5c", "Walnut": "#6c4a31", "Travertine": "#d8ccb6"},
    "wall": {"Warm white": "#ece6dc", "Clay": "#c8a387", "Olive": "#8d8c69", "Deep blue": "#36445e"},
    "table": {"Walnut": "#5a3a25", "Travertine": "#d6c8b0", "Black oak": "#2b2724"},
}
MOMENTS = ["Morning", "Midday", "Golden hour", "Dusk", "Night"]
KEY_BY_INDEX = {v: k for k, v in SEMANTIC.items()}


class Locked(Exception):
    pass


@dataclass
class Shot:
    image: np.ndarray
    index: np.ndarray
    exposure: float
    wb: list
    depth: np.ndarray = None


@dataclass
class Layer:
    id: str
    key: str
    label: str
    set: dict
    on: bool = True

    def to_json(self):
        return {"id": self.id, "key": self.key, "label": self.label, "set": self.set, "on": self.on}


def subprocess_renderer(work_dir, model_path=None, quality="preview"):
    """Render each state in a fresh Python process via ai_render.cli."""
    def render(state, exposure=None, wb=None):
        h = hashlib.sha1(json.dumps([state, exposure, wb, model_path, quality], sort_keys=True).encode()).hexdigest()[:16]
        out = os.path.join(work_dir, "renders", h)
        if not os.path.exists(os.path.join(out, "meta.json")):
            cmd = [sys.executable, "-m", "ai_render.cli", "--state", json.dumps(state), "--out", out, "--quality", quality]
            if model_path:
                cmd += ["--model", model_path]
            if exposure is not None:
                cmd += ["--exposure", repr(exposure), "--wb", ",".join(repr(x) for x in wb)]
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if p.returncode:
                raise RuntimeError(p.stderr[-2000:])
        meta = json.load(open(os.path.join(out, "meta.json")))
        dpath = os.path.join(out, "depth.npy")
        return Shot(np.array(Image.open(os.path.join(out, "image.png")).convert("RGB")),
                    np.load(os.path.join(out, "index.npy")).astype(np.int32), meta["exposure"], meta["wb"],
                    np.load(dpath).astype(np.float32) if os.path.exists(dpath) else None)
    render.cached = lambda state, exposure=None, wb=None: os.path.exists(os.path.join(
        work_dir, "renders", hashlib.sha1(json.dumps([state, exposure, wb, model_path, quality], sort_keys=True).encode()).hexdigest()[:16], "meta.json"))
    return render


@dataclass
class Project:
    id: str
    renderer: object
    layers: list = field(default_factory=list)
    locks: set = field(default_factory=set)
    finisher: object = None  # AI finish callable, or None when not configured
    _memo: dict = field(default_factory=dict)

    # ----- editing -----
    def add_layer(self, key, label, values):
        for k in values:
            if k in self.locks:
                raise Locked(f"{NAMES.get(k, k)} is locked")
        last = self.layers[-1] if self.layers else None
        if last and last.key == key and last.on:
            last.label, last.set = label, dict(values)
            return last
        layer = Layer(uuid.uuid4().hex[:8], key, label, dict(values))
        self.layers.append(layer)
        return layer

    def set_layer(self, layer_id, on):
        layer = next(l for l in self.layers if l.id == layer_id)
        if not on or not any(k in self.locks for k in layer.set):
            layer.on = on
        else:
            raise Locked("That layer edits a locked object")

    def set_lock(self, obj, locked):
        (self.locks.add if locked else self.locks.discard)(obj)

    def reset(self):
        self.layers.clear()
        self.locks.clear()

    # ----- composition -----
    def ai_on(self):
        return any(l.on and l.set.get("ai_finish") for l in self.layers)

    def plan(self):
        """(base_state, [(finish_key, cumulative_state), ...]) for enabled layers."""
        base = dict(DEFAULT)
        for l in self.layers:
            if l.on:
                base.update({k: v for k, v in l.set.items() if k in GLOBAL_KEYS})
        steps, cur = [], dict(base)
        for l in self.layers:
            if not l.on:
                continue
            fin = {k: v for k, v in l.set.items() if k in FINISH_KEYS}
            if fin and any(cur[k] != v for k, v in fin.items()):
                cur = {**cur, **fin}
                steps.append((list(fin), dict(cur)))
        return base, steps

    def pending_renders(self):
        """How many renders the next compose() still has to run (None if unknown)."""
        cached = getattr(self.renderer, "cached", None)
        if not cached:
            return None
        base, steps = self.plan()
        if not cached(base):
            return 1 + len(steps)
        b = self.renderer(base)
        return sum(0 if cached(s, b.exposure, b.wb) else 1 for _, s in steps)

    def compose(self):
        """Base render (+ AI finish of the base), then each finish edit as a masked
        layer. With AI on, each edit is AI-finished only inside its own region, so
        the rest of the approved image never changes."""
        from . import ai_finish as A
        base_state, steps = self.plan()
        base = self.renderer(base_state)
        use_ai = self.ai_on() and self.finisher is not None
        ai_report = None
        start = base.image
        if use_ai:
            r = self.finisher(base.image, base.depth, base.index, A.finish_mask(base.index), seed=7)
            start, ai_report = r["image"], {"accepted": r["accepted"], "edge_agreement": r["edge_agreement"]}
        image, index = start.copy(), base.index
        edited = np.zeros(index.shape, bool)
        for keys, state in steps:
            shot = self.renderer(state, base.exposure, base.wb)
            region = np.zeros(index.shape, bool)
            for k in keys:
                region |= E.edit_region(index, shot.index, k)
            layer_img = shot.image
            if use_ai:
                r = self.finisher(shot.image, shot.depth, shot.index, region & A.finish_mask(shot.index), seed=7)
                layer_img = r["image"]
            image = E.composite(image, layer_img, region)
            index = shot.index
            edited |= region
        outside_same = bool((image[~edited] == start[~edited]).all())
        return {"image": image, "index": index, "edited": edited, "outside_identical": outside_same,
                "renders": 1 + len(steps), "ai": ai_report}

    def pick(self, index, fx, fy):
        h, w = index.shape
        v = int(index[min(h - 1, max(0, int(fy * h))), min(w - 1, max(0, int(fx * w)))])
        key = KEY_BY_INDEX.get(v, "side")
        return {"object": key, "name": NAMES.get(key, key), "editable": key in SWATCH,
                "locked": key in self.locks, "finishes": SWATCH.get(key, {}),
                "current": self.current_state().get(key)}

    def current_state(self):
        base, steps = self.plan()
        return steps[-1][1] if steps else base

    def to_json(self):
        return {"id": self.id, "layers": [l.to_json() for l in self.layers], "locks": sorted(self.locks),
                "state": self.current_state()}


SYN = {"green": ["forest", "sage", "olive"], "blue": ["ink blue", "deep blue"], "orange": ["terracotta", "rust"],
       "red": ["rust", "terracotta"], "grey": ["linen grey", "charcoal"], "gray": ["linen grey", "charcoal"],
       "white": ["warm white", "ivory"], "black": ["black oak", "charcoal"], "stone": ["travertine"],
       "dark": ["walnut", "charcoal", "ink blue", "deep blue"]}
OBJ_WORDS = {"sofa": ["sofa", "couch", "settee"], "rug": ["rug", "carpet"], "floor": ["floor", "flooring"],
             "wall": ["wall"], "table": ["table"]}


def parse_intent(text):
    """Keyword stand-in for the intent engine. Claude replaces this later:
    the contract (text in, list of layer edits out) stays the same."""
    t = text.lower()
    out = []
    for m in MOMENTS:
        w = m.lower().split()[0]
        if w in t or (m == "Golden hour" and "sunset" in t) or (m == "Dusk" and "evening" in t) or (m == "Midday" and "noon" in t):
            out.append(("moment", f"Moment: {m}", {"moment": m}))
            break
    if "lights off" in t or "light off" in t:
        out.append(("lights", "Lights: off", {"pendant": False, "cove": False}))
    elif "lights on" in t or "light on" in t:
        out.append(("lights", "Lights: on", {"pendant": True, "cove": True}))
    if "warm" in t:
        out.append(("kelvin", "Lights: 2700 K", {"kelvin": 2700}))
    elif "cool" in t or "neutral" in t:
        out.append(("kelvin", "Lights: 4000 K", {"kelvin": 4000}))
    for obj, words in OBJ_WORDS.items():
        if not any(w in t for w in words):
            continue
        opts = list(SWATCH[obj])
        pick = next((o for o in opts if o.lower() in t or o.lower().split()[0] in t), None)
        if not pick:
            for w, cands in SYN.items():
                if w in t:
                    pick = next((o for o in opts if o.lower() in cands), None)
                    if pick:
                        break
        if pick:
            out.append((f"{obj}:finish", f"{NAMES[obj]}: {pick}", {obj: pick}))
    return out
