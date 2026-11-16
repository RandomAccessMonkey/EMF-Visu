"""Closed-surface flux of the point-charge field (Gauss's law, Gauss–Ostrogradsky theorem).

Two independent paths
---------------------
* Surface integral: for a point charge q and a planar oriented triangle T, the flux of the
  Coulomb field through T is exactly q/(4 pi eps0) * Omega_T, where Omega_T is the signed solid
  angle of T seen from the charge. Summing over all triangles of the represented mesh gives the
  exact surface integral over that mesh, up to floating-point error. Omega is evaluated with the
  Van Oosterom–Strackee formula, Omega = 2 atan2(a.(b x c), |a||b||c| + (a.b)|c| + (a.c)|b| +
  (b.c)|a|), arranged so that swapping b and c (reversing the triangle) negates Omega bitwise.
* Volume integral: the integral of div E (div D) over the enclosed volume is the sum of the
  distributional source weights q/eps0 (q) of the charges strictly inside, classified by
  distance to the mesh plus ray-casting parity (not by solid angles). This reuses
  ``electrostatics.enclosed_source_weight`` from Phase 2B-1.

Neither path uses the other's result. Their difference is reported.

Floating-point error estimate (surface path): for each unambiguous charge the solid angles of a
closed mesh must sum to 4 pi w with w in {-1, 0, 1}; the measured closure residual
|sum Omega - 4 pi w| plus 8 eps per triangle, times K|q|, is reported as the evaluation
uncertainty. This is a diagnostic only; the reported flux is always the raw sum.
"""

from __future__ import annotations

import math
import time
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from ...geometry import surfaces as geo
from ...i18n import L, LocalizedText
from ...scene.models import Scene, StrictModel
from ...scene.transforms import rotation_matrix_xyz
from ...units import COULOMB_K, EPS0
from ..base import ArrayEntry, ArrayStats, PointSourceInfo
from . import electrostatics as es

Arr = NDArray[np.float64]
APPROX_ZERO_REL = 1e-3  # display classification of E.n only; never alters a value
FOUR_PI = 4 * math.pi


def solid_angles(points: Arr, tri: Arr) -> Arr:
    """Signed solid angle (N, T) of each oriented triangle (T,3,3) seen from each point (N,3).

    Positive when the point is on the side opposite to the triangle normal (i.e. inside an
    outward-oriented surface). Exactly antisymmetric under reversal (v1 <-> v2)."""
    a = tri[None, :, 0, :] - points[:, None, :]
    b = tri[None, :, 1, :] - points[:, None, :]
    c = tri[None, :, 2, :] - points[:, None, :]

    def dot(u: Arr, v: Arr) -> Arr:
        return u[..., 0] * v[..., 0] + u[..., 1] * v[..., 1] + u[..., 2] * v[..., 2]

    bxc = np.stack([b[..., 1] * c[..., 2] - b[..., 2] * c[..., 1],
                    b[..., 2] * c[..., 0] - b[..., 0] * c[..., 2],
                    b[..., 0] * c[..., 1] - b[..., 1] * c[..., 0]], axis=-1)
    det = dot(a, bxc)
    na, nb, nc = np.sqrt(dot(a, a)), np.sqrt(dot(b, b)), np.sqrt(dot(c, c))
    den = na * (nb * nc) + (dot(a, b) * nc + dot(a, c) * nb) + dot(b, c) * na
    result: Arr = 2.0 * np.arctan2(det, den)
    return result


# ------------------------------------------------------------------------------ request


class FluxRequest(StrictModel):
    surfaces: list[geo.GaussSurface] = Field(min_length=1, max_length=16)
    quality: geo.Quality = "final"
    patch_details: bool = True  # per-triangle, per-charge contributions


# ------------------------------------------------------------------------------- result


ValueClass = Literal["exact_analytical", "exact_for_represented_mesh", "numerical_approximation",
                     "numerical_diagnostic", "undefined"]


class ChargeFlux(BaseModel):
    object_id: str
    position_m: list[float]
    charge_C: float
    state: Literal["inside", "outside", "boundary"]
    signed_distance_m: float  # negative inside, positive outside
    near_boundary: bool  # visual warning (|d| <= near-boundary distance); not a classification
    ray_agreement: int  # rays (of 5) agreeing with the inside/outside verdict
    flux_E_V_m: float | None  # this charge's contribution to the surface integral (None: boundary)
    flux_D_C: float | None
    solid_angle_sr: float | None  # sum of signed solid angles over the surface
    volume_weight_E_V_m: float  # its contribution to the volume integral (0 unless inside)
    volume_weight_D_C: float


