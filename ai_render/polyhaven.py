"""Download photo-scanned materials from Poly Haven (CC0, free for commercial use)
into the local library folder.

    python -m ai_render.polyhaven --search oak
    python -m ai_render.polyhaven --get <asset id> [--res 2k]
    python -m ai_render.polyhaven --starter          # the most used scans per category

Each scan lands in LIBRARY_DIR/<id>/ with its maps and an entry.json that
library.Library.load_dir() reads.
"""
import argparse
import io
import json
import os
import urllib.request

from . import library as LIB

API = "https://api.polyhaven.com"
UA = {"User-Agent": "ai-render/0.1 (material library)"}
MAPS = {"color": ["Diffuse", "diff"], "rough": ["Rough", "rough"], "normal": ["nor_gl"], "disp": ["Displacement", "disp"]}


def _get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def _fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def category_of(asset):
    words = [w for t in list(asset.get("categories", [])) + list(asset.get("tags", [])) for w in LIB.tokens(t)]
    words += LIB.tokens(asset.get("name", ""))
    cats = [LIB._WORD_CAT[w] for w in words if w in LIB._WORD_CAT]
    return cats[0] if cats else None


def catalog(get=_get_json):
    """{id: asset} for every texture on Poly Haven."""
    return get(f"{API}/assets?t=textures")


def search(q, get=_get_json, limit=20):
    words = LIB.tokens(q)
    hits = []
    for aid, a in catalog(get).items():
        hay = set(LIB.tokens(aid + " " + a.get("name", ""))) | {w for t in a.get("tags", []) + a.get("categories", []) for w in LIB.tokens(t)}
        if all(any(h.startswith(w) for h in hay) for w in words):
            hits.append((a.get("download_count", 0), aid, a.get("name", aid)))
    return [(aid, name) for _, aid, name in sorted(hits, reverse=True)[:limit]]


def _pick_file(files, keys, res):
    for k in keys:
        by_res = files.get(k) or {}
        f = by_res.get(res) or next(iter(by_res.values()), None)
        if f:
            for fmt in ("jpg", "png"):
                if fmt in f:
                    return f[fmt]["url"], fmt
    return None, None


def _mean_hex(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB").resize((1, 1), Image.Resampling.BOX)
    return "#%02x%02x%02x" % im.getpixel((0, 0))


def download(aid, root=None, res="1k", get=_get_json, fetch=_fetch):
    """Download one scan; returns its entry.json dict. Skips work already done."""
    root = root or LIB.LIBRARY_DIR
    d = os.path.join(root, aid)
    p = os.path.join(d, "entry.json")
    if os.path.exists(p):
        return json.load(open(p))
    info = get(f"{API}/info/{aid}")
    files = get(f"{API}/files/{aid}")
    os.makedirs(d, exist_ok=True)
    maps, color = {}, "#808080"
    for key, names in MAPS.items():
        url, fmt = _pick_file(files, names, res)
        if not url:
            continue
        data = fetch(url)
        fn = f"{key}.{fmt}"
        open(os.path.join(d, fn), "wb").write(data)
        maps[key] = fn
        if key == "color":
            color = _mean_hex(data)
    if "color" not in maps:
        raise RuntimeError(f"{aid}: no colour map found")
    dims = info.get("dimensions") or [1000, 1000]  # millimetres
    entry = {"id": "ph-" + aid, "name": info.get("name", aid), "category": category_of(info) or "other",
             "color": color, "tags": sorted({w for t in info.get("tags", []) + info.get("categories", []) for w in LIB.tokens(t)}),
             "maps": maps, "size_m": max(dims) / 1000, "source": "Poly Haven", "license": "CC0",
             "url": f"https://polyhaven.com/a/{aid}"}
    json.dump(entry, open(p, "w"), indent=1)
    return entry


def starter(per_category=3, root=None, res="1k", get=_get_json, fetch=_fetch):
    """The most downloaded scans for each library category."""
    by_cat = {}
    for aid, a in catalog(get).items():
        c = category_of(a)
        if c and c != "glass":
            by_cat.setdefault(c, []).append((a.get("download_count", 0), aid))
    out = []
    for c, items in sorted(by_cat.items()):
        for _, aid in sorted(items, reverse=True)[:per_category]:
            out.append(download(aid, root, res, get, fetch))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search")
    ap.add_argument("--get")
    ap.add_argument("--starter", action="store_true")
    ap.add_argument("--res", default="1k")
    a = ap.parse_args()
    if a.search:
        for aid, name in search(a.search):
            print(aid, "-", name)
    if a.get:
        print(json.dumps(download(a.get, res=a.res), indent=1))
    if a.starter:
        for e in starter(res=a.res):
            print(e["id"], e["category"], e["name"])


if __name__ == "__main__":
    main()
