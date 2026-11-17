"""Time-dependent source currents at an instant (Phase 4A, magnetoquasistatic).

For fixed geometry every current source's field is linear in its current, so

    B(r, t)   = sum_j I_j(t) B_j,unit(r) + B_static(r)
    dB/dt     = sum_j dI_j/dt B_j,unit(r)
    E_ind     = -dA/dt = -sum_j dI_j/dt A_j,unit(r)

``time_state`` evaluates every source's profile at t (analytical derivative, both one-sided
values at a corner), and ``with_currents`` builds the source sets the solver evaluates: the
sources with currents I_j(t) (the instantaneous B), or with currents dI_j/dt and the static
sources (permanent magnets) removed (dB/dt and E_ind). Nothing here computes a field.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .currents import CurrentSources
from .models import Scene, TimeDependentCurrent
from .profiles import Derivative, derivative_at, max_rate

# Sources whose time-varying current has a validated vector potential (Phase 4A): closed
# circular filaments (loops, the turns of solenoids and finite toroids).
INDUCTION_KINDS = ("circular_loop", "solenoid", "toroid_finite")


@dataclass(frozen=True)
class SourceTime:
    object_id: str
    kind: str
    profile_type: str  # "constant" if no profile is set
    current_A: float  # I(t), per turn
    rate: Derivative  # dI/dt, A/s, per turn
    induction_supported: bool  # its E_ind can be evaluated
    rate_scale: float = 0.0  # largest |dI/dt| of the profile at any time (A/s)

    @property
    def varying(self) -> bool:
        return self.rate.left != 0.0 or self.rate.right != 0.0


@dataclass(frozen=True)
class TimeState:
    t_s: float
    sources: list[SourceTime]

    @property
    def time_dependent(self) -> bool:
        return any(s.profile_type != "constant" for s in self.sources)

    @property
    def derivative_unique(self) -> bool:
        return all(s.rate.unique for s in self.sources)

    @property
    def unsupported_ids(self) -> list[str]:
        """Sources whose current changes at t but whose E_ind is not implemented."""
        return [s.object_id for s in self.sources if s.varying and not s.induction_supported]

    def current(self, oid: str) -> float:
        return next(s.current_A for s in self.sources if s.object_id == oid)

    def rate(self, oid: str) -> float:
        return next(s.rate.value for s in self.sources if s.object_id == oid)


def time_state(scene: Scene, cs: CurrentSources, t: float) -> TimeState:
    by_id = {o.id: o for o in scene.objects}
    out: list[SourceTime] = []
    for obj in cs.objects:
        if obj.current_A is None:  # permanent magnet: static by definition in Phase 4A
            continue
        src = by_id[obj.object_id].source
        if not isinstance(src, TimeDependentCurrent):
            continue
        prof = src.profile
        cur = src.current_at(t)
        rate = derivative_at(prof, t) if prof is not None else Derivative(0.0, 0.0)
        out.append(SourceTime(obj.object_id, obj.kind, prof.type if prof is not None else
                              "constant", float(cur), rate, obj.kind in INDUCTION_KINDS,
                              max_rate(prof) if prof is not None else 0.0))
    return TimeState(float(t), out)


def with_currents(cs: CurrentSources, currents: dict[str, float],
                  drop_static: bool = False) -> CurrentSources:
    """The same sources with each object's current replaced (per turn); magnets kept unless
    ``drop_static``. Geometry and every other attribute are unchanged."""
    def cur(oid: str, old: float) -> float:
        return float(currents.get(oid, old))

    return dataclasses.replace(
        cs,
        wires=[dataclasses.replace(w, current_A=cur(w.object_id, w.current_A)) for w in cs.wires],
        loops=[dataclasses.replace(lp, current_A=cur(lp.object_id, lp.current_A))
               for lp in cs.loops],
        ideal_toroids=[dataclasses.replace(t, current_A=cur(t.object_id, t.current_A))
                       for t in cs.ideal_toroids],
        magnets=[] if drop_static else list(cs.magnets),
        objects=[dataclasses.replace(o, current_A=cur(o.object_id, o.current_A))
                 if o.current_A is not None else o for o in cs.objects],
    )


def at_time(cs: CurrentSources, ts: TimeState) -> CurrentSources:
    """Sources carrying I_j(t): the instantaneous magnetic field."""
    return with_currents(cs, {s.object_id: s.current_A for s in ts.sources})


def rates(cs: CurrentSources, ts: TimeState) -> CurrentSources:
    """Sources carrying dI_j/dt (right-hand value) without static sources: dB/dt and, for the
    supported kinds, E_ind = -A of this set."""
    return with_currents(cs, {s.object_id: s.rate.value for s in ts.sources}, drop_static=True)