class MeshInfo(BaseModel):
    resolution_id: str
    quality: geo.Quality
    triangles: int
    vertices: int
    area_m2: float
    volume_m3: float  # enclosed volume of the represented mesh
    representation: Literal["exact", "inscribed_polyhedron", "custom"]
    ideal_area_m2: float | None
    ideal_volume_m3: float | None
    max_deviation_m: float | None  # geometric approximation of the ideal shape
    natural_orientation: Literal["outward", "inward"]
    l_char_m: float
    tolerance_m: float  # tau_geom used for inside/outside/boundary classification
    near_boundary_m: float


class Enclosed(BaseModel):
    positive_count: int
    negative_count: int
    positive_C: float
    negative_C: float
    total_C: float
    external_count: int
    boundary_count: int


class CellResult(BaseModel):
    index: tuple[int, int, int]
    flux_E_V_m: float
    flux_D_C: float
    enclosed_C: float | None  # None when a charge lies on this cell's boundary
    volume_integral_E_V_m: float | None
    volume_integral_D_C: float | None
    ambiguous_object_ids: list[str]


class SubdivisionResult(BaseModel):
    n: tuple[int, int, int]
    cells: list[CellResult]
    shared_faces: int
    shared_face_max_abs_sum_E_V_m: float  # max |Phi_A + Phi_B| over shared faces
    sum_cell_flux_E_V_m: float
    sum_cell_flux_D_C: float
    outer_flux_E_V_m: float | None  # the parent surface's own flux, for comparison
    cell_flux_difference_E_V_m: float | None
    status: Literal["ok", "ambiguous"]  # ambiguous: a charge lies on an internal cell boundary
    sum_cell_volume_integral_E_V_m: float | None
    parent_volume_integral_E_V_m: float | None
    ambiguous_object_ids: list[str]
    face_order: list[str] = ["-x", "+x", "-y", "+y", "-z", "+z"]


class SurfaceFlux(BaseModel):
    surface_id: str
    index: int  # arrays are named surf<index>.*
    status: Literal["ok", "invalid", "boundary_ambiguous"]
    errors: list[LocalizedText] = []
    orientation: Literal["outward", "inward"]
    orientation_sign: int  # +1 outward, -1 inward
    mesh: MeshInfo | None = None
    charges: list[ChargeFlux] = []
    enclosed: Enclosed | None = None
    flux_E_V_m: float | None = None  # surface integral (solid angles)
    flux_D_C: float | None = None
    flux_E_uncertainty_V_m: float | None = None  # floating-point evaluation (diagnostic)
    flux_D_uncertainty_C: float | None = None
    volume_integral_E_V_m: float | None = None  # integral of div E over V (distributional)
    volume_integral_D_C: float | None = None
    difference_E_V_m: float | None = None  # flux - orientation_sign * volume integral
    difference_D_C: float | None = None
    # Charges that the ideal analytic shape would classify differently (diagnostic only).
    ideal_shape_disagreement_ids: list[str] = []
    subdivision: SubdivisionResult | None = None
    value_classes: dict[str, ValueClass] = {}


class FluxHeader(BaseModel):
    format_version: Literal[1] = 1
    kind: Literal["gauss_flux"] = "gauss_flux"
    status: Literal["ok"] = "ok"
    solver_id: str
    solver_version: str
    quality: geo.Quality
    approx_zero_relative_threshold: float = APPROX_ZERO_REL
    local_sampling: LocalizedText
    surface_method: LocalizedText
    volume_method: LocalizedText
    surfaces: list[SurfaceFlux]
    compute_time_ms: float
    arrays: list[ArrayEntry] = []


# ------------------------------------------------------------------------------ compute


def _entry(name: str, data: Arr, unit: str, quantity: str) -> ArrayEntry:
    flat = data.reshape(-1)
    fin = flat[np.isfinite(flat)]
    return ArrayEntry(name=name, sampling_id=name.split(".")[0], quantity=quantity, symbol=quantity,
                      unit=unit, components=data.shape[-1] if data.ndim > 1 else 1,
                      kind="field" if quantity in ("En", "Dn", "Emag", "flux_E", "flux_D")
                      else "geometry",
                      stats=ArrayStats(min=float(fin.min()) if fin.size else None,
                                       max=float(fin.max()) if fin.size else None,
                                       non_finite_count=int(flat.size - fin.size)))


