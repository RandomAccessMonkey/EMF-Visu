"""World geometry of magnetic sources, shared by every solver and by the Ampère tool.

Phase 3A: a well-formed current source is an enabled object with role ``current_source`` and

* an ``infinite_wire`` source on a ``line`` primitive, or
* a ``circular_loop`` source on a ``ring`` primitive whose world transform is a similarity in
  the ring's own plane (otherwise the ring would be an ellipse, which is not modelled).

Phase 3B adds, with role ``current_source``:

* ``solenoid`` on a ``coil``: expanded into N coaxial circular turns (``LoopSource``) that keep
  the owning object id;
* ``toroid_finite`` on a ``torus``: expanded into N turns in meridional planes;
* ``toroid_ideal`` on a ``torus``: an ``IdealToroidSource`` (closed-form continuous winding);

and with role ``magnetic_material``:

* ``permanent_magnet`` on a ``cylinder``: a ``MagnetSource`` (uniform axial magnetization).

Coils, tori and magnets must have a pure rotation + translation world transform (their
dimensions are edited directly, not by scaling). Anything else is reported as a problem, never
approximated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from ..i18n import L, LocalizedText
from .models import (
    CircularLoopSource,
    CoilPrimitive,
    CylinderPrimitive,
    InfiniteWireSource,
    LinePrimitive,
    PermanentMagnetSource,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
    SolenoidSource,
    ToroidFiniteSource,
    ToroidIdealSource,
    TorusPrimitive,
)
from .transforms import world_matrix

Arr = NDArray[np.float64]
# Relative tolerance for "the in-plane scale is uniform and the in-plane axes are orthogonal".
SIMILARITY_RTOL = 1e-9
# Turns closer than this (relative to the coil or torus size) cannot be told apart by the
# solver's position tolerance and are refused; closer than WARN_SEPARATION × radius is warned.
MIN_SEPARATION_REL = 1e-9
WARN_SEPARATION = 0.01

LoopKind = Literal["circular_loop", "solenoid", "toroid_finite"]
SourceKind = Literal["infinite_wire", "circular_loop", "solenoid", "toroid_finite",
                     "toroid_ideal", "permanent_magnet"]


@dataclass(frozen=True)
class WireSource:
    object_id: str
    current_A: float
    point_m: Arr  # a point on the axis (world)
    direction: Arr  # unit vector; positive current flows along it


@dataclass(frozen=True)
class LoopSource:
    object_id: str
    current_A: float
    center_m: Arr
    normal: Arr  # unit vector; positive current circulates counter-clockwise about it
    radius_m: float
    u: Arr  # unit vector in the loop plane (world image of local +x); v = normal x u
    kind: LoopKind = "circular_loop"


@dataclass(frozen=True)
class MagnetSource:
    """Solid cylinder with uniform magnetization M along its axis (signed)."""

    object_id: str
    magnetization_A_per_m: float
    center_m: Arr
    axis: Arr  # unit vector (local +z); M vector = magnetization * axis
    u: Arr  # unit vector perpendicular to the axis (local +x)
    radius_m: float
    length_m: float

    @property
    def m_vector(self) -> Arr:
        out: Arr = self.magnetization_A_per_m * self.axis
        return out

    @property
    def moment_A_m2(self) -> Arr:
        out: Arr = self.m_vector * math.pi * self.radius_m**2 * self.length_m
        return out


@dataclass(frozen=True)
class IdealToroidSource:
    object_id: str
    current_A: float
    turns: int
    center_m: Arr
    axis: Arr  # unit vector (local +z); H = N I / (2 pi rho) e_phi about +axis for I > 0
    u: Arr
    major_radius_m: float
    core_radius_m: float
    relative_permeability: float


@dataclass
class SourceObject:
    """One scene object that is a magnetic source, with what the tables and the UI need."""

    object_id: str
    kind: SourceKind
    current_A: float | None = None  # per turn for coils and tori
    turns: int = 1
    magnetization_A_per_m: float | None = None
    center_m: Arr | None = None
    axis: Arr | None = None
    params: dict[str, float] = field(default_factory=dict)  # dimensions, by name


@dataclass
class CurrentSources:
    wires: list[WireSource]
    loops: list[LoopSource]  # stand-alone loops and every turn of solenoids and finite toroids
    problems: list[LocalizedText]
    magnets: list[MagnetSource] = field(default_factory=list)
    ideal_toroids: list[IdealToroidSource] = field(default_factory=list)
    objects: list[SourceObject] = field(default_factory=list)
    warnings: list[LocalizedText] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        """Object ids of all sources, one per scene object (turns are not listed separately)."""
        return [o.object_id for o in self.objects]

    @property
    def count(self) -> int:
        return len(self.objects)

    @property
    def free_current_scale_A(self) -> float:
        """Sum of |I| over every free-current filament (a solenoid of N turns counts N|I|)."""
        return float(sum(abs(o.current_A or 0.0) * o.turns for o in self.objects
                         if o.kind != "permanent_magnet"))


def enabled(scene: Scene, obj: SceneObject) -> bool:
    """An object contributes only if it and all of its ancestors are enabled."""
    by_id = {o.id: o for o in scene.objects}
    cur = obj
    while True:
        if not cur.enabled:
            return False
        if cur.parent_id is None:
            return True
        cur = by_id[cur.parent_id]


def is_current_object(o: SceneObject) -> bool:
    return o.role is Role.CURRENT_SOURCE


def is_magnetic_object(o: SceneObject) -> bool:
    """Objects that the magnetostatic model reads (free currents and magnetized material)."""
    return o.role in (Role.CURRENT_SOURCE, Role.MAGNETIC_MATERIAL)


def _unit(v: Arr) -> Arr | None:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 and np.isfinite(n) else None


def _rigid(lin: Arr) -> bool:
    """True if the 3x3 linear part is a rotation (unit, orthogonal columns, det +1)."""
    return bool(np.allclose(lin.T @ lin, np.eye(3), atol=1e-9) and np.linalg.det(lin) > 0)


def solenoid_turn_positions(turns: int, length_m: float) -> Arr:
    """Local axial positions z_k = -L/2 + k L/(N - 1); a single turn sits at z = 0."""
    if turns == 1:
        return np.zeros(1)
    out: Arr = np.asarray(-length_m / 2 + np.arange(turns) * (length_m / (turns - 1)),
                          dtype=np.float64)
    return out


def toroid_turn_angles(turns: int, phase: float) -> Arr:
    out: Arr = np.asarray(phase + 2.0 * np.pi * np.arange(turns) / turns, dtype=np.float64)
    return out


def _cylinder_points(m: MagnetSource, n_axis: int, n_phi: int, n_r: int) -> Arr:
    """Points filling a magnet's cylinder (for the overlap test)."""
    v = np.cross(m.axis, m.u)
    zs = np.linspace(-m.length_m / 2, m.length_m / 2, n_axis)
    phis = np.linspace(0, 2 * np.pi, n_phi, endpoint=False)
    rs = np.linspace(0, m.radius_m, n_r)
    z, ph, r = np.meshgrid(zs, phis, rs, indexing="ij")
    out: Arr = np.asarray(m.center_m + z.reshape(-1, 1) * m.axis
                          + (r * np.cos(ph)).reshape(-1, 1) * m.u
                          + (r * np.sin(ph)).reshape(-1, 1) * v, dtype=np.float64)
    return out


