"""Magnetic part of the probe (Phase 3A, extended in Phase 3B).

Values come from the magnetostatic engine at probe accuracy (float64, magnet quadrature to
1e-11). Besides B, H, ∇·B and ∇·H, the probe reports the material region and the constitutive
relation in force there, M inside a magnet, the nearest filament and magnet boundary, one-sided
limits on a current sheet or core surface (never an invented single value), each source's own
field, and clearly labelled comparisons with idealized models."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from emf_core import engine
from emf_core.i18n import L
from emf_core.scene.currents import (
    CurrentSources,
    IdealToroidSource,
    LoopSource,
    MagnetSource,
    current_sources,
    toroid_turn_angles,
)
from emf_core.scene.models import Scene, TorusPrimitive
from emf_core.scene.timedep import at_time, rates, time_state
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import magnetostatics as ms
from emf_core.solvers.base import TimeSourceInfo
from emf_core.units import MU0

from .orchestrator import Orchestrator
from .schemas import (
    MagneticContribution,
    OneSidedValue,
    ProbeComparison,
    ProbeMagnetic,
    ProbeValue,
)

Arr = NDArray[np.float64]
RTOL = ms.MAGNET_RTOL["probe"]
FILAMENT_KINDS = ("infinite_wire", "circular_loop", "solenoid", "toroid_finite")
ONE_SIDED_REL = 1e-6  # one-sided limits are evaluated at ± this × the object's size


def _values(b: Arr, h: Arr) -> list[ProbeValue]:
    out: list[ProbeValue] = []
    b_ok, h_ok = bool(np.all(np.isfinite(b))), bool(np.all(np.isfinite(h)))
    for q, sym, unit, vec, ok in (("B", "B", "T", b, b_ok), ("H", "H", "A/m", h, h_ok)):
        if ok:
            out.append(ProbeValue(quantity=q, symbol=sym, unit=unit, value=[float(x) for x in vec],
                                  magnitude=float(np.linalg.norm(vec)), kind="vector"))
        else:
            out.append(ProbeValue(quantity=q, symbol=sym, unit=unit, value=None, kind="vector",
                                  status="singular"))
    for q, sym, unit, ok in (("div_B", "∇·B", "T/m", b_ok), ("div_H", "∇·H", "A/m^2", h_ok)):
        out.append(ProbeValue(quantity=q, symbol=sym, unit=unit, value=0.0 if ok else None,
                              status="defined" if ok else "not_evaluated"))
    return out


def _vector_value(q: str, sym: str, unit: str, vec: Arr | None, singular: bool,
                  unsupported: bool) -> ProbeValue:
    """A vector probe value; undefined values are explicit (never shown as zero)."""
    if unsupported or vec is None:
        return ProbeValue(quantity=q, symbol=sym, unit=unit, value=None, kind="vector",
                          status="not_evaluated")
    if singular or not bool(np.all(np.isfinite(vec))):
        return ProbeValue(quantity=q, symbol=sym, unit=unit, value=None, kind="vector",
                          status="singular")
    return ProbeValue(quantity=q, symbol=sym, unit=unit, value=[float(x) for x in vec],
                      magnitude=float(np.linalg.norm(vec)), kind="vector")


def _single(cs: CurrentSources, obj_id: str) -> CurrentSources:
    """The sources of one object only."""
    return CurrentSources(
        wires=[w for w in cs.wires if w.object_id == obj_id],
        loops=[lp for lp in cs.loops if lp.object_id == obj_id], problems=[],
        magnets=[m for m in cs.magnets if m.object_id == obj_id],
        ideal_toroids=[t for t in cs.ideal_toroids if t.object_id == obj_id],
        objects=[o for o in cs.objects if o.object_id == obj_id])


def _comparisons(scene: Scene, cs: CurrentSources, p: Arr, r_min: float
                 ) -> list[ProbeComparison]:
    out: list[ProbeComparison] = []
    prims = {o.id: o.primitive for o in scene.objects}
    for obj in cs.objects:
        if obj.kind == "solenoid" and obj.turns > 1 and obj.params["length_m"] > 0:
            assert obj.center_m is not None and obj.axis is not None
            a, length = obj.params["radius_m"], obj.params["length_m"]
            n = obj.turns / length
            d = p - obj.center_m
            z = float(d @ obj.axis)
            rho = float(np.linalg.norm(d - z * obj.axis))
            inside = rho < a and abs(z) < length / 2
            b = MU0 * n * (obj.current_A or 0.0) * obj.axis if inside else np.zeros(3)
            if not inside:
                note = L("Outside the winding: the ideal long solenoid has no field here, while "
                         "the finite solenoid does (fringe and return field). Not applicable here.",
                         "A tekercsen kívül: az ideális hosszú szolenoidnak itt nincs tere, a "
                         "véges szolenoidnak van (szórt és visszatérő tér). Itt nem alkalmazható.")
                ok = False
            elif abs(z) > length / 2 - a:
                note = L("Inside, but within one radius of an end: the ideal approximation is "
                         "inappropriate here (end effects).",
                         "Belül, de egy sugárnyira a végtől: az ideális közelítés itt nem "
                         "megfelelő (véghatások).")
                ok = False
            else:
                note = L(f"Inside, away from the ends: B ≈ μ₀nI with n = N/L = {n:.4g} 1/m. Valid "
                         f"for a long coil (L/a = {length / a:.3g}).",
                         f"Belül, a végektől távol: B ≈ μ₀nI, n = N/L = {n:.4g} 1/m. Hosszú "
                         f"tekercsre érvényes (L/a = {length / a:.3g}).")
                ok = True
            out.append(ProbeComparison(object_id=obj.object_id, kind="ideal_long_solenoid",
                                       B_T=[float(x) for x in b],
                                       H_A_per_m=[float(x) for x in b / MU0], applicable=ok,
                                       note=note))
        elif obj.kind in ("toroid_finite", "toroid_ideal"):
            prim = prims[obj.object_id]
            assert isinstance(prim, TorusPrimitive) and obj.center_m is not None
            assert obj.axis is not None
            mine = _single(cs, obj.object_id)
            if obj.kind == "toroid_finite":
                t0 = mine.loops[0]
                ideal = IdealToroidSource(obj.object_id, obj.current_A or 0.0, obj.turns,
                                          obj.center_m, obj.axis, t0.u, prim.major_radius_m,
                                          prim.core_radius_m, 1.0)
                tol_b = ms.sheet_tolerance(cs, r_min)
                b, h, _ = ms.ideal_toroid_fields(p[None, :], ideal, tol_b)
                kind: Literal["ideal_toroid", "finite_toroid"] = "ideal_toroid"
                note = L("Ideal continuous-winding toroid with the same R, N, I and its own core "
                         f"radius b_core = {prim.core_radius_m:.4g} m, μᵣ = 1 (idealization: "
                         "zero field outside the core).",
                         "Ideális, folytonos tekercselésű toroid ugyanazzal az R, N, I értékkel "
                         f"és saját magsugarával, b_core = {prim.core_radius_m:.4g} m, μᵣ = 1 "
                         "(idealizáció: a magon kívül nulla tér).")
            else:
                ideal_src = mine.ideal_toroids[0]
                v = np.cross(ideal_src.axis, ideal_src.u)
                loops = []
                for phi in toroid_turn_angles(prim.turns, prim.phase_rad):
                    e_rho = math.cos(phi) * ideal_src.u + math.sin(phi) * v
                    e_phi = -math.sin(phi) * ideal_src.u + math.cos(phi) * v
                    loops.append(LoopSource(obj.object_id, ideal_src.current_A,
                                            obj.center_m + prim.major_radius_m * e_rho, e_phi,
                                            prim.winding_radius_m, e_rho, "toroid_finite"))
                finite = CurrentSources(wires=[], loops=loops, problems=[])
                b = ms.evaluate(p[None, :], finite, r_min)
                h = b / MU0
                kind = "finite_toroid"
                note = L(f"Finite-turn model with the same R, N, I and its own winding radius "
                         f"b_winding = {prim.winding_radius_m:.4g} m, in vacuum (no core).",
                         f"Véges menetszámú modell ugyanazzal az R, N, I értékkel és saját "
                         f"menetsugarával, b_winding = {prim.winding_radius_m:.4g} m, vákuumban "
                         "(mag nélkül).")
            ok = bool(np.all(np.isfinite(b)))
            out.append(ProbeComparison(object_id=obj.object_id, kind=kind,
                                       B_T=[float(x) for x in b[0]] if ok else None,
                                       H_A_per_m=[float(x) for x in h[0]] if ok else None,
                                       applicable=ok, note=note))
        elif obj.kind == "permanent_magnet":
            mg = next(m for m in cs.magnets if m.object_id == obj.object_id)
            r = p - mg.center_m
            dist = float(np.linalg.norm(r))
            size = max(mg.radius_m, mg.length_m)
            if dist == 0:
                continue
            rh = r / dist
            mom = mg.moment_A_m2
            b = MU0 / (4 * math.pi * dist**3) * (3 * float(mom @ rh) * rh - mom)
            far = dist >= 5 * size
            out.append(ProbeComparison(
                object_id=obj.object_id, kind="dipole_far_field", B_T=[float(x) for x in b],
                H_A_per_m=[float(x) for x in b / MU0], applicable=far,
                note=L(f"Point dipole m = Mπa²L = {np.linalg.norm(mom):.4g} A·m²: a far-field "
                       "approximation only" + ("" if far else " — this point is too close "
                                               f"(r < 5 × {size:.3g} m); the full "
                                               "surface-current result above is the field."),
                       f"Pontszerű dipólus, m = Mπa²L = {np.linalg.norm(mom):.4g} A·m²: csak "
                       "távoltéri közelítés" + ("" if far else " — ez a pont túl közel van "
                                                f"(r < 5 × {size:.3g} m); a tér a fenti teljes "
                                                "felületi áramos eredmény."))))
    return out


def magnetic_probe(scene: Scene, point_m: tuple[float, float, float],
                   orch: Orchestrator, time_s: float = 0.0) -> ProbeMagnetic:
    sub = engine.field_subscene(scene, "magnetic")
    request = SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "probe", "points_m": [point_m]}],
        "quantities": ["B"]})
    solver = orch.select(sub, request)  # refuses unsupported scenes with reasons
    cs0 = current_sources(sub)
    ts = time_state(sub, cs0, time_s)
    cs = at_time(cs0, ts)  # every current at the simulation time (Phase 4A)
    cs_rate = rates(cs0, ts)
    r_min = ms.COINCIDENCE_FACTOR * sub.domain.diagonal_m
    tol = ms.sheet_tolerance(cs, r_min)
    p = np.asarray(point_m, np.float64)
    ev = ms.evaluate_bh(p[None, :], cs, r_min, RTOL)
    b, h, m = ev.b[0], ev.h[0], ev.m[0]
    status_code = int(ev.status[0])
    status: Literal["defined", "singular", "sheet", "end_face", "core_boundary"] = (
        "defined", "singular", "sheet", "end_face", "core_boundary")[status_code]
    material: Literal["vacuum", "magnet", "core"] = ("vacuum", "magnet", "core")[
        int(ev.material[0])]
    names = {o.id: o.name or o.id for o in sub.objects}

    contributions: list[MagneticContribution] = []
    singular_id = singular_kind = None
    nearest_id, nearest_d = None, float("inf")
    for obj, bi in zip(cs.objects, ms.source_fields(p[None, :], cs, r_min, RTOL), strict=True):
        one = _single(cs, obj.object_id)
        d_fil = float(ms.distance_to_sources(p[None, :], one)[0])
        d_bnd = float(ms.distance_to_boundaries(p[None, :], one)[0])
        dist = min(d_fil, d_bnd)
        if obj.kind == "permanent_magnet":
            dist = float(ms.distance_to_magnet_surface(p[None, :], one.magnets[0])[0])
        if dist < nearest_d:
            nearest_d, nearest_id = dist, obj.object_id
        hi = ms.source_h(p[None, :], cs, obj.object_id, bi, tol)
        ok = bool(np.all(np.isfinite(bi[0])))
        # A filament source's field is undefined only where the engine found the point
        # indistinguishable from one of its filaments (source-scaled tolerance, Phase 3B.1).
        if not ok and obj.kind in FILAMENT_KINDS and singular_id is None:
            singular_id, singular_kind = obj.object_id, obj.kind
        rate_one = _single(cs_rate, obj.object_id)
        db_i = e_i = None
        st = next((x for x in ts.sources if x.object_id == obj.object_id), None)
        if st is not None:
            dbv = ms.evaluate_bh(p[None, :], rate_one, r_min, RTOL).b[0]
            db_i = [float(x) for x in dbv] if bool(np.all(np.isfinite(dbv))) else None
            if st.induction_supported or not st.varying:
                ev_ = -ms.loops_vector_potential(rate_one.loops, p[None, :])[0][0]
                e_i = [float(x) for x in ev_] if bool(np.all(np.isfinite(ev_))) else None
        contributions.append(MagneticContribution(
            dI_dt_A_per_s=st.rate.value if st is not None else None, dB_dt_T_per_s=db_i,
            E_ind_V_per_m=e_i,
            object_id=obj.object_id, name=names.get(obj.object_id, obj.object_id), kind=obj.kind,
            current_A=float(obj.current_A or 0.0), turns=obj.turns,
            magnetization_A_per_m=obj.magnetization_A_per_m, distance_m=dist,
            B_T=[float(x) for x in bi[0]] if ok else None,
            B_magnitude_T=float(np.linalg.norm(bi[0])) if ok else None,
            H_A_per_m=[float(x) for x in hi[0]] if bool(np.all(np.isfinite(hi[0]))) else None,
            H_magnitude_A_per_m=(float(np.linalg.norm(hi[0]))
                                 if bool(np.all(np.isfinite(hi[0]))) else None)))

    # Nearest magnet boundary, and one-sided limits on a sheet, end face or core surface.
    bnd_id, bnd_d = None, None
    for mg in cs.magnets:
        d = float(ms.distance_to_magnet_surface(p[None, :], mg)[0])
        if bnd_d is None or d < bnd_d:
            bnd_id, bnd_d = mg.object_id, d
    one_sided: list[OneSidedValue] = []
    if status in ("sheet", "end_face", "core_boundary"):
        normal, size = _boundary_normal(p, cs, status)
        delta = ONE_SIDED_REL * size
        for side, sgn in (("inside", -1.0), ("outside", 1.0)):
            q = p + sgn * delta * normal
            e2 = ms.evaluate_bh(q[None, :], cs, r_min, RTOL)
            one_sided.append(OneSidedValue(
                side=side, offset_m=delta,
                B_T=[float(x) for x in e2.b[0]] if np.all(np.isfinite(e2.b[0])) else None,
                H_A_per_m=[float(x) for x in e2.h[0]] if np.all(np.isfinite(e2.h[0])) else None))
    # Time-dependent quantities (Phase 4A).
    db = ms.evaluate_bh(p[None, :], cs_rate, r_min, RTOL).b[0]
    e_ok = not ts.unsupported_ids
    e_ind = -ms.loops_vector_potential(cs_rate.loops, p[None, :])[0][0] if e_ok else None
    time_values = [
        _vector_value("dB_dt", "∂B/∂t", "T/s", db, status == "singular", False),
        _vector_value("E_ind", "E_ind", "V/m", e_ind, status == "singular", not e_ok)]
    fil_d, fil_scale = ms.nearest_filament(p[None, :], cs)
    sing_tol = (float(ms.filament_tolerance(fil_scale)[0]) if math.isfinite(float(fil_d[0]))
                else r_min)
    prec = float(ev.precision[0])
    rel = (next(t.relative_permeability for t in cs.ideal_toroids) if material == "core"
           else None)
    return ProbeMagnetic(
        solver_id=solver.id, solver_version=solver.version,
        classification=("idealized_model" if cs.ideal_toroids else "numerical_approximation"
                        if cs.magnets else "exact_analytical"),
        defined=status == "defined", status=status, singular_tolerance_m=sing_tol,
        relative_precision_bound=prec if prec > 0 else None,
        boundary_tolerance_m=tol, singular_object_id=singular_id, singular_kind=singular_kind,
        values=_values(b, h), nearest_source_id=nearest_id,
        nearest_source_distance_m=nearest_d if nearest_id is not None else None,
        contributions=contributions, mu0_H_per_m=MU0, material=material,
        constitutive=("magnetization" if material == "magnet" else
                      "linear_core" if material == "core" else "vacuum"),
        M_A_per_m=[float(x) for x in m] if material == "magnet" else None,
        relative_permeability=rel, nearest_magnet_id=bnd_id,
        nearest_magnet_boundary_m=bnd_d, one_sided=one_sided,
        comparisons=_comparisons(sub, cs, p, r_min), quadrature_converged=ev.unconverged == 0,
        time_s=ts.t_s, time_dependent=ts.time_dependent, e_ind_available=e_ok,
        derivative_unique=ts.derivative_unique, time_values=time_values,
        time_sources=[TimeSourceInfo(
            object_id=x.object_id, kind=x.kind, profile_type=x.profile_type,
            current_A=x.current_A, dI_dt_A_per_s=x.rate.right, dI_dt_left_A_per_s=x.rate.left,
            derivative_unique=x.rate.unique, induction_supported=x.induction_supported)
            for x in ts.sources])


def _boundary_normal(p: Arr, cs: CurrentSources, status: str) -> tuple[Arr, float]:
    """Outward unit normal of the boundary the point lies on, and the object's size."""
    if status == "core_boundary":
        t = cs.ideal_toroids[0]
        d = p - t.center_m
        z = float(d @ t.axis)
        rv = d - z * t.axis
        rho = float(np.linalg.norm(rv))
        ring = t.center_m + t.major_radius_m * rv / rho
        n = (p - ring) / float(np.linalg.norm(p - ring))
        return n, t.core_radius_m
    mg: MagnetSource = min(cs.magnets, key=lambda m: float(
        ms.distance_to_magnet_surface(p[None, :], m)[0]))
    _, zl, rhat = ms.magnet_local(p[None, :], mg)
    size = max(mg.radius_m, mg.length_m)
    if status == "end_face":
        return float(np.sign(zl[0])) * mg.axis, size
    return rhat[0], size

