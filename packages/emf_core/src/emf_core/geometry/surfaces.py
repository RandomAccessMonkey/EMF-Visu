"""Closed Gaussian surfaces: data model, triangulation, validation and point classification.

Every surface, built-in or custom, is represented by one closed, consistently oriented triangle
mesh. That mesh is the authoritative geometry: it is rendered, it decides which charges are
inside, and the flux is integrated over it. For a sphere or a cylinder the mesh is an inscribed
polyhedral approximation of the ideal shape; how far it deviates from the ideal shape is
reported separately (``IdealComparison``) and never used for classification or integration.

Conventions
-----------
* Triangles are (v0, v1, v2); the oriented normal is (v1 - v0) x (v2 - v0). Reversing a
  triangle swaps v1 and v2 (v0 stays first), so a reversed triangle gives bitwise-negated solid
  angles (see ``solvers/analytical/gauss.py``).
* "outward": normals point out of the enclosed volume (signed volume > 0).
* Local frames: sphere centred at the origin; box/cube axis-aligned, centred; cylinder axis
  along local z, centred. World = R @ local + centre, R = Rx Ry Rz as for scene objects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from ..i18n import L, LocalizedText
from ..scene.models import StrictModel, Vec3
from ..scene.transforms import rotation_matrix_xyz

Arr = NDArray[np.float64]
IArr = NDArray[np.int64]
EPS = float(np.finfo(np.float64).eps)
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Quality = Literal["preview", "final"]

# Triangulation resolutions (notation of the Phase 2B-2 specification).
SPHERE_RES: dict[Quality, tuple[int, int]] = {"preview": (24, 12), "final": (64, 32)}
CYLINDER_RES: dict[Quality, tuple[int, int]] = {"preview": (32, 2), "final": (96, 8)}
MAX_CELLS_PER_AXIS = 8
MAX_CELLS = 512
MAX_CUSTOM_VERTICES = 20_000
MAX_CUSTOM_TRIANGLES = 40_000
# A triangle is degenerate if its area is below this fraction of L_char^2.
DEGENERATE_AREA_FACTOR = 1e-20


# --------------------------------------------------------------------------- data model


class SphereShape(StrictModel):
    type: Literal["sphere"] = "sphere"
    radius_m: PositiveFloat = 1.0


class CubeShape(StrictModel):
    type: Literal["cube"] = "cube"
    side_m: PositiveFloat = 1.0


class BoxShape(StrictModel):
    """Width (local x), depth (local y), height (local z)."""

    type: Literal["box"] = "box"
    size_m: tuple[PositiveFloat, PositiveFloat, PositiveFloat] = (1.0, 1.0, 1.0)


class CylinderShape(StrictModel):
    """Axis along local z; orient it with the surface rotation."""

    type: Literal["cylinder"] = "cylinder"
    radius_m: PositiveFloat = 0.5
    height_m: PositiveFloat = 1.0


class MeshShape(StrictModel):
    """A custom closed triangulated surface in local coordinates (engine-level for now)."""

    type: Literal["mesh"] = "mesh"
    vertices_m: list[Vec3] = Field(min_length=4, max_length=MAX_CUSTOM_VERTICES)
    triangles: list[tuple[int, int, int]] = Field(min_length=4, max_length=MAX_CUSTOM_TRIANGLES)


SurfaceShape = Annotated[SphereShape | CubeShape | BoxShape | CylinderShape | MeshShape,
                         Field(discriminator="type")]


class SurfaceDisplay(StrictModel):
    """Visualization metadata. Ignored by the engine and excluded from every cache key."""

    visible: bool = True
    opacity: float = Field(default=0.3, ge=0.0, le=1.0)
    show_normals: bool = False
    color_by_flux: bool = True


class GaussSurface(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = ""
    shape: SurfaceShape
    center_m: Vec3 = (0.0, 0.0, 0.0)
    rotation_euler_xyz_rad: Vec3 = (0.0, 0.0, 0.0)
    orientation: Literal["outward", "inward"] = "outward"
    # Cells per local axis for the subdivision demonstration (box and cube only).
    subdivision: tuple[int, int, int] | None = None
    display: SurfaceDisplay | None = None

    @model_validator(mode="after")
    def _check(self) -> GaussSurface:
        if self.subdivision is not None:
            if self.shape.type not in ("box", "cube"):
                raise ValueError("subdivision is supported for box and cube surfaces only")
            if any(not 1 <= n <= MAX_CELLS_PER_AXIS for n in self.subdivision):
                raise ValueError(f"subdivision counts must be between 1 and {MAX_CELLS_PER_AXIS}")
            if math.prod(self.subdivision) > MAX_CELLS:
                raise ValueError(f"at most {MAX_CELLS} cells in total")
        if isinstance(self.shape, MeshShape):
            n = len(self.shape.vertices_m)
            if any(not 0 <= i < n for t in self.shape.triangles for i in t):
                raise ValueError("mesh triangle references a vertex that does not exist")
        return self

    def physics_dump(self) -> dict[str, object]:
        """Everything that can change a flux result (no display metadata)."""
        return self.model_dump(mode="json", exclude={"display", "name"})


# --------------------------------------------------------------------------------- mesh


@dataclass
class IdealComparison:
    """How the represented mesh differs from the ideal analytic shape (geometry only)."""

    representation: Literal["exact", "inscribed_polyhedron", "custom"]
    ideal_area_m2: float | None
    ideal_volume_m3: float | None
    max_deviation_m: float | None  # largest distance between mesh and ideal surface


@dataclass
class Mesh:
    vertices: Arr  # (V, 3) world coordinates
    triangles: IArr  # (T, 3) indices, oriented as requested
    resolution_id: str  # e.g. "sphere/lon64-lat32", "box/exact"
    quality: Quality
    ideal: IdealComparison
    natural_orientation: Literal["outward", "inward"] = "outward"  # as generated / as given
    errors: list[LocalizedText] = field(default_factory=list)

    @property
    def tri(self) -> Arr:
        return self.vertices[self.triangles]  # (T, 3, 3)

    @property
    def valid(self) -> bool:
        return not self.errors


def _sphere_local(r: float, n_lon: int, n_lat: int) -> tuple[Arr, IArr]:
    """UV sphere with poles; all vertices on the sphere (inscribed polyhedron)."""
    verts = [(0.0, 0.0, r)]
    for i in range(1, n_lat):
        theta = math.pi * i / n_lat
        for j in range(n_lon):
            phi = 2 * math.pi * j / n_lon
            verts.append((r * math.sin(theta) * math.cos(phi), r * math.sin(theta) * math.sin(phi),
                          r * math.cos(theta)))
    verts.append((0.0, 0.0, -r))
    south = len(verts) - 1

    def ring(i: int, j: int) -> int:  # i = 1 .. n_lat-1
        return 1 + (i - 1) * n_lon + j % n_lon

    tris: list[tuple[int, int, int]] = []
    for j in range(n_lon):
        tris.append((0, ring(1, j), ring(1, j + 1)))
    for i in range(1, n_lat - 1):
        for j in range(n_lon):
            a, b = ring(i, j), ring(i, j + 1)
            c, d = ring(i + 1, j + 1), ring(i + 1, j)
            tris.append((a, d, c))
            tris.append((a, c, b))
    for j in range(n_lon):
        tris.append((south, ring(n_lat - 1, j + 1), ring(n_lat - 1, j)))
    return np.asarray(verts, float), np.asarray(tris, np.int64)


def _cylinder_local(r: float, h: float, n_circ: int, n_ax: int) -> tuple[Arr, IArr]:
    verts: list[tuple[float, float, float]] = []
    for k in range(n_ax + 1):
        z = -h / 2 + h * k / n_ax
        for j in range(n_circ):
            phi = 2 * math.pi * j / n_circ
            verts.append((r * math.cos(phi), r * math.sin(phi), z))
    bottom = len(verts)
    verts.append((0.0, 0.0, -h / 2))
    top = len(verts)
    verts.append((0.0, 0.0, h / 2))

    def v(k: int, j: int) -> int:
        return k * n_circ + j % n_circ

    tris: list[tuple[int, int, int]] = []
    for k in range(n_ax):
        for j in range(n_circ):
            tris.append((v(k, j), v(k, j + 1), v(k + 1, j + 1)))
            tris.append((v(k, j), v(k + 1, j + 1), v(k + 1, j)))
    for j in range(n_circ):
        tris.append((top, v(n_ax, j), v(n_ax, j + 1)))
        tris.append((bottom, v(0, j + 1), v(0, j)))
    return np.asarray(verts, float), np.asarray(tris, np.int64)


# Canonical-normal sign of the quad split (p00, p10, p11), (p00, p11, p01) for a face
# perpendicular to local axis a, with the two other axes in increasing order: e_y x e_z = +x,
# e_x x e_z = -y, e_x x e_y = +z.
_CANON_SIGN = (1, -1, 1)


def grid_box_cells(size: tuple[float, float, float], n: tuple[int, int, int]
                   ) -> tuple[Arr, list[list[tuple[int, int, int]]], list[list[int]]]:
    """Vertex grid of an axis-aligned box split into n cells, and for every cell its 12
    outward triangles (two per face) built from the shared grid vertices.

    Returns (vertices (V,3) local, per-cell triangle lists, per-cell face-of-triangle lists).
    Two neighbouring cells use the *same* two triangles for their shared face, with opposite
    winding (v1 and v2 swapped), so their solid angles cancel exactly."""
    nx, ny, nz = n
    xs = np.linspace(-size[0] / 2, size[0] / 2, nx + 1)
    ys = np.linspace(-size[1] / 2, size[1] / 2, ny + 1)
    zs = np.linspace(-size[2] / 2, size[2] / 2, nz + 1)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    verts = np.stack([gx, gy, gz], axis=-1).reshape(-1, 3)

    def vid(i: int, j: int, k: int) -> int:
        return (i * (ny + 1) + j) * (nz + 1) + k

    def face(axis: int, idx: tuple[int, int, int], outward: int
             ) -> list[tuple[int, int, int]]:
        # The quad at grid position idx on the plane perpendicular to `axis`.
        b, c = [a for a in range(3) if a != axis]

        def corner(db: int, dc: int) -> int:
            p = list(idx)
            p[b] += db
            p[c] += dc
            return vid(p[0], p[1], p[2])

        p00, p10, p11, p01 = corner(0, 0), corner(1, 0), corner(1, 1), corner(0, 1)
        if outward * _CANON_SIGN[axis] > 0:
            return [(p00, p10, p11), (p00, p11, p01)]
        return [(p00, p11, p10), (p00, p01, p11)]

    cells: list[list[tuple[int, int, int]]] = []
    faces: list[list[int]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                tris: list[tuple[int, int, int]] = []
                fidx: list[int] = []
                for axis in range(3):
                    for f, (offset, outward) in enumerate(((0, -1), (1, 1))):
                        idx = [i, j, k]
                        idx[axis] += offset
                        tris += face(axis, (idx[0], idx[1], idx[2]), outward)
                        fidx += [2 * axis + f] * 2  # faces ordered -x,+x,-y,+y,-z,+z
                cells.append(tris)
                faces.append(fidx)
    return verts, cells, faces


def box_size(shape: SurfaceShape) -> tuple[float, float, float]:
    if isinstance(shape, CubeShape):
        return (shape.side_m,) * 3
    assert isinstance(shape, BoxShape)
    return shape.size_m


def to_world(surface: GaussSurface, local: Arr) -> Arr:
    rot = rotation_matrix_xyz(surface.rotation_euler_xyz_rad)
    return np.asarray(local @ rot.T + np.asarray(surface.center_m, float), dtype=np.float64)


def signed_volume(vertices: Arr, triangles: IArr) -> float:
    c = vertices.mean(axis=0)
    t = vertices[triangles] - c
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def areas(tri: Arr) -> Arr:
    return np.asarray(0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]),
                                           axis=1), dtype=np.float64)


def reverse(triangles: IArr) -> IArr:
    return triangles[:, [0, 2, 1]]


def build_mesh(surface: GaussSurface, quality: Quality) -> Mesh:
    """The represented integration surface at the given quality level."""
    s = surface.shape
    ideal: IdealComparison
    if isinstance(s, SphereShape):
        n_lon, n_lat = SPHERE_RES[quality]
        local, tris = _sphere_local(s.radius_m, n_lon, n_lat)
        res = f"sphere/lon{n_lon}-lat{n_lat}"
        ideal = IdealComparison("inscribed_polyhedron", 4 * math.pi * s.radius_m**2,
                                4 / 3 * math.pi * s.radius_m**3, None)
    elif isinstance(s, CylinderShape):
        n_c, n_a = CYLINDER_RES[quality]
        local, tris = _cylinder_local(s.radius_m, s.height_m, n_c, n_a)
        res = f"cylinder/circ{n_c}-ax{n_a}"
        r, h = s.radius_m, s.height_m
        ideal = IdealComparison("inscribed_polyhedron", 2 * math.pi * r * (r + h),
                                math.pi * r * r * h, r * (1 - math.cos(math.pi / n_c)))
    elif isinstance(s, CubeShape | BoxShape):
        size = box_size(s)
        local, cells, _ = grid_box_cells(size, (1, 1, 1))
        tris = np.asarray(cells[0], np.int64)
        res = f"{s.type}/exact"
        ideal = IdealComparison("exact", 2 * (size[0] * size[1] + size[1] * size[2]
                                              + size[0] * size[2]), math.prod(size), 0.0)
    else:
        assert isinstance(s, MeshShape)
        local = np.asarray(s.vertices_m, float)
        tris = np.asarray(s.triangles, np.int64)
        res = f"mesh/custom-{len(tris)}"
        ideal = IdealComparison("custom", None, None, None)
    world = to_world(surface, local)
    mesh = Mesh(world, tris, res, quality, ideal)
    mesh.errors = validate(world, tris)
    if mesh.valid:
        natural = "outward" if signed_volume(world, tris) > 0 else "inward"
        mesh.natural_orientation = natural  # type: ignore[assignment]
        if natural != surface.orientation:
            mesh.triangles = reverse(tris)
        if isinstance(s, SphereShape):
            centre = np.asarray(surface.center_m, float)
            d = point_mesh_distance(centre[None], mesh.tri)[0]
            ideal.max_deviation_m = float(s.radius_m - d)
    return mesh


# --------------------------------------------------------------------------- validation


def validate(vertices: Arr, triangles: IArr) -> list[LocalizedText]:
    """Closed, edge- and vertex-manifold, consistently oriented, non-degenerate, connected,
    enclosing a nonzero volume. Self-intersections are not checked (documented limitation)."""
    errs: list[LocalizedText] = []
    if not np.all(np.isfinite(vertices)):
        return [L("The surface has non-finite vertex coordinates.",
                  "A felület csúcspontjainak koordinátái nem végesek.")]
    tri = vertices[triangles]
    ext = vertices.max(axis=0) - vertices.min(axis=0)
    l_char = float(ext.max()) if vertices.size else 0.0
    if l_char <= 0:
        return [L("The surface has zero size.", "A felület mérete nulla.")]
    a = areas(tri)
    bad = int(np.count_nonzero(a <= DEGENERATE_AREA_FACTOR * l_char**2))
    if bad:
        errs.append(L(f"{bad} triangle(s) have (almost) zero area (degenerate).",
                      f"{bad} háromszög területe (közel) nulla (elfajult)."))
    if np.any((triangles[:, 0] == triangles[:, 1]) | (triangles[:, 1] == triangles[:, 2])
              | (triangles[:, 0] == triangles[:, 2])):
        errs.append(L("A triangle uses the same vertex twice.",
                      "Egy háromszög kétszer használja ugyanazt a csúcsot."))
        return errs
    directed: dict[tuple[int, int], int] = {}
    undirected: dict[tuple[int, int], int] = {}
    for t in triangles.tolist():
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            directed[e] = directed.get(e, 0) + 1
            key = (min(e), max(e))
            undirected[key] = undirected.get(key, 0) + 1
    open_edges = sum(1 for n in undirected.values() if n == 1)
    nonmanifold_edges = sum(1 for n in undirected.values() if n > 2)
    if open_edges:
        errs.append(L(f"The surface is not closed: {open_edges} edge(s) belong to only one "
                      "triangle (a hole). Flux is defined only for closed surfaces.",
                      f"A felület nem zárt: {open_edges} él csak egy háromszöghöz tartozik "
                      "(lyuk). A fluxus csak zárt felületekre értelmezett."))
    if nonmanifold_edges:
        errs.append(L(f"{nonmanifold_edges} edge(s) are shared by more than two triangles "
                      "(non-manifold).",
                      f"{nonmanifold_edges} élen kettőnél több háromszög osztozik (nem sokaság)."))
    if not open_edges and not nonmanifold_edges:
        if any(n != 1 for n in directed.values()):
            errs.append(L("The triangles are not consistently oriented: some neighbours list "
                          "their shared edge in the same direction.",
                          "A háromszögek irányítása nem következetes: egyes szomszédok a közös "
                          "élüket azonos irányban járják be."))
        else:
            # Vertex manifoldness: the link of every vertex is a single cycle.
            nxt: dict[int, dict[int, int]] = {}
            for t in triangles.tolist():
                for k in range(3):
                    v, b, c = t[k], t[(k + 1) % 3], t[(k + 2) % 3]
                    nxt.setdefault(v, {})[b] = c
            pinched = 0
            for links in nxt.values():
                start = next(iter(links))
                cur, steps = start, 0
                while True:
                    cur = links.get(cur, -1)
                    steps += 1
                    if cur == start or cur == -1 or steps > len(links):
                        break
                if cur != start or steps != len(links):
                    pinched += 1
            if pinched:
                errs.append(L(f"{pinched} vertex/vertices join otherwise separate sheets "
                              "(non-manifold vertex).",
                              f"{pinched} csúcs egyébként különálló lapokat köt össze (nem "
                              "sokaság típusú csúcs)."))
    if not errs:
        # One connected component.
        parent = list(range(len(vertices)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for t in triangles.tolist():
            for u in t[1:]:
                parent[find(u)] = find(t[0])
        roots = {find(v) for v in np.unique(triangles).tolist()}
        if len(roots) > 1:
            errs.append(L(f"The surface consists of {len(roots)} separate pieces; use one closed "
                          "surface per Gaussian surface.",
                          f"A felület {len(roots)} különálló darabból áll; Gauss-felületenként "
                          "egy zárt felületet használjon."))
        elif abs(signed_volume(vertices, triangles)) <= 1e-12 * l_char**3:
            errs.append(L("The surface encloses no volume.", "A felület nem zár be térfogatot."))
    return errs


# ------------------------------------------------------------------- point classification


def point_mesh_distance(points: Arr, tri: Arr) -> Arr:
    """Unsigned distance from each point (N,3) to the triangle set (T,3,3)."""
    if points.shape[0] == 0:
        return np.zeros(0)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    p = points[:, None, :]
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = np.einsum("ij,ij->i", n, n)
    ap = p - a
    t = np.einsum("pij,ij->pi", ap, n) / nn
    proj = p - t[..., None] * n
    # Barycentric coordinates of the projection.
    v0, v1 = ab, ac
    v2 = proj - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("pij,ij->pi", v2, v0)
    d21 = np.einsum("pij,ij->pi", v2, v1)
    den = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    inside = (v >= 0) & (w >= 0) & (v + w <= 1)
    plane = np.abs(t) * np.sqrt(nn)

    def seg(p0: Arr, p1: Arr) -> Arr:
        d = p1 - p0
        s = np.clip(np.einsum("pij,ij->pi", p - p0, d) / np.einsum("ij,ij->i", d, d), 0, 1)
        q = p0 + s[..., None] * d
        return np.asarray(np.linalg.norm(p - q, axis=-1), dtype=np.float64)

    edge = np.minimum(np.minimum(seg(a, b), seg(b, c)), seg(c, a))
    dist = np.where(inside, plane, edge)
    return np.asarray(dist.min(axis=1), dtype=np.float64)


# Ray directions for the parity test: fixed, irrational-looking, not aligned with any axis or
# any face of the built-in meshes.
_RAYS = np.array([[0.5773502691896258, 0.5773502691896258, 0.5773502691896258],
                  [-0.3141592653589793, 0.8660254037844386, 0.3889087296526011],
                  [0.7071067811865476, -0.1234567890123457, -0.6963106238227914],
                  [-0.2718281828459045, -0.4142135623730950, 0.8689121373089131],
                  [0.1, 0.2, -0.9746794344808963]])
_RAYS = _RAYS / np.linalg.norm(_RAYS, axis=1, keepdims=True)


def ray_parity_inside(points: Arr, tri: Arr) -> tuple[NDArray[np.bool_], NDArray[np.int64]]:
    """Inside test by ray casting (Möller–Trumbore), majority over five fixed rays.

    Independent of solid angles: this is the classification used by the *volume* integral, so
    that surface and volume integrals are computed by different algorithms. Returns (inside,
    number of rays that agree with the majority)."""
    votes = np.zeros(points.shape[0], np.int64)
    a = tri[:, 0]
    e1, e2 = tri[:, 1] - a, tri[:, 2] - a
    for d in _RAYS:
        h = np.cross(d, e2)  # (T,3)
        det = np.einsum("ij,ij->i", e1, h)
        ok = np.abs(det) > 1e-300
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = points[:, None, :] - a  # (N,T,3)
        u = np.einsum("pij,ij->pi", s, h) * inv
        q = np.cross(s, e1)
        v = (q @ d) * inv
        t = np.einsum("pij,ij->pi", q, e2) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        votes += (hit.sum(axis=1) % 2).astype(np.int64)
    inside = votes >= 3
    agree = np.where(inside, votes, len(_RAYS) - votes)
    return inside, agree


@dataclass
class Classification:
    state: Literal["inside", "outside", "boundary"]
    signed_distance_m: float  # negative inside, positive outside; magnitude = distance to mesh
    near_boundary: bool  # visual warning only
    ray_agreement: int


def tolerances(mesh: Mesh, charge_positions: Arr) -> tuple[float, float, float]:
    """(L_char, tau_geom, near-boundary highlight distance) for this surface and charge set."""
    ext = mesh.vertices.max(axis=0) - mesh.vertices.min(axis=0)
    l_char = float(ext.max())
    scale = max(l_char, float(np.abs(mesh.vertices).max()),
                float(np.abs(charge_positions).max()) if charge_positions.size else 0.0)
    tau = max(1e-12 * l_char, 64 * EPS * scale)
    return l_char, tau, max(0.01 * l_char, 10 * tau)


def classify(mesh: Mesh, positions: Arr, tau: float, near: float) -> list[Classification]:
    if positions.shape[0] == 0:
        return []
    tri = mesh.tri
    dist = point_mesh_distance(positions, tri)
    inside, agree = ray_parity_inside(positions, tri)
    out: list[Classification] = []
    for d, ins, ag in zip(dist, inside, agree, strict=True):
        state: Literal["inside", "outside", "boundary"]
        state = "boundary" if d <= tau else ("inside" if ins else "outside")
        out.append(Classification(state, float(-d if ins else d), bool(d <= near), int(ag)))
    return out
