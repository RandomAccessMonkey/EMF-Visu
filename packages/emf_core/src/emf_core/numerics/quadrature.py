"""Vectorised adaptive Gauss–Kronrod quadrature (G7/K15), Phase 3B.

Integrates many independent one-dimensional integrals of vector-valued integrands at once:

    I_i = ∫_{a_i}^{b_i} f(i, t) dt,  i = 0..n-1,  f: (item indices, t) -> (k, c) values.

Every interval is evaluated with the 15-point Kronrod rule and its embedded 7-point Gauss rule;
the error estimate of an interval is |K15 − G7| (Euclidean norm over the c components). An item
is converged when every interval satisfies

    err_interval ≤ tol_i · (interval length / item length),  tol_i = max(rtol · |I_i|, atol_i),

with |I_i| the current estimate. Rejected intervals are halved. After ``max_levels`` halvings
an interval is accepted as it is and its item is marked not converged; nothing is hidden. The
returned error estimate is the sum of the interval estimates (a conservative bound for smooth
integrands, since K15 is far more accurate than G7).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
Integrand = Callable[[NDArray[np.int64], Arr], Arr]

_XK = np.array([0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
                0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
                0.586087235467691130294144845693013, 0.405845151377397166906606412076961,
                0.207784955007898467600689403773245, 0.000000000000000000000000000000000])
_WK = np.array([0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
                0.104790010322250183839876322541518, 0.140653259715525918745189590510238,
                0.169004726639267902826583426598550, 0.190350578064785409913256402421014,
                0.204432940075298892414161999234649, 0.209482141084727828012999174891714])
_WG = np.array([0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
                0.381830050505118944950369775488975, 0.417959183673469387755102040816327])
# Nodes on [-1, 1]: -x1..-x7, 0, x7..x1; Gauss nodes are the odd-indexed Kronrod nodes.
NODES = np.concatenate([-_XK[:-1], [0.0], _XK[:-1][::-1]])
W_K = np.concatenate([_WK[:-1], [_WK[-1]], _WK[:-1][::-1]])
W_G = np.zeros(15)
W_G[1::2][:3] = _WG[:3]
W_G[7] = _WG[3]
W_G[9::2] = _WG[:3][::-1]


@dataclass
class QuadResult:
    value: Arr  # (n, c)
    error: Arr  # (n,) error estimate (norm over components)
    converged: NDArray[np.bool_]  # (n,)
    intervals: NDArray[np.int64]  # (n,) accepted intervals per item
    evaluations: int  # integrand evaluations in total


def _evaluate(f: Integrand, own: NDArray[np.int64], lo: Arr, hi: Arr,
              components: int) -> tuple[Arr, Arr]:
    mid, half = 0.5 * (lo + hi), 0.5 * (hi - lo)
    t = mid[:, None] + half[:, None] * NODES[None, :]
    vals = f(np.repeat(own, 15), t.ravel()).reshape(own.size, 15, components)
    k = half[:, None] * np.einsum("j,ijc->ic", W_K, vals)
    g = half[:, None] * np.einsum("j,ijc->ic", W_G, vals)
    return k, g


def adaptive_gk(f: Integrand, a: Arr, b: Arr, components: int, rtol: float,
                atol: Arr | float = 0.0, max_levels: int = 40,
                max_active_per_item: int = 256) -> QuadResult:
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    n = a.size
    atol_arr = np.broadcast_to(np.asarray(atol, np.float64), (n,)).copy()
    length = np.abs(b - a)
    value = np.zeros((n, components))
    error = np.zeros(n)
    converged = np.ones(n, bool)
    intervals = np.zeros(n, np.int64)
    keep = length > 0
    own = np.flatnonzero(keep)
    lo, hi = a[keep].copy(), b[keep].copy()
    level = np.zeros(own.size, np.int64)
    evaluations = 0
    # "pending" holds, per item, the K15 sum of its intervals that are not decided yet, so that
    # value + pending is always a complete estimate of the integral.
    pending = np.zeros((n, components))
    k, g = _evaluate(f, own, lo, hi, components)
    evaluations += own.size * 15
    np.add.at(pending, own, k)
    while own.size:
        err = np.linalg.norm(np.nan_to_num(k - g, nan=np.inf, posinf=np.inf, neginf=np.inf),
                             axis=1)
        tol_item = np.maximum(rtol * np.linalg.norm(value + pending, axis=1), atol_arr)
        ok = err <= tol_item[own] * ((hi - lo) / length[own])
        nonfinite = ~np.all(np.isfinite(k), axis=1)
        # Safety cap: an item with too many open intervals stops refining (reported as not
        # converged) instead of growing without bound.
        crowded = np.bincount(own, minlength=n)[own] > max_active_per_item
        accept = ok | (level >= max_levels) | nonfinite | crowded
        np.add.at(value, own[accept], k[accept])
        np.add.at(error, own[accept], err[accept])
        np.add.at(intervals, own[accept], 1)
        converged[own[accept & ~ok]] = False
        np.add.at(pending, own, -k)  # every current interval is either accepted or replaced
        rej = ~accept
        o, l_, h_, lv = own[rej], lo[rej], hi[rej], level[rej]
        m_ = 0.5 * (l_ + h_)
        own = np.concatenate([o, o])
        lo = np.concatenate([l_, m_])
        hi = np.concatenate([m_, h_])
        level = np.concatenate([lv + 1, lv + 1])
        if own.size:
            k, g = _evaluate(f, own, lo, hi, components)
            evaluations += own.size * 15
            np.add.at(pending, own, k)
    return QuadResult(value=value, error=error, converged=converged, intervals=intervals,
                      evaluations=evaluations)
