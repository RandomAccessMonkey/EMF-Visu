"""Prescribed time-dependent currents (Phase 4A).

A profile gives the signed current I(t) of a current source in amperes at time t in seconds,
and its analytical derivative dI/dt in A/s (never a finite difference of samples). The sign
convention is the existing one: positive current flows in the source's positive direction, a
negative value reverses it; there is no separate direction flag.

Profiles and their behaviour outside the defined interval:

* constant:          I(t) = I0 for all t.
* sinusoidal:        I(t) = I_dc + I_peak sin(2 pi f t + phi), for all t.
* ramp:              I(t) = I_start for t <= t_start; I_start + s (t - t_start) on
                     [t_start, t_end]; I_start + s (t_end - t_start) for t >= t_end
                     (held, never extrapolated).
* piecewise_linear:  linear between adjacent keyframes; the first value is held before the
                     first keyframe and the last value after the last one.

At a corner (ramp ends, interior keyframes, or the first/last keyframe where a hold meets a
slope) dI/dt has different left and right values. ``derivative`` returns both; the derivative
is uniquely defined only where they are equal.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import FiniteFloat, PositiveFloat, StrictModel

MAX_FREQUENCY_HZ = 1e6  # bounds the input; the quasistatic check itself is scene-dependent
MAX_KEYFRAMES = 64


class ConstantProfile(StrictModel):
    type: Literal["constant"] = "constant"
    current_A: FiniteFloat = 1.0


class SinusoidalProfile(StrictModel):
    type: Literal["sinusoidal"] = "sinusoidal"
    dc_A: FiniteFloat = 0.0
    peak_A: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1.0
    frequency_Hz: Annotated[PositiveFloat, Field(le=MAX_FREQUENCY_HZ)] = 1.0
    phase_rad: FiniteFloat = 0.0


class RampProfile(StrictModel):
    type: Literal["ramp"] = "ramp"
    start_A: FiniteFloat = 0.0
    slope_A_per_s: FiniteFloat = 1.0
    t_start_s: FiniteFloat = 0.0
    t_end_s: FiniteFloat = 1.0

    @model_validator(mode="after")
    def _order(self) -> RampProfile:
        if not self.t_end_s > self.t_start_s:
            raise ValueError("ramp: t_end_s must be later than t_start_s")
        if not math.isfinite(self.start_A + self.slope_A_per_s * (self.t_end_s - self.t_start_s)):
            raise ValueError("ramp: the final current is not finite")
        return self


class Keyframe(StrictModel):
    t_s: FiniteFloat
    current_A: FiniteFloat


class PiecewiseLinearProfile(StrictModel):
    type: Literal["piecewise_linear"] = "piecewise_linear"
    keyframes: list[Keyframe] = Field(min_length=2, max_length=MAX_KEYFRAMES)

    @model_validator(mode="after")
    def _order(self) -> PiecewiseLinearProfile:
        ts = [k.t_s for k in self.keyframes]
        for a, b in zip(ts, ts[1:], strict=False):
            if b == a:
                raise ValueError(f"piecewise_linear: duplicate keyframe time {a} s")
            if b < a:
                raise ValueError("piecewise_linear: keyframe times must be strictly increasing")
        return self


CurrentProfile = Annotated[ConstantProfile | SinusoidalProfile | RampProfile
                           | PiecewiseLinearProfile, Field(discriminator="type")]


@dataclass(frozen=True)
class Derivative:
    """dI/dt at an instant: left and right limits (A/s). Unique where they are equal."""

    left: float
    right: float

    @property
    def unique(self) -> bool:
        return self.left == self.right

    @property
    def value(self) -> float:
        """The right-hand (forward-in-time) derivative, used where one value is needed; callers
        report ``unique`` alongside it."""
        return self.right


ProfileModel = ConstantProfile | SinusoidalProfile | RampProfile | PiecewiseLinearProfile


def current_at(p: ProfileModel, t: float) -> float:
    if isinstance(p, ConstantProfile):
        return float(p.current_A)
    if isinstance(p, SinusoidalProfile):
        return float(p.dc_A + p.peak_A * math.sin(2.0 * math.pi * p.frequency_Hz * t
                                                  + p.phase_rad))
    if isinstance(p, RampProfile):
        tc = min(max(t, p.t_start_s), p.t_end_s)
        return float(p.start_A + p.slope_A_per_s * (tc - p.t_start_s))
    ks = p.keyframes
    if t <= ks[0].t_s:
        return float(ks[0].current_A)
    if t >= ks[-1].t_s:
        return float(ks[-1].current_A)
    i = bisect.bisect_right([k.t_s for k in ks], t) - 1
    k0, k1 = ks[i], ks[i + 1]
    w = (t - k0.t_s) / (k1.t_s - k0.t_s)
    return float(k0.current_A + w * (k1.current_A - k0.current_A))


def derivative_at(p: ProfileModel, t: float) -> Derivative:
    if isinstance(p, ConstantProfile):
        return Derivative(0.0, 0.0)
    if isinstance(p, SinusoidalProfile):
        w = 2.0 * math.pi * p.frequency_Hz
        d = float(w * p.peak_A * math.cos(w * t + p.phase_rad))
        return Derivative(d, d)
    if isinstance(p, RampProfile):
        s = float(p.slope_A_per_s)
        left = s if p.t_start_s < t <= p.t_end_s else 0.0
        right = s if p.t_start_s <= t < p.t_end_s else 0.0
        return Derivative(left, right)
    ks = p.keyframes
    slopes = [(b.current_A - a.current_A) / (b.t_s - a.t_s) for a, b in zip(ks, ks[1:],
                                                                             strict=False)]
    ts = [k.t_s for k in ks]
    # Segment index containing t from the left (t in (t_i, t_i+1]) and from the right.
    i_left = bisect.bisect_left(ts, t) - 1
    i_right = bisect.bisect_right(ts, t) - 1
    left = float(slopes[i_left]) if 0 <= i_left < len(slopes) else 0.0
    right = float(slopes[i_right]) if 0 <= i_right < len(slopes) else 0.0
    return Derivative(left, right)


def max_rate(p: ProfileModel) -> float:
    """Largest |dI/dt| the profile reaches at any time (A/s): the scale against which a
    derivative counts as zero (e.g. a sinusoid at its extremum, where dI/dt rounds to ~1e-16
    of this instead of exactly 0)."""
    if isinstance(p, ConstantProfile):
        return 0.0
    if isinstance(p, SinusoidalProfile):
        return float(2.0 * math.pi * p.frequency_Hz * p.peak_A)
    if isinstance(p, RampProfile):
        return float(abs(p.slope_A_per_s))
    ks = p.keyframes
    return float(max(abs((b.current_A - a.current_A) / (b.t_s - a.t_s))
                     for a, b in zip(ks, ks[1:], strict=False)))


def corners(p: ProfileModel) -> list[float]:
    """Times at which dI/dt may jump (for reporting and test sampling)."""
    if isinstance(p, RampProfile):
        return [p.t_start_s, p.t_end_s]
    if isinstance(p, PiecewiseLinearProfile):
        return [k.t_s for k in p.keyframes]
    return []