def _surface_and_volume(tri: Arr, ids: list[str], positions: Arr, charges: Arr,
                        cls: list[geo.Classification], sources: list[PointSourceInfo]
                        ) -> tuple[Arr, float | None, float | None, float, float, float, float]:
    """(solid angles (N,T), Phi_E, Phi_D, unc_E, unc_D, volume integral E, volume integral D)."""
    omega = solid_angles(positions, tri) if len(ids) else np.zeros((0, len(tri)))
    ambiguous = any(c.state == "boundary" for c in cls)
    if ambiguous:
        flux_e = flux_d = None
    else:
        flux_e = float(np.sum(COULOMB_K * charges[:, None] * omega)) if len(ids) else 0.0
        flux_d = float(np.sum(charges[:, None] * omega) / FOUR_PI) if len(ids) else 0.0
    unc = 0.0
    unc_d = 0.0
    for k in range(len(ids)):
        if cls[k].state == "boundary":
            continue
        total = float(omega[k].sum())
        w = round(total / FOUR_PI)
        resid = abs(total - FOUR_PI * w) + 8 * geo.EPS * len(tri)
        unc += COULOMB_K * abs(charges[k]) * resid
        unc_d += abs(charges[k]) * resid / FOUR_PI
    inside = {ids[k] for k, c in enumerate(cls) if c.state == "inside"}
    by_pos = {tuple(s.position_m): s for s in sources}

    def contains(p: Arr) -> bool:
        s = by_pos.get(tuple(float(x) for x in p))
        return s is not None and s.object_id in inside

    vol_e = es.enclosed_source_weight(sources, contains, "E")
    vol_d = es.enclosed_source_weight(sources, contains, "D")
    return omega, flux_e, flux_d, unc, unc_d, vol_e, vol_d


def _ideal_inside(surface: geo.GaussSurface, p: Arr) -> bool | None:
    """Inside test against the ideal analytic shape (diagnostic only; never used for results)."""
    rot = rotation_matrix_xyz(surface.rotation_euler_xyz_rad)
    local = (p - np.asarray(surface.center_m, float)) @ rot
    s = surface.shape
    if isinstance(s, geo.SphereShape):
        return bool(np.linalg.norm(local) < s.radius_m)
    if isinstance(s, geo.CylinderShape):
        return bool(np.hypot(local[0], local[1]) < s.radius_m and abs(local[2]) < s.height_m / 2)
    return None


