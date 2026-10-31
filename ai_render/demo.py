"""Phase 1 proof: real path-traced renders, exact passes, and a scene-first
masked edit that leaves every pixel outside the edited object untouched.

    python -m ai_render.demo --out demo_out [--model room.fbx] [--fast]
"""
import argparse
import json
import os
import time

import numpy as np
from PIL import Image

from . import pipeline as P, render as R, edit as E, scene as S, lighting as L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo_out")
    ap.add_argument("--model", default=None, help="SketchUp export (.fbx or .glb)")
    ap.add_argument("--fast", action="store_true", help="small preview renders")
    a = ap.parse_args()
    q = dict(width=640, height=400, samples=32) if a.fast else dict(width=1280, height=800, samples=64)
    os.makedirs(a.out, exist_ok=True)
    log = {"quality": q, "steps": []}

    def step(name, t0, **kw):
        log["steps"].append({"step": name, "seconds": round(time.time() - t0, 1), **kw})
        print(f"[demo] {name}: {time.time() - t0:.1f}s {kw}", flush=True)

    # 1. Approved image + passes
    state = dict(P.DEFAULT)
    t = time.time()
    P.build(state, a.model, q)
    mo = L.MOMENTS[state["moment"]]
    before = R.render(a.out, "before", key=mo["key"], wb_strength=mo["wb"])
    step("approved render + passes", t, exposure=round(before["exposure"], 4))

    # 2. Scene-first edit: change the sofa's material in the 3D scene, re-render
    t = time.time()
    S.set_finish("sofa", "Terracotta")
    after_raw = R.render(a.out, "after_full_rerender", exposure=before["exposure"], wb=before["wb"], passes=False)
    region = E.edit_region(before["index"], after_raw["index"], "sofa")
    result = E.composite(before["image"], after_raw["image"], region)
    Image.fromarray(result).save(os.path.join(a.out, "after_masked_edit.png"))
    Image.fromarray((region * 255).astype(np.uint8)).save(os.path.join(a.out, "edit_region.png"))
    d_raw, _ = E.drift(before["image"], after_raw["image"], region)
    d_ours, _ = E.drift(before["image"], result, region)
    exact = bool((result[~region] == before["image"][~region]).all())
    Image.fromarray(E.diff_image(before["image"], after_raw["image"], region)).save(os.path.join(a.out, "diff_full_rerender.png"))
    Image.fromarray(E.diff_image(before["image"], result, region)).save(os.path.join(a.out, "diff_masked_edit.png"))
    step("sofa -> terracotta", t, region_share=round(float(region.mean()), 4),
         changed_outside_full_rerender=round(d_raw, 5), changed_outside_masked=round(d_ours, 5),
         outside_pixels_byte_identical=exact)

    # 3. Moments: same scene, different time of day and lights
    for moment in ("Dusk", "Night"):
        t = time.time()
        st = dict(state, moment=moment)
        P.build(st, a.model, q)
        mo = L.MOMENTS[moment]
        R.render(a.out, f"moment_{moment.lower()}", passes=False, key=mo["key"], wb_strength=mo["wb"])
        step(f"moment {moment}", t)

    with open(os.path.join(a.out, "results.json"), "w") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    main()
