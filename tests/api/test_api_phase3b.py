"""API tests for Phase 3B: the /ampere endpoint, probe extensions for solenoids, toroids and
magnets, equation statuses, presets 12–14, persistence of Ampère paths, the cost guard, cache
independence and backward compatibility."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire as wire_format
from emf_core.units import MU0
from tests.conftest import charge, loop, magnet, solenoid, torus, wire

V1 = "/api/v1"
HALF_PI = math.pi / 2


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def mreq(points, quantities=("B", "H")):
    return {"samplings": [{"kind": "points", "id": "p", "points_m": points}],
            "quantities": list(quantities)}


def solve(client, scene, request):
    r = client.post(f"{V1}/simulations", json={"scene": scene, "request": request})
    assert r.status_code == 200, r.text
    header, arrays = wire_format.decode(r.content)
    return header, arrays, r.headers["X-EMF-Cache"]


def probe(client, scene, point):
    r = client.post(f"{V1}/probe", json={"scene": scene, "point_m": point})
    assert r.status_code == 200, r.text
    return r.json()["magnetic"]


def ampere(client, scene, *paths):
    return client.post(f"{V1}/ampere", json={"scene": scene, "ampere": {"paths": list(paths)}})


CIRCLE = {"id": "c", "shape": {"type": "circle", "radius_m": 0.1}}


# ------------------------------------------------------------------------------- /ampere


def test_ampere_endpoint_and_cache(client):
    scene = {"objects": [wire("w", 10.0)]}
    r = ampere(client, scene, CIRCLE)
    assert r.status_code == 200 and r.headers["X-EMF-Cache"] == "miss"
    body = r.json()
    (p,) = body["paths"]
    assert p["status"] == "verified" and p["enclosure"]["value_A"] == 10.0
    assert p["circulation_H_A"] == pytest.approx(10.0, rel=1e-4)
    assert p["circulation_B_T_m"] == pytest.approx(MU0 * 10.0, rel=1e-4)
    assert body["method"]["hu"]
    assert ampere(client, scene, CIRCLE).headers["X-EMF-Cache"] == "hit"
    # Adding a charge (electric only) does not change the magnetic subscene: still a hit.
    with_q = {"objects": [wire("w", 10.0), charge("q", 1e-9, (0.5, 0, 0))]}
    assert ampere(client, with_q, CIRCLE).headers["X-EMF-Cache"] == "hit"
    # A display-only change of the path does not change the result key; geometry does.
    shown = dict(CIRCLE, display={"visible": False}, name="renamed")
    assert ampere(client, scene, shown).headers["X-EMF-Cache"] == "hit"
    bigger = dict(CIRCLE, shape={"type": "circle", "radius_m": 0.2})
    assert ampere(client, scene, bigger).headers["X-EMF-Cache"] == "miss"


def test_ampere_invalid_and_unsupported(client):
    bad = {"id": "p", "shape": {"type": "polygon", "vertices_m": [[0, 0, 0], [1, 0, 0]],
                                "closed": True}}
    r = ampere(client, {"objects": [wire("w", 1.0, (5, 5, 0))]}, bad)
    assert r.status_code == 200 and r.json()["paths"][0]["status"] == "invalid"
    assert r.json()["paths"][0]["invalid_reasons"][0]["hu"]
    assert ampere(client, {"objects": []}, dict(CIRCLE, rtol=0.5)).status_code == 422
    # Ideal toroid with another source: refused as a scene.
    r = ampere(client, {"objects": [torus(model="toroid_ideal"), wire("w", 1.0, (1, 0, 0))]},
               CIRCLE)
    assert r.status_code == 422


def test_ampere_preset_paths_give_documented_values(client):
    presets = {p["number"]: p for p in client.get(f"{V1}/presets").json()}
    expected = {12: 12.0, 13: 24.0, 14: 0.0}
    for n, value in expected.items():
        pre = presets[n]
        assert pre["ampere_paths"], n
        (p,) = ampere(client, pre["scene"], *pre["ampere_paths"]).json()["paths"]
        assert p["status"] == "verified", (n, p["status"])
        assert abs(p["enclosure"]["value_A"]) == value
    (mp,) = ampere(client, presets[14]["scene"], *presets[14]["ampere_paths"]).json()["paths"]
    assert abs(mp["bound_current_from_B_A"]) == pytest.approx(5e5 * 0.08, rel=1e-4)
    ideal = presets[13]["variants"][1]["scene"]
    (ip,) = ampere(client, ideal, *presets[13]["ampere_paths"]).json()["paths"]
    assert ip["status"] == "verified" and ip["enclosure"]["value_A"] == 24.0


# ------------------------------------------------------------------------------- probe


def test_probe_solenoid_contributions_and_ideal_comparison(client):
    scene = {"objects": [solenoid()]}
    m = probe(client, scene, [0.0, 0.0, 0.0])
    assert m["status"] == "defined" and m["material"] == "vacuum"
    (c,) = m["contributions"]
    assert c["kind"] == "solenoid" and c["turns"] == 20
    b = next(v for v in m["values"] if v["quantity"] == "B")["value"]
    assert np.allclose(c["B_T"], b, rtol=1e-12)
    comp = {x["kind"]: x for x in m["comparisons"]}
    ideal = comp["ideal_long_solenoid"]
    assert ideal["B_T"][2] == pytest.approx(MU0 * 100.0, rel=1e-12)
    assert ideal["note"]["hu"]
    assert b[2] < ideal["B_T"][2]  # finite coil (L = 2.5 diameters) is weaker


def test_probe_ideal_toroid_core_and_boundary(client):
    scene = {"objects": [torus(model="toroid_ideal", mu_r=200.0)]}
    m = probe(client, scene, [0.12, 0.0, 0.0])
    assert m["material"] == "core" and m["constitutive"] == "linear_core"
    assert m["relative_permeability"] == 200.0
    h = next(v for v in m["values"] if v["quantity"] == "H")["value"]
    assert h[1] == pytest.approx(24 / (2 * math.pi * 0.12), rel=1e-12)
    edge = probe(client, scene, [0.15, 0.0, 0.0])
    assert edge["status"] == "core_boundary" and not edge["defined"]
    sides = {s["side"]: s for s in edge["one_sided"]}
    assert set(sides) == {"inside", "outside"}
    assert np.linalg.norm(sides["outside"]["B_T"]) == 0.0
    assert np.linalg.norm(sides["inside"]["B_T"]) > 0


def test_probe_magnet_inside_outside_sheet(client):
    scene = {"objects": [magnet(m=5e5)]}
    inside = probe(client, scene, [0.0, 0.0, 0.0])
    assert inside["material"] == "magnet" and inside["constitutive"] == "magnetization"
    assert inside["M_A_per_m"] == [0.0, 0.0, 5e5]
    b = next(v for v in inside["values"] if v["quantity"] == "B")["value"]
    h = next(v for v in inside["values"] if v["quantity"] == "H")["value"]
    assert h[2] == pytest.approx(b[2] / MU0 - 5e5, rel=1e-12) and h[2] < 0
    far = probe(client, scene, [0.0, 0.0, 1.0])
    dip = {x["kind"]: x for x in far["comparisons"]}["dipole_far_field"]
    fb = next(v for v in far["values"] if v["quantity"] == "B")["value"]
    assert dip["applicable"] and dip["B_T"][2] == pytest.approx(fb[2], rel=1e-2)
    sheet = probe(client, scene, [0.04, 0.0, 0.01])
    assert sheet["status"] == "sheet" and not sheet["defined"]
    sides = {s["side"]: s for s in sheet["one_sided"]}
    jump = np.subtract(sides["inside"]["B_T"], sides["outside"]["B_T"])
    assert jump[2] == pytest.approx(MU0 * 5e5, rel=1e-3)


# ---------------------------------------------------------------------------- equations


def eqs(client, scene, paths=()):
    r = client.post(f"{V1}/equations/evaluate", json={"scene": scene, "paths": list(paths)})
    assert r.status_code == 200, r.text
    return {e["id"]: e for e in r.json()["equations"]}


def test_equation_statuses_for_new_sources(client):
    s = eqs(client, {"objects": [solenoid()]})
    assert s["finite_solenoid_superposition"]["usage"] == "evaluated"
    assert s["ideal_solenoid_B"]["usage"] == "approximation"
    assert s["ideal_toroid_H"]["status"] == "not_applicable"
    assert s["magnet_sheet_field"]["status"] == "not_applicable"

    t = eqs(client, {"objects": [torus()]})
    assert t["finite_toroid_superposition"]["usage"] == "evaluated"
    assert t["ideal_toroid_B"]["usage"] == "approximation"

    ti = eqs(client, {"objects": [torus(model="toroid_ideal", mu_r=100.0)]})
    assert ti["ideal_toroid_H"]["usage"] == "evaluated"
    assert ti["finite_toroid_superposition"]["status"] == "not_applicable"
    assert ti["b_mu0_h"]["status"] != "applicable"  # B = μ0 μr H inside the core

    m = eqs(client, {"objects": [magnet()]})
    assert m["magnet_sheet_field"]["usage"] == "evaluated"
    assert m["h_from_b_m"]["usage"] == "evaluated"
    assert m["dipole_far_field"]["usage"] == "approximation"
    assert m["b_mu0_h"]["status"] == "applicable_under_assumptions"
    for e in (*s.values(), *m.values()):
        assert e["name"]["hu"] and e["meaning"]["hu"]


def test_ampere_integral_status_depends_on_paths(client):
    scene = {"objects": [wire("w", 1.0)]}
    without = eqs(client, scene)["ampere_integral"]
    with_path = eqs(client, scene, [CIRCLE])["ampere_integral"]
    assert with_path["usage"] == "checked"
    assert without["usage"] != "checked"


# ------------------------------------------------------------------------------ presets


def test_presets_12_to_14(client):
    presets = {p["number"]: p for p in client.get(f"{V1}/presets").json()}
    for n in (12, 13, 14):
        assert presets[n]["available"] and presets[n]["view_hint"]["probe_m"] is not None
        assert presets[n]["name"]["hu"]
    s = presets[12]["scene"]["objects"][0]
    assert s["primitive"] == {"type": "coil", "radius_m": 0.04, "length_m": 0.2, "turns": 20}
    v = presets[13]["variants"]
    assert [x["scene"]["objects"][0]["source"]["type"] for x in v] == ["toroid_finite",
                                                                      "toroid_ideal"]
    t = v[0]["scene"]["objects"][0]["primitive"]
    assert (t["major_radius_m"], t["turns"]) == (0.12, 24)
    mg = presets[14]["scene"]["objects"][0]
    assert mg["role"] == "magnetic_material"
    assert mg["source"] == {"type": "permanent_magnet", "magnetization_A_per_m": 5e5}
    for n in (12, 14):
        header, arrays, _ = solve(client, presets[n]["scene"], mreq([[0.0, 0.0, 0.0]]))
        assert header["status"] == "ok" and np.all(np.isfinite(arrays["p.B"]))


# ------------------------------------------------------------------- persistence, cost


def test_projects_persist_ampere_paths_and_new_sources(client):
    scene = {"objects": [solenoid(), magnet(pos=(0.3, 0, 0))]}
    path = dict(CIRCLE, reversed=True, rtol=1e-6, display={"visible": True,
                                                          "show_surface": True})
    created = client.post(f"{V1}/projects", json={"name": "3b", "scene": scene, "view": {},
                                                  "paths": [path]}).json()
    back = client.get(f"{V1}/projects/{created['id']}").json()
    assert back["scene"]["objects"][0]["primitive"]["type"] == "coil"
    assert back["scene"]["objects"][1]["source"]["type"] == "permanent_magnet"
    (p,) = back["paths"]
    assert p["reversed"] is True and p["rtol"] == 1e-6 and p["display"]["show_surface"]
    assert "ampere_paths" not in back["view"]
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": {
        "objects": [loop("l", 1.0, 0.2)]}, "view": {}}).json()
    assert client.get(f"{V1}/projects/{old['id']}").json()["paths"] == []


def test_cost_guard_refuses_huge_magnet_grids(client):
    scene = {"objects": [magnet(f"m{k}", pos=(0.2 * k, 0, 0)) for k in range(16)],
             "domain": {"min_m": [-1, -1, -1], "max_m": [4, 1, 1]}}
    req = {"samplings": [{"kind": "plane_grid", "id": "g", "quantities": ["B"],
                          "u_extent_m": 5.0, "v_extent_m": 2.0, "nu": 1024, "nv": 1024}],
           "quantities": ["B"]}
    r = client.post(f"{V1}/simulations", json={"scene": scene, "request": req})
    assert r.status_code == 413, r.text


def test_magnet_in_electric_subscene_is_dropped(client):
    q = charge("q", 1e-9, (0.3, 0, 0))
    ereq = mreq([[0.0, 0.3, 0.0]], ("E", "phi"))
    _, a, miss = solve(client, {"objects": [q]}, ereq)
    _, b, hit = solve(client, {"objects": [q, magnet(), solenoid(pos=(0, 0, 0.5))]}, ereq)
    assert hit == "hit" and np.array_equal(a["p.E"], b["p.E"])
