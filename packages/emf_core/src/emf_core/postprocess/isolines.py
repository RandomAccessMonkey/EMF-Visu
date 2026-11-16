"""Iso-contours (marching squares) and iso-surfaces (marching tetrahedra) of a scalar field.

Both start from samples of the scalar on a regular grid and locate sign changes of
``value - level`` along grid edges. Each crossing is then refined on its edge with the Illinois
(regula falsi) method using the *exact* scalar evaluator, so every output vertex lies on the true
level set to ``VERTEX_RTOL``. What remains approximate is the geometry between vertices: straight
segments / flat triangles replace curved ones (error O(h^2 * curvature)), and features smaller
than a grid cell are missed.

A sample that coincides with a point source has no value. If the caller supplies the sign of the
divergence there (``singular_sign``: +1 where the scalar tends to +infinity, −1 for −infinity),
the sample is treated as lying beyond every level on that side, which is exactly what the scalar
does; the crossing on each adjacent edge is then located with the exact evaluator like any other.
Without a sign, cells touching such a sample are skipped."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
ScalarFn = Callable[[Arr], Arr]  # (N, 3) points -> (N,) values

VERTEX_RTOL = 1e-9  # |value - level| <= VERTEX_RTOL * scale at every vertex (or 30 iterations)
_MAX_ITER = 30


def _with_singular(values: Arr, level: float, singular_sign: Arr | None) -> Arr:
    """Residuals value - level, with signed large stand-ins at singular samples."""
    s = values - level
    if singular_sign is None:
        return s
    finite = np.isfinite(s)
    big = 1e3 * (float(np.abs(s[finite]).max()) if finite.any() else 1.0) + 1.0
    fill = ~finite & (singular_sign != 0)
    return np.where(fill, singular_sign * big, s)


def refine_crossings(pa: Arr, pb: Arr, sa: Arr, sb: Arr, level: float, fn: ScalarFn,
                     scale: float) -> Arr:
    """Root of fn(p) - level on each segment pa->pb, given end residuals sa, sb of opposite sign."""
    # Canonical orientation (a = the end above the level): the same grid edge then yields a
    # bitwise identical vertex from every cell that shares it, so surfaces have no cracks.
    swap = sa < 0
    pa, pb = np.where(swap[:, None], pb, pa), np.where(swap[:, None], pa, pb)
    sa, sb = np.where(swap, sb, sa), np.where(swap, sa, sb)
    tol = VERTEX_RTOL * scale
    p = pa + (sa / (sa - sb))[:, None] * (pb - pa)
    todo = np.arange(pa.shape[0])
    side = np.zeros(pa.shape[0], np.int8)
    for _ in range(_MAX_ITER):
        if todo.size == 0:
            break
        sp = fn(p[todo]) - level
        done = np.abs(sp) <= tol
        same_a = np.sign(sp) == np.sign(sa[todo])
        ia, ib = todo[same_a], todo[~same_a]
        # Illinois modification: halve the retained end's residual when it is kept twice.
        sb[ia] = np.where(side[ia] == 1, sb[ia] * 0.5, sb[ia])
        sa[ib] = np.where(side[ib] == -1, sa[ib] * 0.5, sa[ib])
        pa[ia], sa[ia], side[ia] = p[ia], sp[same_a], 1
        pb[ib], sb[ib], side[ib] = p[ib], sp[~same_a], -1
        todo = todo[~done]
        p[todo] = pa[todo] + (sa[todo] / (sa[todo] - sb[todo]))[:, None] * (pb[todo] - pa[todo])
    return p


# Marching squares: corners c0=(j,i) c1=(j,i+1) c2=(j+1,i+1) c3=(j+1,i); edges e0=c0c1 e1=c1c2
# e2=c2c3 e3=c3c0. Entry: edge pairs for each case index (bit k set = corner k above the level).
_SQUARES: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((3, 0),), 2: ((0, 1),), 3: ((3, 1),), 4: ((1, 2),), 6: ((0, 2),), 7: ((3, 2),),
    8: ((2, 3),), 9: ((0, 2),), 11: ((1, 2),), 12: ((3, 1),), 13: ((0, 1),), 14: ((3, 0),),
}


def contour_segments(values: Arr, points: Arr, level: float, fn: ScalarFn, scale: float,
                     mask: NDArray[np.bool_] | None = None,
                     singular_sign: Arr | None = None) -> Arr:
    """Line segments (S, 2, 3) of the level set on a plane grid.

    ``values`` (nv, nu) and ``points`` (nv, nu, 3) are the grid samples; ``mask`` (nv-1, nu-1)
    marks cells to skip."""
    nv, nu = values.shape
    s = _with_singular(values, level, singular_sign)
    above = s > 0
    fin = np.isfinite(s)
    # Crossings on horizontal edges (j, i)-(j, i+1) and vertical edges (j, i)-(j+1, i).
    hx = (above[:, :-1] != above[:, 1:]) & fin[:, :-1] & fin[:, 1:]
    vx = (above[:-1, :] != above[1:, :]) & fin[:-1, :] & fin[1:, :]
    hp = np.full((nv, nu - 1, 3), np.nan)
    vp = np.full((nv - 1, nu, 3), np.nan)
    if hx.any():
        hp[hx] = refine_crossings(points[:, :-1][hx], points[:, 1:][hx], s[:, :-1][hx],
                                  s[:, 1:][hx], level, fn, scale)
    if vx.any():
        vp[vx] = refine_crossings(points[:-1, :][vx], points[1:, :][vx], s[:-1, :][vx],
                                  s[1:, :][vx], level, fn, scale)
    edge_pts = (hp[:-1], vp[:, 1:], hp[1:], vp[:, :-1])  # e0, e1, e2, e3 per cell
    ok = fin[:-1, :-1] & fin[:-1, 1:] & fin[1:, 1:] & fin[1:, :-1]
    if mask is not None:
        ok &= ~mask
    case = (above[:-1, :-1] * 1 + above[:-1, 1:] * 2 + above[1:, 1:] * 4 + above[1:, :-1] * 8)
    centre_above = 0.25 * (s[:-1, :-1] + s[:-1, 1:] + s[1:, 1:] + s[1:, :-1]) > 0
    out: list[Arr] = []

    def emit(sel: NDArray[np.bool_], pairs: tuple[tuple[int, int], ...]) -> None:
        if sel.any():
            for a, b in pairs:
                out.append(np.stack([edge_pts[a][sel], edge_pts[b][sel]], axis=1))

    for c, pairs in _SQUARES.items():
        emit(ok & (case == c), pairs)
    # Saddle cells: the sign at the cell centre decides which corners are connected.
    emit(ok & (case == 5) & centre_above, ((0, 1), (2, 3)))
    emit(ok & (case == 5) & ~centre_above, ((3, 0), (1, 2)))
    emit(ok & (case == 10) & centre_above, ((3, 0), (1, 2)))
    emit(ok & (case == 10) & ~centre_above, ((0, 1), (2, 3)))
    return np.concatenate(out, axis=0) if out else np.empty((0, 2, 3))


# Each cube is split into 6 tetrahedra sharing the main diagonal c0-c6. Corner numbering:
# index = dx + 2*dy + 4*dz.
_TETS = np.array([[0, 1, 3, 7], [0, 1, 5, 7], [0, 2, 3, 7], [0, 2, 6, 7], [0, 4, 5, 7],
                  [0, 4, 6, 7]])


def isosurface_triangles(values: Arr, points: Arr, level: float, fn: ScalarFn,
                         scale: float, singular_sign: Arr | None = None) -> Arr:
    """Triangles (T, 3, 3) of the level set on a lattice. ``values`` (nz, ny, nx) and ``points``
    (nz, ny, nx, 3). Marching tetrahedra: no ambiguous cases, surface is watertight inside the
    lattice."""
    nz, ny, nx = values.shape
    s = _with_singular(values, level, singular_sign)
    corners_s = []
    corners_p = []
    for c in range(8):
        dx, dy, dz = c & 1, (c >> 1) & 1, (c >> 2) & 1
        sl = (slice(dz, nz - 1 + dz), slice(dy, ny - 1 + dy), slice(dx, nx - 1 + dx))
        corners_s.append(s[sl].ravel())
        corners_p.append(points[sl].reshape(-1, 3))
    cs = np.stack(corners_s, axis=1)  # (cells, 8)
    cp = np.stack(corners_p, axis=1)  # (cells, 8, 3)
    cell_ok = np.all(np.isfinite(cs), axis=1)
    # Only cells the surface passes through.
    crossing = cell_ok & (cs.max(axis=1) > 0) & (cs.min(axis=1) <= 0)
    cs, cp = cs[crossing], cp[crossing]
    if cs.shape[0] == 0:
        return np.empty((0, 3, 3))
    ts = cs[:, _TETS].reshape(-1, 4)  # (tets, 4)
    tp = cp[:, _TETS].reshape(-1, 4, 3)
    above = ts > 0
    n_above = above.sum(axis=1)
    tri_pa: list[Arr] = []
    tri_pb: list[Arr] = []
    tri_sa: list[Arr] = []
    tri_sb: list[Arr] = []

    def add(sel: NDArray[np.bool_], order: NDArray[np.int64],
            tris: tuple[tuple[tuple[int, int], ...], ...]) -> None:
        # ``order`` permutes each selected tetrahedron's vertices; ``tris`` lists triangles as
        # three (from, to) vertex pairs in the permuted numbering.
        p = np.take_along_axis(tp[sel], order[:, :, None], axis=1)
        v = np.take_along_axis(ts[sel], order, axis=1)
        for tri in tris:
            for a, b in tri:
                tri_pa.append(p[:, a])
                tri_pb.append(p[:, b])
                tri_sa.append(v[:, a])
                tri_sb.append(v[:, b])

    for lone_above in (True, False):  # one vertex on one side, three on the other
        sel = n_above == (1 if lone_above else 3)
        if sel.any():
            flag = above[sel] if lone_above else ~above[sel]
            order = np.argsort(~flag, axis=1, kind="stable")  # the lone vertex first
            add(sel, order, (((0, 1), (0, 2), (0, 3)),))
    sel = n_above == 2
    if sel.any():
        order = np.argsort(~above[sel], axis=1, kind="stable")  # above: 0,1; below: 2,3
        add(sel, order, (((0, 2), (0, 3), (1, 3)), ((0, 2), (1, 3), (1, 2))))
    if not tri_pa:
        return np.empty((0, 3, 3))
    pa, pb = np.concatenate(tri_pa), np.concatenate(tri_pb)
    sa, sb = np.concatenate(tri_sa), np.concatenate(tri_sb)
    # The pieces were appended vertex-by-vertex per group; rebuild (T, 3, 3) group by group.
    verts = refine_crossings(pa, pb, sa, sb, level, fn, scale)
    tris_out: list[Arr] = []
    pos = 0
    for chunk in range(0, len(tri_pa), 3):
        n = tri_pa[chunk].shape[0]
        tris_out.append(np.stack([verts[pos:pos + n], verts[pos + n:pos + 2 * n],
                                  verts[pos + 2 * n:pos + 3 * n]], axis=1))
        pos += 3 * n
    return np.concatenate(tris_out, axis=0)
