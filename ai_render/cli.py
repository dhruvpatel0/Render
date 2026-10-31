"""Render one state in a fresh process. The web service calls this so Blender
always starts clean and a crash cannot take the server down.

    python -m ai_render.cli --state '{"sofa": "Forest"}' --out DIR [--model F] [--quality preview|final]
                            [--exposure X --wb R,G,B]
"""
import argparse
import json
import os

import numpy as np

from . import pipeline as P, render as R, lighting as L

QUALITY = {"preview": dict(width=960, height=600, samples=32),
           "final": dict(width=1920, height=1200, samples=96)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model")
    ap.add_argument("--quality", default="preview", choices=QUALITY)
    ap.add_argument("--exposure", type=float)
    ap.add_argument("--wb")
    ap.add_argument("--inspect", action="store_true", help="only list the scene materials, no render")
    a = ap.parse_args()
    state = {**P.DEFAULT, **json.loads(a.state)}
    mats = P.build(state, a.model, QUALITY[a.quality])
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "materials.json"), "w") as f:
        json.dump(mats, f)
    if a.inspect:
        return
    mo = L.MOMENTS[state["moment"]]
    wb = np.array([float(x) for x in a.wb.split(",")], np.float32) if a.wb else None
    r = R.render(a.out, "image", exposure=a.exposure, wb=wb, passes=False, key=mo["key"], wb_strength=mo["wb"])
    np.save(os.path.join(a.out, "index.npy"), r["index"].astype(np.uint8))
    np.save(os.path.join(a.out, "depth.npy"), r["depth"].astype(np.float16))
    np.save(os.path.join(a.out, "matindex.npy"), r["matindex"].astype(np.uint16))
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump({"exposure": r["exposure"], "wb": [float(x) for x in r["wb"]], "state": state}, f)


if __name__ == "__main__":
    main()
