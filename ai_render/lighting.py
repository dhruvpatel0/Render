"""Moments (time of day) and interior lights."""
import math
import bpy
from mathutils import Vector

from . import materials as M

MOMENTS = {
    # sun elevation/azimuth in degrees, sun strength (W/m2), sun tint, sky strength
    "Morning":     dict(el=24, az=28, sun=3.2, tint=(1.0, 0.93, 0.84), sky=1.0, night=False, key=0.20, wb=0.55),
    "Midday":      dict(el=48, az=20, sun=4.0, tint=(1.0, 0.98, 0.95), sky=1.0, night=False, key=0.20, wb=0.6),
    "Golden hour": dict(el=14, az=30, sun=3.0, tint=(1.0, 0.78, 0.55), sky=0.8, night=False, key=0.20, wb=0.45),
    "Dusk":        dict(el=-2, az=24, sun=0.0, tint=(1, 1, 1), sky=0.9, night=False, key=0.12, wb=0.3),
    "Night":       dict(el=-20, az=24, sun=0.0, tint=(1, 1, 1), sky=0.0, night=True, key=0.09, wb=0.2),
}


def kelvin_rgb(k):
    t = k / 100
    r = 255 if t <= 66 else 329.7 * (t - 60) ** -0.1332
    g = 99.47 * math.log(t) - 161.12 if t <= 66 else 288.12 * (t - 60) ** -0.0755
    b = 255 if t >= 66 else (0 if t <= 19 else 138.52 * math.log(t - 10) - 305.04)
    c = [max(0, min(255, v)) / 255 for v in (r, g, b)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c)


def setup_world(moment):
    m = MOMENTS[moment]
    w = bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    if m["night"]:
        bg.inputs["Color"].default_value = (0.004, 0.006, 0.014, 1)
        bg.inputs["Strength"].default_value = 1.0
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "MULTIPLE_SCATTERING"
        sky.sun_disc = False
        sky.sun_elevation = math.radians(m["el"])
        sky.sun_rotation = math.radians(270 - m["az"])
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.25 * m["sky"]
    if m["sun"] > 0:
        el, az = math.radians(m["el"]), math.radians(m["az"])
        # direction the light travels: into the room through the left-wall window (+x)
        d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), -math.sin(el)))
        sun = bpy.data.lights.new("Sun", "SUN")
        sun.energy = m["sun"]
        sun.color = m["tint"]
        sun.angle = math.radians(0.6)
        ob = bpy.data.objects.new("Sun", sun)
        bpy.context.scene.collection.objects.link(ob)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def add_interior_lights(pendant=True, cove=True, downlights=None, kelvin=2700, moment="Golden hour"):
    """Physically based fixtures. Downlights default to on after dark."""
    sc = bpy.context.scene
    col = kelvin_rgb(kelvin)
    if downlights is None:
        downlights = MOMENTS[moment]["night"] or moment == "Dusk"

    def light(name, kind, energy, loc, **kw):
        L = bpy.data.lights.new(name, kind)
        L.energy = energy
        L.color = col
        for k, v in kw.items():
            setattr(L, k, v)
        ob = bpy.data.objects.new(name, L)
        sc.collection.objects.link(ob)
        ob.location = loc
        return ob

    if pendant:
        light("Pendant bulb", "POINT", 45, (0, 3.1, 1.6), shadow_soft_size=0.05)
        bpy.ops.mesh.primitive_circle_add(vertices=48, radius=0.2, fill_type="NGON", location=(0, 3.1, 1.565))
        disc = bpy.context.active_object
        disc.name = "Pendant diffuser"
        disc.data.materials.append(M.emission(col, 6, "Diffuser"))
        disc["semantic"] = "pendant"
        disc.pass_index = 9
    if cove:
        ob = light("LED cove", "AREA", 70, (0, 4.93, 2.74), shape="RECTANGLE", size=4.9, size_y=0.04)
        ob.rotation_euler = (math.radians(-25), 0, 0)
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 4.985, 2.76))
        strip = bpy.context.active_object
        strip.name = "LED strip"
        strip.scale = (4.9, 0.02, 1)
        strip.data.materials.append(M.emission(col, 25, "LED"))
        strip["semantic"] = "lights"
        strip.pass_index = 12
    if downlights:
        for x in (-1.6, 1.6):
            for y in (1.4, 3.9):
                ob = light("Downlight", "SPOT", 30, (x, y, 2.78), spot_size=math.radians(80),
                           spot_blend=0.6, shadow_soft_size=0.04)
                bpy.ops.mesh.primitive_circle_add(vertices=32, radius=0.045, fill_type="NGON", location=(x, y, 2.795))
                d = bpy.context.active_object
                d.data.materials.append(M.emission(col, 15, "Downlight"))
                d["semantic"] = "lights"
                d.pass_index = 12


def add_room_light(bounds, on=True, kelvin=3000):
    """Imported models: one soft ceiling light, since fixture positions are unknown."""
    if not on:
        return
    lo, hi = bounds
    L = bpy.data.lights.new("Room light", "AREA")
    L.shape = "RECTANGLE"
    L.size = max(0.5, (hi.x - lo.x) * 0.5)
    L.size_y = max(0.5, (hi.y - lo.y) * 0.5)
    L.energy = 40 * L.size * L.size_y
    L.color = kelvin_rgb(kelvin)
    ob = bpy.data.objects.new("Room light", L)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z - 0.05)
