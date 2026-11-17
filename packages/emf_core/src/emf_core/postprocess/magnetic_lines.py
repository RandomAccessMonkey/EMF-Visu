"""Magnetic field lines: adaptive numerical integration of dr/ds = ±B/|B| (Phase 3A).

Magnetic field lines have no sources or sinks (∇·B = 0). A traced line therefore ends only for
a computational reason, and every reason is recorded:

* ``closed_loop``: the integrator came back to its start point (criteria below);
* ``domain_boundary``: it left the region of interest — truncated by the drawing region, not a
  physical end (the line continues outside);
* ``source_singularity``: it came within the guard radius of an ideal current filament, where B
  is singular. A B line cannot physically end there, so this is a numerical outcome;
* ``stagnation_point``: |B| fell below the threshold or reversed within one step (a zero of B);
* ``max_length`` / ``integration_failure``: step budget exhausted, step-size underflow or a
  non-finite field value.

Integration: Dormand–Prince RK5(4) (coefficients shared with the electric tracer), adaptive per
line, vectorised over lines; step h ≤ h_max and h ≤ 0.5 × distance to the nearest filament.
Leaving the domain is handled as in the electric tracer (shortened steps, then linear clipping).

Closed-loop detection (all conditions must hold for the step from y_a to y_b):

1. Arc length travelled L ≥ L_min = max(2 d₀, 20 δ), where d₀ is the distance from the start
   point to the nearest filament. A closed B line links a current (Ampère: ∮B·dl = μ₀I_linked ≠ 0
   along a field line), so it must go around a filament and is at least 2 d₀ long.
2. The trace has moved away from the start by at least d₀ at some point (integration progress).
3. The point of the step closest to the start lies inside the step, and its distance to the
   start is ≤ δ, with δ = max(5 × accumulated local error estimate, 10 × atol). The step is
   represented by the cubic Hermite interpolant through its end points and end tangents (the
   integrator's own curve to fourth order in h), not by the straight chord, whose sagitta
   h²/(8r) can exceed δ.
4. The tangent there agrees with the start tangent: t·t₀ ≥ 0.98.

The line then ends at that point of the interpolated step; the remaining gap is stored. Start
and end are never joined artificially. A line that does not close is traced backward from its
seed as well, so it is drawn from end to end.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .field_lines import _A, _B5, _E, _unit

Arr = NDArray[np.float64]
FieldFn = Callable[[Arr], Arr]
DistFn = Callable[[Arr], Arr]  # (N, 3) -> (N,) distance to the nearest current filament
RegionFn = Callable[[Arr], NDArray[np.int64]]  # material region code per point (Phase 3B)

CLOSURE_TANGENT_COS = 0.98
CLOSURE_ERR_FACTOR = 5.0
CLOSURE_ATOL_FACTOR = 10.0

EndReason = Literal["closed_loop", "domain_boundary", "source_singularity", "stagnation_point",
                    "max_length", "integration_failure"]

_OK, _CLOSED, _BOUNDARY, _SINGULAR, _STAGNATION, _MAXLEN, _FAIL = range(7)
NAMES: dict[int, EndReason] = {
    _CLOSED: "closed_loop", _BOUNDARY: "domain_boundary", _SINGULAR: "source_singularity",
    _STAGNATION: "stagnation_point", _MAXLEN: "max_length", _FAIL: "integration_failure"}


@dataclass(frozen=True)
class Settings:
    atol: float
    h_max: float
    h_min: float
    max_length: float
    max_steps: int
    guard_radius: float
    stagnation_B: float


def _hermite(p0: Arr, p1: Arr, m0: Arr, m1: Arr, t: Arr) -> tuple[Arr, Arr]:
    """Cubic Hermite point and derivative at parameter t in [0, 1] (rows)."""
    t = t[:, None]
    t2, t3 = t * t, t * t * t
    pt = ((2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * p1
          + (t3 - t2) * m1)
    dt = ((6 * t2 - 6 * t) * p0 + (3 * t2 - 4 * t + 1) * m0 + (-6 * t2 + 6 * t) * p1
          + (3 * t2 - 2 * t) * m1)
    return pt, dt


@dataclass
class Trace:
    points: Arr
    reason: EndReason
    steps: int
    closure_gap: float | None


def trace(field_fn: FieldFn, dist_fn: DistFn, seeds: Arr, direction: float,
          domain_min: Arr, domain_max: Arr, s: Settings, detect_closure: bool,
          scale_fn: DistFn | None = None, region_fn: RegionFn | None = None) -> list[Trace]:
    """``dist_fn``: distance to singular filaments (capture as ``source_singularity``).
    ``scale_fn`` (default ``dist_fn``): distance to anything the line must not step over
    carelessly (filaments, current sheets, core surfaces); it limits the step and sets the
    closure length scale d0 (Phase 3B)."""
    scale = scale_fn if scale_fn is not None else dist_fn
    m = seeds.shape[0]
    if m == 0:
        return []

    def f(y: Arr) -> tuple[Arr, Arr]:
        d, mag = _unit(field_fn(y))
        return direction * d, mag

    y = seeds.astype(np.float64).copy()
    k1, mag0 = f(y)
    d0 = scale(y)
    t0 = k1.copy()
    h = np.full(m, min(s.h_max, max(0.25 * float(np.min(d0)), s.h_min)))
    length = np.zeros(m)
    err_sum = np.zeros(m)
    far = np.zeros(m)  # largest distance from the start reached so far
    steps = np.zeros(m, np.int64)
    buf = np.empty((m, s.max_steps + 2, 3))
    buf[:, 0] = y
    count = np.ones(m, np.int64)
    code = np.full(m, _OK)
    gap = np.full(m, np.nan)
    code[~np.isfinite(mag0)] = _FAIL
    code[np.isfinite(mag0) & (mag0 <= s.stagnation_B)] = _STAGNATION
    code[(code == _OK) & (dist_fn(y) <= s.guard_radius)] = _SINGULAR
    h_clip = float(np.sqrt(8.0 * s.atol * s.h_max))
    delta_floor = CLOSURE_ATOL_FACTOR * s.atol

    for _ in range(8 * s.max_steps):
        act = np.flatnonzero(code == _OK)
        if act.size == 0:
            break
        ya, ka = y[act], k1[act]
        # Filaments bound the step strictly; sheets and core surfaces only down to 2 atol, so a
        # line can reach and cross them (the crossing rule below) instead of approaching them
        # in ever smaller steps.
        dist = np.minimum(dist_fn(ya), np.maximum(scale(ya), 2.0 * s.atol))
        ha = np.minimum(h[act], np.minimum(s.h_max, np.maximum(0.5 * dist, s.h_min)))
        ks = [ka]
        finite = np.ones(act.size, bool)
        for a in _A[1:]:
            yi = ya + ha[:, None] * sum(c * k for c, k in zip(a, ks, strict=True))
            ki, mi = f(yi)
            finite &= np.isfinite(mi) & (mi > 0)
            ks.append(ki)
        kst = np.stack(ks, axis=0)
        y_new = ya + ha[:, None] * np.tensordot(_B5[:6], kst[:6], axes=1)
        err = ha * np.linalg.norm(np.tensordot(_E, kst, axes=1), axis=1)
        err = np.where(finite, err, np.inf)
        accept = err <= s.atol
        if region_fn is not None:
            # B is discontinuous across a current sheet or core surface (tangential jump), so no
            # step across it meets the error test. A step that crosses such a surface and is
            # already no longer than atol is accepted: the position error it adds is <= atol.
            crossing = (~accept) & finite & (ha <= s.atol) & (
                region_fn(ya) != region_fn(y_new))
            accept |= crossing
        exits = accept & np.any((y_new < domain_min) | (y_new > domain_max), axis=1)
        redo = np.empty(0, np.int64)
        if exits.any():
            dv = y_new[exits] - ya[exits]
            with np.errstate(divide="ignore", invalid="ignore"):
                t_hi = np.where(dv > 0, (domain_max - ya[exits]) / dv, np.inf)
                t_lo = np.where(dv < 0, (domain_min - ya[exits]) / dv, np.inf)
            t_exit = np.clip(np.minimum(t_hi, t_lo).min(axis=1), 0.0, 1.0)
            too_long = ha[exits] > h_clip
            redo = np.flatnonzero(exits)[too_long]
            accept[redo] = False
            err[redo] = s.atol
            ha[redo] = np.maximum(0.9 * t_exit[too_long] * ha[redo], 0.5 * h_clip)
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            factor = np.where(err > 0, 0.9 * (s.atol / err) ** 0.2, 5.0)
        h_next = ha * np.clip(np.nan_to_num(factor, nan=0.2), 0.2, 5.0)
        h_next[redo] = ha[redo]
        h[act] = h_next
        rej = act[~accept]
        code[rej[h[rej] < s.h_min]] = _FAIL

        acc = np.flatnonzero(accept)
        if acc.size == 0:
            continue
        ia = act[acc]
        p0, yn, k_new = ya[acc], y_new[acc], kst[6][acc]
        _, mag_new = _unit(field_fn(yn))
        new = np.full(acc.size, _OK)

        outside = np.any((yn < domain_min) | (yn > domain_max), axis=1)
        if outside.any():
            dvec = yn[outside] - p0[outside]
            with np.errstate(divide="ignore", invalid="ignore"):
                t_hi = np.where(dvec > 0, (domain_max - p0[outside]) / dvec, np.inf)
                t_lo = np.where(dvec < 0, (domain_min - p0[outside]) / dvec, np.inf)
            t = np.clip(np.minimum(t_hi, t_lo).min(axis=1), 0.0, 1.0)
            yn[outside] = np.clip(p0[outside] + t[:, None] * dvec, domain_min, domain_max)
            new[outside] = _BOUNDARY

        seg = yn - p0
        seg_len = np.linalg.norm(seg, axis=1)
        length[ia] += seg_len
        err_sum[ia] += np.where(np.isfinite(err[acc]), err[acc], 0.0)
        steps[ia] += 1

        if detect_closure:
            start = buf[ia, 0]
            ta, tb = ka[acc], k_new  # unit tangents at both ends of the step
            # Derivatives with respect to the step parameter: the integrator's arc-length step
            # (not the chord) times the unit tangent.
            hh = ha[acc][:, None]
            with np.errstate(divide="ignore", invalid="ignore"):
                tpar = np.einsum("ij,ij->i", start - p0, seg) / seg_len**2
            # Closest point to the start on the cubic Hermite interpolant of the step (the
            # integrator's own curve to fourth order in h), not on the straight chord, whose
            # sagitta h²/(8r) could exceed the tolerance. Two Newton steps from the chord value.
            tt = np.clip(np.nan_to_num(tpar, nan=-1.0), -0.5, 1.5)
            for _ in range(2):
                hp, dp = _hermite(p0, yn, ta * hh, tb * hh, tt)
                with np.errstate(divide="ignore", invalid="ignore"):
                    tt = tt + np.einsum("ij,ij->i", start - hp, dp) / np.einsum("ij,ij->i", dp, dp)
                tt = np.clip(np.nan_to_num(tt, nan=-1.0), -0.5, 1.5)
            hp, dp = _hermite(p0, yn, ta * hh, tb * hh, tt)
            dgap = np.linalg.norm(hp - start, axis=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                tangent_ok = np.einsum("ij,ij->i", dp, t0[ia]) / np.linalg.norm(dp, axis=1) >= \
                    CLOSURE_TANGENT_COS
            delta = np.maximum(CLOSURE_ERR_FACTOR * err_sum[ia], delta_floor)
            l_min = np.maximum(2.0 * d0[ia], 20.0 * delta)
            closed = ((new == _OK) & (length[ia] >= l_min) & (far[ia] >= d0[ia])
                      & (tt >= 0.0) & (tt <= 1.0) & (dgap <= delta) & tangent_ok)
            if closed.any():
                yn[closed] = hp[closed]
                new[closed] = _CLOSED
                gap[ia[closed]] = dgap[closed]
            far[ia] = np.maximum(far[ia], np.linalg.norm(yn - start, axis=1))

        sing = (new == _OK) & (dist_fn(yn) <= s.guard_radius)
        new[sing] = _SINGULAR
        reversed_ = np.einsum("ij,ij->i", k_new, ka[acc]) < -0.9
        stag = (new == _OK) & ((mag_new <= s.stagnation_B) | reversed_)
        new[stag & np.isfinite(mag_new)] = _STAGNATION
        new[(new == _OK) & ~np.isfinite(mag_new)] = _FAIL
        over = (new == _OK) & ((length[ia] >= s.max_length) | (steps[ia] >= s.max_steps))
        new[over] = _MAXLEN

        buf[ia, count[ia]] = yn
        count[ia] += 1
        y[ia], k1[ia] = yn, k_new
        code[ia] = new

    code[code == _OK] = _MAXLEN
    return [Trace(points=buf[i, : count[i]].copy(), reason=NAMES[int(code[i])],
                  steps=int(steps[i]), closure_gap=float(gap[i]) if np.isfinite(gap[i]) else None)
            for i in range(m)]


@dataclass
class Line:
    points: Arr  # ordered along +B
    start_reason: EndReason
    end_reason: EndReason
    steps: int
    closure_gap: float | None
    seed_index: int


def trace_lines(field_fn: FieldFn, dist_fn: DistFn, seeds: Arr, domain_min: Arr,
                domain_max: Arr, s: Settings, scale_fn: DistFn | None = None,
                region_fn: RegionFn | None = None) -> list[Line]:
    """Trace a complete line through every seed: forward along +B with closure detection; if it
    does not close, also backward along −B from the seed, joined at the seed."""
    fwd = trace(field_fn, dist_fn, seeds, 1.0, domain_min, domain_max, s, True, scale_fn,
                region_fn)
    open_idx = [i for i, t in enumerate(fwd) if t.reason != "closed_loop"]
    back = trace(field_fn, dist_fn, seeds[open_idx], -1.0, domain_min, domain_max, s, False,
                 scale_fn, region_fn)
    back_by = dict(zip(open_idx, back, strict=True))
    out: list[Line] = []
    for i, tf in enumerate(fwd):
        if tf.reason == "closed_loop":
            out.append(Line(tf.points, "closed_loop", "closed_loop", tf.steps, tf.closure_gap, i))
            continue
        tb = back_by[i]
        pts = np.vstack([tb.points[::-1], tf.points[1:]])
        out.append(Line(pts, tb.reason, tf.reason, tf.steps + tb.steps, None, i))
    return out


def polyline_distance(points: Arr, line: Arr) -> Arr:
    """Distance from each point (k, 3) to a polyline (n, 3)."""
    if line.shape[0] < 2:
        return np.linalg.norm(points[:, None, :] - line[None, :, :], axis=2).min(axis=1)
    a, b = line[:-1], line[1:]
    ab = b - a
    ab2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-300)
    ap = points[:, None, :] - a[None, :, :]
    t = np.clip(np.einsum("kij,ij->ki", ap, ab) / ab2, 0.0, 1.0)
    proj = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    out: Arr = np.linalg.norm(points[:, None, :] - proj, axis=2).min(axis=1)
    return out