def _subdivide(surface: geo.GaussSurface, ids: list[str], positions: Arr, charges: Arr,
               sources: list[PointSourceInfo], tau: float, outer_flux: float | None,
               parent_vol: float | None, prefix: str,
               arrays: dict[str, Arr]) -> SubdivisionResult:
    assert surface.subdivision is not None
    n = surface.subdivision
    local, cells, faces = geo.grid_box_cells(geo.box_size(surface.shape), n)
    world = geo.to_world(surface, local)
    flip = surface.orientation == "inward"
    c_count = len(cells)
    face_e = np.zeros((c_count, 6))
    face_d = np.zeros((c_count, 6))
    corners = np.zeros((c_count, 8, 3))
    results: list[CellResult] = []
    on_internal: set[str] = set()
    all_tri: list[Arr] = []
    for ci, (tris, fidx) in enumerate(zip(cells, faces, strict=True)):
        t_idx = np.asarray(tris, np.int64)
        if flip:
            t_idx = geo.reverse(t_idx)
        tri = world[t_idx]
        all_tri.append(tri)
        dist = geo.point_mesh_distance(positions, tri) if len(ids) else np.zeros(0)
        inside, _ = geo.ray_parity_inside(positions, tri) if len(ids) else (np.zeros(0, bool), 0)
        boundary_ids = [ids[k] for k in range(len(ids)) if dist[k] <= tau]
        omega = solid_angles(positions, tri) if len(ids) else np.zeros((0, len(tri)))
        flux_tri_e = (COULOMB_K * charges[:, None] * omega).sum(axis=0) if len(ids) else \
            np.zeros(len(tri))
        flux_tri_d = (charges[:, None] * omega).sum(axis=0) / FOUR_PI if len(ids) else \
            np.zeros(len(tri))
        for t, f in enumerate(fidx):
            face_e[ci, f] += flux_tri_e[t]
            face_d[ci, f] += flux_tri_d[t]
        cls = [geo.Classification("boundary" if dist[k] <= tau else
                                  ("inside" if inside[k] else "outside"),
                                  0.0, False, 5) for k in range(len(ids))]
        if boundary_ids:
            enc = vol_e = vol_d = None
            for k in range(len(ids)):
                if dist[k] <= tau:
                    on_internal.add(ids[k])
        else:
            enc = float(sum(charges[k] for k in range(len(ids)) if cls[k].state == "inside"))
            _, _, _, _, _, vol_e, vol_d = _surface_and_volume(tri, ids, positions, charges, cls,
                                                              sources)
        idx = (ci // (n[1] * n[2]), (ci // n[2]) % n[1], ci % n[2])
        # Corner m = dx + 2 dy + 4 dz of the cell, in grid order (stable under rotation).
        for m in range(8):
            dx, dy, dz = m & 1, (m >> 1) & 1, (m >> 2) & 1
            corners[ci, m] = world[((idx[0] + dx) * (n[1] + 1) + idx[1] + dy) * (n[2] + 1)
                                   + idx[2] + dz]
        results.append(CellResult(index=idx, flux_E_V_m=float(face_e[ci].sum()),
                                  flux_D_C=float(face_d[ci].sum()), enclosed_C=enc,
                                  volume_integral_E_V_m=vol_e, volume_integral_D_C=vol_d,
                                  ambiguous_object_ids=boundary_ids))
    # Shared faces: +x of (i,j,k) with -x of (i+1,j,k), etc.
    shared = 0
    worst = 0.0
    neighbour = np.full((c_count, 6), -1.0)

    def cid(i: int, j: int, k: int) -> int:
        return (i * n[1] + j) * n[2] + k

    for ci, r in enumerate(results):
        i, j, k = r.index
        for axis in range(3):
            nb = [i, j, k]
            nb[axis] += 1
            if nb[axis] < n[axis]:
                cj = cid(*nb)
                neighbour[ci, 2 * axis + 1] = cj
                neighbour[cj, 2 * axis] = ci
                shared += 1
                worst = max(worst, abs(face_e[ci, 2 * axis + 1] + face_e[cj, 2 * axis]))
    # A charge on an outer face of a cell is also on the parent boundary (then the parent is
    # already ambiguous); a charge strictly inside the parent but on a cell boundary is the
    # internal-boundary case.
    internal = sorted(on_internal)
    status: Literal["ok", "ambiguous"] = "ambiguous" if internal else "ok"
    sum_e = float(face_e.sum())
    sum_vol = None if internal else float(sum(r.volume_integral_E_V_m or 0.0 for r in results))
    arrays[f"{prefix}.cells.face_flux_E"] = face_e
    arrays[f"{prefix}.cells.face_flux_D"] = face_d
    arrays[f"{prefix}.cells.face_neighbor"] = neighbour
    arrays[f"{prefix}.cells.corners"] = corners
    return SubdivisionResult(
        n=n, cells=results, shared_faces=shared, shared_face_max_abs_sum_E_V_m=worst,
        sum_cell_flux_E_V_m=sum_e, sum_cell_flux_D_C=float(face_d.sum()),
        outer_flux_E_V_m=outer_flux,
        cell_flux_difference_E_V_m=None if outer_flux is None else sum_e - outer_flux,
        status=status, sum_cell_volume_integral_E_V_m=sum_vol,
        parent_volume_integral_E_V_m=parent_vol, ambiguous_object_ids=internal)


def compute(scene: Scene, request: FluxRequest, solver_id: str, solver_version: str
            ) -> tuple[FluxHeader, dict[str, Arr]]:
    t0 = time.perf_counter()
    ids, positions, charges = es.point_charge_table(scene)
    keep = charges != 0.0  # a zero charge has no field: it is neither a source nor singular
    ids = [i for i, k in zip(ids, keep, strict=True) if k]
    positions, charges = positions[keep], charges[keep]
    sources = es.point_source_table(scene, [])
    r_min = es.COINCIDENCE_FACTOR * scene.domain.diagonal_m
    arrays: dict[str, Arr] = {}
    out: list[SurfaceFlux] = []
    for si, surface in enumerate(request.surfaces):
        prefix = f"surf{si}"
        sign = 1 if surface.orientation == "outward" else -1
        mesh = geo.build_mesh(surface, request.quality)
        res = SurfaceFlux(surface_id=surface.id, index=si, status="ok",
                          orientation=surface.orientation, orientation_sign=sign)
        if not mesh.valid:
            res.status, res.errors = "invalid", mesh.errors
            out.append(res)
            continue
        tri = mesh.tri
        l_char, tau, near = geo.tolerances(mesh, positions)
        cls = geo.classify(mesh, positions, tau, near)
        omega, flux_e, flux_d, unc_e, unc_d, vol_e, vol_d = _surface_and_volume(
            tri, ids, positions, charges, cls, sources)
        ambiguous = any(c.state == "boundary" for c in cls)
        res.mesh = MeshInfo(
            resolution_id=mesh.resolution_id, quality=request.quality, triangles=len(tri),
            vertices=len(mesh.vertices), area_m2=float(geo.areas(tri).sum()),
            volume_m3=abs(geo.signed_volume(mesh.vertices, mesh.triangles)),
            representation=mesh.ideal.representation, ideal_area_m2=mesh.ideal.ideal_area_m2,
            ideal_volume_m3=mesh.ideal.ideal_volume_m3, max_deviation_m=mesh.ideal.max_deviation_m,
            natural_orientation=mesh.natural_orientation, l_char_m=l_char, tolerance_m=tau,
            near_boundary_m=near)
        res.charges = [ChargeFlux(
            object_id=ids[k], position_m=[float(x) for x in positions[k]],
            charge_C=float(charges[k]), state=c.state, signed_distance_m=c.signed_distance_m,
            near_boundary=c.near_boundary, ray_agreement=c.ray_agreement,
            flux_E_V_m=None if c.state == "boundary" else float(COULOMB_K * charges[k]
                                                                  * omega[k].sum()),
            flux_D_C=None if c.state == "boundary" else float(charges[k] * omega[k].sum()
                                                                / FOUR_PI),
            solid_angle_sr=None if c.state == "boundary" else float(omega[k].sum()),
            volume_weight_E_V_m=float(charges[k] / EPS0) if c.state == "inside" else 0.0,
            volume_weight_D_C=float(charges[k]) if c.state == "inside" else 0.0,
        ) for k, c in enumerate(cls)]
        inside = [k for k, c in enumerate(cls) if c.state == "inside"]
        res.enclosed = Enclosed(
            positive_count=sum(1 for k in inside if charges[k] > 0),
            negative_count=sum(1 for k in inside if charges[k] < 0),
            positive_C=float(sum(charges[k] for k in inside if charges[k] > 0)),
            negative_C=float(sum(charges[k] for k in inside if charges[k] < 0)),
            total_C=float(sum(charges[k] for k in inside)),
            external_count=sum(1 for c in cls if c.state == "outside"),
            boundary_count=sum(1 for c in cls if c.state == "boundary"))
        res.ideal_shape_disagreement_ids = [
            ids[k] for k, c in enumerate(cls) if c.state != "boundary"
            and (ideal := _ideal_inside(surface, positions[k])) is not None
            and ideal != (c.state == "inside")]
        if ambiguous:
            res.status = "boundary_ambiguous"
        else:
            res.flux_E_V_m, res.flux_D_C = flux_e, flux_d
            res.flux_E_uncertainty_V_m, res.flux_D_uncertainty_C = unc_e, unc_d
            res.volume_integral_E_V_m, res.volume_integral_D_C = vol_e, vol_d
            assert flux_e is not None and flux_d is not None
            res.difference_E_V_m = flux_e - sign * vol_e
            res.difference_D_C = flux_d - sign * vol_d
        res.value_classes = {
            "flux": "undefined" if ambiguous else "exact_for_represented_mesh",
            "volume_integral": "undefined" if ambiguous else "exact_analytical",
            "enclosed_charge": "exact_analytical",
            "uncertainty": "numerical_diagnostic",
            "local_flux_density": "exact_analytical",
            "patch_flux": "exact_for_represented_mesh",
            "mesh_geometry": "exact_analytical" if mesh.ideal.representation == "exact"
            else "numerical_approximation",
        }
        # Per-triangle data: integrated contributions (solid angles) and pointwise E.n at the
        # centroid (a sample, not the patch integral).
        normals_raw = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area2 = np.linalg.norm(normals_raw, axis=1)
        normals = normals_raw / area2[:, None]
        centroids = tri.mean(axis=1)
        e_c = es.evaluate(centroids, positions, charges, r_min)[0]
        en = np.einsum("ij,ij->i", e_c, normals)
        emag = np.linalg.norm(e_c, axis=1)
        cls_n = np.where(emag == 0, 0.0, np.where(np.abs(en) <= APPROX_ZERO_REL * emag, 0.0,
                                                  np.sign(en)))
        tri_flux_e = (COULOMB_K * charges[:, None] * omega).sum(axis=0) if len(ids) else \
            np.zeros(len(tri))
        tri_flux_d = (charges[:, None] * omega).sum(axis=0) / FOUR_PI if len(ids) else \
            np.zeros(len(tri))
        if ambiguous:
            tri_flux_e = np.where(np.isfinite(tri_flux_e), tri_flux_e, np.nan)
        arrays[f"{prefix}.triangles"] = tri
        arrays[f"{prefix}.normals"] = normals
        arrays[f"{prefix}.centroids"] = centroids
        arrays[f"{prefix}.area"] = area2 / 2
        arrays[f"{prefix}.En"] = en
        arrays[f"{prefix}.Dn"] = EPS0 * en
        arrays[f"{prefix}.Emag"] = emag
        arrays[f"{prefix}.En_class"] = cls_n
        arrays[f"{prefix}.flux_E"] = tri_flux_e
        arrays[f"{prefix}.flux_D"] = tri_flux_d
        if request.patch_details and len(ids):
            arrays[f"{prefix}.charge_flux_E"] = COULOMB_K * charges[:, None] * omega
        if surface.subdivision is not None:
            res.subdivision = _subdivide(surface, ids, positions, charges, sources, tau,
                                         res.flux_E_V_m, res.volume_integral_E_V_m, prefix,
                                         arrays)
        out.append(res)
    units = {"triangles": "m", "normals": "1", "centroids": "m", "area": "m^2", "En": "V/m",
             "Dn": "C/m^2", "Emag": "V/m", "En_class": "1", "flux_E": "V*m", "flux_D": "C",
             "charge_flux_E": "V*m", "face_flux_E": "V*m", "face_flux_D": "C",
             "face_neighbor": "1", "corners": "m"}
    entries = [_entry(name, data, units[name.split(".")[-1]], name.split(".")[-1])
               for name, data in arrays.items()]
    header = FluxHeader(
        solver_id=solver_id, solver_version=solver_version, quality=request.quality,
        local_sampling=L("E·n and D·n are sampled at triangle centroids (pointwise values, not "
                         "patch integrals).",
                         "Az E·n és D·n értékek a háromszögek súlypontjában vett mintavételek "
                         "(pontbeli értékek, nem felületelem-integrálok)."),
        surface_method=L("Surface integral: signed solid angle of every oriented triangle seen "
                         "from every charge, Φ = Σ q/(4πε₀) Ω. Exact for the represented "
                         "triangulated surface up to floating-point error.",
                         "Felületi integrál: minden irányított háromszög előjeles térszöge "
                         "minden töltésből nézve, Φ = Σ q/(4πε₀) Ω. A reprezentált háromszögelt "
                         "felületre egzakt, a lebegőpontos hibától eltekintve."),
        volume_method=L("Volume integral: sum of the distributional source weights qᵢ/ε₀ of the "
                        "charges strictly inside, classified by distance to the mesh and "
                        "ray-casting parity (independent of the solid angles).",
                        "Térfogati integrál: a szigorúan belül lévő töltések qᵢ/ε₀ "
                        "disztribúciós forrássúlyainak összege; a besorolás a hálótól mért "
                        "távolság és sugárkövetéses paritás alapján történik (a térszögektől "
                        "függetlenül)."),
        surfaces=out, compute_time_ms=(time.perf_counter() - t0) * 1e3, arrays=entries)
    return header, arrays


def surface_context(scene: Scene, surfaces: list[geo.GaussSurface]) -> tuple[int, bool, bool]:
    """(number of surfaces, any charge on a surface boundary, any invalid surface), for the
    equation registry. Uses the preview mesh, which is enough to detect these states."""
    _, positions, charges = es.point_charge_table(scene)
    positions = positions[charges != 0.0]
    ambiguous = invalid = False
    for surface in surfaces:
        mesh = geo.build_mesh(surface, "preview")
        if not mesh.valid:
            invalid = True
            continue
        _, tau, near = geo.tolerances(mesh, positions)
        if any(c.state == "boundary" for c in geo.classify(mesh, positions, tau, near)):
            ambiguous = True
    return len(surfaces), ambiguous, invalid
