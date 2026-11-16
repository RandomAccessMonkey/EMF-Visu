"""Finite-difference diagnostics of divergence and curl (a numerical check, never a result).

The authoritative divergence and curl of the point-charge field are the exact analytical ones
returned by the solver. This module estimates the same operators numerically from the exact
field, so that a user (or a test) can see that the numerical estimate is consistent with the
exact value *within its stated uncertainty*. It does not solve any field equation.

Method
------
Central differences of the field with steps h and h/2 give Jacobians J(h) and J(h/2), each
with truncation error O(h^2). Richardson extrapolation R = (4 J(h/2) - J(h)) / 3 removes the
h^2 term. The uncertainty of each Jacobian entry is the sum of

* a truncation estimate |J(h) - J(h/2)| (the difference that Richardson removes; the remaining
  error of R is O(h^4) and is much smaller whenever this estimate is meaningful), and
* a round-off bound 8 * eps * max|F| / h (cancellation in the differences, with the
  coefficients of R).

Divergence = trace(R), curl = (R32 - R23, R13 - R31, R21 - R12); their uncertainties are the
sums of the uncertainties of the entries involved. The actual step lengths (x + h) - (x - h)
are used, so representation error in the sample positions does not bias the estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
FieldFn = Callable[[Arr], Arr]  # (N, 3) -> (N, 3)

EPS = float(np.finfo(np.float64).eps)
RELATIVE_STEP = 1e-3  # default h = RELATIVE_STEP * (distance to the nearest singularity)


@dataclass(frozen=True)
class Estimate:
    div: float
    div_uncertainty: float
    curl: Arr  # (3,)
    curl_uncertainty: Arr  # (3,)
    step_m: float

    @property
    def div_consistent_with_zero(self) -> bool:
        return abs(self.div) <= self.div_uncertainty

    @property
    def curl_consistent_with_zero(self) -> bool:
        return bool(np.all(np.abs(self.curl) <= self.curl_uncertainty))


def _jacobian(field: FieldFn, p: Arr, h: float) -> tuple[Arr, float]:
    """J[i, j] = dF_i/dx_j by central differences, and max |F| over the stencil."""
    stencil = np.empty((6, 3))
    steps = np.empty(3)
    for j in range(3):
        xp, xm = p.copy(), p.copy()
        xp[j] += h
        xm[j] -= h
        stencil[2 * j], stencil[2 * j + 1] = xp, xm
        steps[j] = xp[j] - xm[j]  # the step actually taken in floating point
    f = field(stencil)
    jac = np.empty((3, 3))
    for j in range(3):
        jac[:, j] = (f[2 * j] - f[2 * j + 1]) / steps[j]
    return jac, float(np.abs(f).max())


def estimate(field: FieldFn, point: Arr, h: float) -> Estimate:
    p = np.asarray(point, dtype=np.float64)
    j1, f1 = _jacobian(field, p, h)
    j2, f2 = _jacobian(field, p, h / 2)
    rich = (4.0 * j2 - j1) / 3.0
    unc = np.abs(j1 - j2) + 8.0 * EPS * max(f1, f2) / h
    curl = np.array([rich[2, 1] - rich[1, 2], rich[0, 2] - rich[2, 0], rich[1, 0] - rich[0, 1]])
    curl_unc = np.array([unc[2, 1] + unc[1, 2], unc[0, 2] + unc[2, 0], unc[1, 0] + unc[0, 1]])
    return Estimate(div=float(np.trace(rich)), div_uncertainty=float(np.trace(unc)), curl=curl,
                    curl_uncertainty=curl_unc, step_m=h)