def magnet_local(points: Arr, m: MagnetSource) -> tuple[Arr, Arr]:
    """(rho, z) of points in a magnet's local cylindrical coordinates."""
    d = points - m.center_m
    z = d @ m.axis
    rho = np.linalg.norm(d - z[:, None] * m.axis, axis=1)
    return rho, z


def magnets_overlap(a: MagnetSource, b: MagnetSource, tol: float) -> bool:
    """Whether two magnets share interior points. Exact for the separated case (bounding
    spheres apart); otherwise checked by dense sampling of each cylinder against the other."""
    ra = math.hypot(a.radius_m, a.length_m / 2)
    rb = math.hypot(b.radius_m, b.length_m / 2)
    if float(np.linalg.norm(a.center_m - b.center_m)) >= ra + rb:
        return False
    for p, q in ((a, b), (b, a)):
        pts = _cylinder_points(p, 33, 48, 9)
        rho, z = magnet_local(pts, q)
        if np.any((rho < q.radius_m - tol) & (np.abs(z) < q.length_m / 2 - tol)):
            return True
    return False


def current_sources(scene: Scene) -> CurrentSources:
    out = CurrentSources(wires=[], loops=[], problems=[])
    for o in scene.objects:
        if not is_magnetic_object(o) or not enabled(scene, o):
            continue
        label = o.name or o.id
        m = world_matrix(scene, o)
        lin, pos = m[:3, :3], m[:3, 3].copy()
        src, prim = o.source, o.primitive
        if o.role is Role.MAGNETIC_MATERIAL:
            if isinstance(src, PermanentMagnetSource) and isinstance(prim, CylinderPrimitive):
                if not _rigid(lin):
                    out.problems.append(_scaled(label))
                    continue
                out.magnets.append(MagnetSource(
                    o.id, float(src.magnetization_A_per_m), pos, lin[:, 2].copy(),
                    lin[:, 0].copy(), float(prim.radius_m), float(prim.height_m)))
                out.objects.append(SourceObject(
                    o.id, "permanent_magnet", magnetization_A_per_m=float(
                        src.magnetization_A_per_m), center_m=pos, axis=lin[:, 2].copy(),
                    params={"radius_m": float(prim.radius_m), "length_m": float(prim.height_m)}))
            else:
                out.problems.append(L(
                    f"Object '{label}' has role 'magnetic_material' but is not a supported "
                    "magnetic material. Supported: a uniformly magnetized cylindrical permanent "
                    "magnet (a cylinder with a 'permanent_magnet' source). General magnetic "
                    "materials are a later milestone; nothing is approximated.",
                    f"A(z) '{label}' objektum szerepe 'magnetic_material', de nem támogatott "
                    "mágneses anyag. Támogatott: egyenletesen mágnesezett hengeres állandó "
                    "mágnes (henger 'permanent_magnet' forrással). Az általános mágneses anyagok "
                    "egy későbbi mérföldkő tárgyai; semmit sem közelítünk."))
            continue
        if isinstance(src, InfiniteWireSource) and isinstance(prim, LinePrimitive):
            d = _unit(lin @ np.array([0.0, 0.0, 1.0]))
            if d is None:
                out.problems.append(L(f"Wire '{label}' has a degenerate direction.",
                                      f"A(z) '{label}' vezeték iránya elfajult."))
                continue
            out.wires.append(WireSource(o.id, float(src.current_A), pos, d))
            out.objects.append(SourceObject(o.id, "infinite_wire", float(src.current_A),
                                            center_m=pos, axis=d))
        elif isinstance(src, CircularLoopSource) and isinstance(prim, RingPrimitive):
            cx, cy = lin[:, 0], lin[:, 1]
            sx, sy = float(np.linalg.norm(cx)), float(np.linalg.norm(cy))
            if (abs(sx - sy) > SIMILARITY_RTOL * max(sx, sy)
                    or abs(float(cx @ cy)) > SIMILARITY_RTOL * sx * sy):
                out.problems.append(L(
                    f"Loop '{label}' is scaled non-uniformly in its own plane, which would make it "
                    "an ellipse. Only circular loops are modelled; use the radius instead.",
                    f"A(z) '{label}' hurok saját síkjában nem egyenletesen van skálázva, így "
                    "ellipszis lenne. Csak kör alakú hurok modellezhető; a sugarat módosítsa."))
                continue
            n = _unit(np.cross(cx, cy))
            assert n is not None
            out.loops.append(LoopSource(o.id, float(src.current_A), pos, n,
                                        float(prim.radius_m) * sx, cx / sx))
            out.objects.append(SourceObject(o.id, "circular_loop", float(src.current_A),
                                            center_m=pos, axis=n,
                                            params={"radius_m": float(prim.radius_m) * sx}))
        elif isinstance(src, SolenoidSource) and isinstance(prim, CoilPrimitive):
            if not _rigid(lin):
                out.problems.append(_scaled(label))
                continue
            axis, u = lin[:, 2].copy(), lin[:, 0].copy()
            zk = solenoid_turn_positions(prim.turns, prim.length_m)
            if prim.turns > 1:
                spacing = prim.length_m / (prim.turns - 1)
                size = max(prim.radius_m, prim.length_m)
                if spacing <= MIN_SEPARATION_REL * size:
                    out.problems.append(_too_close(label, spacing))
                    continue
                if spacing < WARN_SEPARATION * prim.radius_m:
                    out.warnings.append(_close_warning(label, spacing))
            for z in zk:
                out.loops.append(LoopSource(o.id, float(src.current_A), pos + z * axis, axis,
                                            float(prim.radius_m), u, "solenoid"))
            out.objects.append(SourceObject(o.id, "solenoid", float(src.current_A),
                                            prim.turns, center_m=pos, axis=axis,
                                            params={"radius_m": float(prim.radius_m),
                                                    "length_m": float(prim.length_m)}))
        elif isinstance(src, ToroidFiniteSource) and isinstance(prim, TorusPrimitive):
            if not _rigid(lin):
                out.problems.append(_scaled(label))
                continue
            ex, ey, ez = lin[:, 0], lin[:, 1], lin[:, 2]
            r_maj, b = float(prim.major_radius_m), float(prim.winding_radius_m)
            if prim.turns > 1:
                # Closest approach of neighbouring turns: their innermost points (rho = R - b).
                sep = 2.0 * (r_maj - b) * math.sin(math.pi / prim.turns)
                if sep <= MIN_SEPARATION_REL * r_maj:
                    out.problems.append(_too_close(label, sep))
                    continue
                if sep < WARN_SEPARATION * b:
                    out.warnings.append(_close_warning(label, sep))
            for phi in toroid_turn_angles(prim.turns, float(prim.phase_rad)):
                e_rho = math.cos(phi) * ex + math.sin(phi) * ey
                e_phi = -math.sin(phi) * ex + math.cos(phi) * ey
                out.loops.append(LoopSource(o.id, float(src.current_A), pos + r_maj * e_rho,
                                            e_phi.copy(), b, e_rho.copy(), "toroid_finite"))
            out.objects.append(SourceObject(o.id, "toroid_finite", float(src.current_A),
                                            prim.turns, center_m=pos, axis=ez.copy(),
                                            params={"major_radius_m": r_maj,
                                                    "winding_radius_m": b}))
        elif isinstance(src, ToroidIdealSource) and isinstance(prim, TorusPrimitive):
            if not _rigid(lin):
                out.problems.append(_scaled(label))
                continue
            out.ideal_toroids.append(IdealToroidSource(
                o.id, float(src.current_A), prim.turns, pos, lin[:, 2].copy(), lin[:, 0].copy(),
                float(prim.major_radius_m), float(prim.core_radius_m),
                float(src.relative_permeability)))
            out.objects.append(SourceObject(
                o.id, "toroid_ideal", float(src.current_A), prim.turns, center_m=pos,
                axis=lin[:, 2].copy(),
                params={"major_radius_m": float(prim.major_radius_m),
                        "core_radius_m": float(prim.core_radius_m),
                        "relative_permeability": float(src.relative_permeability)}))
        else:
            out.problems.append(L(
                f"Object '{label}' has role 'current_source' but is not a supported current "
                "source. Supported: an infinite straight wire (a line with an 'infinite_wire' "
                "source), a circular loop (a ring with a 'circular_loop' source), a solenoid (a "
                "coil with a 'solenoid' source) and a toroid (a torus with a 'toroid_finite' or "
                "'toroid_ideal' source). Nothing is approximated by a simpler model.",
                f"A(z) '{label}' objektum szerepe 'current_source', de nem támogatott áramforrás. "
                "Támogatott: végtelen egyenes vezető (vonal 'infinite_wire' forrással), körvezető "
                "(gyűrű 'circular_loop' forrással), szolenoid (tekercs 'solenoid' forrással) és "
                "toroid (tórusz 'toroid_finite' vagy 'toroid_ideal' forrással). Egyszerűbb "
                "modellel nem helyettesítjük."))
    if out.ideal_toroids and len(out.objects) > 1:
        out.problems.append(L(
            "The ideal toroid is a self-contained idealized model (continuous winding, linear "
            "core, perfect confinement). It cannot be combined with other magnetic sources: its "
            "core would also respond to their fields, which this model does not describe. Use the "
            "finite-turn toroid to combine sources.",
            "Az ideális toroid önálló, idealizált modell (folytonos tekercselés, lineáris mag, "
            "tökéletes térbezárás). Nem kombinálható más mágneses forrással: a mag azok terére "
            "is reagálna, amit ez a modell nem ír le. Források kombinálásához a véges menetszámú "
            "toroidot használja."))
    tol = 1e-9 * max([1.0] + [max(m.radius_m, m.length_m) for m in out.magnets])
    for i, a in enumerate(out.magnets):
        for b2 in out.magnets[i + 1:]:
            if magnets_overlap(a, b2, tol):
                out.problems.append(L(
                    f"Magnets '{a.object_id}' and '{b2.object_id}' overlap. Overlapping "
                    "prescribed magnetizations are not modelled (the magnetization of the common "
                    "region would be undefined).",
                    f"A(z) '{a.object_id}' és '{b2.object_id}' mágnes átfedi egymást. Az átfedő "
                    "előírt mágnesezettségeket nem modellezzük (a közös tartomány "
                    "mágnesezettsége nem lenne értelmezett)."))
    return out


