"""Material library and automatic matching. No Blender here.

A SketchUp model already says which material sits on which face, but its
materials are flat colours or small photos. We keep the assignment and swap
each SketchUp material for a physically based library material: built-in
procedural ones (always available) plus downloaded scans (Poly Haven).

An assignment value is a library id, optionally with a colour to tint it:
"linen" or "linen#8a8a8a". Tinting keeps the designer's chosen colour while
the library supplies the weave, grain and roughness.
"""
import json
import os
import re
from dataclasses import dataclass, field


@dataclass
class Entry:
    id: str
    name: str
    category: str
    color: str            # display colour, also the default base colour
    recipe: str           # procedural recipe in materials.py, or "scan"
    tags: tuple = ()
    params: dict = field(default_factory=dict)
    tintable: bool = False
    source: str = "Built-in"
    license: str = ""
    maps: dict = None     # scan only: {"color": path, "rough": path, "normal": path, "disp": path}
    size_m: float = 1.0   # real-world size of one texture tile

    def to_json(self):
        return {"id": self.id, "name": self.name, "category": self.category, "color": self.color,
                "tintable": self.tintable, "source": self.source, "license": self.license}


def _e(id, name, category, color, recipe, tags="", tintable=False, **params):
    return Entry(id, name, category, color, recipe, tuple(tags.split()), params, tintable)


BUILTIN = [
    _e("oak-planks", "Oak planks", "wood", "#b78a5c", "wood_planks", "oak floor parquet plank light"),
    _e("ash-planks", "Pale ash planks", "wood", "#d2b48c", "wood_planks", "ash birch maple pale light floor plank"),
    _e("walnut-planks", "Walnut planks", "wood", "#6c4a31", "wood_planks", "walnut dark floor plank", gloss=0.4),
    _e("walnut-veneer", "Walnut veneer", "wood", "#5a3a25", "walnut", "walnut veneer dark furniture"),
    _e("oak-veneer", "Oak veneer", "wood", "#a87f55", "walnut", "oak veneer furniture"),
    _e("teak-veneer", "Teak veneer", "wood", "#8a5a33", "walnut", "teak cherry mahogany veneer"),
    _e("black-oak", "Black stained oak", "wood", "#2b2724", "walnut", "black ebony stained oak"),
    _e("linen", "Linen", "fabric", "#b8b2a7", "fabric", "linen cotton fabric upholstery textile cloth", True),
    _e("boucle", "Boucle", "fabric", "#e6e0d4", "fabric", "boucle wool fabric upholstery", True, bump=0.5),
    _e("velvet", "Velvet", "fabric", "#3f5b47", "velvet", "velvet plush fabric", True),
    _e("wool-rug", "Wool rug", "fabric", "#e4dccd", "wool", "rug carpet wool", True),
    _e("leather", "Leather", "leather", "#6b3f2a", "leather", "leather hide skin", True),
    _e("travertine", "Travertine", "stone", "#d8ccb6", "stone", "travertine limestone stone beige"),
    _e("carrara", "Carrara marble", "stone", "#ece9e4", "marble", "marble carrara white calacatta statuario"),
    _e("nero-marble", "Nero marquina", "stone", "#1d1d1f", "marble", "marble black nero marquina", vein="#d9d9d9"),
    _e("terrazzo", "Terrazzo", "stone", "#d9d4cc", "terrazzo", "terrazzo"),
    _e("granite", "Dark granite", "stone", "#3c3b3a", "stone", "granite quartz countertop dark slate"),
    _e("concrete", "Concrete", "concrete", "#9c9893", "concrete", "concrete cement microcement screed", True),
    _e("plaster", "Lime plaster", "plaster", "#ece6dc", "plaster", "plaster wall stucco lime", True),
    _e("matte-paint", "Matte paint", "paint", "#f2f0ec", "matte", "paint painted wall emulsion color colour", True, rough=0.85),
    _e("satin-paint", "Satin lacquer", "paint", "#f2f0ec", "matte", "lacquer satin gloss cabinet joinery", True, rough=0.35),
    _e("ceramic-tile", "Ceramic tile", "tile", "#efece6", "tile", "tile ceramic porcelain subway", True),
    _e("brass", "Brushed brass", "metal", "#c8a35a", "metal", "brass gold bronze", rough=0.28),
    _e("steel", "Brushed steel", "metal", "#b9bcbf", "metal", "steel stainless aluminium aluminum metal nickel brushed", rough=0.3),
    _e("chrome", "Chrome", "metal", "#d6d8da", "metal", "chrome mirror polished", rough=0.04),
    _e("black-metal", "Black metal", "metal", "#262626", "metal", "black iron powder coat", rough=0.45),
    _e("copper", "Copper", "metal", "#b87333", "metal", "copper", rough=0.25),
    _e("clear-glass", "Clear glass", "glass", "#dfe9ec", "glass", "glass glazing window clear"),
    _e("frosted-glass", "Frosted glass", "glass", "#e8eeee", "glass", "frosted satin glass", rough=0.3),
]

