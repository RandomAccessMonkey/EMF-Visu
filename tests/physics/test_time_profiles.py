"""Phase 4A: prescribed current profiles I(t) and their analytical derivatives."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

from emf_core.scene.models import CircularLoopSource
from emf_core.scene.profiles import (
    ConstantProfile,
    CurrentProfile,
    PiecewiseLinearProfile,
    RampProfile,
    SinusoidalProfile,
    corners,
    current_at,
    derivative_at,
)

PROFILE = TypeAdapter(CurrentProfile)


def central_difference(p, t, h=1e-6):
    return (current_at(p, t + h) - current_at(p, t - h)) / (2 * h)


def test_constant_profile():
    p = ConstantProfile(current_A=-3.5)
    for t in (-10.0, 0.0, 1e9):
        assert current_at(p, t) == -3.5
        d = derivative_at(p, t)
        assert d.left == d.right == 0.0 and d.unique


def test_sinusoid_value_and_analytical_derivative():
    p = SinusoidalProfile(dc_A=0.5, peak_A=2.0, frequency_Hz=3.0, phase_rad=0.4)
    w = 2 * math.pi * 3.0
    for t in np.linspace(-1, 1, 41):
        assert current_at(p, t) == pytest.approx(0.5 + 2.0 * math.sin(w * t + 0.4), abs=1e-15)
        d = derivative_at(p, t)
        assert d.unique and d.value == pytest.approx(2.0 * w * math.cos(w * t + 0.4), rel=1e-15,
                                                    abs=1e-13)
        # Independent check: the derivative agrees with a central difference of I(t).
        assert d.value == pytest.approx(central_difference(p, t), rel=1e-7, abs=1e-7)


def test_sinusoid_phase_relation_quarter_period():
    p = SinusoidalProfile(peak_A=2.0, frequency_Hz=1.0)
    assert derivative_at(p, 0.25).value == pytest.approx(0.0, abs=1e-14)  # current at its peak
    assert current_at(p, 0.25) == pytest.approx(2.0, rel=1e-15)
    assert current_at(p, 0.0) == 0.0 and derivative_at(p, 0.0).value == pytest.approx(4 * math.pi)


def test_ramp_inside_before_after_and_corners():
    p = RampProfile(start_A=0.0, slope_A_per_s=5.0, t_start_s=0.0, t_end_s=1.0)
    assert current_at(p, -0.5) == 0.0 and current_at(p, 0.4) == pytest.approx(2.0)
    assert current_at(p, 1.0) == 5.0 and current_at(p, 7.0) == 5.0  # held, not extrapolated
    assert derivative_at(p, 0.4).value == 5.0 and derivative_at(p, 0.4).unique
    assert derivative_at(p, -0.5).value == 0.0 and derivative_at(p, 3.0).value == 0.0
    start, end = derivative_at(p, 0.0), derivative_at(p, 1.0)
    assert (start.left, start.right, start.unique) == (0.0, 5.0, False)
    assert (end.left, end.right, end.unique) == (5.0, 0.0, False)
    assert corners(p) == [0.0, 1.0]


def test_piecewise_linear_slopes_holds_and_corners():
    p = PiecewiseLinearProfile.model_validate({"keyframes": [
        {"t_s": 0.0, "current_A": 0.0}, {"t_s": 1.0, "current_A": 2.0},
        {"t_s": 3.0, "current_A": -2.0}, {"t_s": 4.0, "current_A": -2.0}]})
    assert current_at(p, 0.5) == 1.0 and current_at(p, 2.0) == 0.0
    assert current_at(p, -1.0) == 0.0 and current_at(p, 9.0) == -2.0
    assert derivative_at(p, 0.5).value == 2.0 and derivative_at(p, 2.0).value == -2.0
    assert derivative_at(p, 3.5).value == 0.0 and derivative_at(p, 5.0).value == 0.0
    k1 = derivative_at(p, 1.0)
    assert (k1.left, k1.right, k1.unique) == (2.0, -2.0, False)
    k0 = derivative_at(p, 0.0)
    assert (k0.left, k0.right) == (0.0, 2.0)
    k3 = derivative_at(p, 3.0)
    assert (k3.left, k3.right) == (-2.0, 0.0)
    for t in (0.3, 1.7, 3.2):
        assert derivative_at(p, t).value == pytest.approx(central_difference(p, t), rel=1e-6)


@pytest.mark.parametrize("bad", [
    {"type": "sinusoidal", "frequency_Hz": 0.0},
    {"type": "sinusoidal", "frequency_Hz": -1.0},
    {"type": "sinusoidal", "frequency_Hz": 2e6},
    {"type": "sinusoidal", "peak_A": -1.0},
    {"type": "sinusoidal", "dc_A": float("nan")},
    {"type": "ramp", "t_start_s": 1.0, "t_end_s": 1.0},
    {"type": "ramp", "t_start_s": 2.0, "t_end_s": 1.0},
    {"type": "ramp", "slope_A_per_s": float("inf")},
    {"type": "piecewise_linear", "keyframes": [{"t_s": 0, "current_A": 1}]},
    {"type": "piecewise_linear", "keyframes": [{"t_s": 0, "current_A": 1},
                                               {"t_s": 0, "current_A": 2}]},
    {"type": "piecewise_linear", "keyframes": [{"t_s": 1, "current_A": 1},
                                               {"t_s": 0, "current_A": 2}]},
    {"type": "constant", "current_A": float("nan")},
])
def test_invalid_profiles_are_rejected(bad):
    with pytest.raises(ValidationError):
        PROFILE.validate_python(bad)


def test_profile_and_current_cannot_conflict():
    ok = CircularLoopSource.model_validate({"current_A": 0.0, "profile": {
        "type": "sinusoidal", "peak_A": 2.0, "frequency_Hz": 1.0}})
    assert ok.current_at(0.25) == pytest.approx(2.0)
    # With a profile, current_A is derived as I(0): any submitted value is replaced.
    stale = CircularLoopSource.model_validate({"current_A": 7.0, "profile": {
        "type": "sinusoidal", "dc_A": 0.5, "peak_A": 2.0, "frequency_Hz": 1.0,
        "phase_rad": 0.3}})
    assert stale.current_A == pytest.approx(0.5 + 2.0 * math.sin(0.3), rel=1e-15)
    assert stale.current_at(0.0) == stale.current_A
    # No profile: the constant current, at every time (old projects).
    old = CircularLoopSource.model_validate({"current_A": -4.0})
    assert old.profile is None and old.current_at(123.0) == -4.0


def test_evaluation_is_deterministic():
    p = SinusoidalProfile(dc_A=0.1, peak_A=2.0, frequency_Hz=7.0, phase_rad=1.1)
    ts = 0.0 + 0.01 * np.arange(200)
    a = [(current_at(p, t), derivative_at(p, t).value) for t in ts]
    b = [(current_at(p, t), derivative_at(p, t).value) for t in ts]
    assert a == b
