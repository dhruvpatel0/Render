"""AI Render: render core prototype (Phase 1).

The 3D scene is the source of truth. Every image is a path-traced render of
that scene plus exact helper passes (depth, normals, object masks), so later
edits can be confined to one object.
"""
