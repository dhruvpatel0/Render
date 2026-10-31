"""Write a one-page HTML report next to the demo renders."""
import json
import os
import sys

TPL = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Render core proof</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:24px 16px;background:#f4f5f4;color:#16191a}}
h1{{font-size:1.8rem;margin:.2em 0}}h2{{margin-top:2em}}img{{width:100%;border-radius:4px;display:block}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.g3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
figcaption{{font-size:.85rem;color:#5b6264;margin:.3em 0 1em}}code{{background:#e6e8e7;padding:1px 5px;border-radius:3px}}
td,th{{padding:6px 10px;border-bottom:1px solid #d4d8d7;text-align:left}}@media(max-width:700px){{.g2,.g3{{grid-template-columns:1fr}}}}</style>
<h1>Render core proof: change the sofa, nothing else moves</h1>
<p>Path-traced in Blender Cycles on CPU ({w}×{h}, {spp} samples + denoise). No AI step yet: this proves the geometry, light and masking layer that the AI finish will sit on.</p>
<h2>1. Approved image and its exact passes</h2>
<figure><img src="before.png"><figcaption>Approved render, golden hour, 3000 K pendant and LED cove.</figcaption></figure>
<div class="g3"><figure><img src="before_depth.png"><figcaption>Depth</figcaption></figure>
<figure><img src="before_normal.png"><figcaption>Surface normals</figcaption></figure>
<figure><img src="before_ids.png"><figcaption>Object IDs (masks in <code>masks/</code>)</figcaption></figure></div>
<h2>2. "Make the sofa terracotta"</h2>
<p>The material is changed in the 3D scene, the room is re-rendered, and only the sofa's region is taken from the new render.</p>
<div class="g2"><figure><img src="after_masked_edit.png"><figcaption>Result of the masked edit</figcaption></figure>
<figure><img src="diff_masked_edit.png"><figcaption>Changed pixels: green inside the sofa region, red outside. There is no red.</figcaption></figure>
<figure><img src="after_full_rerender.png"><figcaption>Plain full re-render, for comparison</figcaption></figure>
<figure><img src="diff_full_rerender.png"><figcaption>Even a physically correct re-render shifts pixels everywhere (bounce light and denoiser noise). Red = changed outside the sofa.</figcaption></figure></div>
<table><tr><th>Measure</th><th>Value</th></tr>
<tr><td>Edit region (share of image)</td><td>{region:.1%}</td></tr>
<tr><td>Pixels changed outside region, full re-render</td><td>{raw:.1%}</td></tr>
<tr><td>Pixels changed outside region, masked edit</td><td>{ours:.2%}</td></tr>
<tr><td>Outside pixels byte-identical to approved image</td><td>{exact}</td></tr></table>
<h2>3. Same scene, different moment</h2>
<div class="g2"><figure><img src="moment_dusk.png"><figcaption>Dusk: sky light fades, downlights switch on.</figcaption></figure>
<figure><img src="moment_night.png"><figcaption>Night: only the interior fixtures light the room.</figcaption></figure></div>
<h2>Timings (4 CPU cores, no GPU)</h2>
<table><tr><th>Step</th><th>Seconds</th></tr>{rows}</table>
<p>On a cloud GPU the same renders are expected to take a few seconds each.</p>
"""


def write(out):
    r = json.load(open(os.path.join(out, "results.json")))
    edit = next(s for s in r["steps"] if s["step"].startswith("sofa"))
    rows = "".join(f"<tr><td>{s['step']}</td><td>{s['seconds']}</td></tr>" for s in r["steps"])
    html = TPL.format(w=r["quality"]["width"], h=r["quality"]["height"], spp=r["quality"]["samples"],
                      region=edit["region_share"], raw=edit["changed_outside_full_rerender"],
                      ours=edit["changed_outside_masked"], exact="Yes" if edit["outside_pixels_byte_identical"] else "No",
                      rows=rows)
    open(os.path.join(out, "index.html"), "w").write(html)


if __name__ == "__main__":
    write(sys.argv[1])
