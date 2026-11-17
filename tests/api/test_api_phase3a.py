"""API tests for Phase 3A: magnetic requests and units, simultaneous E and B in the probe,
singular state on a filament, equation applicability derived from the scene, presets 9-11,
independent electric and magnetic caches, persistence and backward compatibility."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire as wire_format
from emf_core.units import MU0
from tests.conftest import charge, loop, wire

V1 = "/api/v1"


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def magnetic_request(points):
    return {"samplings": [{"kind": "points", "id": "p", "points_m": points}],
            "quantities": ["B", "H", "div_B", "div_H"]}


def solve(client, scene, request):
    r = client.post(f"{V1}/simulations", json={"scene": scene, "request": request})
    assert r.status_code == 200, r.text
    header, arrays = wire_format.decode(r.content)
    return header, arrays, r.headers["X-EMF-Cache"]


def test_magnetic_solve_returns_b_and_h_with_units(client):
    header, arrays, _ = solve(client, {"objects": [wire("w", 10.0)]},
                              magnetic_request([[1.0, 0, 0]]))
    assert header["solver_id"] == "analytical.magnetostatics.filaments"
    assert header["classification"] == "exact_analytical"
    units = {a["quantity"]: a["unit"] for a in header["arrays"]}
    assert units == {"B": "T", "H": "A/m", "div_B": "T/m", "div_H": "A/m^2"}
    assert arrays["p.B"][0][1] == pytest.approx(2e-6 * MU0 / (4e-7 * math.pi), rel=1e-6)
    assert arrays["p.H"][0][1] == pytest.approx(10 / (2 * math.pi), rel=1e-6)
    assert header["model_context"]["regime"] == "magnetostatic"
    assert header["current_sources"][0]["kind"] == "infinite_wire"


def test_mixed_electric_and_magnetic_quantities_are_rejected(client):
    r = client.post(f"{V1}/simulations", json={
        "scene": {}, "request": {"samplings": [{"kind": "points", "id": "p",
                                                 "points_m": [[0, 0, 0]]}],
                                 "quantities": ["E", "B"]}})
    assert r.status_code == 422


def test_probe_shows_e_and_b_simultaneously_without_mixing_them(client):
    scene = {"objects": [charge("q", 1e-9, (0, 0, 0)), wire("w", 10.0, (0.5, 0, 0), name="W")]}
    p = client.post(f"{V1}/probe", json={"scene": scene, "point_m": [0.5, 1.0, 0.0]}).json()
    electric = {v["quantity"]: v for v in p["values"]}
    magnetic = {v["quantity"]: v for v in p["magnetic"]["values"]}
    assert set(electric) == {"E", "phi", "D", "div_E", "curl_E", "div_D", "curl_D"}
    assert set(magnetic) == {"B", "H", "div_B", "div_H"}
    assert electric["E"]["unit"] == "V/m" and magnetic["B"]["unit"] == "T"
    assert magnetic["H"]["unit"] == "A/m"
    # The wire does not change E; the charge does not change B.
    e_only = client.post(f"{V1}/probe", json={"scene": {"objects": [scene["objects"][0]]},
                                              "point_m": [0.5, 1.0, 0.0]}).json()
    assert electric["E"]["value"] == {v["quantity"]: v for v in e_only["values"]}["E"]["value"]
    b = np.array(magnetic["B"]["value"])
    h = np.array(magnetic["H"]["value"])
    assert np.allclose(b, MU0 * h, rtol=1e-15)
    assert np.linalg.norm(b) == pytest.approx(MU0 * 10 / (2 * math.pi * 1.0), rel=1e-12)
    assert magnetic["div_B"]["value"] == 0.0
    m = p["magnetic"]
    assert m["nearest_source_id"] == "w" and m["nearest_source_distance_m"] == pytest.approx(1.0)
    assert m["mu0_H_per_m"] == MU0 and m["defined"] is True


def test_probe_contributions_sum_to_the_total(client):
    scene = {"objects": [wire("a", 10.0, (-0.5, 0, 0)), wire("b", -4.0, (0.5, 0, 0)),
                         loop("l", 3.0, 0.4, (0, 0.2, 0.1))]}
    m = client.post(f"{V1}/probe", json={"scene": scene, "point_m": [0.1, 0.6, 0.3]}).json()[
        "magnetic"]
    total = np.array({v["quantity"]: v for v in m["values"]}["B"]["value"])
    parts = np.sum([c["B_T"] for c in m["contributions"]], axis=0)
    assert np.allclose(total, parts, rtol=1e-14, atol=0)
    assert [c["kind"] for c in m["contributions"]] == ["infinite_wire", "infinite_wire",
                                                       "circular_loop"]


def test_probe_on_a_wire_and_on_a_loop_is_singular_and_identifies_the_source(client):
    scene = {"objects": [wire("w", 10.0, (0.5, 0, 0), name="W1"), loop("l", 3.0, 0.4)]}
    for point, oid, kind in (([0.5, 0.0, 1.3], "w", "infinite_wire"),
                             ([0.0, 0.4, 0.0], "l", "circular_loop")):
        m = client.post(f"{V1}/probe", json={"scene": scene, "point_m": point}).json()["magnetic"]
        assert m["defined"] is False
        assert m["singular_object_id"] == oid and m["singular_kind"] == kind
        by = {v["quantity"]: v for v in m["values"]}
        assert by["B"]["status"] == "singular" and by["B"]["value"] is None
        assert by["div_B"]["status"] == "not_evaluated"


def test_equation_statuses_follow_the_scene(client):
    def eq(scene):
        r = client.post(f"{V1}/equations/evaluate", json={"scene": scene}).json()
        return r, {e["id"]: e for e in r["equations"]}

    resp, wire_only = eq({"objects": [wire("w", 10.0)]})
    assert resp["solver_ids"] == ["analytical.magnetostatics.filaments"]
    assert wire_only["infinite_wire_field"]["status"] == "applicable"
    assert wire_only["infinite_wire_field"]["usage"] == "evaluated"
    assert wire_only["loop_field_elliptic"]["status"] == "not_applicable"
    assert wire_only["loop_axis_field"]["status"] == "not_applicable"
    assert wire_only["gauss_magnetic"]["status"] == "applicable"
    assert wire_only["b_mu0_h"]["usage"] == "evaluated" and wire_only["h_from_b"]["status"] == \
        "applicable"
    assert wire_only["biot_savart"]["status"] == "applicable"
    assert wire_only["biot_savart_integral"]["usage"] == "satisfied"
    ampere = wire_only["ampere_static"]
    assert ampere["status"] == "applicable" and ampere["usage"] == "satisfied"
    assert "3B" in ampere["usage_note"]["en"]
    assert wire_only["superposition_magnetic"]["status"] == "applicable_under_assumptions"
    assert wire_only["coulomb_field"]["status"] == "not_applicable"
    for e in wire_only.values():
        assert e["name"]["hu"] and e["meaning"]["hu"]
        assert all(s["unit"] is not None for s in e["symbols"])

    _, loops = eq({"objects": [loop("a", 1.0, 0.3), loop("b", 2.0, 0.5, (0, 0, 0.4))]})
    assert loops["loop_field_elliptic"]["status"] == "applicable"
    assert loops["loop_axis_field"]["status"] == "applicable_under_assumptions"
    assert loops["infinite_wire_field"]["status"] == "not_applicable"
    assert loops["superposition_magnetic"]["status"] == "applicable"

    resp, mixed = eq({"objects": [charge("q", 1e-9, (0, 0, 0)), wire("w", 10.0, (1, 0, 0))]})
    assert resp["solver_ids"] == ["analytical.electrostatics.point_charges",
                                  "analytical.magnetostatics.filaments"]
    assert mixed["coulomb_field"]["status"] == "applicable"
    assert mixed["infinite_wire_field"]["status"] == "applicable"
    assert mixed["gauss_magnetic"]["status"] == "applicable"

    _, charges_only = eq({"objects": [charge("q", 1e-9, (0, 0, 0))]})
    assert charges_only["gauss_magnetic"]["status"] == "not_evaluated"
    assert charges_only["infinite_wire_field"]["status"] == "not_evaluated"


def test_presets_9_to_11(client):
    presets = {p["number"]: p for p in client.get(f"{V1}/presets").json()}
    assert [presets[n]["available"] for n in (9, 10, 11)] == [True, True, True]
    assert [v["id"] for v in presets[10]["variants"]] == ["same", "opposite", "unequal"]
    assert presets[11]["view_hint"] == {"mode": "2d", "plane": "xz", "probe_m": None}  # 3B: probe_m
    for n in (9, 10, 11):
        scenes = [presets[n]["scene"]] + [v["scene"] for v in presets[n]["variants"]]
        for scene in scenes:
            header, arrays, _ = solve(client, scene, magnetic_request([[0.13, 0.07, 0.3]]))
            assert header["status"] == "ok" and np.all(np.isfinite(arrays["p.B"]))
    # Preset 11: B at the centre of the loop is mu0 I / (2 a) along +z.
    header, arrays, _ = solve(client, presets[11]["scene"], magnetic_request([[0, 0, 0]]))
    assert arrays["p.B"][0][2] == pytest.approx(MU0 * 10 / (2 * 0.5), rel=1e-6)


def test_electric_and_magnetic_caches_are_independent(client):
    q = charge("q", 1e-9, (0, 0, 0))
    w = wire("w", 10.0, (1, 0, 0))
    mreq = magnetic_request([[0.3, 0.4, 0.0]])
    ereq = {"samplings": [{"kind": "points", "id": "p", "points_m": [[0.3, 0.4, 0.0]]}],
            "quantities": ["E"]}
    assert solve(client, {"objects": [q, w]}, mreq)[2] == "miss"
    assert solve(client, {"objects": [q, w]}, ereq)[2] == "miss"
    moved_q = charge("q", 1e-9, (0.2, 0, 0))
    moved_w = wire("w", 10.0, (1.2, 0, 0))
    assert solve(client, {"objects": [moved_q, w]}, mreq)[2] == "hit"  # charge moved: B kept
    assert solve(client, {"objects": [q, moved_w]}, ereq)[2] == "hit"  # wire moved: E kept
    assert solve(client, {"objects": [q, moved_w]}, mreq)[2] == "miss"


def test_flux_ignores_current_sources(client):
    surface = {"id": "S", "shape": {"type": "sphere", "radius_m": 0.5}}
    body = lambda objs: {"scene": {"objects": objs}, "flux": {"surfaces": [surface]}}  # noqa: E731
    a = client.post(f"{V1}/flux", json=body([charge("q", 1e-9, (0, 0, 0))]))
    b = client.post(f"{V1}/flux", json=body([charge("q", 1e-9, (0, 0, 0)), wire("w", 5.0)]))
    assert a.status_code == b.status_code == 200
    assert b.headers["X-EMF-Cache"] == "hit"


def test_malformed_current_source_is_refused_for_both_fields(client):
    bad = {"objects": [{"id": "w", "primitive": {"type": "sphere"}, "role": "current_source",
                        "source": {"type": "infinite_wire", "current_A": 1.0}}]}
    for q in (["B"], ["E"]):
        r = client.post(f"{V1}/simulations", json={"scene": bad, "request": {
            "samplings": [{"kind": "points", "id": "p", "points_m": [[1, 0, 0]]}],
            "quantities": q}})
        assert r.status_code == 422 and r.json()["detail"]["reasons"][0]["hu"]
    ellipse = {"objects": [loop("l", 1.0, 0.5) | {"transform": {"scale": [1, 2, 1]}}]}
    r = client.post(f"{V1}/simulations", json={"scene": ellipse, "request": magnetic_request(
        [[1, 0, 0]])})
    assert r.status_code == 422 and "ellipse" in r.json()["detail"]["reasons"][0]["en"]


def test_projects_with_currents_persist_and_old_projects_still_load(client):
    scene = {"objects": [wire("w", -7.5, (0.1, 0.2, 0.0), (0.3, 0.0, 0.0)),
                         loop("l", 2.0, 0.6, (0, 0, 0.5))]}
    created = client.post(f"{V1}/projects", json={"name": "magnets", "scene": scene,
                                                  "view": {"showBLines": False}}).json()
    back = client.get(f"{V1}/projects/{created['id']}").json()
    assert back["scene"]["objects"][0]["source"] == {"type": "infinite_wire", "current_A": -7.5}
    assert back["scene"]["objects"][1]["source"]["type"] == "circular_loop"
    assert back["view"]["showBLines"] is False
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": {
        "objects": [charge("q", 1e-9, (0, 0, 0))]}, "view": {"heatmap": "phi"}}).json()
    again = client.get(f"{V1}/projects/{old['id']}").json()
    assert again["scene"]["objects"][0]["source"]["type"] == "point_charge"
