import time

from fastapi.testclient import TestClient

from ai_render import server, service
from tests.test_service import fake_renderer


def test_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DATA", str(tmp_path))
    monkeypatch.setattr(service, "subprocess_renderer", lambda *a, **k: fake_renderer())
    monkeypatch.setattr(server.S, "subprocess_renderer", lambda *a, **k: fake_renderer())
    c = TestClient(server.app)
    p = c.post("/api/projects").json()

    def wait():
        for _ in range(100):
            v = c.get(f"/api/projects/{p['id']}").json()
            if v["status"] != "rendering":
                return v
            time.sleep(0.02)
    assert wait()["status"] == "ready"
    pick = c.get(f"/api/projects/{p['id']}/pick", params={"x": 20 / 60, "y": 15 / 40}).json()
    assert pick["object"] == "sofa"
    c.post(f"/api/projects/{p['id']}/locks", json={"object": "sofa", "locked": True})
    r = c.post(f"/api/projects/{p['id']}/layers", json={"key": "sofa:finish", "label": "Sofa: Forest", "set": {"sofa": "Forest"}})
    assert r.status_code == 409
    c.post(f"/api/projects/{p['id']}/locks", json={"object": "sofa", "locked": False})
    r = c.post(f"/api/projects/{p['id']}/intent", json={"text": "make the sofa forest green"}).json()
    assert r["applied"] == ["Sofa: Forest"]
    v = wait()
    assert v["state"]["sofa"] == "Forest" and v["outside_identical"]
    assert c.get(v["image"]).status_code == 200
    assert c.post("/api/projects", files={"model": ("room.skp", b"x")}).status_code == 400
