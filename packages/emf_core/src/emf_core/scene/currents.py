"""World geometry of current sources (Phase 3A), shared by every solver.

A well-formed current source is an enabled object with role ``current_source`` and either

* an ``infinite_wire`` source on a ``line`` primitive, or
* a ``circular_loop`` source on a ``ring`` primitive whose world transform is a similarity in
  the ring's own plane (otherwise the ring would be an ellipse, which is not modelled).

Anything else with role ``current_source`` is reported as a problem, never approximated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..i18n import L, LocalizedText
from .models import (
    CircularLoopSource,
    InfiniteWireSource,
    LinePrimitive,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
)
from .transforms import world_matrix

Arr = NDArray[np.float64]
# Relative tolerance for "the in-plane scale is uniform and the in-plane axes are orthogonal".
SIMILARITY_RTOL = 1e-9


@dataclass(frozen=True)
class WireSource:
    object_id: str
    current_A: float
    point_m: Arr  # a point on the axis (world)
    direction: Arr  # unit vector; positive current flows along it


@dataclass(frozen=True)
class LoopSource:
    object_id: str
    current_A: float
    center_m: Arr
    normal: Arr  # unit vector; positive current circulates counter-clockwise about it
    radius_m: float
    u: Arr  # unit vector in the loop plane (world image of local +x); v = normal x u


@dataclass
class CurrentSources:
    wires: list[WireSource]
    loops: list[LoopSource]
    problems: list[LocalizedText]

    @property
    def ids(self) -> list[str]:
        return [w.object_id for w in self.wires] + [lp.object_id for lp in self.loops]

    @property
    def count(self) -> int:
        return len(self.wires) + len(self.loops)


def enabled(scene: Scene, obj: SceneObject) -> bool:
    """An object contributes only if it and all of its ancestors are enabled."""
    by_id = {o.id: o for o in scene.objects}
    cur = obj
    while True:
        if not cur.enabled:
            return False
        if cur.parent_id is None:
            return True
        cur = by_id[cur.parent_id]


def is_current_object(o: SceneObject) -> bool:
    return o.role is Role.CURRENT_SOURCE


def _unit(v: Arr) -> Arr | None:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 and np.isfinite(n) else None


def current_sources(scene: Scene) -> CurrentSources:
    out = CurrentSources(wires=[], loops=[], problems=[])
    for o in scene.objects:
        if not is_current_object(o) or not enabled(scene, o):
            continue
        label = o.name or o.id
        m = world_matrix(scene, o)
        lin, pos = m[:3, :3], m[:3, 3].copy()
        if isinstance(o.source, InfiniteWireSource) and isinstance(o.primitive, LinePrimitive):
            d = _unit(lin @ np.array([0.0, 0.0, 1.0]))
            if d is None:
                out.problems.append(L(f"Wire '{label}' has a degenerate direction.",
                                      f"A(z) '{label}' vezeték iránya elfajult."))
                continue
            out.wires.append(WireSource(o.id, float(o.source.current_A), pos, d))
        elif isinstance(o.source, CircularLoopSource) and isinstance(o.primitive, RingPrimitive):
            cx, cy = lin[:, 0], lin[:, 1]
            sx, sy = float(np.linalg.norm(cx)), float(np.linalg.norm(cy))
            if (abs(sx - sy) > SIMILARITY_RTOL * max(sx, sy)
                    or abs(float(cx @ cy)) > SIMILARITY_RTOL * sx * sy):
                out.problems.append(L(
                    f"Loop '{label}' is scaled non-uniformly in its own plane, which would make it "
                    "an ellipse. Only circular loops are modelled; use the radius instead.",
                    f"A(z) '{label}' hurok saját síkjában nem egyenletesen van skálázva, így "
                    "ellipszis lenne. Csak kör alakú hurok modellezhető; a sugarat módosítsa."))
                continue
            n = _unit(np.cross(cx, cy))
            assert n is not None
            out.loops.append(LoopSource(o.id, float(o.source.current_A), pos, n,
                                        float(o.primitive.radius_m) * sx, cx / sx))
        else:
            out.problems.append(L(
                f"Object '{label}' has role 'current_source' but is not a supported current "
                "source. Supported: an infinite straight wire (a line with an 'infinite_wire' "
                "source) and a circular loop (a ring with a 'circular_loop' source). Nothing is "
                "approximated by a simpler model.",
                f"A(z) '{label}' objektum szerepe 'current_source', de nem támogatott áramforrás. "
                "Támogatott: végtelen egyenes vezeték (vonal 'infinite_wire' forrással) és "
                "körvezető (gyűrű 'circular_loop' forrással). Egyszerűbb modellel nem "
                "helyettesítjük."))
    return out