# words in a SketchUp material name -> category
CATEGORY_WORDS = {
    "wood": "wood timber oak walnut ash teak maple birch pine cherry mahogany beech parquet plank veneer laminate ebony",
    "fabric": "fabric linen cotton velvet boucle textile upholstery cloth rug carpet wool curtain drape cushion",
    "leather": "leather hide",
    "stone": "stone marble travertine granite limestone terrazzo quartz onyx slate calacatta carrara quartzite",
    "concrete": "concrete cement microcement screed",
    "plaster": "plaster stucco",
    "paint": "paint painted lacquer emulsion wall ceiling",
    "tile": "tile tiles ceramic porcelain mosaic",
    "metal": "metal steel brass bronze chrome aluminium aluminum iron copper gold nickel",
    "glass": "glass glazing translucent window",
}
# what an object is -> likely category (used when the material name says nothing)
OBJECT_HINTS = {"sofa": "fabric", "rug": "fabric", "floor": "wood", "wall": "paint",
                "ceiling": "paint", "table": "wood", "window": "glass", "sidetable": "stone"}

GENERIC = {"wood", "fabric", "stone", "metal", "glass", "tile", "tiles", "paint", "wall", "floor", "color", "colour"}
_WORD_CAT = {w: c for c, ws in CATEGORY_WORDS.items() for w in ws.split()}


class Library:
    def __init__(self, entries=None):
        self.entries = {e.id: e for e in (entries if entries is not None else BUILTIN)}

    def add(self, entry):
        self.entries[entry.id] = entry

    def get(self, value):
        """Entry and tint for an assignment value like "linen#8a8a8a"."""
        lid, _, tint = value.partition("#")
        return self.entries[lid], ("#" + tint if tint else None)

    def name(self, value):
        e, tint = self.get(value)
        return e.name + (f" ({tint})" if tint else "")

    def search(self, q="", category=None, limit=40):
        words = tokens(q)
        out = []
        for e in self.entries.values():
            if category and e.category != category:
                continue
            hay = set(tokens(e.name)) | set(e.tags) | {e.category}
            if all(any(h.startswith(w) for h in hay) for w in words):
                out.append(e)
        out.sort(key=lambda e: (e.source == "Built-in", e.category, e.name))  # scans first
        return out[:limit]

    def load_dir(self, root):
        """Add downloaded scans: one folder per material holding entry.json + maps."""
        if not os.path.isdir(root):
            return 0
        n = 0
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d, "entry.json")
            if os.path.exists(p):
                j = json.load(open(p))
                maps = {k: os.path.join(root, d, v) for k, v in j["maps"].items()}
                self.add(Entry(j["id"], j["name"], j["category"], j["color"], "scan", tuple(j.get("tags", ())),
                               {}, False, j.get("source", "Poly Haven"), j.get("license", "CC0"), maps,
                               j.get("size_m", 1.0)))
                n += 1
        return n

    # ----- matching -----
    def match(self, name, color=None, texture=None, objects=(), limit=6):
        """Rank library materials for one SketchUp material.
        Returns [{"value", "entry", "score", "why"}], best first."""
        words = tokens(name) + tokens(texture or "")
        cats = [_WORD_CAT[w] for w in words if w in _WORD_CAT]
        cat = cats[0] if cats else None
        why_cat = "name" if cat else None
        if not cat:
            hinted = [OBJECT_HINTS[o] for o in objects if o in OBJECT_HINTS]
            cat, why_cat = (hinted[0], "object") if hinted else (None, None)
        out = []
        for e in self.entries.values():
            s, why = 0.0, []
            if cat and e.category == cat:
                s += 0.5 if why_cat == "name" else 0.4
                why.append(f"{cat} ({why_cat})")
            specific = sorted({w for w in words if w in e.tags and w not in GENERIC})
            if specific:
                s += min(0.3, 0.15 * len(specific))
                why.append("name: " + ", ".join(specific))
            if color:
                d = color_distance(color, e.color)
                if e.tintable:
                    s += 0.1  # keeps the SketchUp colour exactly
                else:
                    s += 0.2 * max(0.0, 1 - d / 60)
                    if d < 20:
                        why.append("colour")
            if e.source != "Built-in" and s > 0:
                s += 0.02  # prefer real scans on a tie
            value = e.id + (color if (e.tintable and color) else "")
            out.append({"value": value, "entry": e, "score": round(min(s, 1.0), 3), "why": why})
        out.sort(key=lambda r: -r["score"])
        return out[:limit]

    def auto(self, material, threshold=0.5):
        """Best match for a scene material, or None when we are not confident:
        then the SketchUp material is kept as it is."""
        m = self.match(material["slot"], material.get("color"), material.get("texture"), material.get("objects", ()), 1)
        return m[0] if m and m[0]["score"] >= threshold else None


def tokens(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    return [w for w in re.split(r"[^a-z]+", text.lower()) if len(w) > 1]


def _lab(hex_):
    h = hex_.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (0.4124 * lin[0] + 0.3576 * lin[1] + 0.1805 * lin[2]) / 0.9505
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    z = (0.0193 * lin[0] + 0.1192 * lin[1] + 0.9505 * lin[2]) / 1.089
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def color_distance(a, b):
    """CIE76 distance between two hex colours (about 2.3 = just noticeable)."""
    la, lb = _lab(a), _lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


LIBRARY_DIR = os.environ.get("AI_RENDER_LIBRARY", os.path.abspath(os.path.join("data", "library")))
_default = None


def default_library():
    """Built-in materials plus any scans downloaded into LIBRARY_DIR."""
    global _default
    if _default is None:
        _default = Library()
        _default.load_dir(LIBRARY_DIR)
    return _default
