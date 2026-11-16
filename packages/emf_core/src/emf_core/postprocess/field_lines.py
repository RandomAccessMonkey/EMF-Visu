"""Electric field lines: adaptive numerical integration of dr/ds = ±E/|E|.

Method
------
* Arc-length parametrisation, Dormand–Prince RK5(4) with per-line adaptive step size. A step is
  accepted when the embedded error estimate is below ``atol`` (a length).
* Step limits: ``h <= h_max`` and ``h <= 0.5 * distance to the nearest point source`` (so steps
  shrink where the field varies fastest); ``h < h_min`` ends the line as an integration failure.
* Lines are seeded on a small sphere (or circle) of radius ``seed_radius`` around each positive
  source and integrated along +E; lines that must come from outside the domain are seeded around
  negative sources and integrated along −E, then reversed. Backward lines that reach a positive
  source duplicate forward lines and are discarded.
* Leaving the domain: a step that crosses the boundary is repeated with a shorter step until
  the crossing step is at most ``sqrt(8 * atol * h_max)`` long; only then is the last segment
  clipped linearly, which keeps the clipping error at the level of ``atol``.
* Termination (stored per line, never inferred later):
    - ``negative_charge`` / ``positive_charge``: inside the guard radius of a source of the
      matching sign *and* that source's own Coulomb field dominates there;
    - ``domain_boundary``: the line left the region of interest (last segment clipped to it);
    - ``stagnation_point``: |E| fell below ``stagnation_E`` or the field direction reversed
      within one accepted step (a zero of E was crossed);
    - ``max_length``: arc length or step budget exhausted;
    - ``integration_failure``: step size underflow or a non-finite field value.

The guard and seed radii are numerical and drawing safeguards derived from the sampling
resolution. They do not alter the field: inside them the line is drawn as the straight radial
segment to the source, which is the exact limit of the Coulomb field at the source.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
FieldFn = Callable[[Arr], Arr]  # (N, 3) points -> (N, 3) field vectors
EndReason = Literal["positive_charge", "negative_charge", "domain_boundary", "stagnation_point",
                    "max_length", "integration_failure"]

# Dormand–Prince 5(4) coefficients.
_A = (
    (),
    (1 / 5,),
    (3 / 40, 9 / 40),
    (44 / 45, -56 / 15, 32 / 9),
    (19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729),
    (9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656),
    (35 / 384, 0.0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84),
)
_B5 = np.array(_A[6] + (0.0,))
_B4 = np.array((5179 / 57600, 0.0, 7571 / 16695, 393 / 640, -92097 / 339200, 187 / 2100, 1 / 40))
_E = _B5 - _B4

_OK, _SINK, _BOUNDARY, _STAGNATION, _MAXLEN, _FAIL = range(6)


@dataclass(frozen=True)
class PointSources:
    """Point singularities of the field: lines start/end on them."""

    positions: Arr  # (n, 3)
    strengths: Arr  # (n,) signed; the sign decides source (+) or sink (−)
    coulomb_constant: float  # own field magnitude of source i at distance d: K |s_i| / d^2


@dataclass(frozen=True)
class TraceSettings:
    atol: float  # accepted local error per step, metres
    h_max: float
    h_min: float
    max_length: float
    max_steps: int
    guard_radius: float  # capture radius around sources, metres
    stagnation_E: float  # |E| below this is treated as a zero of the field


@dataclass
class Trace:
    points: Arr  # (k, 3), ordered along the integration direction
    reason: EndReason
    source_index: int | None  # index of the source the line ended on
    steps: int


@dataclass
class _State:
    y: Arr
    h: Arr
    k1: Arr
    length: Arr
    steps: NDArray[np.int64]
    buf: Arr
    count: NDArray[np.int64]
    code: NDArray[np.int64]
    hit: NDArray[np.int64]
    extra: dict[str, Arr] = field(default_factory=dict)


def _unit(e: Arr) -> tuple[Arr, Arr]:
    mag = np.sqrt(np.einsum("ij,ij->i", e, e))
    with np.errstate(invalid="ignore", divide="ignore"):
        d = e / mag[:, None]
    return d, mag


def trace(
    field_fn: FieldFn,
    seeds: Arr,
    direction: float,
    sources: PointSources,
    domain_min: Arr,
    domain_max: Arr,
    s: TraceSettings,
) -> list[Trace]:
    """Integrate one line from every seed along ``direction * E``. Vectorised over lines."""
    m = seeds.shape[0]
    if m == 0:
        return []
    sink_sign = -np.sign(direction)  # forward lines end on negative sources
    is_sink = np.sign(sources.strengths) == sink_sign
    nz = sources.strengths != 0.0

    def f(y: Arr) -> tuple[Arr, Arr]:
        d, mag = _unit(field_fn(y))
        return direction * d, mag

    y = seeds.astype(np.float64).copy()
    k1, mag0 = f(y)
    st = _State(
        y=y, h=np.full(m, min(s.h_max, 4 * s.guard_radius)), k1=k1, length=np.zeros(m),
        steps=np.zeros(m, np.int64), buf=np.empty((m, s.max_steps + 2, 3)),
        count=np.ones(m, np.int64), code=np.full(m, _OK), hit=np.full(m, -1),
    )
    st.buf[:, 0] = y
    bad0 = ~np.isfinite(mag0) | (mag0 <= s.stagnation_E)
    st.code[bad0 & ~np.isfinite(mag0)] = _FAIL
    st.code[bad0 & np.isfinite(mag0)] = _STAGNATION

    h_clip = float(np.sqrt(8.0 * s.atol * s.h_max))

    def nearest(yv: Arr) -> tuple[Arr, NDArray[np.int64]]:
        if not nz.any():
            return np.full(yv.shape[0], np.inf), np.full(yv.shape[0], -1)
        d = np.linalg.norm(yv[:, None, :] - sources.positions[None, nz, :], axis=2)
        j = d.argmin(axis=1)
        return d[np.arange(yv.shape[0]), j], np.flatnonzero(nz)[j]

    for _ in range(8 * s.max_steps):
        act = np.flatnonzero(st.code == _OK)
        if act.size == 0:
            break
        ya, ka = st.y[act], st.k1[act]
        dist, _ = nearest(ya)
        h = np.minimum(st.h[act], np.minimum(s.h_max, np.maximum(0.5 * dist, s.h_min)))
        ks = [ka]
        finite = np.ones(act.size, bool)
        for a in _A[1:]:
            yi = ya + h[:, None] * sum(c * k for c, k in zip(a, ks, strict=True))
            ki, mi = f(yi)
            finite &= np.isfinite(mi) & (mi > 0)
            ks.append(ki)
        kst = np.stack(ks, axis=0)  # (7, n, 3); ks[6] is evaluated at the 5th-order solution
        y_new = ya + h[:, None] * np.tensordot(_B5[:6], kst[:6], axes=1)
        err = h * np.linalg.norm(np.tensordot(_E, kst, axes=1), axis=1)
        err = np.where(finite, err, np.inf)
        accept = err <= s.atol
        # A step that leaves the domain is only accepted once it is short enough for linear
        # clipping to be accurate; otherwise retry with a step that stops just inside.
        exits = accept & np.any((y_new < domain_min) | (y_new > domain_max), axis=1)
        if exits.any():
            dv = y_new[exits] - ya[exits]
            with np.errstate(divide="ignore", invalid="ignore"):
                t_hi = np.where(dv > 0, (domain_max - ya[exits]) / dv, np.inf)
                t_lo = np.where(dv < 0, (domain_min - ya[exits]) / dv, np.inf)
            t_exit = np.clip(np.minimum(t_hi, t_lo).min(axis=1), 0.0, 1.0)
            too_long = h[exits] > h_clip
            redo = np.flatnonzero(exits)[too_long]
            accept[redo] = False
            err[redo] = s.atol  # keep the step-size controller neutral for these lines
            h[redo] = np.maximum(0.9 * t_exit[too_long] * h[redo], 0.5 * h_clip)
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            factor = np.where(err > 0, 0.9 * (s.atol / err) ** 0.2, 5.0)
        h_next = h * np.clip(np.nan_to_num(factor, nan=0.2), 0.2, 5.0)
        if exits.any():
            h_next[redo] = h[redo]
        st.h[act] = h_next

        # Rejected: retry with the smaller step; underflow is a numerical failure, never an end.
        rej = act[~accept]
        st.code[rej[st.h[rej] < s.h_min]] = _FAIL

        acc = np.flatnonzero(accept)
        if acc.size == 0:
            continue
        ia = act[acc]
        yn, k_new = y_new[acc], kst[6][acc]
        _, mag_new = _unit(field_fn(yn))
        code = np.full(acc.size, _OK)
        hit = np.full(acc.size, -1)

        # 1. Left the region of interest: clip the last segment to the boundary.
        outside = np.any((yn < domain_min) | (yn > domain_max), axis=1)
        if outside.any():
            p0, p1 = ya[acc][outside], yn[outside]
            dvec = p1 - p0
            with np.errstate(divide="ignore", invalid="ignore"):
                t_hi = np.where(dvec > 0, (domain_max - p0) / dvec, np.inf)
                t_lo = np.where(dvec < 0, (domain_min - p0) / dvec, np.inf)
            t = np.clip(np.minimum(t_hi, t_lo).min(axis=1), 0.0, 1.0)
            yn[outside] = np.clip(p0 + t[:, None] * dvec, domain_min, domain_max)
            code[outside] = _BOUNDARY

        # 2. Captured by a sink whose own field dominates here.
        if is_sink.any():
            dsk = np.linalg.norm(yn[:, None, :] - sources.positions[None, is_sink, :], axis=2)
            j = dsk.argmin(axis=1)
            dmin = dsk[np.arange(acc.size), j]
            idx = np.flatnonzero(is_sink)[j]
            own = sources.coulomb_constant * np.abs(sources.strengths[idx]) / np.maximum(
                dmin, 1e-300) ** 2
            radial = (sources.positions[idx] - yn) / np.maximum(dmin, 1e-300)[:, None]
            # Field of everything else, along the unit vector: |E_total - E_own|.
            e_tot = field_fn(yn)
            e_own = -np.sign(sources.strengths[idx])[:, None] * own[:, None] * radial
            others = np.linalg.norm(np.nan_to_num(e_tot) - e_own, axis=1)
            captured = (code == _OK) & (dmin < s.guard_radius) & (
                (others <= 0.5 * own) | (dmin < 4 * s.h_min))
            code[captured] = _SINK
            hit[captured] = idx[captured]

        # 3. Zero of the field: tiny magnitude, or direction reversed within one step.
        reversed_ = np.einsum("ij,ij->i", k_new, ka[acc]) < -0.9
        stag = (code == _OK) & ((mag_new <= s.stagnation_E) | reversed_)
        code[stag & np.isfinite(mag_new)] = _STAGNATION
        code[(code == _OK) & ~np.isfinite(mag_new)] = _FAIL

        st.length[ia] += np.linalg.norm(yn - ya[acc], axis=1)
        st.steps[ia] += 1
        over = (code == _OK) & ((st.length[ia] >= s.max_length) | (st.steps[ia] >= s.max_steps))
        code[over] = _MAXLEN

        st.buf[ia, st.count[ia]] = yn
        st.count[ia] += 1
        st.y[ia], st.k1[ia] = yn, k_new
        st.code[ia], st.hit[ia] = code, hit

    st.code[st.code == _OK] = _MAXLEN
    names: dict[int, EndReason] = {
        _SINK: "negative_charge" if direction > 0 else "positive_charge",
        _BOUNDARY: "domain_boundary", _STAGNATION: "stagnation_point", _MAXLEN: "max_length",
        _FAIL: "integration_failure",
    }
    out: list[Trace] = []
    for i in range(m):
        pts = st.buf[i, : st.count[i]].copy()
        hit_i = int(st.hit[i])
        if st.code[i] == _SINK:  # draw the exact radial limit down to the source itself
            pts = np.vstack([pts, sources.positions[hit_i]])
        out.append(Trace(points=pts, reason=names[int(st.code[i])],
                         source_index=hit_i if hit_i >= 0 else None, steps=int(st.steps[i])))
    return out


def fibonacci_sphere(n: int) -> Arr:
    """n quasi-uniform unit vectors (golden-angle spiral)."""
    i = np.arange(n) + 0.5
    z = 1.0 - 2.0 * i / n
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = i * (np.pi * (3.0 - np.sqrt(5.0)))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def circle(n: int, u: Arr, v: Arr) -> Arr:
    """n unit vectors, uniformly spaced in the plane spanned by orthonormal u, v (first along u)."""
    a = 2.0 * np.pi * np.arange(n) / n
    return np.cos(a)[:, None] * u + np.sin(a)[:, None] * v


def seed_radii(field_fn: FieldFn, sources: PointSources, guard_radius: float) -> Arr:
    """Per-source seed radius: at most the guard radius, at most a tenth of the distance to the
    nearest other source, and small enough that the source's own field is at least 10x the field
    of everything else (so the field on the seed sphere is radial to about 10 %)."""
    n = sources.positions.shape[0]
    r = np.full(n, guard_radius)
    nz = sources.strengths != 0.0
    for i in range(n):
        if not nz[i]:
            continue
        others = nz.copy()
        others[i] = False
        if not others.any():
            continue
        d = np.linalg.norm(sources.positions[others] - sources.positions[i], axis=1)
        r[i] = min(r[i], 0.1 * float(d.min()))
        # External field at the source position, from the direct sum of the other sources.
        dv = sources.positions[i] - sources.positions[others]
        e_ext = float(np.linalg.norm(
            ((sources.coulomb_constant * sources.strengths[others] / d**3)[:, None] * dv).sum(0)))
        if e_ext > 0:
            r_dom = np.sqrt(sources.coulomb_constant * abs(sources.strengths[i]) / (10.0 * e_ext))
            r[i] = min(r[i], float(r_dom))
    return r
