"""Phase 4B: rigid-body motion profiles, poses, material velocities and velocity jumps."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core.scene import motion as mo
from emf_core.scene.transforms import rotation_matrix_xyz

C0 = np.array([0.1, -0.2, 0.3])
R0 = rotation_matrix_xyz((0.3, -0.2, 0.5))


def prof(**kw: object) -> mo.MotionProfile:
    return mo.MotionProfile.model_validate(kw)


def numeric_velocity(m: mo.MotionProfile, t: float, h: float = 1e-6) -> tuple[np.ndarray,
                                                                              np.ndarray]:
    """Central differences of the pose (V from c, omega from dR/dt R^T)."""
    a, b = mo.pose(m, C0, R0, t - h), mo.pose(m, C0, R0, t + h)
    v = (b.center - a.center) / (2 * h)
    p = mo.pose(m, C0, R0, t)
    w_mat = (b.rotation - a.rotation) / (2 * h) @ p.rotation.T
    return v, np.array([w_mat[2, 1], w_mat[0, 2], w_mat[1, 0]])


def test_stationary_profile_keeps_the_reference_pose():
    p = mo.pose(prof(), C0, R0, 12.3)
    assert np.array_equal(p.center, C0) and np.allclose(p.rotation, R0, atol=0)
    assert p.unique and not p.velocity_right.any() and not p.omega_right.any()
    pts = np.random.default_rng(1).normal(size=(5, 3))
    assert not p.material_velocity(pts, "right").any()


@pytest.mark.parametrize("m,t", [
    (prof(translation={"type": "constant_velocity", "velocity_m_per_s": (0.5, -1, 2),
                       "t0_s": 0.2}), 0.7),
    (prof(translation={"type": "constant_acceleration", "velocity_m_per_s": (1, 0, 0),
                       "acceleration_m_per_s2": (0, 2, -1), "t0_s": -0.1}), 0.4),
    (prof(translation={"type": "sinusoidal", "amplitude_m": 0.02, "axis": (0, 3, 4),
                       "frequency_Hz": 2.0, "phase_rad": 0.3}), 0.13),
    (prof(rotation={"type": "constant_angular_velocity", "axis": (1, 1, 0),
                    "omega_rad_per_s": -3.0}), 0.4),
    (prof(translation={"type": "constant_velocity", "velocity_m_per_s": (0, 0, 1)},
          rotation={"type": "constant_angular_velocity", "axis": (0, 0, 2),
                    "omega_rad_per_s": 5.0}), 1.1),
])
def test_analytical_velocities_match_the_pose_derivative(m: mo.MotionProfile, t: float):
    p = mo.pose(m, C0, R0, t)
    v, w = numeric_velocity(m, t)
    assert p.unique
    assert np.allclose(p.velocity_right, v, rtol=1e-7, atol=1e-8)
    assert np.allclose(p.omega_right, w, rtol=1e-7, atol=1e-8)


def test_closed_form_positions():
    m = prof(translation={"type": "constant_acceleration", "velocity_m_per_s": (1, 2, 3),
                          "acceleration_m_per_s2": (4, 0, -2), "t0_s": 1.0})
    dt = 0.5
    expect = C0 + np.array([1, 2, 3]) * dt + 0.5 * np.array([4, 0, -2]) * dt * dt
    assert np.allclose(mo.pose(m, C0, R0, 1.5).center, expect, rtol=0, atol=1e-15)
    s = prof(translation={"type": "sinusoidal", "amplitude_m": 0.1, "axis": (0, 0, 5),
                          "frequency_Hz": 0.25, "phase_rad": 0.0})
    assert np.allclose(mo.pose(s, C0, R0, 1.0).center, C0 + [0, 0, 0.1], atol=1e-15)


def test_rotation_follows_the_right_hand_rule_and_is_orthonormal():
    m = prof(rotation={"type": "constant_angular_velocity", "axis": (0, 0, 1),
                       "omega_rad_per_s": math.pi / 2})
    p = mo.pose(m, np.zeros(3), np.eye(3), 1.0)  # a quarter turn about +z
    assert np.allclose(p.rotation @ [1, 0, 0], [0, 1, 0], atol=1e-15)
    assert np.allclose(p.rotation.T @ p.rotation, np.eye(3), atol=1e-15)
    # u = omega × (r − c): at r − c = +x the velocity is along +y for omega along +z.
    u = p.material_velocity(np.array([[1.0, 0.0, 0.0]]), "right")[0]
    assert np.allclose(u, [0, math.pi / 2, 0])
    neg = prof(rotation={"type": "constant_angular_velocity", "axis": (0, 0, -1),
                         "omega_rad_per_s": math.pi / 2})
    assert np.allclose(mo.pose(neg, np.zeros(3), np.eye(3), 1.0).rotation @ [1, 0, 0],
                       [0, -1, 0], atol=1e-15)


def test_combined_material_velocity_is_v_plus_omega_cross_r():
    m = prof(translation={"type": "constant_velocity", "velocity_m_per_s": (1, 0, 0)},
             rotation={"type": "constant_angular_velocity", "axis": (0, 1, 0),
                       "omega_rad_per_s": 2.0})
    p = mo.pose(m, C0, R0, 0.3)
    r = p.center + np.array([0.0, 0.0, 0.5])
    u = p.material_velocity(r[None, :], "right")[0]
    assert np.allclose(u, [1, 0, 0] + np.cross([0, 2, 0], [0, 0, 0.5]))


def test_velocity_jumps_at_window_ends_are_reported_with_both_limits():
    m = prof(translation={"type": "constant_velocity", "velocity_m_per_s": (2, 0, 0),
                          "t_start_s": 1.0, "t_end_s": 3.0})
    assert mo.corners(m) == [1.0, 3.0]
    a = mo.pose(m, C0, R0, 1.0)
    assert not a.unique and not a.velocity_left.any() and a.velocity_right[0] == 2
    b = mo.pose(m, C0, R0, 3.0)
    assert not b.unique and b.velocity_left[0] == 2 and not b.velocity_right.any()
    assert mo.pose(m, C0, R0, 2.0).unique
    # Held outside the window, never extrapolated.
    assert np.allclose(mo.pose(m, C0, R0, 10.0).center, mo.pose(m, C0, R0, 3.0).center)
    assert np.allclose(mo.pose(m, C0, R0, -5.0).center, mo.pose(m, C0, R0, 1.0).center)
    assert mo.resolve_side(False, "undefined") is None
    assert mo.resolve_side(False, "left") == "left"
    assert mo.resolve_side(True, "undefined") == "right"


@pytest.mark.parametrize("bad", [
    {"translation": {"type": "sinusoidal", "axis": (0, 0, 0)}},
    {"translation": {"type": "sinusoidal", "frequency_Hz": 0}},
    {"translation": {"type": "sinusoidal", "frequency_Hz": 1e9}},
    {"translation": {"type": "sinusoidal", "amplitude_m": -1}},
    {"rotation": {"type": "constant_angular_velocity", "axis": (0, 0, 0)}},
    {"translation": {"type": "constant_velocity", "velocity_m_per_s": (math.nan, 0, 0)}},
    {"translation": {"type": "constant_velocity", "t_start_s": 2, "t_end_s": 1}},
    {"translation": {"type": "warp"}},
])
def test_invalid_motion_is_rejected(bad: dict[str, object]):
    with pytest.raises(ValidationError):
        mo.MotionProfile.model_validate(bad)
