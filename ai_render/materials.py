"""Procedural PBR materials, so the prototype needs no texture downloads."""
import bpy


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    return m, nt, bsdf


def _hex(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, 1.0)


def _bump(nt, bsdf, height_socket, strength=0.2, distance=0.01):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height_socket, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])


def plaster(color="#ece6dc", name="Plaster"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Roughness"].default_value = 0.92
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 60
    n.inputs["Detail"].default_value = 8
    _bump(nt, bsdf, n.outputs["Fac"], 0.05)
    return m


def wood_planks(color="#b78a5c", name="Oak floor", gloss=0.35):
    """Plank floor: brick texture lays out boards, wave texture adds grain."""
    m, nt, bsdf = _new(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.5
    br.squash_frequency = 1
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.0015
    br.inputs["Brick Width"].default_value = 1.2
    br.inputs["Row Height"].default_value = 0.18
    base = _hex(color)
    dark = tuple(c * 0.86 for c in base[:3]) + (1,)
    br.inputs["Color1"].default_value = base
    br.inputs["Color2"].default_value = dark
    br.inputs["Mortar"].default_value = tuple(c * 0.55 for c in base[:3]) + (1,)
    nt.links.new(mp.outputs["Vector"], br.inputs["Vector"])
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.inputs["Scale"].default_value = 6
    wv.inputs["Distortion"].default_value = 8
    wv.inputs["Detail"].default_value = 6
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.25
    nt.links.new(br.outputs["Color"], mix.inputs["A"])
    nt.links.new(wv.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1 - gloss
    bsdf.inputs["Coat Weight"].default_value = 0.15
    _bump(nt, bsdf, br.outputs["Fac"], 0.3, 0.004)
    return m


def fabric(color="#b8b2a7", name="Linen"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Roughness"].default_value = 0.95
    bsdf.inputs["Sheen Weight"].default_value = 0.6
    bsdf.inputs["Sheen Roughness"].default_value = 0.4
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 400
    n.inputs["Detail"].default_value = 4
    _bump(nt, bsdf, n.outputs["Fac"], 0.25, 0.002)
    return m


def wool(color="#e4dccd", name="Wool rug"):
    m = fabric(color, name)
    m.node_tree.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 1.0
    return m


def walnut(color="#5a3a25", name="Walnut"):
    m, nt, bsdf = _new(name)
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 3
    wv.inputs["Distortion"].default_value = 12
    wv.inputs["Detail"].default_value = 8
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    base = _hex(color)
    ramp.color_ramp.elements[0].color = tuple(c * 0.6 for c in base[:3]) + (1,)
    ramp.color_ramp.elements[1].color = base
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Coat Weight"].default_value = 0.4
    bsdf.inputs["Coat Roughness"].default_value = 0.15
    return m


def stone(color="#d6c8b0", name="Travertine"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Roughness"].default_value = 0.55
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 25
    n.inputs["Detail"].default_value = 10
    _bump(nt, bsdf, n.outputs["Fac"], 0.15)
    return m


def brass(name="Brass"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex("#c8a35a")
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.28
    return m


def matte(color, name, rough=0.8):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def glass(name="Glass"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Roughness"].default_value = 0.0
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.5
    return m


def emission(color_rgb, strength, name):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = (*color_rgb, 1)
    bsdf.inputs["Emission Color"].default_value = (*color_rgb, 1)
    bsdf.inputs["Emission Strength"].default_value = strength
    return m


# Finishes the user can pick per object. Keys match the walkthrough page.
CATALOG = {
    "sofa": {"Linen grey": lambda: fabric("#b8b2a7", "Sofa linen grey"),
             "Terracotta": lambda: fabric("#b0603e", "Sofa terracotta"),
             "Forest": lambda: fabric("#3f5b47", "Sofa forest"),
             "Ink blue": lambda: fabric("#2e3d5a", "Sofa ink blue")},
    "rug": {"Ivory": lambda: wool("#e4dccd", "Rug ivory"),
            "Sage": lambda: wool("#9ea891", "Rug sage"),
            "Rust": lambda: wool("#9f573a", "Rug rust"),
            "Charcoal": lambda: wool("#4a4949", "Rug charcoal")},
    "floor": {"Oak": lambda: wood_planks("#b78a5c", "Floor oak"),
              "Walnut": lambda: wood_planks("#6c4a31", "Floor walnut", 0.4),
              "Travertine": lambda: stone("#d8ccb6", "Floor travertine")},
    "wall": {"Warm white": lambda: plaster("#ece6dc", "Wall warm white"),
             "Clay": lambda: plaster("#c8a387", "Wall clay"),
             "Olive": lambda: plaster("#8d8c69", "Wall olive"),
             "Deep blue": lambda: plaster("#36445e", "Wall deep blue")},
    "table": {"Walnut": lambda: walnut("#5a3a25", "Table walnut"),
              "Travertine": lambda: stone("#d6c8b0", "Table travertine"),
              "Black oak": lambda: walnut("#2b2724", "Table black oak")},
}


# ----- library recipes (see library.py) -----

def velvet(color="#3f5b47", name="Velvet"):
    m = fabric(color, name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Sheen Weight"].default_value = 1.0
    b.inputs["Sheen Roughness"].default_value = 0.25
    b.inputs["Roughness"].default_value = 0.8
    return m


def leather(color="#6b3f2a", name="Leather"):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Coat Weight"].default_value = 0.2
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.inputs["Scale"].default_value = 180
    _bump(nt, bsdf, v.outputs["Distance"], 0.15, 0.002)
    return m


def marble(color="#ece9e4", name="Marble", vein="#8f8f8f"):
    m, nt, bsdf = _new(name)
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 2.5
    n.inputs["Detail"].default_value = 12
    n.inputs["Distortion"].default_value = 3
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 1.5
    wv.inputs["Distortion"].default_value = 18
    wv.inputs["Detail"].default_value = 10
    nt.links.new(n.outputs["Color"], wv.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = _hex(vein)
    ramp.color_ramp.elements[1].position = 0.12
    ramp.color_ramp.elements[1].color = _hex(color)
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.12
    bsdf.inputs["Coat Weight"].default_value = 0.3
    return m


def terrazzo(color="#d9d4cc", name="Terrazzo"):
    m, nt, bsdf = _new(name)
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.inputs["Scale"].default_value = 40
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = _hex("#8d8a84")
    ramp.color_ramp.elements[1].position = 0.08
    ramp.color_ramp.elements[1].color = _hex(color)
    nt.links.new(v.outputs["Distance"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.3
    return m


def concrete(color="#9c9893", name="Concrete"):
    m = stone(color, name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.75
    return m


def tile(color="#efece6", name="Tile"):
    m, nt, bsdf = _new(name)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 3.3
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Brick Width"].default_value = 0.6
    br.inputs["Row Height"].default_value = 0.3
    br.inputs["Color1"].default_value = _hex(color)
    br.inputs["Color2"].default_value = _hex(color)
    br.inputs["Mortar"].default_value = tuple(c * 0.7 for c in _hex(color)[:3]) + (1,)
    nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.15
    _bump(nt, bsdf, br.outputs["Fac"], 0.4, 0.003)
    return m


def metal(color="#b9bcbf", name="Metal", rough=0.3):
    m, nt, bsdf = _new(name)
    bsdf.inputs["Base Color"].default_value = _hex(color)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = rough
    return m


def scan(maps, name, size_m=1.0, tint=None):
    """Photo-scanned PBR set (colour, roughness, normal, displacement) with box
    projection at real-world size, so it works on SketchUp faces without UVs."""
    m, nt, bsdf = _new(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / size_m,) * 3
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def tex(key, non_color):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(maps[key], check_existing=True)
        if non_color:
            t.image.colorspace_settings.name = "Non-Color"
        t.projection = "BOX"
        t.projection_blend = 0.2
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t

    if "color" in maps:
        c = tex("color", False)
        out = c.outputs["Color"]
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(out, mix.inputs["A"])
            mix.inputs["B"].default_value = _hex(tint)
            out = mix.outputs["Result"]
        nt.links.new(out, bsdf.inputs["Base Color"])
    if "rough" in maps:
        nt.links.new(tex("rough", True).outputs["Color"], bsdf.inputs["Roughness"])
    if "normal" in maps:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex("normal", True).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m


RECIPES = {"wood_planks": wood_planks, "walnut": walnut, "fabric": fabric, "wool": wool, "velvet": velvet,
           "leather": leather, "stone": stone, "marble": marble, "terrazzo": terrazzo, "concrete": concrete,
           "plaster": plaster, "matte": None, "tile": tile, "metal": metal, "glass": None}


def from_library(entry, tint=None):
    """Blender material for a library entry (see library.py), optionally tinted."""
    color = tint or entry.color
    name = f"{entry.name} {tint}" if tint else entry.name
    p = dict(entry.params)
    if entry.recipe == "scan":
        return scan(entry.maps, name, entry.size_m, tint)
    if entry.recipe == "matte":
        return matte(color, name, p.get("rough", 0.8))
    if entry.recipe == "glass":
        m = glass(name)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = p.get("rough", 0.0)
        return m
    if entry.recipe == "fabric":
        m = fabric(color, name)
        if "bump" in p:
            m.node_tree.nodes["Bump"].inputs["Strength"].default_value = p["bump"]
        return m
    if entry.recipe == "wood_planks":
        return wood_planks(color, name, p.get("gloss", 0.35))
    if entry.recipe == "metal":
        return metal(color, name, p.get("rough", 0.3))
    if entry.recipe == "marble":
        return marble(color, name, p.get("vein", "#8f8f8f"))
    return RECIPES[entry.recipe](color, name)
