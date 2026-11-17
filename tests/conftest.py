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


def solenoid(oid: str = "s", current: float = 1.0, radius: float = 0.04, length: float = 0.2,
             turns: int = 20, pos: Any = (0, 0, 0), rot: Any = (0, 0, 0)) -> dict[str, Any]:
    """Finite discrete-turn solenoid along local +z."""
    return {"id": oid, "primitive": {"type": "coil", "radius_m": radius, "length_m": length,
                                     "turns": turns}, "role": "current_source",
            "source": {"type": "solenoid", "current_A": current},
            "transform": {"position_m": pos, "rotation_euler_xyz_rad": rot}}


def torus(oid: str = "t", model: str = "toroid_finite", current: float = 1.0, major: float = 0.12,
          b_w: float = 0.03, b_c: float = 0.03, turns: int = 24, mu_r: float = 1.0,
          pos: Any = (0, 0, 0), rot: Any = (0, 0, 0)) -> dict[str, Any]:
    """Toroid about local +z; finite-turn or ideal continuous-winding model."""
    src: dict[str, Any] = {"type": model, "current_A": current}
    if model == "toroid_ideal":
        src["relative_permeability"] = mu_r
    return {"id": oid, "primitive": {"type": "torus", "major_radius_m": major,
                                     "winding_radius_m": b_w, "core_radius_m": b_c,
                                     "turns": turns},
            "role": "current_source", "source": src,
            "transform": {"position_m": pos, "rotation_euler_xyz_rad": rot}}


def magnet(oid: str = "m", m: float = 5e5, radius: float = 0.04, length: float = 0.08,
           pos: Any = (0, 0, 0), rot: Any = (0, 0, 0)) -> dict[str, Any]:
    """Uniformly magnetized cylinder, M along local +z."""
    return {"id": oid, "primitive": {"type": "cylinder", "radius_m": radius,
                                     "height_m": length},
            "role": "magnetic_material", "source": {"type": "permanent_magnet",
                                                    "magnetization_A_per_m": m},
            "transform": {"position_m": pos, "rotation_euler_xyz_rad": rot}}
