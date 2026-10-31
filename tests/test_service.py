import numpy as np
import pytest

from ai_render import service as S
from ai_render.scene import SEMANTIC

H, W = 40, 60
COLORS = {"Linen grey": 10, "Terracotta": 20, "Forest": 30, "Ivory": 40, "Sage": 50}


def fake_renderer():
    """Sofa occupies a block, rug another. Pixel values encode the finish, and
    the moment shifts every pixel, like a global relight would."""
    calls = []

    def render(state, exposure=None, wb=None):
        calls.append(state)
        idx = np.full((H, W), SEMANTIC["side"], np.int32)
        idx[10:20, 10:30] = SEMANTIC["sofa"]
        idx[25:35, 5:55] = SEMANTIC["rug"]
        g = 100 if state["moment"] == "Golden hour" else 60
        img = np.full((H, W, 3), g, np.uint8)
        img[idx == SEMANTIC["sofa"]] = COLORS[state["sofa"]]
        img[idx == SEMANTIC["rug"]] = COLORS[state["rug"]]
        # a little "bounce light" noise everywhere that depends on the sofa colour
        img[0, 0] = COLORS[state["sofa"]] + 1
        return S.Shot(img, idx, 1.0, [1, 1, 1])
    render.calls = calls
    return render


def test_finish_edit_changes_only_that_object():
    p = S.Project("p", fake_renderer())
    before = p.compose()["image"]
    p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})
    out = p.compose()
    sofa = out["index"] == SEMANTIC["sofa"]
    assert (out["image"][sofa] == 30).all()
    assert out["outside_identical"]
    assert (out["image"][~out["edited"]] == before[~out["edited"]]).all()
    assert out["image"][0, 0, 0] == before[0, 0, 0]  # bounce change outside the sofa was not taken


def test_toggle_layer_off_restores_original():
    p = S.Project("p", fake_renderer())
    before = p.compose()["image"]
    layer = p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})
    p.set_layer(layer.id, False)
    assert (p.compose()["image"] == before).all()


def test_moment_is_global_and_finishes_stay():
    p = S.Project("p", fake_renderer())
    p.add_layer("sofa:finish", "Sofa: Terracotta", {"sofa": "Terracotta"})
    p.add_layer("moment", "Moment: Night", {"moment": "Night"})
    out = p.compose()
    assert (out["image"][out["index"] == SEMANTIC["side"]][1:] == 60).all()
    assert (out["image"][out["index"] == SEMANTIC["sofa"]] == 20).all()


def test_locked_object_rejects_edits():
    p = S.Project("p", fake_renderer())
    p.set_lock("sofa", True)
    with pytest.raises(S.Locked):
        p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})


def test_repeated_edit_replaces_last_layer():
    p = S.Project("p", fake_renderer())
    p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})
    p.add_layer("sofa:finish", "Sofa: Terracotta", {"sofa": "Terracotta"})
    assert len(p.layers) == 1 and p.current_state()["sofa"] == "Terracotta"


def test_two_finish_layers_compose():
    p = S.Project("p", fake_renderer())
    p.add_layer("sofa:finish", "Sofa: Forest", {"sofa": "Forest"})
    p.add_layer("rug:finish", "Rug: Sage", {"rug": "Sage"})
    out = p.compose()
    assert (out["image"][out["index"] == SEMANTIC["sofa"]] == 30).all()
    assert (out["image"][out["index"] == SEMANTIC["rug"]] == 50).all()


def test_pick_returns_finishes():
    p = S.Project("p", fake_renderer())
    idx = p.compose()["index"]
    r = p.pick(idx, 20 / W, 15 / H)
    assert r["object"] == "sofa" and "Forest" in r["finishes"]


def test_parse_intent():
    edits = S.parse_intent("switch to night, make the sofa forest green and a travertine floor")
    keys = {e[0] for e in edits}
    assert {"moment", "sofa:finish", "floor:finish"} <= keys
    assert S.parse_intent("blue sofa")[0][2] == {"sofa": "Ink blue"}
