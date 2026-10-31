"""Scene building: a sample interior, or an imported SketchUp export (FBX/glTF).

Every object gets a semantic key ("sofa", "floor", ...) and a matching
pass_index, so the renderer can output an exact mask per object.
"""
import math
import bpy
import bmesh
from mathutils import Vector

from . import materials as M

SEMANTIC = {"floor": 1, "wall": 2, "side": 3, "ceiling": 4, "window": 5, "sofa": 6,
            "rug": 7, "table": 8, "pendant": 9, "art": 10, "sidetable": 11, "lights": 12,
            "outside": 13}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def tag(obj, key):
    obj["semantic"] = key
    obj.pass_index = SEMANTIC[key]
    return obj


def box(name, x0, x1, y0, y1, z0, z1, mat, key, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.scale = (x1 - x0, y1 - y0, z1 - z0)
    ob.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.context.view_layer.update()
    # apply scale so bevels stay round
    me.transform(ob.matrix_basis.to_3x3().to_4x4())
    ob.scale = (1, 1, 1)
    me.materials.append(mat)
    if bevel:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 5
        mod.limit_method = "NONE"
        for p in me.polygons:
            p.use_smooth = True
    return tag(ob, key)


def cylinder(name, x, y, z0, z1, r, mat, key, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=z1 - z0,
                                        location=(x, y, (z0 + z1) / 2))
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return tag(ob, key)


def build_sample_room(finishes):
    """A 5 m x 5 m living room with a window on the left wall."""
    sc = bpy.context.scene
    wall_side = M.plaster("#ebe7e0", "Side walls")
    wall_back = _slot(M.CATALOG["wall"][finishes["wall"]](), "Back wall")
    ceiling = M.plaster("#f3f1ed", "Ceiling")
    floor = _slot(M.CATALOG["floor"][finishes["floor"]](), "Floor")
    trim = M.matte("#f2f0ec", "Trim", 0.5)
    frame = M.matte("#2b2b2b", "Window frame", 0.4)

    box("Floor", -2.5, 2.5, -0.2, 5.0, -0.05, 0.0, floor, "floor")
    box("Ceiling", -2.65, 2.65, -0.35, 5.15, 2.8, 2.95, ceiling, "ceiling")
    box("Back wall", -2.65, 2.65, 5.0, 5.15, 0, 2.8, wall_back, "wall")
    box("Front wall", -2.65, 2.65, -0.35, -0.2, 0, 2.8, wall_side, "side")
    box("Right wall", 2.5, 2.65, -0.35, 5.15, 0, 2.8, wall_side, "side")
    # left wall with a window opening y 1.5..3.9, z 0.75..2.45
    for args in [(-0.35, 1.5, 0, 2.8), (3.9, 5.15, 0, 2.8), (1.5, 3.9, 0, 0.75), (1.5, 3.9, 2.45, 2.8)]:
        box("Left wall", -2.65, -2.5, args[0], args[1], args[2], args[3], wall_side, "side")
    # window frame + mullions + glass
    for f in [(1.5, 1.56, 0.75, 2.45), (3.84, 3.9, 0.75, 2.45), (1.5, 3.9, 0.75, 0.81),
              (1.5, 3.9, 2.39, 2.45), (2.67, 2.73, 0.75, 2.45), (1.5, 3.9, 1.57, 1.62)]:
        box("Window frame", -2.6, -2.54, f[0], f[1], f[2], f[3], frame, "window")
    g = box("Glass", -2.575, -2.565, 1.5, 3.9, 0.75, 2.45, M.glass(), "window")
    g.visible_shadow = False
    outside = M.matte("#5b6b4a", "Garden", 0.9)
    box("Garden", -40, -2.66, -40, 40, -0.15, -0.05, outside, "outside")
    # skirting
    box("Skirting", -2.5, 2.5, 4.985, 5.0, 0, 0.09, trim, "side")
    box("Skirting", 2.485, 2.5, -0.2, 5.0, 0, 0.09, trim, "side")

    # sofa
    sofa = _slot(M.CATALOG["sofa"][finishes["sofa"]](), "Sofa fabric")
    leg = M.walnut("#3a2618", "Sofa legs")
    box("Sofa base", -1.2, 1.2, 4.0, 4.95, 0.1, 0.42, sofa, "sofa", 0.03)
    box("Sofa back", -1.08, 1.08, 4.74, 4.95, 0.42, 0.86, sofa, "sofa", 0.04)
    box("Sofa arm L", -1.24, -1.06, 4.0, 4.95, 0.1, 0.66, sofa, "sofa", 0.05)
    box("Sofa arm R", 1.06, 1.24, 4.0, 4.95, 0.1, 0.66, sofa, "sofa", 0.05)
    box("Seat cushion L", -1.05, -0.005, 4.02, 4.76, 0.42, 0.57, sofa, "sofa", 0.05)
    box("Seat cushion R", 0.005, 1.05, 4.02, 4.76, 0.42, 0.57, sofa, "sofa", 0.05)
    for x0, x1 in [(-1.03, -0.03), (0.03, 1.03)]:
        c = box("Back cushion", x0, x1, 4.58, 4.76, 0.55, 0.98, sofa, "sofa", 0.07)
        c.rotation_euler.x = math.radians(-8)
    for x in (-1.15, 1.15):
        for y in (4.06, 4.89):
            box("Sofa leg", x - 0.03, x + 0.03, y - 0.03, y + 0.03, 0, 0.1, leg, "sofa")

    # rug + coffee table
    box("Rug", -1.5, 1.5, 2.1, 4.55, 0, 0.012, _slot(M.CATALOG["rug"][finishes["rug"]](), "Rug"), "rug", 0.004)
    table = _slot(M.CATALOG["table"][finishes["table"]](), "Coffee table")
    box("Table top", -0.62, 0.62, 2.75, 3.45, 0.36, 0.40, table, "table", 0.008)
    for x in (-0.56, 0.56):
        for y in (2.81, 3.39):
            box("Table leg", x - 0.025, x + 0.025, y - 0.025, y + 0.025, 0.012, 0.36, table, "table")

    # side table with books
    cylinder("Side table", 1.62, 4.5, 0.0, 0.52, 0.24, M.stone("#cfc3ad", "Side table stone"), "sidetable")
    box("Books", 1.5, 1.74, 4.42, 4.6, 0.52, 0.56, M.matte("#7a3b2e", "Book red", 0.7), "sidetable", 0.004)
    box("Books", 1.52, 1.72, 4.43, 4.58, 0.56, 0.59, M.matte("#e8e1d3", "Book cream", 0.7), "sidetable", 0.004)

    # art above sofa
    box("Art frame", -0.6, 0.6, 4.96, 5.0, 1.25, 2.0, M.matte("#1f1f1f", "Art frame", 0.5), "art")
    art = M.matte("#d9cbb2", "Canvas", 0.9)
    nt = art.node_tree
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 1.2
    wv.inputs["Distortion"].default_value = 4
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = M._hex("#b0603e")
    ramp.color_ramp.elements[1].color = M._hex("#e8dcc4")
    e = ramp.color_ramp.elements.new(0.5)
    e.color = M._hex("#3f5b47")
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    box("Art canvas", -0.56, 0.56, 4.955, 4.965, 1.29, 1.96, art, "art")

    # pendant over the table
    cylinder("Pendant cord", 0, 3.1, 1.78, 2.8, 0.004, M.matte("#1a1a1a", "Cord", 0.5), "pendant", 12)
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=0.24, radius2=0.06, depth=0.24,
                                    end_fill_type="NOTHING", location=(0, 3.1, 1.66))
    shade = bpy.context.active_object
    shade.name = "Pendant shade"
    shade.data.materials.append(M.brass())
    for p in shade.data.polygons:
        p.use_smooth = True
    shade.modifiers.new("thick", "SOLIDIFY").thickness = 0.004
    tag(shade, "pendant")
    return {"camera": dict(location=(0.2, 0.1, 1.45), lens=16, shift_y=-0.04, target_y=5)}