def _scaled(label: str) -> LocalizedText:
    return L(f"Object '{label}' is scaled. Coils, tori and magnets are sized by their own "
             "dimension fields; a scaled transform would distort the modelled geometry, so it is "
             "refused. Reset the scale to 1 and edit the dimensions instead.",
             f"A(z) '{label}' objektum skálázva van. A tekercsek, tóruszok és mágnesek méretét a "
             "saját méretmezőik adják meg; a skálázott transzformáció torzítaná a modellezett "
             "geometriát, ezért elutasítjuk. Állítsa a skálát 1-re, és a méreteket módosítsa.")


def _too_close(label: str, sep: float) -> LocalizedText:
    return L(f"The turns of '{label}' are only {sep:.3g} m apart, which the solver's position "
             "tolerance cannot resolve; the configuration is refused.",
             f"A(z) '{label}' menetei csak {sep:.3g} m-re vannak egymástól, amit a megoldó "
             "helytűrése nem tud feloldani; az elrendezést elutasítjuk.")


def _close_warning(label: str, sep: float) -> LocalizedText:
    return L(f"The turns of '{label}' are close together ({sep:.3g} m). The field varies on that "
             "scale between the turns; sampled pictures may not resolve it (probe values do).",
             f"A(z) '{label}' menetei közel vannak egymáshoz ({sep:.3g} m). A tér ezen a "
             "skálán változik a menetek között; a mintavételezett ábrák ezt nem feltétlenül "
             "oldják fel (a szonda értékei igen).")
