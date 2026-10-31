import json

import numpy as np
from fastapi.testclient import TestClient

from ai_render import library as LIB
from ai_render import server
from ai_render import service as S
from ai_render.scene import SEMANTIC

L = LIB.Library()


def best(name, color=None, objects=()):
    m = L.auto({"slot": name, "color": color, "objects": objects})
    return m and m["value"]


def test_matches_sketchup_names():
    assert best("Wood_Floor_Oak", "#b3906c") == "oak-planks"
    assert best("Marble_Carrara", "#ededec") == "carrara"
    assert best("Wood_Walnut") in ("walnut-veneer", "walnut-planks")
    assert best("Metal_Brushed", "#cbcbcb") == "steel"
    # tintable materials keep the designer's colour
    assert best("Fabric_Grey", "#8a8a8a") == "linen#8a8a8a"
    assert best("BlackLeather", "#222222") == "leather#222222"


def test_object_hint_and_no_guessing():
    # a generic SketchUp colour on a sofa becomes fabric in that colour
    assert best("[Color M07]", "#a0a2a6", ("sofa",)) == "linen#a0a2a6"
    # a generic colour with nothing to go on is left as the SketchUp original
    assert best("Color_A01", "#ff0000") is None


def test_search_and_values():
    assert {e.id for e in L.search("marble")} == {"carrara", "nero-marble"}
    assert all(e.category == "metal" for e in L.search(category="metal"))
    e, tint = L.get("velvet#2e3d5a")
    assert e.id == "velvet" and tint == "#2e3d5a"
    assert L.name("velvet#2e3d5a") == "Velvet (#2e3d5a)"


def test_load_downloaded_scans(tmp_path):
    d = tmp_path / "oak_veneer_01"
    d.mkdir()
    (d / "entry.json").write_text(json.dumps({"id": "ph-oak_veneer_01", "name": "Oak Veneer 01", "category": "wood",
                                              "color": "#a87f55", "tags": ["oak", "veneer"],
                                              "maps": {"color": "diff.jpg", "rough": "rough.jpg"}}))
    lib = LIB.Library()
    assert lib.load_dir(str(tmp_path)) == 1
    e = lib.entries["ph-oak_veneer_01"]
    assert e.recipe == "scan" and e.maps["color"].endswith("diff.jpg") and e.source == "Poly Haven"
    # a real scan wins a tie with the built-in procedural version
    assert lib.auto({"slot": "Oak_Veneer"})["value"] == "ph-oak_veneer_01"


H, W = 40, 60
MATS = [{"slot": "Fabric_Grey", "index": 1, "color": "#8a8a8a", "texture": None, "objects": ["sofa"]},
        {"slot": "Wood_Floor_Oak", "index": 2, "color": "#b3906c", "texture": None, "objects": ["floor"]},
        {"slot": "Color_A01", "index": 3, "color": "#ff0000", "texture": None, "objects": ["side"]}]
SHADE = {None: 5}


def model_renderer():
    """Sofa fabric on one block, oak floor on another, a red wall elsewhere.
    The pixel value encodes which library material each slot got."""
    calls = []

    def render(state, exposure=None, wb=None):
        calls.append(state)
        idx = np.full((H, W), SEMANTIC["side"], np.int32)
        mi = np.full((H, W), 3, np.int32)
        idx[10:20, 10:30], mi[10:20, 10:30] = SEMANTIC["sofa"], 1
        idx[25:40, :], mi[25:40, :] = SEMANTIC["floor"], 2
        img = np.full((H, W, 3), 100, np.uint8)
        for m in MATS:
            v = state.get("mat:" + m["slot"])
            img[mi == m["index"]] = 5 + (sum(map(ord, v)) % 200 if v else 0)
        return S.Shot(img, idx, 1.0, [1, 1, 1], None, mi, MATS)
    render.calls = calls
    render.inspect = lambda: MATS
    return render


def test_auto_match_goes_into_the_base():
    p = S.Project("p", model_renderer())
    p.compose()
    assert p.auto_materials == {"mat:Fabric_Grey": "linen#8a8a8a", "mat:Wood_Floor_Oak": "oak-planks"}
    assert p.renderer.calls[0]["mat:Fabric_Grey"] == "linen#8a8a8a"
    view = {m["slot"]: m for m in p.to_json()["materials"]}
    assert view["Color_A01"]["current_name"] == "SketchUp original" and view["Wood_Floor_Oak"]["auto"]


def test_material_swap_changes_only_that_material():
    p = S.Project("p", model_renderer())
    before = p.compose()["image"]
    p.add_layer("mat:Fabric_Grey", "Fabric_Grey: Velvet", {"mat:Fabric_Grey": "velvet#2e3d5a"})
    out = p.compose()
    sofa = out["matindex"] == 1
    assert not (out["image"][sofa] == before[sofa]).all()
    assert out["outside_identical"]
    assert (out["image"][~out["edited"]] == before[~out["edited"]]).all()
    # the floor and wall pixels away from the sofa are untouched
    assert (out["image"][30:, :] == before[30:, :]).all()


def test_locked_material_cannot_change():
    p = S.Project("p", model_renderer())
    p.set_lock("mat:Fabric_Grey", True)
    try:
        p.add_layer("mat:Fabric_Grey", "x", {"mat:Fabric_Grey": "velvet"})
        assert False
    except S.Locked:
        pass


def test_pick_returns_material_and_suggestions():
    p = S.Project("p", model_renderer())
    out = p.compose()
    r = p.pick(out["index"], 20 / W, 15 / H, out["matindex"], out["materials"])
    m = r["material"]
    assert m["slot"] == "Fabric_Grey" and m["current"] == "linen#8a8a8a"
    assert m["suggestions"][0]["value"].startswith("linen") and m["suggestions"][0]["color"] == "#8a8a8a"


def test_library_api():
    c = TestClient(server.app)
    r = c.get("/api/library", params={"q": "oak"}).json()
    assert "wood" in r["categories"] and {"oak-planks", "oak-veneer"} <= {i["id"] for i in r["items"]}