def import_model(path):
    """Import a SketchUp export. Semantic keys come from object or material names."""
    if path.lower().endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif path.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError("Export from SketchUp as .fbx or .glb")
    for m in bpy.data.materials:
        m["slot"] = m.name  # the SketchUp material name: stable id for assignments
    words = {"sofa": "sofa", "couch": "sofa", "rug": "rug", "carpet": "rug", "floor": "floor",
             "table": "table", "lamp": "pendant", "light": "pendant", "window": "window",
             "glass": "window", "art": "art", "frame": "art", "wall": "wall", "ceiling": "ceiling"}
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        name = (ob.name + " " + " ".join(m.name for m in ob.data.materials if m)).lower()
        key = next((k for w, k in words.items() if w in name), "side")
        tag(ob, key)
        if _is_glass(ob, name):
            ob.visible_shadow = False  # let sunlight through windows (no caustics needed)
    return {"camera": auto_camera()}


def _is_glass(ob, name):
    if "glass" in name or "glazing" in name:
        return True
    for m in ob.data.materials:
        b = m and m.node_tree and m.node_tree.nodes.get("Principled BSDF")
        if b and (b.inputs["Transmission Weight"].default_value > 0.5 or b.inputs["Alpha"].default_value < 0.9):
            return True
    return False


