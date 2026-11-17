"""Phase 4B: motional EMF, flux through moving surfaces and the generalized Faraday law.

Uniform-field cases use an analytical field model (``uniform_field_model``) through the same
code path as scenes; finite-coil cases use the actual Helmholtz-pair scenes of the presets."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core.induction import FluxSurface, InductionRequest, compute
from emf_core.motional import evaluate_moving, richardson, uniform_field_model
from emf_core.presets import PRESETS
from emf_core.scene.models import (
    CircularLoopSource,
    Domain,
    InfiniteWireSource,
    LinePrimitive,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
)

B0 = 0.4
TOL_GEO = 1e-12
PRESET = {p.id: p for p in PRESETS}


def uniform(b: tuple[float, float, float] = (0.0, 0.0, B0)):
    return uniform_field_model(lambda t: np.asarray(b, float))


def rod(v: float = 0.5, length: float = 0.1, x0: float = 0.05, reversed_: bool = False,
        **motion: object) -> FluxSurface:
    return FluxSurface.model_validate({
        "id": "rod", "reversed": reversed_,
        "shape": {"type": "sliding_rod", "rail_separation_m": length, "rail_length_m": 1.0,
                  "rod_position_m": x0,
                  "rod_motion": {"type": "constant_velocity", "velocity_m_per_s": (v, 0, 0),
                                 **motion}}})


def rotating(omega: float = 4.0, axis=(1.0, 0.0, 0.0), shape=None, turns: int = 1,
             reversed_: bool = False, rot=(0.0, 0.0, 0.0)) -> FluxSurface:
    return FluxSurface.model_validate({
        "id": "coil", "reversed": reversed_, "turns": turns, "rotation_euler_xyz_rad": rot,
        "shape": shape or {"type": "rectangle", "width_m": 0.2, "height_m": 0.1},
        "motion": {"rotation": {"type": "constant_angular_velocity", "axis": axis,
                                "omega_rad_per_s": omega}}})


# ------------------------------------------------------------------- sliding rod, uniform B


def test_sliding_rod_emf_is_minus_blv_and_matches_the_flux_change():
    r = evaluate_moving(rod(), uniform(), 0.4, "undefined", TOL_GEO)
    assert r.status == "verified"
    assert r.emf_motional_V == pytest.approx(-B0 * 0.1 * 0.5, rel=1e-12)
    assert r.emf_V == 0.0 and r.emf_total_V == r.emf_motional_V  # static field
    x = 0.05 + 0.5 * 0.4
    assert r.flux_Wb == pytest.approx(B0 * 0.1 * x, rel=1e-12)  # flux–area relationship
    assert r.dflux_dt_V == pytest.approx(B0 * 0.1 * 0.5, rel=1e-10)
    assert abs(r.difference_V) <= r.tolerance_V
    assert r.motion.rod_position_m == pytest.approx(x) and r.motion.rod_velocity_m_per_s == 0.5
    assert r.reference.kind == "sliding_rod_BLv"
    assert r.reference.emf_V == pytest.approx(r.emf_motional_V, rel=1e-12)
    # Lenz: the flux grows, the EMF drives circulation against the traversal.
    assert r.lenz.flux_trend == "increasing" and r.lenz.circulation == "against_path"
    # Only the rod moves; the rails are stationary.
    assert all(s.moving for s in r.motional_samples)
    assert r.motion.rails_m and len(r.motion.rod_m) == 2


@pytest.mark.parametrize("v,length,b", [(0.5, 0.1, B0), (-0.5, 0.1, B0), (1.5, 0.1, B0),
                                        (0.5, 0.3, B0), (0.5, 0.1, -B0)])
def test_sliding_rod_scaling_and_sign_reversals(v: float, length: float, b: float):
    r = evaluate_moving(rod(v=v, length=length, x0=0.6), uniform((0, 0, b)), 0.2, "undefined",
                        TOL_GEO)
    assert r.status == "verified"
    assert r.emf_motional_V == pytest.approx(-b * length * v, rel=1e-12)


def test_sliding_rod_reversed_traversal_reverses_emf_and_flux():
    a = evaluate_moving(rod(), uniform(), 0.1, "undefined", TOL_GEO)
    b = evaluate_moving(rod(reversed_=True), uniform(), 0.1, "undefined", TOL_GEO)
    assert b.status == "verified"
    assert b.emf_motional_V == pytest.approx(-a.emf_motional_V, rel=1e-12)
    assert b.flux_Wb == pytest.approx(-a.flux_Wb, rel=1e-12)


def test_sliding_rod_field_in_plane_gives_no_emf():
    r = evaluate_moving(rod(), uniform((B0, 0, 0)), 0.1, "undefined", TOL_GEO)
    assert r.status == "verified" and abs(r.emf_motional_V) < 1e-18 and abs(r.flux_Wb) < 1e-18


def test_rod_velocity_jump_is_undefined_unless_a_convention_is_chosen():
    s = rod(t_end_s=0.2)
    u = evaluate_moving(s, uniform(), 0.2, "undefined", TOL_GEO)
    assert u.status == "motion_undefined" and u.emf_motional_V is None
    assert u.flux_Wb is not None and not u.motion.unique
    left = evaluate_moving(s, uniform(), 0.2, "left", TOL_GEO)
    right = evaluate_moving(s, uniform(), 0.2, "right", TOL_GEO)
    assert left.status == right.status == "verified"
    assert left.emf_motional_V == pytest.approx(-B0 * 0.1 * 0.5) and right.emf_motional_V == 0
    assert left.derivative.method == "backward" and right.derivative.method == "forward"


def test_rod_leaving_the_rails_is_invalid():
    r = evaluate_moving(rod(v=1.0, x0=0.5), uniform(), 0.6, "undefined", TOL_GEO)
    assert r.status == "invalid" and "rails" in r.invalid_reasons[0].en
    with pytest.raises(ValidationError):  # rod motion must run along the rails
        FluxSurface.model_validate({"id": "r", "shape": {
            "type": "sliding_rod", "rod_motion": {"type": "constant_velocity",
                                                  "velocity_m_per_s": (0.5, 0.1, 0)}}})


# ----------------------------------------------------------------- rotating coil, uniform B


@pytest.mark.parametrize("t", [0.0, 0.1, 0.37, 0.785398])
def test_rotating_coil_flux_is_ba_cos_and_emf_is_minus_dphi_dt(t: float):
    omega, area = 4.0, 0.02
    r = evaluate_moving(rotating(omega), uniform(), t, "undefined", TOL_GEO)
    assert r.status == "verified"
    assert r.flux_Wb == pytest.approx(B0 * area * math.cos(omega * t), abs=1e-15)
    expect = B0 * area * omega * math.sin(omega * t)
    assert r.emf_motional_V == pytest.approx(expect, abs=1e-14)
    assert r.dflux_dt_V == pytest.approx(-expect, rel=1e-7, abs=1e-12)
    assert abs(r.dflux_dt_V + expect) <= r.tolerance_V
    assert r.reference.kind == "rotating_coil"
    assert r.reference.emf_V == pytest.approx(r.emf_motional_V, abs=1e-14)


def test_rotating_coil_scales_with_angular_speed_and_reverses_with_orientation():
    base = evaluate_moving(rotating(4.0), uniform(), 0.3, "undefined", TOL_GEO)
    # Same angle omega t with twice the speed: twice the EMF.
    fast = evaluate_moving(rotating(8.0), uniform(), 0.15, "undefined", TOL_GEO)
    assert fast.emf_motional_V == pytest.approx(2 * base.emf_motional_V, rel=1e-10)
    rev = evaluate_moving(rotating(4.0, reversed_=True), uniform(), 0.3, "undefined", TOL_GEO)
    assert rev.status == "verified"
    assert rev.emf_motional_V == pytest.approx(-base.emf_motional_V, rel=1e-10)
    assert rev.flux_Wb == pytest.approx(-base.flux_Wb, rel=1e-10)
    # Reversed sense of rotation from the same start: the flux is even in t, the EMF odd, so
    # at the same t the EMF is the same and it is reversed at −t.
    neg = evaluate_moving(rotating(-4.0), uniform(), 0.3, "undefined", TOL_GEO)
    assert neg.status == "verified"
    assert neg.emf_motional_V == pytest.approx(base.emf_motional_V, rel=1e-10)
    back = evaluate_moving(rotating(4.0), uniform(), -0.3, "undefined", TOL_GEO)
    assert back.emf_motional_V == pytest.approx(-base.emf_motional_V, rel=1e-10)


def test_n_turn_measurement_coil_multiplies_flux_and_emf():
    one = evaluate_moving(rotating(), uniform(), 0.3, "undefined", TOL_GEO)
    from emf_core.induction import scale_turns
    five = scale_turns(evaluate_moving(rotating(turns=5), uniform(), 0.3, "undefined", TOL_GEO),
                       5)
    assert five.turns == 5 and five.status == "verified"
    for name in ("flux_Wb", "emf_motional_V", "emf_total_V", "dflux_dt_V"):
        assert getattr(five, name) == pytest.approx(5 * getattr(one, name), rel=1e-12)


@pytest.mark.parametrize("shape", [{"type": "circle", "radius_m": 0.07},
                                   {"type": "polygon", "vertices_m": [(0, 0, 0), (0.1, 0, 0),
                                                                      (0.05, 0.08, 0)]}])
def test_other_shapes_rotate_with_the_same_law(shape: dict[str, object]):
    r = evaluate_moving(rotating(3.0, axis=(0, 1, 0), shape=shape), uniform(), 0.2,
                        "undefined", TOL_GEO)
    assert r.status == "verified"
    area = r.area_m2
    assert r.flux_Wb == pytest.approx(B0 * area * math.cos(0.6), rel=1e-9)


def test_pure_translation_in_a_uniform_field_induces_nothing():
    s = FluxSurface.model_validate({"id": "t", "shape": {"type": "circle", "radius_m": 0.05},
                                    "motion": {"translation": {"type": "constant_velocity",
                                                               "velocity_m_per_s": (3, 1, 2)}}})
    r = evaluate_moving(s, uniform(), 0.5, "undefined", TOL_GEO)
    assert r.status == "verified"
    assert abs(r.emf_motional_V) < 1e-15 and abs(r.dflux_dt_V) < 1e-12


# ----------------------------------------------------- time-varying field, transformer EMF


def test_time_varying_field_with_stationary_geometry_is_transformer_only():
    w = 3.0
    fm = uniform_field_model(lambda t: np.array([0, 0, B0 * math.sin(w * t)]),
                             lambda t: np.array([0, 0, B0 * w * math.cos(w * t)]))
    s = FluxSurface.model_validate({"id": "s", "shape": {"type": "circle", "radius_m": 0.1},
                                    "motion": {}})
    r = evaluate_moving(s, fm, 0.2, "undefined", TOL_GEO)
    area = math.pi * 0.01
    assert r.status == "verified" and r.emf_motional_V == 0.0
    assert r.emf_V == pytest.approx(-B0 * w * math.cos(w * 0.2) * area, rel=1e-10)
    assert r.dflux_dt_V == pytest.approx(-r.emf_V, rel=1e-6)
    assert abs(r.difference_V) <= r.tolerance_V


def test_combined_transformer_and_motional_emf_satisfy_the_generalized_law():
    w, omega = 3.0, 10.0
    fm = uniform_field_model(lambda t: np.array([0, 0, B0 * math.sin(w * t)]),
                             lambda t: np.array([0, 0, B0 * w * math.cos(w * t)]))
    r = evaluate_moving(rotating(omega, shape={"type": "circle", "radius_m": 0.1}), fm, 0.1,
                        "undefined", TOL_GEO)
    t, a = 0.1, math.pi * 0.01
    dphi = a * B0 * (w * math.cos(w * t) * math.cos(omega * t)
                     - omega * math.sin(w * t) * math.sin(omega * t))
    assert r.status == "verified" and r.generalized_complete
    assert r.emf_V != 0 and r.emf_motional_V != 0
    assert r.emf_total_V == pytest.approx(r.emf_V + r.emf_motional_V, rel=1e-15)
    assert r.dflux_dt_V == pytest.approx(dphi, rel=1e-6)
    assert r.emf_total_V == pytest.approx(-dphi, rel=1e-10)
    assert r.reference is None  # the uniform references are for static fields only


def test_richardson_converges_for_smooth_functions_and_flags_jumps():
    d = richardson(math.sin, 0.3, 0.05, "central", 1e-12)
    assert d.converged and d.value == pytest.approx(math.cos(0.3), abs=1e-12)
    f = richardson(math.exp, 0.0, 0.05, "forward", 1e-9)
    assert f.converged and f.value == pytest.approx(1.0, abs=1e-9)
    b = richardson(math.exp, 0.0, 0.05, "backward", 1e-9)
    assert b.converged and b.value == pytest.approx(1.0, abs=1e-9)
    jump = richardson(lambda x: abs(x), 0.0, 0.1, "central", 1e-12)
    assert jump.converged and jump.value == 0.0  # symmetric: the central difference is 0
    bad = richardson(lambda x: math.nan, 0.0, 0.1, "central", 1e-12)
    assert not bad.converged


# -------------------------------------------------------------------- finite-coil scenes


def test_sliding_rod_preset_against_the_actual_local_field_and_blv():
    p = PRESET["sliding_rod_generator"]
    for t in (0.0, 0.1, 0.25):
        r = compute(p.scene, InductionRequest(surfaces=p.flux_surfaces, time_s=t), "s",
                    "1").surfaces[0]
        assert r.status == "verified"
        # Independent check: the rod's EMF from a direct quadrature of the solver's B along
        # the rod (v e_x × B · e_y dy = −v B_z dy).
        from emf_core.scene.currents import current_sources
        from emf_core.solvers.analytical import magnetostatics as ms
        x = -0.1 + 0.02 + 0.5 * t
        ys, ws = np.polynomial.legendre.leggauss(40)
        pts = np.column_stack([np.full(40, x), 0.05 * ys, np.zeros(40)])
        bz = ms.evaluate_bh(pts, current_sources(p.scene), 1e-12).b[:, 2]
        assert r.emf_motional_V == pytest.approx(-0.5 * float(bz @ ws) * 0.05, rel=1e-9)
        # The uniform-field reference BLv is an approximation: close, but not equal.
        ref = r.reference.emf_V
        assert abs(ref - r.emf_motional_V) / abs(r.emf_motional_V) < 0.05
        assert ref != pytest.approx(r.emf_motional_V, rel=1e-6)


def test_rotating_coil_preset_follows_the_generator_waveform():
    p = PRESET["rotating_coil_generator"]
    vals = []
    for t in np.linspace(0, 1, 9):
        r = compute(p.scene, InductionRequest(surfaces=p.flux_surfaces, time_s=float(t)), "s",
                    "1").surfaces[0]
        assert r.status == "verified", (t, r.status)
        vals.append((r.flux_Wb, r.emf_motional_V, r.reference.flux_Wb, r.reference.emf_V))
    v = np.array(vals)
    peak = np.abs(v[:, 1]).max()
    # Nearly uniform central field: the waveform is close to the ideal sinusoid.
    assert np.max(np.abs(v[:, 1] - v[:, 3])) < 0.01 * peak
    assert np.max(np.abs(v[:, 0] - v[:, 2])) < 0.01 * np.abs(v[:, 0]).max()
    assert v[0, 0] > 0 and abs(v[0, 1]) < 1e-3 * peak  # starts at maximum flux, zero EMF


def test_combined_preset_shows_both_contributions_separately():
    p = PRESET["combined_induction_motion"]
    r = compute(p.scene, InductionRequest(surfaces=p.flux_surfaces, time_s=0.3), "s",
                "1").surfaces[0]
    assert r.status == "verified" and r.generalized_complete
    assert abs(r.emf_V) > 0 and abs(r.emf_motional_V) > 0
    assert r.emf_total_V == pytest.approx(r.emf_V + r.emf_motional_V)
    assert abs(r.emf_total_V + r.dflux_dt_V) <= r.tolerance_V


def _scene(*objs: SceneObject) -> Scene:
    return Scene(objects=list(objs), domain=Domain(min_m=(-0.3,) * 3, max_m=(0.3,) * 3))


def test_time_varying_wire_gives_a_motional_only_result():
    wire = SceneObject(id="w", name="w", role=Role.CURRENT_SOURCE,
                       primitive=LinePrimitive(length_m=1.0),
                       source=InfiniteWireSource.model_validate({"current_A": 0.0, "profile": {
                           "type": "sinusoidal", "peak_A": 5.0, "frequency_Hz": 1.0}}))
    # The wire runs along z through the origin; a rod circuit moves in the xz plane beside it.
    s = FluxSurface.model_validate({
        "id": "r", "center_m": (0.05, 0.0, -0.05), "rotation_euler_xyz_rad": (math.pi / 2, 0, 0),
        "shape": {"type": "sliding_rod", "rail_separation_m": 0.1, "rail_length_m": 0.2,
                  "rod_position_m": 0.05,
                  "rod_motion": {"type": "constant_velocity", "velocity_m_per_s": (0.5, 0, 0)}}})
    r = compute(_scene(wire), InductionRequest(surfaces=[s], time_s=0.1), "s", "1").surfaces[0]
    assert r.status == "unsupported" and "Motional-only" in r.status_reason.en
    assert r.emf_motional_V is not None and r.emf_motional_V != 0
    assert r.emf_V is None and r.emf_total_V is None and not r.generalized_complete


def test_moving_surface_pierced_by_a_filament_is_singular():
    loop = SceneObject(id="l", name="l", role=Role.CURRENT_SOURCE,
                       primitive=RingPrimitive(radius_m=0.05),
                       source=CircularLoopSource(current_A=1.0))
    # A disk in the xz plane through the loop's ring: the filament pierces it.
    s = FluxSurface.model_validate({
        "id": "d", "shape": {"type": "circle", "radius_m": 0.03}, "center_m": (0.05, 0, 0),
        "rotation_euler_xyz_rad": (math.pi / 2, 0, 0),
        "motion": {"translation": {"type": "constant_velocity",
                                   "velocity_m_per_s": (0, 0, 0.01)}}})
    r = compute(_scene(loop), InductionRequest(surfaces=[s], time_s=0.0), "s", "1").surfaces[0]
    assert r.status == "singular" and r.flux_Wb is None


def test_stationary_surfaces_are_unchanged_by_phase_4b():
    p = PRESET["changing_b_in_loop"]
    req = InductionRequest(surfaces=p.flux_surfaces, time_s=0.3)
    r = compute(p.scene, req, "s", "1").surfaces[0]
    assert r.status == "verified" and not r.moving and r.motion is None
    assert r.derivative is None and r.emf_motional_V is None
    dumped = p.flux_surfaces[0].model_dump(mode="json")
    assert "motion" not in dumped and "turns" not in dumped  # persisted form unchanged
    assert "velocity_convention" not in req.model_dump(mode="json")
