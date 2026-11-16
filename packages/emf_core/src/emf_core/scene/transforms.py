"""World transforms for the object hierarchy (float64, column-vector convention)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .models import Scene, SceneObject, Transform

Mat4 = NDArray[np.float64]


def rotation_matrix_xyz(angles_rad: tuple[float, float, float]) -> NDArray[np.float64]:
    """R = Rx(a) @ Ry(b) @ Rz(c) — identical to Three.js Euler order 'XYZ'."""
    a, b, c = angles_rad
    ca, sa, cb, sb, cc, sc = np.cos(a), np.sin(a), np.cos(b), np.sin(b), np.cos(c), np.sin(c)
    rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], dtype=np.float64)
    ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]], dtype=np.float64)
    rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]], dtype=np.float64)
    return rx @ ry @ rz


def local_matrix(t: Transform) -> Mat4:
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = rotation_matrix_xyz(t.rotation_euler_xyz_rad) * np.asarray(t.scale, np.float64)
    m[:3, 3] = t.position_m
    return m


def world_matrix(scene: Scene, obj: SceneObject) -> Mat4:
    by_id = {o.id: o for o in scene.objects}
    m = local_matrix(obj.transform)
    cur = obj
    while cur.parent_id is not None:
        cur = by_id[cur.parent_id]
        m = local_matrix(cur.transform) @ m
    return m


def world_position(scene: Scene, obj: SceneObject) -> NDArray[np.float64]:
    return world_matrix(scene, obj)[:3, 3].copy()
