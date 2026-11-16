"""API tests for Phase 2B-2: flux endpoint, caching, classifications and units, situations,
surface-aware equation statuses, and Gaussian surfaces in saved projects."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire
from emf_core.units import EPS0
from tests.conftest import charge

V1 = "/api/v1"
Q = 1e-9
SCENE = {"objects": [charge("a", Q, (0.1, 0, 0)), charge("x", 2 * Q, (1.6, 0, 0))]}
SPHERE = {"id": "S1", "name": "Sphere", "shape": {"type": "sphere", "radius_m": 0.9},
          "display": {"visible": True, "opacity": 0.3, "show_normals": False,
                      "color_by_flux": True}}


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def flux(client, scene=SCENE, surfaces=(SPHERE,), quality="final"):
    r = client.post(f"{V1}/flux", json={"scene": scene, "flux": {"surfaces": list(surfaces),
                                                                  "quality": quality}})
    assert r.status_code == 200, r.text
    header, arrays = wire.decode(r.content)
    return r, header, arrays


def test_flux_result_classifications_units_and_arrays(client):
    r, h, a = flux(client)
    assert r.headers["content-type"] == "application/vnd.emf.result"
    assert h["kind"] == "gauss_flux" and h["quality"] == "final"
    s = h["surfaces"][0]
    assert s["status"] == "ok" and s["orientation"] == "outward" and s["orientation_sign"] == 1
    assert s["flux_E_V_m"] == pytest.approx(Q / EPS0, rel=1e-12)
    assert s["flux_D_C"] == pytest.approx(Q, rel=1e-12)
    assert s["volume_integral_E_V_m"] == Q / EPS0 and s["volume_integral_D_C"] == Q
    assert abs(s["difference_E_V_m"]) <= s["flux_E_uncertainty_V_m"]
    assert s["enclosed"] == {"positive_count": 1, "negative_count": 0, "positive_C": Q,
                             "negative_C": 0.0, "total_C": Q, "external_count": 1,
                             "boundary_count": 0}
    assert s["value_classes"] == {
        "flux": "exact_for_represented_mesh", "volume_integral": "exact_analytical",
        "enclosed_charge": "exact_analytical", "uncertainty": "numerical_diagnostic",
        "local_flux_density": "exact_analytical", "patch_flux": "exact_for_represented_mesh",
        "mesh_geometry": "numerical_approximation"}
    m = s["mesh"]
    assert m["resolution_id"] == "sphere/lon64-lat32" and m["triangles"] == 3968
    assert m["representation"] == "inscribed_polyhedron" and m["max_deviation_m"] > 0
    assert m["tolerance_m"] > 0 and m["near_boundary_m"] >= 10 * m["tolerance_m"]
    units = {e["name"].split(".", 1)[1]: e["unit"] for e in h["arrays"]}
    assert units["En"] == "V/m" and units["Dn"] == "C/m^2" and units["flux_E"] == "V*m"
    assert units["flux_D"] == "C" and units["area"] == "m^2"
    assert a["surf0.triangles"].shape == (3968, 3, 3) and a["surf0.charge_flux_E"].shape == \
        (2, 3968)
    assert "centroid" in h["local_sampling"]["en"] and h["local_sampling"]["hu"]
    assert h["approx_zero_relative_threshold"] == 1e-3
    cls = a["surf0.En_class"]
    assert set(np.unique(cls)) <= {-1.0, 0.0, 1.0}


def test_flux_cache_ignores_display_metadata_and_names_but_not_physics(client):
    r1, *_ = flux(client)
    restyled = {**SPHERE, "name": "renamed", "display": {**SPHERE["display"], "opacity": 0.9,
                                                         "show_normals": True}}
    assert flux(client, surfaces=[restyled])[0].headers["x-emf-cache"] == "hit"
    moved = {**SPHERE, "center_m": [0.1, 0, 0]}
    assert flux(client, surfaces=[moved])[0].headers["x-emf-cache"] == "miss"
    reversed_ = {**SPHERE, "orientation": "inward"}
    _, h, _ = flux(client, surfaces=[reversed_])
    assert h["surfaces"][0]["flux_E_V_m"] == pytest.approx(-Q / EPS0, rel=1e-12)
    r_prev, h_prev, _ = flux(client, quality="preview")
    assert r_prev.headers["x-emf-cache"] == "miss"  # the mesh resolution is part of the key
    assert h_prev["quality"] == "preview"
    assert h_prev["surfaces"][0]["mesh"]["resolution_id"] == "sphere/lon24-lat12"
    assert r1.headers["x-emf-cache"] == "miss"


def test_charge_and_surface_changes_update_the_flux(client):
    out = {"objects": [charge("a", Q, (1.2, 0, 0))]}
    assert flux(client, scene=out)[1]["surfaces"][0]["flux_E_V_m"] == pytest.approx(0, abs=1e-9)
    bigger = {**SPHERE, "shape": {"type": "sphere", "radius_m": 1.3}}
    _, h, _ = flux(client, scene=out, surfaces=[bigger])
    assert h["surfaces"][0]["flux_E_V_m"] == pytest.approx(Q / EPS0, rel=1e-12)


def test_boundary_and_invalid_surfaces(client):
    on = {"objects": [charge("a", Q, (0.5, 0, 0))]}
    cube = {"id": "C", "shape": {"type": "cube", "side_m": 1.0}}
    _, h, _ = flux(client, scene=on, surfaces=[cube])
    s = h["surfaces"][0]
    assert s["status"] == "boundary_ambiguous" and s["flux_E_V_m"] is None
    assert s["charges"][0]["state"] == "boundary" and s["value_classes"]["flux"] == "undefined"
    open_mesh = {"id": "M", "shape": {"type": "mesh",
                                      "vertices_m": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                                                     [0.5, 0.5, 1]],
                                      "triangles": [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]}}
    _, h, _ = flux(client, surfaces=[open_mesh])
    assert h["surfaces"][0]["status"] == "invalid" and h["surfaces"][0]["errors"][0]["hu"]
    bad = client.post(f"{V1}/flux", json={"scene": SCENE, "flux": {"surfaces": [
        {"id": "B", "shape": {"type": "sphere", "radius_m": 1}, "subdivision": [2, 2, 2]}]}})
    assert bad.status_code == 422


def test_unsupported_scene_is_refused(client):
    scene = {"objects": [{"id": "c", "primitive": {"type": "sphere"}, "role": "conductor"}]}
    r = client.post(f"{V1}/flux", json={"scene": scene, "flux": {"surfaces": [SPHERE]}})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "unsupported"


def test_situations_cover_the_nine_guided_cases(client):
    sits = client.get(f"{V1}/gauss/situations").json()
    assert [s["number"] for s in sits] == list(range(1, 10))
    results = {}
    for s in sits:
        assert s["name"]["hu"] and s["expectation"]["hu"]
        _, h, _ = flux(client, scene=s["scene"], surfaces=s["surfaces"])
        results[s["id"]] = h["surfaces"]
    assert results["charge_on_surface"][0]["status"] == "boundary_ambiguous"
    assert results["charges_outside"][0]["flux_E_V_m"] == pytest.approx(0, abs=1e-9)
    three = [x["flux_E_V_m"] for x in results["same_charges_three_shapes"]]
    assert np.ptp(three) < 1e-12 * 56 and three[0] == pytest.approx(0.5 * Q / EPS0, rel=1e-12)


def test_equation_statuses_follow_the_surfaces(client):
    def statuses(scene, surfaces):
        eqs = client.post(f"{V1}/equations/evaluate", json={"scene": scene,
                                                              "surfaces": surfaces}).json()
        return {e["id"]: (e["status"], e["usage"]) for e in eqs["equations"]}

    none = statuses(SCENE, [])
    assert none["electric_flux"] == ("not_evaluated", "not_used")
    assert none["gauss_integral_E"][0] == "applicable_under_assumptions"
    ok = statuses(SCENE, [SPHERE])
    assert ok["electric_flux"] == ("applicable", "evaluated")
    assert ok["gauss_integral_E"] == ("applicable", "checked")
    assert ok["divergence_theorem_D"] == ("applicable", "checked")
    assert ok["divergence_theorem"][1] == "satisfied"
    on = statuses({"objects": [charge("a", Q, (0.9, 0, 0))]},
                  [{"id": "C", "shape": {"type": "cube", "side_m": 1.8}}])
    assert on["gauss_integral_E"][0] == "applicable_under_assumptions"
    assert on["electric_flux"][0] == "applicable_under_assumptions"


def test_projects_store_gaussian_surfaces_compatibly(client):
    body = {"name": "gauss", "scene": SCENE, "view": {"mode": "3d"}, "surfaces": [SPHERE]}
    pid = client.post(f"{V1}/projects", json=body).json()["id"]
    got = client.get(f"{V1}/projects/{pid}").json()
    assert got["surfaces"][0]["shape"] == {"type": "sphere", "radius_m": 0.9}
    assert got["surfaces"][0]["display"]["opacity"] == 0.3
    assert got["view"] == {"mode": "3d"}  # the storage key does not leak into the view
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": SCENE, "view": {}}).json()
    assert old["surfaces"] == []  # projects without surfaces still load