def scene_bounds():
    pts = [ob.matrix_world @ Vector(c) for ob in bpy.context.scene.objects
           if ob.type == "MESH" for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def auto_camera():
    """Eye-level camera near one end of the model, looking along +Y.
    A starting point only: the Frame step in the app lets people pick their own."""
    lo, hi = scene_bounds()
    size = hi - lo
    z = lo.z + min(1.5, max(0.4 * size.z, 0.5))
    return dict(location=((lo.x + hi.x) / 2, lo.y + 0.08 * size.y, z), lens=16, shift_y=0.0)


def _slot(mat, slot):
    mat["slot"] = slot
    return mat


def _srgb_hex(rgba):
    to = lambda c: c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return "#" + "".join(f"{round(max(0, min(1, to(c))) * 255):02x}" for c in rgba[:3])


def scene_materials():
    """Every material on a mesh, keyed by its slot (the SketchUp material name).
    Gives each one a stable pass_index, so the render can output a material map."""
    found = {}
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        for m in ob.data.materials:
            if not m:
                continue
            slot = m.get("slot") or m.name
            m["slot"] = slot
            info = found.setdefault(slot, {"slot": slot, "objects": set(), "mats": []})
            info["objects"].add(ob.get("semantic", "side"))
            if m not in info["mats"]:
                info["mats"].append(m)
    out = []
    for i, slot in enumerate(sorted(found), 1):
        info = found[slot]
        m = info["mats"][0]
        color, texture = _srgb_hex(m.diffuse_color), None
        b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes and m.node_tree else None
        if b:
            sock = b.inputs["Base Color"]
            color = _srgb_hex(sock.default_value)
            for link in sock.links:
                if link.from_node.type == "TEX_IMAGE" and link.from_node.image:
                    texture = link.from_node.image.name
        for mm in info["mats"]:
            mm.pass_index = i
        out.append({"slot": slot, "index": i, "color": color, "texture": texture,
                    "objects": sorted(info["objects"])})
    return out


def apply_materials(assign, library):
    """Scene-first material swap: {slot: library value}. Every face that used the
    SketchUp material gets the library material, nothing else changes."""
    for slot, value in assign.items():
        entry, tint = library.get(value)
        new = M.from_library(entry, tint)
        new["slot"] = slot
        for ob in bpy.context.scene.objects:
            if ob.type != "MESH":
                continue
            for i, m in enumerate(ob.data.materials):
                if m and (m.get("slot") or m.name) == slot:
                    ob.data.materials[i] = new


def set_finish(key, finish):
    """Scene-first edit: swap the material on every object with this semantic key."""
    mat = M.CATALOG[key][finish]()
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH" or ob.get("semantic") != key or ob.name.startswith("Sofa leg"):
            continue
        ob.data.materials.clear()
        ob.data.materials.append(mat)


def add_camera(location, lens, shift_y=0.0, target_y=5.0):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = lens
    cam.sensor_width = 36
    cam.shift_y = shift_y
    ob = bpy.data.objects.new("Camera", cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = location
    # level camera, looking down +Y: vertical lines stay vertical (two-point perspective)
    ob.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.camera = ob
    return ob
