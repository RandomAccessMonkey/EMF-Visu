"""Phase 4A: magnetic flux through stationary surfaces, Faraday's law ∮E_ind·dl = -dPhi/dt,
Lenz's-law signs and mutual induction.

Independent references:
* flux through a coaxial disk: QUADPACK over rho of B_z from ``bs.loop_local_reference`` (direct
  Biot–Savart, no elliptic integrals), Phi = ∫_0^R B_z(rho, z) 2 pi rho drho;
* mutual inductance of two coaxial circles: Maxwell's closed form
  M = mu0 sqrt(a b) [(2/k - k) K(k) - (2/k) E(k)], k^2 = 4ab / ((a+b)^2 + d^2);
* in the solver the two sides of Faraday's law come from different fields (B on the surface, A on
  the boundary) and different quadratures, so their agreement is itself a Stokes check.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import ellipe, ellipk

from emf_core import induction
from emf_core.induction import _area2, _triangulate
from emf_core.units import MU0
from emf_core.verification import biot_savart as bs
from tests.conftest import loop, magnet, scene_of, solenoid, torus, wire

pytestmark = pytest.mark.filterwarnings("error::scipy.integrate.IntegrationWarning")

SINE = {"type": "sinusoidal", "dc_A": 0.0, "peak_A": 2.0, "frequency_Hz": 1.0, "phase_rad": 0.0}
RAMP = {"type": "ramp", "start_A": 0.0, "slope_A_per_s": 5.0, "t_start_s": 0.0, "t_end_s": 1.0}


def with_profile(obj, profile, current0):
    obj["source"]["profile"] = profile
    obj["source"]["current_A"] = current0
    return obj


def circle(r, center=(0, 0, 0), rot=(0, 0, 0), reversed_=False, rtol=1e-4, sid="S"):
    return {"id": sid, "shape": {"type": "circle", "radius_m": r}, "center_m": center,
            "rotation_euler_xyz_rad": rot, "reversed": reversed_, "rtol": rtol}


def compute(objs, surfaces, t, mutual=True, **scene_extra):
    req = induction.InductionRequest.model_validate({"surfaces": list(surfaces), "time_s": t,
                                                     "mutual": mutual})
    return induction.compute(scene_of(*objs, **scene_extra), req, "t", "0").surfaces


def disk_flux_reference(a, rr, z):
    def bz(rho):
        # 5e-14: QUADPACK's estimate floors near 2e-14 on some sub-intervals here; the outer
        # integral needs only 1e-10.
        return bs.loop_local_reference(rho - a, rho, z, a, 1.0,
                                       epsrel=5e-14)[1] * 2 * math.pi * rho
    pts = [x for x in (a,) if 0 < x < rr]
    # B_z changes sign near rho = a for disks wider than the loop: the tolerance is set on
    # 1e-10 of ∫|f| (a relative tolerance cannot be met for a cancelling integral), and the inner
    # reference (~2e-14) limits how far the outer estimate can be certified.
    scale = quad(lambda r: abs(bz(r)), 0.0, rr, epsabs=0.0, epsrel=1e-6, points=pts or None,
                 limit=200)[0]
    return quad(bz, 0.0, rr, epsabs=1e-10 * scale, epsrel=1e-10, points=pts or None,
                limit=200)[0]


def maxwell_m(a, b, d):
    k2 = 4 * a * b / ((a + b) ** 2 + d * d)
    k = math.sqrt(k2)
    return MU0 * math.sqrt(a * b) * ((2 / k - k) * ellipk(k2) - 2 / k * ellipe(k2))


# ------------------------------------------------------------------- flux and mutual


@pytest.mark.parametrize("rr,z", [(0.03, 0.02), (0.08, 0.02), (0.03, -0.05), (0.2, 0.1)])
def test_coaxial_flux_against_independent_quadrature_and_maxwell(rr, z):
    (r,) = compute([loop("l", 1.0, 0.05)], [circle(rr, (0, 0, z), rtol=1e-8)], 0.0)
    assert r.status == "verified"
    ref = disk_flux_reference(0.05, rr, z)
    unit = r.sources[0].unit_flux_Wb_per_A
    assert unit == pytest.approx(ref, rel=1e-8)
    assert unit == pytest.approx(maxwell_m(0.05, rr, z), rel=1e-9)
    m = r.mutual[0]
    assert pytest.approx(maxwell_m(0.05, rr, z), rel=1e-9) == m.M21_H and m.reciprocity_ok
    assert r.flux_Wb == pytest.approx(unit, rel=1e-15)  # I = 1 A


def test_flux_converges_under_refinement():
    ref = maxwell_m(0.05, 0.045, 0.002)  # a disk just inside the wire, close to its plane
    errs = []
    for rtol in (1e-3, 1e-5, 1e-7, 1e-9):
        (r,) = compute([loop("l", 1.0, 0.05)], [circle(0.045, (0, 0, 0.002), rtol=rtol)], 0.0,
                       mutual=False)
        assert r.surface_converged
        err = abs(r.sources[0].unit_flux_Wb_per_A - ref)
        assert err <= max(r.sources[0].unit_flux_error, 1e-6 * rtol * abs(ref)) + 1e-14 * ref
        errs.append(err / ref)
    assert errs[-1] < 1e-9 and errs[-1] <= errs[0]


def test_flux_near_the_wire_with_a_rapidly_varying_field():
    """Disk of radius 1.2a just 1e-3 a above the loop plane: B·n is sharply peaked over the
    wire; the adaptive quadrature still converges to the reference."""
    a = 0.05
    (r,) = compute([loop("l", 1.0, a)], [circle(1.2 * a, (0, 0, 1e-3 * a), rtol=1e-6)], 0.0,
                   mutual=False)
    assert r.status == "verified" and r.surface_converged
    assert r.sources[0].unit_flux_Wb_per_A == pytest.approx(maxwell_m(a, 1.2 * a, 1e-3 * a),
                                                            rel=1e-6)


def test_normal_reversal_rigid_motion_and_polygon_area():
    base = compute([loop("l", 1.0, 0.05)], [circle(0.04, (0, 0, 0.03))], 0.0)[0]
    rev = compute([loop("l", 1.0, 0.05)], [circle(0.04, (0, 0, 0.03), reversed_=True)], 0.0)[0]
    assert rev.flux_Wb == pytest.approx(-base.flux_Wb, rel=1e-12)
    assert np.allclose(rev.normal, [0, 0, -1]) and np.allclose(base.normal, [0, 0, 1])
    # Move and rotate source and surface together: the flux is unchanged.
    rot, shift = (0.4, -0.3, 0.2), np.array([0.3, -0.1, 0.25])
    from emf_core.scene.transforms import rotation_matrix_xyz
    rmat = rotation_matrix_xyz(rot)
    moved = compute([loop("l", 1.0, 0.05, tuple(shift), rot)],
                    [circle(0.04, tuple(shift + rmat @ np.array([0, 0, 0.03])), rot)], 0.0)[0]
    assert moved.flux_Wb == pytest.approx(base.flux_Wb, rel=1e-9)
    concave = np.array([[0, 0], [4, 0], [4, 3], [2, 1], [0, 3]], float)
    tris = _triangulate(concave)
    assert len(tris) == 3
    assert sum(abs(_area2(np.array(t))) for t in tris) == pytest.approx(abs(_area2(concave)))


def test_rectangle_and_polygon_surfaces_verify():
    src = with_profile(solenoid(turns=5, radius=0.04, length=0.05), SINE, 0.0)
    rect = {"id": "R", "shape": {"type": "rectangle", "width_m": 0.05, "height_m": 0.06},
            "center_m": (0.07, 0, 0)}
    poly = {"id": "P", "shape": {"type": "polygon", "closed": True, "vertices_m": [
        [-0.03, -0.02, 0], [0.04, -0.03, 0], [0.02, 0.0, 0], [0.05, 0.04, 0], [-0.02, 0.03, 0]]},
        "center_m": (0, 0, 0.06)}
    for r in compute([src], [rect, poly], 0.1):
        assert r.status == "verified", (r.surface_id, r.status)
        assert r.relative_error is not None and r.relative_error < 1e-6
        assert r.mutual[0].reciprocity_ok


# ------------------------------------------------------------------------- Faraday's law


@pytest.mark.parametrize("rr,z,rot", [(0.03, 0.02, (0, 0, 0)), (0.08, -0.01, (0, 0, 0)),
                                      (0.04, 0.03, (0.5, 0.2, 0.0))])
def test_faraday_over_a_sinusoidal_period(rr, z, rot):
    src = with_profile(loop("l", 0.0, 0.05, (0, 0, 0), rot), SINE, 0.0)
    for t in np.linspace(0, 1, 9):
        (r,) = compute([src], [circle(rr, (0, 0, z))], float(t), mutual=False)
        assert r.status == "verified", (t, r.status)
        assert r.emf_V == pytest.approx(-r.dflux_dt_V, rel=1e-6, abs=r.tolerance_V)
        # Analytical time dependence of the result itself.
        unit = r.sources[0].unit_flux_Wb_per_A
        assert r.flux_Wb == pytest.approx(2 * math.sin(2 * math.pi * t) * unit, abs=1e-20)
        assert r.dflux_dt_V == pytest.approx(4 * math.pi * math.cos(2 * math.pi * t) * unit,
                                             abs=1e-20)


def test_faraday_ramp_increasing_decreasing_and_constant():
    up = with_profile(loop("l", 0.0, 0.05), RAMP, 0.0)
    down = with_profile(loop("l", 0.0, 0.05), {**RAMP, "slope_A_per_s": -5.0}, 0.0)
    surf = [circle(0.03, (0, 0, 0.02))]
    ru, rd = compute([up], surf, 0.5)[0], compute([down], surf, 0.5)[0]
    assert ru.status == rd.status == "verified"
    assert ru.emf_V < 0 < rd.emf_V and ru.emf_V == pytest.approx(-rd.emf_V, rel=1e-12)
    assert ru.lenz.flux_trend == "increasing" and ru.lenz.circulation == "against_path"
    assert rd.lenz.flux_trend == "decreasing" and rd.lenz.circulation == "along_path"
    after = compute([up], surf, 2.0)[0]  # ramp finished: constant current
    assert after.status == "verified" and after.no_change
    assert after.emf_V == 0.0 and after.dflux_dt_V == 0.0
    assert after.lenz.flux_trend == "steady" and after.lenz.circulation == "none"
    const = compute([loop("l", 3.0, 0.05)], surf, 0.7)[0]
    assert const.emf_V == 0.0 and const.flux_Wb != 0.0


def test_extremum_of_a_sinusoid_is_steady():
    (r,) = compute([with_profile(loop("l", 0.0, 0.05), SINE, 0.0)], [circle(0.03, (0, 0, 0.02))],
                   0.25, mutual=False)
    assert r.lenz.flux_trend == "steady" and r.status == "verified"


def test_reversed_boundary_and_normal_keep_faraday():
    src = with_profile(loop("l", 0.0, 0.05), SINE, 0.0)
    f = compute([src], [circle(0.03, (0, 0, 0.02))], 0.1)[0]
    b = compute([src], [circle(0.03, (0, 0, 0.02), reversed_=True)], 0.1)[0]
    assert b.status == "verified"
    assert b.emf_V == pytest.approx(-f.emf_V, rel=1e-10)
    assert b.dflux_dt_V == pytest.approx(-f.dflux_dt_V, rel=1e-10)
    assert b.lenz.flux_trend != f.lenz.flux_trend


def test_superposition_and_static_magnet_background():
    a = with_profile(loop("a", 0.0, 0.05), SINE, 0.0)
    b = with_profile(loop("b", 1.0, 0.03, (0, 0, 0.06)), {**RAMP, "start_A": 1.0}, 1.0)
    surf = [circle(0.04, (0, 0, 0.03))]
    both = compute([a, b], surf, 0.3)[0]
    sa, sb = compute([a], surf, 0.3)[0], compute([b], surf, 0.3)[0]
    assert both.status == "verified"
    assert both.emf_V == pytest.approx(sa.emf_V + sb.emf_V, rel=1e-10)
    m = magnet(m=5e5, pos=(0, 0, 0.3), radius=0.02, length=0.04)
    with_m = compute([a, m], surf, 0.3)[0]
    assert with_m.status == "verified"
    assert with_m.dflux_dt_V == pytest.approx(sa.dflux_dt_V, rel=1e-12)
    assert with_m.flux_Wb != pytest.approx(sa.flux_Wb, rel=1e-6)
    assert with_m.static_flux_Wb != 0.0


def test_coil_presets_like_configurations_verify():
    sol = with_profile(solenoid(turns=20, radius=0.04, length=0.2), RAMP, 0.0)
    (r,) = compute([sol], [circle(0.03, (0, 0, 0.12))], 0.5)
    assert r.status == "verified" and r.lenz.circulation == "against_path"
    phi = math.pi / 24
    tor = with_profile(torus(turns=24), {**SINE, "frequency_Hz": 50.0}, 0.0)
    rect = {"id": "T", "shape": {"type": "rectangle", "width_m": 0.1, "height_m": 0.1},
            "center_m": (0.12 * math.cos(phi), 0.12 * math.sin(phi), 0.0),
            "rotation_euler_xyz_rad": (math.pi / 2, 0.0, phi)}
    (t,) = compute([tor], [rect], 0.001)
    assert t.status == "verified" and t.mutual[0].reciprocity_ok


# -------------------------------------------------------------- invalid and singular cases


def test_invalid_surfaces_are_rejected():
    bad = {"id": "B", "shape": {"type": "polygon", "closed": True, "vertices_m": [
        [0, 0, 0], [0.1, 0.1, 0], [0.1, 0, 0], [0, 0.1, 0]]}}
    (r,) = compute([loop("l", 1.0, 0.05)], [bad], 0.0)
    assert r.status == "invalid" and not r.valid and r.flux_Wb is None
    assert any("intersects itself" in x.en for x in r.invalid_reasons)


def test_filament_in_or_through_the_surface_is_singular_not_zero():
    # Coplanar disk larger than the loop: the wire lies in the surface.
    (r,) = compute([loop("l", 1.0, 0.05)], [circle(0.08)], 0.0)
    assert r.status == "singular" and r.flux_Wb is None and r.status_reason is not None
    # A wire through the surface.
    (w,) = compute([wire("w", 2.0, (0.01, 0, 0))], [circle(0.05)], 0.0)
    assert w.status == "singular" and w.flux_Wb is None
    # The boundary through a filament.
    (b,) = compute([loop("l", 1.0, 0.05)], [circle(0.05)], 0.0)
    assert b.status == "singular"


def test_time_varying_wire_flux_shown_but_emf_unsupported():
    w = with_profile(wire("w", 0.0, (0.0, 0.2, 0.0), (math.pi / 2, 0, 0)), SINE, 0.0)
    (r,) = compute([w], [circle(0.05, (0, 0, 0))], 0.1)
    # The wire runs along y at y = 0.2 m... it is parallel to the disk plane and off it.
    assert r.status in ("unsupported", "singular")
    w2 = with_profile(wire("w", 0.0, (0.0, 0.0, 0.2), (0, math.pi / 2, 0)), SINE, 0.0)
    (r2,) = compute([w2], [circle(0.05, (0, 0, 0))], 0.1)
    assert r2.status == "unsupported" and r2.emf_V is None
    assert r2.flux_Wb is not None and r2.dflux_dt_V is not None
    assert r2.mutual[0].available is False


# ------------------------------------------------------------------------ mutual induction


def test_mutual_inductance_is_independent_of_amplitude_and_flips_with_orientation():
    surf = [circle(0.03, (0, 0, 0.04))]
    m2 = compute([with_profile(loop("l", 0.0, 0.05), SINE, 0.0)], surf, 0.1)[0].mutual[0]
    m7 = compute([with_profile(loop("l", 0.0, 0.05), {**SINE, "peak_A": 7.0}, 0.0)], surf,
                 0.1)[0].mutual[0]
    assert m2.M12_H == m7.M12_H and m2.M21_H == m7.M21_H
    assert m2.reciprocity_ok and m2.reciprocity_relative < 1e-8
    rev = compute([loop("l", 1.0, 0.05)], [circle(0.03, (0, 0, 0.04), reversed_=True)],
                  0.0)[0].mutual[0]
    assert pytest.approx(-m2.M12_H, rel=1e-12) == rev.M12_H
    assert pytest.approx(-m2.M21_H, rel=1e-9) == rev.M21_H
    # EMF_2 = -M12 dI1/dt
    (r,) = compute([with_profile(loop("l", 0.0, 0.05), SINE, 0.0)], surf, 0.1)
    assert r.emf_V == pytest.approx(-m2.M12_H * 4 * math.pi * math.cos(0.2 * math.pi),
                                    rel=1e-6)


def test_mutual_reciprocity_for_tilted_and_offset_loops():
    src = loop("l", 1.0, 0.05, (0.02, -0.01, 0.0), (0.3, 0.1, 0.0))
    for surf in (circle(0.04, (0.05, 0.02, 0.07), (0.0, 0.6, 0.0)),
                 {"id": "R", "shape": {"type": "rectangle", "width_m": 0.06, "height_m": 0.03},
                  "center_m": (0.0, 0.0, -0.06), "rotation_euler_xyz_rad": (0.2, 0.0, 0.4)}):
        (r,) = compute([src], [surf], 0.0)
        m = r.mutual[0]
        assert r.status == "verified" and m.reciprocity_ok, (m.M12_H, m.M21_H)
        assert m.reciprocity_relative < 1e-6
