from __future__ import annotations

from typing import Any

from emf_core.scene.models import Scene
from emf_core.solvers import SolveRequest


def charge(oid: str, q: float, pos: tuple[float, float, float], **extra: Any) -> dict[str, Any]:
    return {"id": oid, "primitive": {"type": "point"}, "role": "charge_source",
            "source": {"type": "point_charge", "charge_C": q},
            "transform": {"position_m": pos}, **extra}


def scene_of(*objects: dict[str, Any], **extra: Any) -> Scene:
    return Scene.model_validate({"objects": list(objects), **extra})


def points_request(points: list[tuple[float, float, float]], *quantities: str) -> SolveRequest:
    return SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": points}],
        "quantities": list(quantities) or ["E", "phi"],
    })


def wire(oid: str, current: float, pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
         rot: tuple[float, float, float] = (0.0, 0.0, 0.0), **extra: Any) -> dict[str, Any]:
    """Infinite straight wire through pos along the world image of local +z (rotation rot)."""
    return {"id": oid, "primitive": {"type": "line"}, "role": "current_source",
            "source": {"type": "infinite_wire", "current_A": current},
            "transform": {"position_m": pos, "rotation_euler_xyz_rad": rot}, **extra}


def loop(oid: str, current: float, radius: float, pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
         rot: tuple[float, float, float] = (0.0, 0.0, 0.0), **extra: Any) -> dict[str, Any]:
    """Circular loop centred at pos, normal = world image of local +z (rotation rot)."""
    return {"id": oid, "primitive": {"type": "ring", "radius_m": radius}, "role": "current_source",
            "source": {"type": "circular_loop", "current_A": current},
            "transform": {"position_m": pos, "rotation_euler_xyz_rad": rot}, **extra}
