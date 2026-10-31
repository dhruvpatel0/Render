# AI Render: render core (Phase 1)

Upload a SketchUp model, get a photoreal render, and change one thing without anything else moving.

This repo is the first piece: the **render core**. The 3D scene is the source of truth. Every image is a
path-traced render of that scene plus exact helper passes, so later edits, including the AI finish, can be
confined to one object.

## What works today

- **Scene:** a sample 5 m x 5 m living room, or an imported SketchUp export (`.fbx` or `.glb`). Every object gets a
  semantic key (`sofa`, `floor`, `rug`, ...) and an object index.
- **Materials:** procedural PBR finishes (oak and walnut planks, linen, wool, walnut, travertine, plaster, brass, glass).
- **Light:** physical sky + sun per moment (Morning, Midday, Golden hour, Dusk, Night); pendant, LED cove and
  downlights with colour temperature in Kelvin.
- **Render:** Blender Cycles, fixed seed, denoised; deterministic tone mapping with fixed exposure and white balance.
- **Passes:** depth, normals, object IDs, one mask PNG per object.
- **Edits:** scene-first. Change the material in the scene, re-render, then composite only the object's region.
  Outside the region the result is byte-identical to the approved image, and the verifier checks it.

## Run it

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m ai_render.demo --out demo_out            # full size, ~15 min on 4 CPU cores
python -m ai_render.demo --out demo_out --fast     # preview size, ~2 min
python -m ai_render.demo --out demo_out --model my_room.fbx
python -m ai_render.report demo_out                # writes demo_out/index.html
pytest -q
```

## Layout

| File | What it does |
| --- | --- |
| `ai_render/scene.py` | Sample room, SketchUp import, semantic tags, scene-first `set_finish` |
| `ai_render/materials.py` | Procedural PBR materials and the finish catalog |
| `ai_render/lighting.py` | Sky, sun and interior fixtures per moment |
| `ai_render/render.py` | Cycles setup, multilayer EXR read, passes, tone mapping |
| `ai_render/edit.py` | Edit region, masked composite, drift verifier |
| `ai_render/demo.py` | End-to-end proof: approved image, sofa edit, dusk and night |

## Next

1. AI finish: geometry-locked diffusion (depth + edge control, masked inpainting) on top of the path-traced base.
   Needs network access to an image model provider and an API key, or a GPU host.
2. GPU rendering (CUDA/OptiX) for seconds-per-image instead of minutes.
3. Real SketchUp scenes: better automatic labelling of objects and materials.

## Proof renders

Full-size output of `python -m ai_render.demo` (1280×800, 64 samples, 4 CPU cores) is in [`docs/proof/`](docs/proof/).
Changing the sofa to terracotta left 0.00% of pixels outside the sofa changed; a plain full re-render changed 67%
of them slightly (bounce light and denoiser noise).

| Approved | Masked edit | Changed pixels |
| --- | --- | --- |
| ![](docs/proof/before.png) | ![](docs/proof/after_masked_edit.png) | ![](docs/proof/diff_masked_edit.png) |
