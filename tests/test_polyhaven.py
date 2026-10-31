import io
import json

from PIL import Image

from ai_render import library as LIB
from ai_render import polyhaven as PH

ASSETS = {"oak_veneer_01": {"name": "Oak Veneer 01", "categories": ["wood"], "tags": ["oak", "veneer"], "download_count": 900},
          "marble_01": {"name": "Marble 01", "categories": ["rock"], "tags": ["marble", "white"], "download_count": 500},
          "rusty_metal": {"name": "Rusty Metal", "categories": ["metal"], "tags": ["rust"], "download_count": 10}}


def jpg(rgb):
    b = io.BytesIO()
    Image.new("RGB", (8, 8), rgb).save(b, "JPEG")
    return b.getvalue()


def fake_get(url):
    if url.endswith("/assets?t=textures"):
        return ASSETS
    aid = url.rsplit("/", 1)[1]
    if "/info/" in url:
        return {**ASSETS[aid], "dimensions": [2000, 2000]}
    base = f"https://dl.example/{aid}"
    return {"Diffuse": {"1k": {"jpg": {"url": base + "_diff.jpg"}}},
            "Rough": {"1k": {"jpg": {"url": base + "_rough.jpg"}}},
            "nor_gl": {"1k": {"jpg": {"url": base + "_nor.jpg"}, "exr": {"url": base + "_nor.exr"}}},
            "Displacement": {"1k": {"png": {"url": base + "_disp.png"}}}}


fetched = []


def fake_fetch(url):
    fetched.append(url)
    return jpg((168, 127, 85))


def test_search():
    assert PH.search("oak", fake_get) == [("oak_veneer_01", "Oak Veneer 01")]


def test_download_writes_entry_the_library_reads(tmp_path):
    e = PH.download("oak_veneer_01", str(tmp_path), get=fake_get, fetch=fake_fetch)
    assert e["category"] == "wood" and e["size_m"] == 2.0 and e["license"] == "CC0"
    assert set(e["maps"]) == {"color", "rough", "normal", "disp"} and e["maps"]["disp"] == "disp.png"
    assert LIB.color_distance(e["color"], "#a87f55") < 5
    n = len(fetched)
    PH.download("oak_veneer_01", str(tmp_path), get=fake_get, fetch=fake_fetch)
    assert len(fetched) == n  # already downloaded: nothing fetched again
    lib = LIB.Library()
    lib.load_dir(str(tmp_path))
    assert lib.entries["ph-oak_veneer_01"].maps["color"].endswith("color.jpg")


def test_starter_picks_top_scans_per_category(tmp_path):
    got = PH.starter(1, str(tmp_path), get=fake_get, fetch=fake_fetch)
    assert {e["category"] for e in got} == {"wood", "stone", "metal"}
    assert json.load(open(tmp_path / "marble_01" / "entry.json"))["category"] == "stone"
