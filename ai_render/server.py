"""Web app: upload, moment, render, tap-to-edit, edit layers.

    uvicorn ai_render.server:app --port 8000
"""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image
from pydantic import BaseModel

from . import service as S

DATA = os.environ.get("AI_RENDER_DATA", os.path.abspath("data"))
QUALITY = os.environ.get("AI_RENDER_QUALITY", "preview")
WEB = os.path.join(os.path.dirname(__file__), "web")

app = FastAPI(title="AI Render")
_worker = ThreadPoolExecutor(max_workers=1)  # one render at a time on this machine
_projects = {}
_lock = threading.Lock()


class Entry:
    def __init__(self, pid, model_path):
        self.dir = os.path.join(DATA, pid)
        os.makedirs(self.dir, exist_ok=True)
        self.project = S.Project(pid, S.subprocess_renderer(self.dir, model_path, QUALITY))
        self.model = os.path.basename(model_path) if model_path else None
        self.status, self.error, self.version, self.pending = "idle", None, 0, 0
        self.index, self.outside_identical, self.generation = None, True, 0


def _get(pid):
    e = _projects.get(pid)
    if not e:
        raise HTTPException(404, "Project not found")
    return e


def _compose(e, gen):
    try:
        out = e.project.compose()
        if gen != e.generation:
            return  # a newer edit superseded this one
        Image.fromarray(out["image"]).save(os.path.join(e.dir, "current.png"))
        e.index, e.outside_identical = out["index"], out["outside_identical"]
        e.version += 1
        e.status, e.error = "ready", None
    except Exception as ex:  # surfaced to the UI
        e.status, e.error = "error", str(ex)[-500:]


def _kick(e):
    with _lock:
        e.generation += 1
        e.status = "rendering"
        try:
            e.pending = e.project.pending_renders()
        except Exception:
            e.pending = None
        _worker.submit(_compose, e, e.generation)


def _view(e):
    return {**e.project.to_json(), "model": e.model, "status": e.status, "error": e.error,
            "version": e.version, "pending": e.pending, "outside_identical": e.outside_identical,
            "image": f"/api/projects/{e.project.id}/image.png?v={e.version}" if e.version else None}


@app.get("/", response_class=HTMLResponse)
def home():
    return open(os.path.join(WEB, "index.html"), encoding="utf-8").read()


@app.get("/api/catalog")
def catalog():
    return {"finishes": S.SWATCH, "moments": S.MOMENTS, "names": S.NAMES}


@app.post("/api/projects")
async def create(model: UploadFile | None = File(None)):
    pid = uuid.uuid4().hex[:10]
    path = None
    if model and model.filename:
        ext = os.path.splitext(model.filename)[1].lower()
        if ext not in (".fbx", ".glb", ".gltf"):
            raise HTTPException(400, "Export your SketchUp model as .fbx or .glb, then upload that file.")
        os.makedirs(os.path.join(DATA, pid), exist_ok=True)
        path = os.path.join(DATA, pid, "model" + ext)
        with open(path, "wb") as f:
            f.write(await model.read())
    e = _projects[pid] = Entry(pid, path)
    _kick(e)
    return _view(e)


@app.get("/api/projects/{pid}")
def get(pid: str):
    return _view(_get(pid))


@app.get("/api/projects/{pid}/image.png")
def image(pid: str):
    e = _get(pid)
    p = os.path.join(e.dir, "current.png")
    if not os.path.exists(p):
        raise HTTPException(404, "Still rendering")
    return FileResponse(p, media_type="image/png")


class LayerIn(BaseModel):
    key: str
    label: str
    set: dict


@app.post("/api/projects/{pid}/layers")
def add_layer(pid: str, body: LayerIn):
    e = _get(pid)
    try:
        e.project.add_layer(body.key, body.label, body.set)
    except S.Locked as ex:
        raise HTTPException(409, f"{ex}. Unlock it to change it.")
    _kick(e)
    return _view(e)


class Toggle(BaseModel):
    on: bool


@app.patch("/api/projects/{pid}/layers/{lid}")
def toggle(pid: str, lid: str, body: Toggle):
    e = _get(pid)
    try:
        e.project.set_layer(lid, body.on)
    except S.Locked as ex:
        raise HTTPException(409, str(ex))
    except StopIteration:
        raise HTTPException(404, "Layer not found")
    _kick(e)
    return _view(e)


class LockIn(BaseModel):
    object: str
    locked: bool


@app.post("/api/projects/{pid}/locks")
def lock(pid: str, body: LockIn):
    e = _get(pid)
    e.project.set_lock(body.object, body.locked)
    return _view(e)


@app.post("/api/projects/{pid}/reset")
def reset(pid: str):
    e = _get(pid)
    e.project.reset()
    _kick(e)
    return _view(e)


@app.get("/api/projects/{pid}/pick")
def pick(pid: str, x: float, y: float):
    e = _get(pid)
    if e.index is None:
        raise HTTPException(409, "Still rendering")
    return e.project.pick(e.index, x, y)


@app.get("/api/projects/{pid}/mask.png")
def mask(pid: str, object: str):
    """Selection overlay: a soft tint over the object plus a crisp outline."""
    import io
    import numpy as np
    from scipy import ndimage
    from fastapi.responses import Response
    from .scene import SEMANTIC
    e = _get(pid)
    if e.index is None or object not in SEMANTIC:
        raise HTTPException(404, "No mask")
    m = e.index == SEMANTIC[object]
    edge = ndimage.binary_dilation(m, iterations=2) & ~m
    rgba = np.zeros(m.shape + (4,), np.uint8)
    rgba[m] = (255, 106, 61, 46)
    rgba[edge] = (255, 106, 61, 255)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


class IntentIn(BaseModel):
    text: str


@app.post("/api/projects/{pid}/intent")
def intent(pid: str, body: IntentIn):
    e = _get(pid)
    edits = S.parse_intent(body.text)
    done, skipped = [], []
    for key, label, values in edits:
        try:
            e.project.add_layer(key, label, values)
            done.append(label)
        except S.Locked:
            skipped.append(label)
    if done:
        _kick(e)
    return {"applied": done, "skipped_locked": skipped, "understood": bool(edits), "project": _view(e)}
