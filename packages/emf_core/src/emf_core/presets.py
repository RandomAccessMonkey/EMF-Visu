"""Preset catalog. All presets of the product definition are listed; a preset is only
``available`` when a solver that supports its scene exists. Unavailable presets carry no scene.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .ampere import AmperePath
from .circuits import EddyDisk, PassiveCircuit
from .coax import CoaxSpec
from .i18n import L, LocalizedText
from .induction import FluxSurface
from .lorentz import TestCharge
from .scene.models import (
    CircularLoopSource,
    CoilPrimitive,
    CylinderPrimitive,
    Domain,
    GroupPrimitive,
    InfiniteWireSource,
    LinePrimitive,
    PermanentMagnetSource,
    PointChargeSource,
    PointPrimitive,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
    SolenoidSource,
    ToroidFiniteSource,
    ToroidIdealSource,
    TorusPrimitive,
    Transform,
)


class PresetVariant(BaseModel):
    """An alternative configuration of the same preset (Phase 3A: preset 10)."""

    id: str
    name: LocalizedText
    description: LocalizedText
    expected_behavior: LocalizedText
    scene: Scene


class ViewHint(BaseModel):
    """View the preset opens with (display only; never part of the physics)."""

    mode: Literal["2d", "3d"] | None = None
    plane: Literal["xy", "xz", "yz"] | None = None
    probe_m: tuple[float, float, float] | None = None  # default probe point (Phase 3B)


class TimeHint(BaseModel):
    """Simulation-time range and step a time-dependent preset opens with (Phase 4A). The
    physics at a time t does not depend on these; they only set the playback."""

    start_s: float
    end_s: float
    step_s: float
    initial_s: float = 0.0


class Preset(BaseModel):
    id: str
    number: int
    name: LocalizedText
    available: bool
    planned_phase: int | None = None
    description: LocalizedText | None = None  # short guided explanation
    expected_behavior: LocalizedText | None = None
    equation_ids: list[str] = []
    scene: Scene | None = None
    variants: list[PresetVariant] = []  # the first variant, if any, is the default scene
    view_hint: ViewHint | None = None
    ampere_paths: list[AmperePath] = []  # default Ampère paths (Phase 3B)
    # Phase 4A: default Faraday measurement surfaces and the time range the preset opens with.
    flux_surfaces: list[FluxSurface] = []
    time: TimeHint | None = None
    # Phase 4B: a test charge (Lorentz-force probe and optional trajectory).
    test_charge: TestCharge | None = None
    # Phase 4C: passive circuits and eddy-current disks.
    circuits: list[PassiveCircuit] = []
    eddy_disks: list[EddyDisk] = []
    # Coaxial-cable TEM model (standalone analytical model, shown instead of the scene).
    coax: CoaxSpec | None = None


def _charge(oid: str, name: str, q: float, pos: tuple[float, float, float],
            parent_id: str | None = None) -> SceneObject:
    return SceneObject(id=oid, name=name, primitive=PointPrimitive(), role=Role.CHARGE_SOURCE,
                       source=PointChargeSource(charge_C=q), transform=Transform(position_m=pos),
                       parent_id=parent_id)


def dipole_objects(group_id: str, name: str, q: float, d: float,
                   pos: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[SceneObject]:
    """A dipole as two real point charges: +q at local (−d/2, 0, 0) and −q at (+d/2, 0, 0),
    children of a group whose transform positions and orients the pair."""
    return [
        SceneObject(id=group_id, name=name, primitive=GroupPrimitive(kind="dipole"),
                    transform=Transform(position_m=pos)),
        _charge(f"{group_id}_pos", "q₊", abs(q), (-d / 2, 0.0, 0.0), group_id),
        _charge(f"{group_id}_neg", "q₋", -abs(q), (d / 2, 0.0, 0.0), group_id),
    ]


_EQ = ["coulomb_field", "coulomb_potential", "superposition", "e_from_potential",
       "gauss_electric_vacuum", "div_E_point_charges", "curl_E_electrostatic",
       "constitutive_d_linear"]

_AVAILABLE = [
    Preset(
        id="single_positive_charge", number=1, available=True, equation_ids=_EQ,
        name=L("Single positive point charge", "Egyetlen pozitív ponttöltés"),
        description=L("One positive charge of +1 nC at the origin. The arrows show the force "
                      "direction on a positive test charge.",
                      "Egy +1 nC nagyságú pozitív töltés az origóban. A nyilak a pozitív "
                      "próbatöltésre ható erő irányát mutatják."),
        expected_behavior=L("E points radially outward and falls off as 1/r²; φ is positive and "
                            "falls off as 1/r.",
                            "E sugárirányban kifelé mutat és 1/r² szerint csökken; φ pozitív és "
                            "1/r szerint csökken."),
        scene=Scene(objects=[_charge("q1", "q₁", 1e-9, (0, 0, 0))]),
    ),
    Preset(
        id="single_negative_charge", number=2, available=True, equation_ids=_EQ,
        name=L("Single negative point charge", "Egyetlen negatív ponttöltés"),
        description=L("One negative charge of −1 nC at the origin.",
                      "Egy −1 nC nagyságú negatív töltés az origóban."),
        expected_behavior=L("E points radially inward; φ is negative.",
                            "E sugárirányban befelé mutat; φ negatív."),
        scene=Scene(objects=[_charge("q1", "q₁", -1e-9, (0, 0, 0))]),
    ),
    Preset(
        id="electric_dipole", number=3, available=True, equation_ids=_EQ,
        name=L("Electric dipole", "Elektromos dipólus"),
        description=L("Two point charges, +1 nC and −1 nC, separated by d = 1 m along x. Select "
                      "the dipole to change q and d together.",
                      "Két ponttöltés, +1 nC és −1 nC, egymástól d = 1 m távolságra az x tengely "
                      "mentén. A dipólust kijelölve q és d együtt módosítható."),
        expected_behavior=L("The field leaves the positive charge and enters the negative one; "
                            "φ = 0 on the symmetry plane x = 0; far away |E| falls off as 1/r³.",
                            "A mező a pozitív töltésből indul és a negatívba érkezik; az x = 0 "
                            "szimmetriasíkon φ = 0; nagy távolságban |E| 1/r³ szerint csökken."),
        scene=Scene(objects=dipole_objects("dipole", "Dipole", 1e-9, 1.0)),
    ),
    Preset(
        id="multiple_charges", number=4, available=True, equation_ids=_EQ,
        name=L("Multiple interacting point charges", "Több kölcsönható ponttöltés"),
        description=L("Four charges of mixed sign. Drag them to see superposition at work.",
                      "Négy, vegyes előjelű töltés. Mozgassa őket a szuperpozíció "
                      "megfigyeléséhez."),
        expected_behavior=L("The total field is the vector sum of the four Coulomb fields.",
                            "Az eredő mező a négy Coulomb-tér vektori összege."),
        scene=Scene(objects=[_charge("q1", "q₁", 2e-9, (-0.8, -0.6, 0)),
                             _charge("q2", "q₂", -1e-9, (0.8, -0.6, 0)),
                             _charge("q3", "q₃", 1e-9, (0.0, 0.8, 0)),
                             _charge("q4", "q₄", -2e-9, (0.9, 0.9, 0))]),
    ),
]

def _wire(oid: str, name: str, current: float, x: float, y: float = 0.0) -> SceneObject:
    """Infinite wire along +z through (x, y, 0); the line length (4 m) is display-only."""
    return SceneObject(id=oid, name=name, primitive=LinePrimitive(length_m=4.0),
                       role=Role.CURRENT_SOURCE, source=InfiniteWireSource(current_A=current),
                       transform=Transform(position_m=(x, y, 0.0)))


def _loop(oid: str, name: str, current: float, radius: float) -> SceneObject:
    return SceneObject(id=oid, name=name, primitive=RingPrimitive(radius_m=radius),
                       role=Role.CURRENT_SOURCE, source=CircularLoopSource(current_A=current))


_EQ_WIRE = ["biot_savart", "biot_savart_integral", "infinite_wire_field", "b_mu0_h", "h_from_b",
            "gauss_magnetic", "div_B_filaments", "ampere_static"]
_EQ_WIRES = [*_EQ_WIRE, "superposition_magnetic"]
_EQ_LOOP = ["biot_savart", "biot_savart_integral", "loop_axis_field", "loop_field_elliptic",
            "b_mu0_h", "h_from_b", "gauss_magnetic", "div_B_filaments", "ampere_static"]


def _two_wires(i1: float, i2: float) -> Scene:
    return Scene(objects=[_wire("w1", "I₁", i1, -0.5), _wire("w2", "I₂", i2, 0.5)])


_VARIANTS_10 = [
    PresetVariant(
        id="same", name=L("Same direction", "Azonos irány"),
        description=L("Two infinite wires along z at x = ±0.5 m, both carrying +10 A (out of the "
                      "xy cross-section, ⊙).",
                      "Két végtelen vezető a z tengellyel párhuzamosan, x = ±0,5 m-nél, mindkettőben "
                      "+10 A (az xy metszetből kifelé, ⊙)."),
        expected_behavior=L("Between the wires the two contributions oppose each other and B = 0 "
                            "exactly midway; far away the lines encircle both wires like one "
                            "wire carrying 20 A.",
                            "A vezetők között a két járulék ellentétes, és pontosan félúton "
                            "B = 0; távolabb a vonalak mindkét vezetőt körülölelik, mintha egy "
                            "20 A-es vezető lenne."),
        scene=_two_wires(10.0, 10.0)),
    PresetVariant(
        id="opposite", name=L("Opposite directions", "Ellentétes irány"),
        description=L("+10 A at x = −0.5 m (⊙) and −10 A at x = +0.5 m (⊗).",
                      "+10 A x = −0,5 m-nél (⊙) és −10 A x = +0,5 m-nél (⊗)."),
        expected_behavior=L("Between the wires the contributions reinforce each other; the "
                            "field lines are circles around each wire, shifted apart, and far "
                            "away the field falls off faster (as 1/r²).",
                            "A vezetők között a járulékok erősítik egymást; az erővonalak "
                            "egymástól eltolt körök az egyes vezetők körül, és nagy távolságban a "
                            "tér gyorsabban (1/r² szerint) csökken."),
        scene=_two_wires(10.0, -10.0)),
    PresetVariant(
        id="unequal", name=L("Unequal currents", "Különböző áramok"),
        description=L("Same direction, 10 A at x = −0.5 m and 4 A at x = +0.5 m.",
                      "Azonos irány, 10 A x = −0,5 m-nél és 4 A x = +0,5 m-nél."),
        expected_behavior=L("The zero of B moves towards the weaker wire, to x = 3/14 m ≈ "
                            "0.214 m, where 10 A/(0.714 m) = 4 A/(0.286 m).",
                            "B nullhelye a gyengébb vezető felé tolódik, x = 3/14 m ≈ 0,214 m-re, "
                            "ahol 10 A/(0,714 m) = 4 A/(0,286 m)."),
        scene=_two_wires(10.0, 4.0)),
]

_MAGNETIC = [
    Preset(
        id="straight_wire", number=9, available=True, equation_ids=_EQ_WIRE,
        name=L("Straight current-carrying wire", "Egyenes áramvezető"),
        description=L("An infinitely long straight wire along z through the origin carrying "
                      "I = 10 A (out of the xy cross-section). The drawn segment is only a "
                      "picture of the infinite wire.",
                      "Végtelen hosszú egyenes vezető a z tengely mentén, az origón át, "
                      "I = 10 A árammal (az xy metszetből kifelé). A megjelenített szakasz csak "
                      "a végtelen vezető ábrázolása."),
        expected_behavior=L("B circles the wire counter-clockwise seen from +z (right-hand "
                            "rule) and |B| = μ₀I/(2πr): 2 µT at 1 m.",
                            "B a vezetőt +z felől nézve az óramutatóval ellentétesen kerüli meg "
                            "(jobbkéz-szabály), és |B| = μ₀I/(2πr): 1 m-en 2 µT."),
        scene=Scene(objects=[_wire("w1", "I", 10.0, 0.0)]),
    ),
    Preset(
        id="two_parallel_wires", number=10, available=True, equation_ids=_EQ_WIRES,
        name=L("Two parallel current-carrying wires", "Két párhuzamos áramvezető"),
        description=_VARIANTS_10[0].description,
        expected_behavior=_VARIANTS_10[0].expected_behavior,
        scene=_VARIANTS_10[0].scene, variants=_VARIANTS_10,
    ),
    Preset(
        id="circular_loop", number=11, available=True, equation_ids=_EQ_LOOP,
        name=L("Circular current loop", "Köráram"),
        description=L("A thin circular loop of radius a = 0.5 m in the xy plane carrying "
                      "I = 10 A counter-clockwise seen from +z. The 2D view opens on the xz "
                      "cross-section through the loop axis.",
                      "Vékony körvezető a = 0,5 m sugárral az xy síkban, I = 10 A árammal, +z "
                      "felől nézve az óramutatóval ellentétes irányban. A 2D nézet a körvezető "
                      "tengelyén átmenő xz metszeten nyílik meg."),
        expected_behavior=L("On the axis B points along +z with B = μ₀Ia²/(2(a² + z²)^{3/2}), "
                            "12.6 µT at the centre; the field lines close around the wire "
                            "(⊙ on one side of the cross-section, ⊗ on the other).",
                            "A tengelyen B a +z irányba mutat, B = μ₀Ia²/(2(a² + z²)^{3/2}), a "
                            "középpontban 12,6 µT; az erővonalak a vezető körül záródnak (a "
                            "metszet egyik oldalán ⊙, a másikon ⊗)."),
        scene=Scene(objects=[_loop("loop1", "Loop", 10.0, 0.5)]),
        view_hint=ViewHint(mode="2d", plane="xz"),
    ),
]

_EQ_SOL = ["finite_solenoid_superposition", "solenoid_turn_spacing", "solenoid_turn_density",
           "ideal_solenoid_B", "ideal_solenoid_H", "loop_field_elliptic", "superposition_magnetic",
           "ampere_integral", "ampere_static", "gauss_magnetic", "b_mu0_h"]
_EQ_TOR = ["finite_toroid_superposition", "ideal_toroid_H", "ideal_toroid_B",
           "constitutive_b_linear", "ampere_integral", "ampere_static", "gauss_magnetic"]
_EQ_MAG = ["magnet_sheet_field", "constitutive_b_general", "h_from_b_m", "bound_currents",
           "magnetic_moment", "dipole_far_field", "free_bound_currents", "ampere_integral",
           "ampere_vacuum_B", "gauss_magnetic"]
_HALF_PI = 1.5707963267948966


def _torus(source: ToroidFiniteSource | ToroidIdealSource) -> Scene:
    return Scene(
        objects=[SceneObject(id="toroid1", name="Toroid", role=Role.CURRENT_SOURCE,
                             primitive=TorusPrimitive(major_radius_m=0.12, winding_radius_m=0.03,
                                                      core_radius_m=0.03, turns=24),
                             source=source)],
        domain=Domain(min_m=(-0.2, -0.2, -0.1), max_m=(0.2, 0.2, 0.1)))


_TOROID_PATH = AmperePath.model_validate({"id": "A1", "name": "Coaxial circle",
                                          "shape": {"type": "circle", "radius_m": 0.12}})

_VARIANTS_13 = [
    PresetVariant(
        id="finite", name=L("Finite-turn model", "Véges menetszámú modell"),
        description=L("24 separate circular turns (b_winding = 0.03 m) around a centreline of "
                      "radius R = 0.12 m, 1 A each, in vacuum.",
                      "24 különálló kör alakú menet (b_winding = 0,03 m) egy R = 0,12 m sugarú "
                      "középvonal körül, egyenként 1 A, vákuumban."),
        expected_behavior=L("A strong field circulating inside the winding (about μ₀NI/(2πρ)), "
                            "rippled by the discrete turns, and a weak leakage field outside "
                            "that is not forced to zero. The coaxial Ampère path links all 24 "
                            "turns: ∮H·dl = 24 A.",
                            "Erős, a tekercselésen belül körbefutó tér (kb. μ₀NI/(2πρ)), a diszkrét "
                            "menetek miatt hullámos, és gyenge szórt tér kívül, amelyet nem "
                            "kényszerítünk nullára. A koaxiális Ampère-út mind a 24 menetet "
                            "körülöleli: ∮H·dl = 24 A."),
        scene=_torus(ToroidFiniteSource(current_A=1.0))),
    PresetVariant(
        id="ideal", name=L("Ideal continuous winding", "Ideális folytonos tekercselés"),
        description=L("The idealized model: continuous winding on a circular core of radius "
                      "b_core = 0.03 m with μᵣ = 1 (change μᵣ under Parameters), perfect "
                      "confinement.",
                      "Az idealizált modell: folytonos tekercselés egy b_core = 0,03 m sugarú, "
                      "kör keresztmetszetű magon, μᵣ = 1 (a Paraméterek alatt módosítható), "
                      "tökéletes térbezárás."),
        expected_behavior=L("H = NI/(2πρ) and B = μ₀μᵣH inside the core, exactly zero outside "
                            "(an idealization, not the field of a real winding).",
                            "A magban H = NI/(2πρ) és B = μ₀μᵣH, kívül pontosan nulla (idealizáció, "
                            "nem egy valódi tekercs tere)."),
        scene=_torus(ToroidIdealSource(current_A=1.0, relative_permeability=1.0))),
]

_COILS_AND_MAGNETS = [
    Preset(
        id="solenoid", number=12, available=True, equation_ids=_EQ_SOL,
        name=L("Finite solenoid", "Véges szolenoid"),
        description=L("20 discrete circular turns of radius a = 0.04 m over a winding length "
                      "L = 0.20 m along z, 1 A each (turn spacing L/(N−1) ≈ 10.5 mm). The 2D "
                      "view is the xz cross-section through the axis. Each turn's field is "
                      "added exactly; lead wires and helical connections are not modelled.",
                      "20 diszkrét, a = 0,04 m sugarú kör alakú menet L = 0,20 m tekercshosszon "
                      "a z tengely mentén, egyenként 1 A (menetköz L/(N−1) ≈ 10,5 mm). A 2D "
                      "nézet a tengelyen átmenő xz metszet. Minden menet terét egzaktul "
                      "összeadjuk; a hozzávezetéseket és a csavarvonalas összeköttetést nem "
                      "modellezzük."),
        expected_behavior=L("Inside, the turns' fields add up to a strong, nearly uniform axial "
                            "field, strongest at the centre (≈ 0.11 mT vs. the ideal "
                            "μ₀nI = 0.126 mT; the coil is only 2.5 diameters long). Near the "
                            "ends fewer turns contribute and the field spreads out (fringe "
                            "field); outside the coil it is weak. The ideal value becomes a good "
                            "approximation in the middle of a long, densely wound coil. The "
                            "Ampère rectangle encloses 12 turns: ∮H·dl = 12 A.",
                            "Belül a menetek terei erős, közel homogén tengelyirányú térré adódnak, "
                            "amely a középpontban a legerősebb (≈ 0,11 mT, szemben az ideális "
                            "μ₀nI = 0,126 mT-val; a tekercs csak 2,5 átmérőnyi hosszú). A végek "
                            "közelében kevesebb menet járul hozzá, és a tér szétterül (szórt tér); "
                            "a tekercsen kívül gyenge. Az ideális érték egy hosszú, sűrűn "
                            "tekercselt tekercs közepén válik jó közelítéssé. Az Ampère-téglalap "
                            "12 menetet zár közre: ∮H·dl = 12 A."),
        scene=Scene(objects=[SceneObject(
            id="solenoid1", name="Solenoid", role=Role.CURRENT_SOURCE,
            primitive=CoilPrimitive(radius_m=0.04, length_m=0.2, turns=20),
            source=SolenoidSource(current_A=1.0))],
            domain=Domain(min_m=(-0.15, -0.15, -0.25), max_m=(0.15, 0.15, 0.25))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.0, 0.0, 0.0)),
        ampere_paths=[AmperePath.model_validate({
            "id": "A1", "name": "Rectangle",
            "shape": {"type": "rectangle", "width_m": 0.06, "height_m": 0.12},
            "center_m": (0.04, 0.0, 0.0), "rotation_euler_xyz_rad": (-_HALF_PI, 0.0, 0.0)})],
    ),
    Preset(
        id="toroid", number=13, available=True, equation_ids=_EQ_TOR,
        name=L("Toroidal solenoid", "Toroid tekercs"),
        description=_VARIANTS_13[0].description, expected_behavior=_VARIANTS_13[0].expected_behavior,
        scene=_VARIANTS_13[0].scene, variants=_VARIANTS_13,
        view_hint=ViewHint(mode="2d", plane="xy", probe_m=(0.12, 0.0, 0.0)),
        ampere_paths=[_TOROID_PATH],
    ),
    Preset(
        id="permanent_magnet", number=14, available=True, equation_ids=_EQ_MAG,
        name=L("Uniformly magnetized cylindrical permanent magnet",
               "Egyenletesen mágnesezett hengeres állandó mágnes"),
        description=L("A cylinder of radius 0.04 m and length 0.08 m with uniform magnetization "
                      "M = 5×10⁵ A/m along +z (equivalent B_r = μ₀M ≈ 0.63 T, a "
                      "parameterization, not a material curve). Its field comes from the bound "
                      "surface current K = M × n on the side wall.",
                      "0,04 m sugarú, 0,08 m hosszú henger egyenletes M = 5×10⁵ A/m "
                      "mágnesezettséggel a +z irányban (egyenértékű B_r = μ₀M ≈ 0,63 T, "
                      "paraméterezés, nem anyaggörbe). Tere a palást K = M × n kötött felületi "
                      "áramából származik."),
        expected_behavior=L("B lines leave the north (+z) end, return outside and close through "
                            "the magnet. Inside, H = B/μ₀ − M points backwards (from N to S), "
                            "opposite to B. The Ampère rectangle cuts the side wall: "
                            "∮H·dl = 0 (no free current) while ∮B·dl = μ₀ M L ≠ 0 (bound current). "
                            "Far away the field approaches a dipole with m = Mπa²L.",
                            "A B-vonalak az északi (+z) végen lépnek ki, kívül visszatérnek, és a "
                            "mágnesen át záródnak. Belül H = B/μ₀ − M visszafelé mutat (É-tól "
                            "D felé), B-vel ellentétesen. Az Ampère-téglalap metszi a palástot: "
                            "∮H·dl = 0 (nincs szabad áram), míg ∮B·dl = μ₀ M L ≠ 0 (kötött áram). "
                            "Távol a tér egy m = Mπa²L momentumú dipóluséhoz közelít."),
        scene=Scene(objects=[SceneObject(
            id="magnet1", name="Magnet", role=Role.MAGNETIC_MATERIAL,
            primitive=CylinderPrimitive(radius_m=0.04, height_m=0.08),
            source=PermanentMagnetSource(magnetization_A_per_m=5e5))],
            domain=Domain(min_m=(-0.2, -0.2, -0.2), max_m=(0.2, 0.2, 0.2))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.0, 0.0, 0.0)),
        ampere_paths=[AmperePath.model_validate({
            "id": "A1", "name": "Rectangle through the wall",
            "shape": {"type": "rectangle", "width_m": 0.05, "height_m": 0.12},
            "center_m": (0.045, 0.0, 0.0), "rotation_euler_xyz_rad": (-_HALF_PI, 0.0, 0.0)})],
    ),
]

_PLANNED: list[tuple[int, str, str, str, int]] = [
    (5, "infinite_line_charge", "Infinite line charge", "Végtelen vonaltöltés", 2),
    (6, "parallel_plate_capacitor", "Parallel plate capacitor", "Síkkondenzátor", 2),
    (7, "coaxial_conductors", "Coaxial cylindrical conductors", "Koaxiális hengeres vezetők", 2),
    (8, "charged_conducting_sphere", "Charged conducting sphere", "Töltött vezető gömb", 2),
    (17, "electrostatic_plus_induced", "Electrostatic field combined with an induced rotational "
     "electric field", "Elektrosztatikus mező és indukált örvényes elektromos mező együtt", 4),
    (18, "dielectric_in_capacitor", "Dielectric material inside a capacitor",
     "Dielektrikum a kondenzátorban", 5),
    (19, "finite_conductivity_conductor", "Conductor with finite conductivity",
     "Véges vezetőképességű vezető", 5),
    (20, "plane_wave", "Electromagnetic plane wave propagation",
     "Elektromágneses síkhullám terjedése", 5),
]

# --------------------------------------------------------------- Phase 4A: induction presets

_EQ_IND = ["current_sinusoidal", "vector_potential_coulomb", "e_ind_from_a", "e_decomposition",
           "faraday_differential", "magnetic_flux", "flux_derivative", "faraday_integral",
           "lenz_law", "magnetoquasistatic", "loop_field_elliptic"]


def _toroid_measurement_rotation(phi: float) -> tuple[float, float, float]:
    """Euler XYZ angles that put a rectangle's local x along e_rho(phi) and local y along +z
    (normal along -e_phi): the plane through the toroid axis at azimuth phi."""
    import numpy as np
    from scipy.spatial.transform import Rotation

    ex = np.array([np.cos(phi), np.sin(phi), 0.0])
    ey = np.array([0.0, 0.0, 1.0])
    mat = np.column_stack([ex, ey, np.cross(ex, ey)])
    a, b, c = Rotation.from_matrix(mat).as_euler("XYZ")
    return (float(a), float(b), float(c))


_TOROID_PHI = 3.141592653589793 / 24  # midway between turns 0 and 1 (24 turns)

_INDUCTION = [
    Preset(
        id="changing_b_in_loop", number=15, available=True, equation_ids=_EQ_IND,
        name=L("Sinusoidally driven circular loop", "Szinuszosan táplált körvezető"),
        description=L("A circular loop of radius 0.05 m carries I(t) = 2 sin(2π·1 Hz·t) A. A "
                      "stationary disk of radius 0.03 m, coaxial with the loop and 0.02 m above "
                      "it, is the Faraday measurement surface; its boundary circle is the "
                      "integration path. Magnetoquasistatic model: B follows I(t) instantly.",
                      "Egy 0,05 m sugarú körvezetőben I(t) = 2 sin(2π·1 Hz·t) A folyik. Egy "
                      "álló, 0,03 m sugarú, a hurokkal koaxiális korong 0,02 m-rel fölötte a "
                      "Faraday-mérőfelület; határoló köre az integrálási út. "
                      "Magnetokvázisztatikus modell: B azonnal követi I(t)-t."),
        expected_behavior=L("B grows and reverses with the current. The induced field E_ind "
                            "circulates about the axis, largest when the current crosses zero "
                            "(dI/dt largest) and zero at the current's peaks. Its direction "
                            "opposes the change of flux (Lenz). ∮E_ind·dl and −dΦ/dt are "
                            "computed independently and agree.",
                            "B az árammal együtt nő és megfordul. Az indukált E_ind a tengely "
                            "körül kering, akkor a legnagyobb, amikor az áram nullán halad át "
                            "(dI/dt a legnagyobb), és nulla az áram csúcsainál. Iránya a "
                            "fluxusváltozással ellentétes (Lenz). ∮E_ind·dl és −dΦ/dt "
                            "egymástól függetlenül számítva megegyezik."),
        scene=Scene(objects=[SceneObject(
            id="loop1", name="Driven loop", role=Role.CURRENT_SOURCE,
            primitive=RingPrimitive(radius_m=0.05),
            source=CircularLoopSource.model_validate({"current_A": 0.0, "profile": {
                "type": "sinusoidal", "dc_A": 0.0, "peak_A": 2.0, "frequency_Hz": 1.0,
                "phase_rad": 0.0}}))],
            domain=Domain(min_m=(-0.1, -0.1, -0.1), max_m=(0.1, 0.1, 0.1))),
        view_hint=ViewHint(mode="2d", plane="xy", probe_m=(0.03, 0.0, 0.0)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Coaxial disk", "shape": {"type": "circle", "radius_m": 0.03},
            "center_m": (0.0, 0.0, 0.02)})],
        time=TimeHint(start_s=0.0, end_s=2.0, step_s=0.02),
    ),
    Preset(
        id="faraday_induction", number=16, available=True,
        equation_ids=["current_ramp", *_EQ_IND[1:], "finite_solenoid_superposition"],
        name=L("Ramping finite solenoid", "Rámpával táplált véges szolenoid"),
        description=L("The 20-turn solenoid of preset 12 (a = 0.04 m, L = 0.20 m) with its "
                      "current ramped from 0 A to 5 A over 1 s (5 A/s), then held. A stationary "
                      "coaxial measurement loop of radius 0.03 m sits 0.02 m beyond the end "
                      "turn.",
                      "A 12. előbeállítás 20 menetes szolenoidja (a = 0,04 m, L = 0,20 m), "
                      "árama 1 s alatt 0 A-ről 5 A-re nő (5 A/s), majd állandó. Egy álló, "
                      "koaxiális, 0,03 m sugarú mérőhurok 0,02 m-rel a végső menet után "
                      "helyezkedik el."),
        expected_behavior=L("During the ramp the axial B grows linearly and the flux through the "
                            "loop increases at a constant rate, so the EMF is constant and "
                            "negative: E_ind circulates clockwise seen along +z, against the "
                            "growing flux (Lenz). After t = 1 s the current is constant: B stays, "
                            "the EMF and E_ind vanish. At t = 0 and t = 1 s dI/dt jumps; the "
                            "application reports both one-sided values.",
                            "A rámpa alatt a tengelyirányú B lineárisan nő, a hurkon átmenő "
                            "fluxus állandó ütemben nő, így az EMF állandó és negatív: E_ind +z "
                            "felől nézve az óramutató járásával megegyezően kering, a növekvő "
                            "fluxus ellen (Lenz). t = 1 s után az áram állandó: B megmarad, az "
                            "EMF és E_ind eltűnik. t = 0-nál és t = 1 s-nál dI/dt ugrik; az "
                            "alkalmazás mindkét egyoldali értéket megadja."),
        scene=Scene(objects=[SceneObject(
            id="solenoid1", name="Solenoid", role=Role.CURRENT_SOURCE,
            primitive=CoilPrimitive(radius_m=0.04, length_m=0.2, turns=20),
            source=SolenoidSource.model_validate({"current_A": 0.0, "profile": {
                "type": "ramp", "start_A": 0.0, "slope_A_per_s": 5.0, "t_start_s": 0.0,
                "t_end_s": 1.0}}))],
            domain=Domain(min_m=(-0.15, -0.15, -0.25), max_m=(0.15, 0.15, 0.25))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.02, 0.0, 0.12)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Measurement loop", "shape": {"type": "circle", "radius_m": 0.03},
            "center_m": (0.0, 0.0, 0.12)})],
        time=TimeHint(start_s=0.0, end_s=1.5, step_s=0.01, initial_s=0.5),
    ),
    Preset(
        id="toroid_mutual_induction", number=21, available=True,
        equation_ids=[*_EQ_IND, "finite_toroid_superposition", "mutual_inductance",
                      "mutual_reciprocity"],
        name=L("Finite-turn toroid and mutual induction",
               "Véges menetszámú toroid és kölcsönös indukció"),
        description=L("The finite-turn toroid of preset 13 (R = 0.12 m, b = 0.03 m, N = 24) "
                      "driven by I(t) = sin(2π·50 Hz·t) A. A separate passive rectangular "
                      "measurement loop (0.10 m × 0.10 m) encircles the winding's cross-section "
                      "in the plane through the axis midway between two turns. No current flows "
                      "in the measurement loop: only its EMF and the mutual inductance are "
                      "computed.",
                      "A 13. előbeállítás véges menetszámú toroidja (R = 0,12 m, b = 0,03 m, "
                      "N = 24), I(t) = sin(2π·50 Hz·t) A árammal. Egy külön passzív, téglalap "
                      "alakú mérőhurok (0,10 m × 0,10 m) körülöleli a tekercselés "
                      "keresztmetszetét a tengelyen átmenő síkban, két menet között félúton. A "
                      "mérőhurokban nem folyik áram: csak az EMF-je és a kölcsönös "
                      "induktivitás számítódik."),
        expected_behavior=L("Almost all of the toroidal flux passes through the measurement "
                            "loop, so M₁₂ is large and EMF₂ = −M₁₂ dI/dt follows the source "
                            "current's derivative. M₁₂ (flux of the toroid through the loop) "
                            "and M₂₁ (flux of the loop's field through the 24 turns) are "
                            "computed independently and agree (reciprocity).",
                            "A toroidális fluxus szinte teljes egészében átmegy a mérőhurkon, "
                            "így M₁₂ nagy, és EMF₂ = −M₁₂ dI/dt a forrásáram deriváltját követi. "
                            "M₁₂ (a toroid fluxusa a hurkon át) és M₂₁ (a hurok terének fluxusa "
                            "a 24 meneten át) egymástól függetlenül számítva megegyezik "
                            "(reciprocitás)."),
        scene=Scene(objects=[SceneObject(
            id="toroid1", name="Toroid", role=Role.CURRENT_SOURCE,
            primitive=TorusPrimitive(major_radius_m=0.12, winding_radius_m=0.03,
                                     core_radius_m=0.03, turns=24),
            source=ToroidFiniteSource.model_validate({"current_A": 0.0, "profile": {
                "type": "sinusoidal", "dc_A": 0.0, "peak_A": 1.0, "frequency_Hz": 50.0,
                "phase_rad": 0.0}}))],
            domain=Domain(min_m=(-0.2, -0.2, -0.1), max_m=(0.2, 0.2, 0.1))),
        view_hint=ViewHint(mode="2d", plane="xy", probe_m=(0.12, 0.0, 0.0)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Measurement loop",
            "shape": {"type": "rectangle", "width_m": 0.1, "height_m": 0.1},
            "center_m": (0.12 * 0.9914448613738104, 0.12 * 0.13052619222005157, 0.0),
            "rotation_euler_xyz_rad": _toroid_measurement_rotation(_TOROID_PHI),
            # traversed so that the normal is +e_phi, along the toroidal field: M12 > 0
            "reversed": True})],
        time=TimeHint(start_s=0.0, end_s=0.04, step_s=0.0005),
    ),
]

# ------------------------------------------------- Phase 4B: moving conductors and particles

_HH_R = 0.15  # Helmholtz pair: coil radius = separation
_HH_I = 100.0  # A per loop (e.g. a 10-turn coil at 10 A, modelled as one thin loop)
_EQ_MOT = ["material_velocity", "motional_field", "motional_emf", "generalized_emf",
           "moving_surface_flux", "generalized_faraday", "loop_field_elliptic"]


def _helmholtz(current: float = _HH_I) -> list[SceneObject]:
    return [SceneObject(id=f"coil{k}", name=f"Coil {k}", role=Role.CURRENT_SOURCE,
                        primitive=RingPrimitive(radius_m=_HH_R),
                        source=CircularLoopSource(current_A=current),
                        transform=Transform(position_m=(0.0, 0.0, z)))
            for k, z in ((1, -_HH_R / 2), (2, _HH_R / 2))]


_HH_DOMAIN = Domain(min_m=(-0.2, -0.2, -0.2), max_m=(0.2, 0.2, 0.2))

_MOTION = [
    Preset(
        id="sliding_rod_generator", number=22, available=True,
        equation_ids=[*_EQ_MOT, "translational_velocity", "sliding_rod_emf", "flux_area_change",
                      "lenz_law"],
        name=L("Sliding-rod generator", "Csúszó rudas generátor"),
        description=L("Two stationary rails 0.10 m apart in the midplane of a Helmholtz pair "
                      "(two coaxial loops, radius 0.15 m, 0.15 m apart, 100 A each), joined by a "
                      "fixed segment at x = −0.10 m. A straight rod slides along the rails at "
                      "0.50 m/s from t = 0 and stops at t = 0.3 s. The field is the actual field "
                      "of the two finite coils, not a declared uniform field.",
                      "Két álló sín 0,10 m távolságra egy Helmholtz-pár (két koaxiális hurok, "
                      "sugár 0,15 m, távolság 0,15 m, egyenként 100 A) középsíkjában, x = −0,10 "
                      "m-nél rögzített szakasszal összekötve. Egy egyenes rúd t = 0-tól 0,50 m/s "
                      "sebességgel csúszik a síneken, és t = 0,3 s-kor megáll. A tér a két véges "
                      "tekercs tényleges tere, nem előírt homogén tér."),
        expected_behavior=L("The rod sweeps field lines into the circuit: the flux grows and the "
                            "motional EMF ∮(u × B)·dl ≈ −BLv appears only on the rod (rails and "
                            "connecting segment are at rest). −dΦ/dt from the flux values agrees "
                            "with it. Near the rail ends the field is weaker than at the centre, "
                            "so the EMF departs from the uniform-field reference BLv. After the "
                            "rod stops the EMF is zero; at t = 0.3 s the velocity jumps and the "
                            "instantaneous EMF is undefined unless a one-sided convention is "
                            "chosen.",
                            "A rúd erővonalakat söpör az áramkörbe: a fluxus nő, és a ∮(u × B)·dl "
                            "≈ −BLv mozgási EMF csak a rúdon keletkezik (a sínek és az összekötő "
                            "szakasz áll). A fluxusértékekből számolt −dΦ/dt ezzel megegyezik. A "
                            "sínek végeinél a tér gyengébb, mint középen, így az EMF eltér a BLv "
                            "homogén referenciától. A rúd megállása után az EMF nulla; t = 0,3 "
                            "s-kor a sebesség ugrik, és a pillanatnyi EMF egyoldali konvenció "
                            "nélkül nem értelmezett."),
        scene=Scene(objects=_helmholtz(), domain=_HH_DOMAIN),
        view_hint=ViewHint(mode="3d", plane="xy", probe_m=(0.0, 0.0, 0.0)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Rail circuit", "center_m": (-0.1, 0.0, 0.0),
            "shape": {"type": "sliding_rod", "rail_separation_m": 0.1, "rail_length_m": 0.2,
                      "rod_position_m": 0.02,
                      "rod_motion": {"type": "constant_velocity",
                                     "velocity_m_per_s": (0.5, 0.0, 0.0), "t_end_s": 0.3}}})],
        time=TimeHint(start_s=0.0, end_s=0.4, step_s=0.005, initial_s=0.1),
    ),
    Preset(
        id="rotating_coil_generator", number=23, available=True,
        equation_ids=[*_EQ_MOT, "angular_velocity_rotation", "rotating_coil_flux",
                      "multi_turn_linkage", "lenz_law"],
        name=L("Generator principle: rotating coil", "Generátorelv: forgó tekercs"),
        description=L("A rectangular measurement loop (0.08 m × 0.06 m) at the centre of the "
                      "Helmholtz pair of preset 22 rotates about the x axis at ω = 2π rad/s "
                      "(1 revolution per second). Its starting orientation has the normal along "
                      "+z, along B. Change the axis, ω, the initial orientation or the number of "
                      "turns of the measurement coil.",
                      "Egy téglalap alakú mérőhurok (0,08 m × 0,06 m) a 22. előbeállítás "
                      "Helmholtz-párjának közepén az x tengely körül forog ω = 2π rad/s "
                      "szögsebességgel (másodpercenként egy fordulat). Kezdetben normálisa +z, "
                      "B irányú. Módosítható a tengely, ω, a kezdeti orientáció vagy a "
                      "mérőtekercs menetszáma."),
        expected_behavior=L("The flux follows the angle of the normal, Φ ≈ BA cos ωt, and the "
                            "motional EMF ≈ BAω sin ωt is largest when the coil's plane is "
                            "parallel to B. The generalized Faraday law holds at every time; in "
                            "the nearly uniform central field the waveform matches the ideal "
                            "uniform-field reference closely.",
                            "A fluxus a normális szögét követi, Φ ≈ BA cos ωt, a mozgási EMF ≈ "
                            "BAω sin ωt pedig akkor a legnagyobb, amikor a tekercs síkja "
                            "párhuzamos B-vel. Az általánosított Faraday-törvény minden "
                            "időpontban teljesül; a közel homogén középső térben a hullámforma "
                            "jól egyezik az ideális homogén referenciával."),
        scene=Scene(objects=_helmholtz(), domain=_HH_DOMAIN),
        view_hint=ViewHint(mode="3d", plane="yz", probe_m=(0.0, 0.0, 0.0)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Rotating coil",
            "shape": {"type": "rectangle", "width_m": 0.08, "height_m": 0.06},
            "motion": {"rotation": {"type": "constant_angular_velocity", "axis": (1.0, 0.0, 0.0),
                                    "omega_rad_per_s": 6.283185307179586}}})],
        time=TimeHint(start_s=0.0, end_s=2.0, step_s=0.01, initial_s=0.125),
    ),
    Preset(
        id="charged_particle_magnetic", number=24, available=True,
        equation_ids=["lorentz_force", "magnetic_force", "electric_force",
                      "magnetic_force_no_work", "cyclotron_frequency", "cyclotron_radius",
                      "newton_lorentz", "kinetic_energy", "nonrelativistic_validity",
                      "loop_field_elliptic"],
        name=L("Charged particle in a magnetic field", "Töltött részecske mágneses térben"),
        description=L("A proton (q = 1.602×10⁻¹⁹ C, m = 1.673×10⁻²⁷ kg) starts near the centre "
                      "of the Helmholtz pair of preset 22 (B ≈ 0.60 mT along z) with v₀ = "
                      "(1000, 0, 200) m/s. It is a test particle: it does not change the field.",
                      "Egy proton (q = 1,602×10⁻¹⁹ C, m = 1,673×10⁻²⁷ kg) a 22. előbeállítás "
                      "Helmholtz-párjának közepe közeléből indul (B ≈ 0,60 mT, z irányú) v₀ = "
                      "(1000, 0, 200) m/s sebességgel. Próbarészecske: nem változtatja meg a "
                      "teret."),
        expected_behavior=L("The magnetic force is perpendicular to the velocity, so the "
                            "proton moves on a helix about the field: gyration with ω_c = |q|B/m "
                            "≈ 5.8×10⁴ rad/s and radius r_c = m v⊥/(|q|B) ≈ 17 mm, drifting "
                            "along z at 200 m/s. Only magnetic forces act, so the kinetic energy "
                            "stays constant. In the nearly uniform centre the path matches the "
                            "ideal helix.",
                            "A mágneses erő merőleges a sebességre, így a proton csavarvonalon "
                            "mozog a tér körül: körfrekvenciája ω_c = |q|B/m ≈ 5,8×10⁴ rad/s, "
                            "sugara r_c = m v⊥/(|q|B) ≈ 17 mm, közben z irányban 200 m/s-mal "
                            "halad. Csak mágneses erő hat, így a mozgási energia állandó. A közel "
                            "homogén középen a pálya az ideális csavarvonalnak felel meg."),
        scene=Scene(objects=_helmholtz(), domain=_HH_DOMAIN),
        view_hint=ViewHint(mode="3d", plane="xy", probe_m=(0.0, 0.0, -0.03)),
        test_charge=TestCharge.model_validate({
            "charge_C": 1.602176634e-19, "mass_kg": 1.67262192369e-27,
            "position_m": (0.0, 0.0, -0.03), "velocity_m_per_s": (1000.0, 0.0, 200.0),
            "trajectory": {"enabled": True, "start_s": 0.0, "end_s": 3.3e-4,
                           "tolerance": 0.02, "max_steps": 20000}}),
        time=TimeHint(start_s=0.0, end_s=3.3e-4, step_s=1.1e-6),
    ),
    Preset(
        id="combined_induction_motion", number=25, available=True,
        equation_ids=[*_EQ_MOT, "current_sinusoidal", "e_ind_from_a", "translational_velocity",
                      "faraday_integral", "lenz_law"],
        name=L("Combined transformer and motional induction",
               "Transzformátor- és mozgási indukció együtt"),
        description=L("A circular source loop (radius 0.10 m) carries I(t) = 10 sin(2π·1 Hz·t) "
                      "A. A coaxial measurement loop (radius 0.03 m) oscillates along the axis "
                      "about z = 0.05 m with amplitude 0.03 m at 0.5 Hz. Both the field and the "
                      "circuit change.",
                      "Egy kör alakú forráshurok (sugár 0,10 m) árama I(t) = 10 sin(2π·1 Hz·t) "
                      "A. Egy koaxiális mérőhurok (sugár 0,03 m) a tengely mentén z = 0,05 m "
                      "körül 0,03 m amplitúdóval, 0,5 Hz-cel rezeg. A tér és az áramkör is "
                      "változik."),
        expected_behavior=L("The transformer EMF ∮E_ind·dl (changing current) and the motional "
                            "EMF ∮(u × B)·dl (moving loop) are shown separately; their sum, the "
                            "generalized EMF, equals −dΦ/dt of the flux through the moving "
                            "surface at every time.",
                            "A transzformátor-EMF ∮E_ind·dl (változó áram) és a mozgási EMF "
                            "∮(u × B)·dl (mozgó hurok) külön látható; összegük, az általánosított "
                            "EMF minden időpontban megegyezik a mozgó felületen átmenő fluxus "
                            "−dΦ/dt értékével."),
        scene=Scene(objects=[SceneObject(
            id="loop1", name="Source loop", role=Role.CURRENT_SOURCE,
            primitive=RingPrimitive(radius_m=0.1),
            source=CircularLoopSource.model_validate({"current_A": 0.0, "profile": {
                "type": "sinusoidal", "dc_A": 0.0, "peak_A": 10.0, "frequency_Hz": 1.0,
                "phase_rad": 0.0}}))],
            domain=Domain(min_m=(-0.15, -0.15, -0.1), max_m=(0.15, 0.15, 0.15))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.02, 0.0, 0.05)),
        flux_surfaces=[FluxSurface.model_validate({
            "id": "F1", "name": "Moving loop", "shape": {"type": "circle", "radius_m": 0.03},
            "center_m": (0.0, 0.0, 0.05),
            "motion": {"translation": {"type": "sinusoidal", "amplitude_m": 0.03,
                                       "axis": (0.0, 0.0, 1.0), "frequency_Hz": 0.5,
                                       "phase_rad": 0.0}}})],
        time=TimeHint(start_s=0.0, end_s=2.0, step_s=0.01, initial_s=0.2),
    ),
]

# ------------------------------------------------------- Phase 4C: passive circuits

_EQ_CIRC = ["passive_loop_equation", "flux_linkage", "circuit_voltage_equation",
            "resistance_sigma", "joule_heating", "self_magnetic_energy", "lenz_passive",
            "transformer_induced_current", "loop_field_elliptic"]


def _src_loop(oid: str, name: str, radius: float, z: float, profile: dict[str, object]
              ) -> SceneObject:
    return SceneObject(id=oid, name=name, role=Role.CURRENT_SOURCE,
                       primitive=RingPrimitive(radius_m=radius),
                       source=CircularLoopSource.model_validate({"current_A": 0.0,
                                                                 "profile": profile}),
                       transform=Transform(position_m=(0.0, 0.0, z)))


def _copper_loop(cid: str, name: str, radius: float, z: float) -> PassiveCircuit:
    return PassiveCircuit.model_validate({
        "id": cid, "name": name,
        "path": {"id": cid, "shape": {"type": "circle", "radius_m": radius},
                 "center_m": (0.0, 0.0, z)},
        "electrical": {"material": "copper", "wire_radius_m": 0.001,
                       "self_inductance": {"mode": "thin_loop"}}})


_CIRCUITS = [
    Preset(
        id="shorted_loop_induction", number=26, available=True,
        equation_ids=[*_EQ_CIRC, "fixed_rl_equation", "thin_loop_inductance"],
        name=L("Shorted loop induction", "Rövidre zárt hurok indukciója"),
        description=L("A circular source loop (radius 0.05 m, at the origin, axis +z) whose current "
                      "ramps from 0 to 5 A in 0.1 s and is then held. A shorted copper loop "
                      "(radius 0.04 m, wire radius 1 mm, 0.04 m above) is a passive circuit: "
                      "R = ℓ/(σA) ≈ 1.38 mΩ, ℒ ≈ 0.19 µH from the thin-loop formula, "
                      "τ = ℒ/R ≈ 0.14 ms.",
                      "Egy kör alakú forráshurok (sugár 0,05 m, az origóban, tengely +z), árama "
                      "0,1 s alatt 0-ról 5 A-re nő, majd állandó. Egy rövidre zárt rézhurok "
                      "(sugár 0,04 m, huzalsugár 1 mm, 0,04 m-rel fölötte) passzív áramkör: "
                      "R = ℓ/(σA) ≈ 1,38 mΩ, ℒ ≈ 0,19 µH a vékony hurok képletéből, "
                      "τ = ℒ/R ≈ 0,14 ms."),
        expected_behavior=L("While the source current rises, the shorted loop carries a current "
                            "of opposite sense, I ≈ −(1/R) dΦ/dt after the very short RL "
                            "transient (τ ≈ 0.14 ms, faster than one 1 ms step). When the source "
                            "current becomes constant at t = 0.1 s the induced current decays "
                            "with τ. The loop's own field, its Joule heating and magnetic energy "
                            "are shown.",
                            "Amíg a forrásáram nő, a rövidre zárt hurokban ellentétes irányú áram "
                            "folyik, I ≈ −(1/R) dΦ/dt a nagyon rövid RL tranziens után (τ ≈ 0,14 "
                            "ms, rövidebb egy 1 ms-os lépésnél). Amikor t = 0,1 s-kor a forrásáram "
                            "állandó lesz, az indukált áram τ időállandóval lecseng. Látható a "
                            "hurok saját tere, Joule-hője és mágneses energiája."),
        scene=Scene(objects=[_src_loop("src", "Source loop", 0.05, 0.0, {
            "type": "ramp", "start_A": 0.0, "slope_A_per_s": 50.0, "t_start_s": 0.0,
            "t_end_s": 0.1})], domain=Domain(min_m=(-0.1, -0.1, -0.1), max_m=(0.1, 0.1, 0.1))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.0, 0.0, 0.02)),
        circuits=[_copper_loop("P1", "Shorted loop", 0.04, 0.04)],
        time=TimeHint(start_s=0.0, end_s=0.5, step_s=0.001, initial_s=0.05),
    ),
    Preset(
        id="magnetic_braking_rod", number=27, available=True,
        equation_ids=["motional_induced_current", "magnetic_force_loop", "translational_dynamics",
                      "electromagnetic_power", "energy_exchange", "joule_heating",
                      "passive_loop_equation", "motional_emf", "sliding_rod_emf",
                      "finite_solenoid_superposition"],
        name=L("Magnetic braking: sliding rod", "Mágneses fékezés: csúszó rúd"),
        description=L("A finite solenoid (200 turns, radius 0.05 m, length 0.10 m, 10 A, axis +z, "
                      "centred at the origin) provides the field; its actual finite-turn field is "
                      "used. Rails 0.10 m apart and 0.30 m long lie in the plane z = 0.06 m "
                      "(1 cm above the top turn), centred on y = 0 and running from x = −0.15 m "
                      "to +0.15 m. The rod (mass 20 g) starts at x = −0.05 m with +0.50 m/s; "
                      "the circuit has R = 2 mΩ and ℒ = 5 µH; no external force or damping.",
                      "Egy véges szolenoid (200 menet, sugár 0,05 m, hossz 0,10 m, 10 A, tengely "
                      "+z, az origó körül) adja a teret; a tényleges véges menetszámú tér "
                      "számít. A 0,10 m-re lévő, 0,30 m hosszú sínek a z = 0,06 m síkban "
                      "(1 cm-rel a felső menet fölött) fekszenek, y = 0 körül, x = −0,15 m-től "
                      "+0,15 m-ig. A rúd (20 g) x = −0,05 m-ről +0,50 m/s sebességgel indul; az "
                      "áramkör R = 2 mΩ, ℒ = 5 µH; nincs külső erő vagy csillapítás."),
        expected_behavior=L("The moving rod has a motional EMF; the closed circuit carries an "
                            "induced current, and the force I L × B on the rod opposes its "
                            "motion: the rod slows down while kinetic energy turns into Joule "
                            "heat and magnetic energy. With these parameters the braking is "
                            "weak (the speed drops by about 0.2 % before the rod reaches the end "
                            "of the rails at t ≈ 0.40 s, where the circuit opens and the "
                            "simulation stops). Lower R or m, or a stronger field, brakes more. "
                            "BLv is shown only as a comparison with the local field.",
                            "A mozgó rúdban mozgási EMF keletkezik; a zárt áramkörben indukált "
                            "áram folyik, és a rúdra ható I L × B erő a mozgással ellentétes: a "
                            "rúd lassul, mozgási energiája Joule-hővé és mágneses energiává "
                            "alakul. Ezekkel a paraméterekkel a fékezés gyenge (a sebesség kb. "
                            "0,2 %-kal csökken, mielőtt a rúd t ≈ 0,40 s-kor a sínek végére ér, "
                            "ahol az áramkör megszakad és a szimuláció leáll). Kisebb R vagy m, "
                            "illetve erősebb tér jobban fékez. A BLv csak a helyi térrel való "
                            "összehasonlítás."),
        scene=Scene(objects=[SceneObject(
            id="solenoid1", name="Solenoid", role=Role.CURRENT_SOURCE,
            primitive=CoilPrimitive(radius_m=0.05, length_m=0.1, turns=200),
            source=SolenoidSource(current_A=10.0))],
            domain=Domain(min_m=(-0.2, -0.2, -0.1), max_m=(0.2, 0.2, 0.15))),
        view_hint=ViewHint(mode="3d", plane="xy", probe_m=(0.0, 0.0, 0.06)),
        circuits=[PassiveCircuit.model_validate({
            "id": "R1", "name": "Rod circuit",
            "path": {"id": "R1", "center_m": (-0.15, 0.0, 0.06),
                     "shape": {"type": "sliding_rod", "rail_separation_m": 0.1,
                               "rail_length_m": 0.3, "rod_position_m": 0.1,
                               "rod_motion": {"type": "stationary"}}},
            "electrical": {"resistance_ohm": 0.002,
                           "self_inductance": {"mode": "user", "value_H": 5e-6}},
            "mechanics": {"mode": "dynamic", "mass_kg": 0.02, "initial_velocity_m_per_s": 0.5,
                          "external_force_N": 0.0, "damping_N_s_per_m": 0.0}})],
        time=TimeHint(start_s=0.0, end_s=2.0, step_s=0.005, initial_s=0.1),
    ),
    Preset(
        id="eddy_current_disk", number=28, available=True,
        equation_ids=["annular_resistance", "annular_current_density", "coupled_band_dynamics",
                      "transformer_induced_current", "lenz_passive", "joule_heating",
                      "inductance_matrix", "current_sinusoidal", "loop_field_elliptic"],
        name=L("Axisymmetric eddy-current disk (annular-band approximation)",
               "Tengelyszimmetrikus örvényáramú korong (körgyűrű-sávos közelítés)"),
        description=L("A copper disk (radius 0.10 m, thickness 5 mm, normal +z, at the origin) "
                      "divided into 20 concentric annular bands, each a coupled passive loop. "
                      "A coaxial source loop (radius 0.07 m, 0.02 m above) carries "
                      "I(t) = 10 sin(2π·10 Hz·t) A. Reduced-order axisymmetric approximation, "
                      "not a continuous eddy-current solution.",
                      "Egy rézkorong (sugár 0,10 m, vastagság 5 mm, normális +z, az origóban) "
                      "20 koncentrikus körgyűrű-sávra osztva, mindegyik csatolt passzív hurok. "
                      "Egy koaxiális forráshurok (sugár 0,07 m, 0,02 m-rel fölötte) árama "
                      "I(t) = 10 sin(2π·10 Hz·t) A. Redukált rendű, tengelyszimmetrikus "
                      "közelítés, nem folytonos örvényáram-megoldás."),
        expected_behavior=L("The changing flux induces azimuthal currents that differ from band "
                            "to band (largest near the source loop's radius), opposing the "
                            "change of flux; the coupled currents create their own field. The "
                            "current density, Joule heating per band and the total magnetic "
                            "energy are shown. Refining the bands (10 → 20 → 40) changes the "
                            "current density by about 1 %.",
                            "A változó fluxus sávonként eltérő azimutális áramokat indukál (a "
                            "forráshurok sugara közelében a legnagyobbat), a fluxusváltozással "
                            "szemben; a csatolt áramok saját teret keltenek. Látható az "
                            "áramsűrűség, a sávonkénti Joule-hő és a teljes mágneses energia. A "
                            "sávok finomítása (10 → 20 → 40) kb. 1 %-kal változtatja az "
                            "áramsűrűséget."),
        scene=Scene(objects=[_src_loop("src", "Source loop", 0.07, 0.02, {
            "type": "sinusoidal", "dc_A": 0.0, "peak_A": 10.0, "frequency_Hz": 10.0,
            "phase_rad": 0.0})], domain=Domain(min_m=(-0.15, -0.15, -0.1),
                                               max_m=(0.15, 0.15, 0.1))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.05, 0.0, 0.01)),
        eddy_disks=[EddyDisk.model_validate({
            "id": "D1", "name": "Copper disk", "outer_radius_m": 0.1, "inner_radius_m": 0.0,
            "thickness_m": 0.005, "material": "copper", "bands": 20})],
        time=TimeHint(start_s=0.0, end_s=0.3, step_s=0.001, initial_s=0.0),
    ),
    Preset(
        id="coupled_passive_circuits", number=29, available=True,
        equation_ids=[*_EQ_CIRC, "mutual_inductance_passive", "inductance_matrix",
                      "coupled_magnetic_energy", "thin_loop_inductance", "current_sinusoidal"],
        name=L("Coupled passive circuits", "Csatolt passzív áramkörök"),
        description=L("One circular source loop (radius 0.05 m, at the origin, axis +z) with "
                      "I(t) = 2 sin(2π·1 kHz·t) A. Two shorted copper loops (wire radius 1 mm): "
                      "radius 0.04 m at z = +0.03 m and radius 0.06 m at z = −0.03 m, both "
                      "axis +z. At 1 kHz ωℒ ≈ R, so inductive coupling matters.",
                      "Egy kör alakú forráshurok (sugár 0,05 m, az origóban, tengely +z), árama "
                      "I(t) = 2 sin(2π·1 kHz·t) A. Két rövidre zárt rézhurok (huzalsugár 1 mm): "
                      "0,04 m sugarú z = +0,03 m-en és 0,06 m sugarú z = −0,03 m-en, mindkettő "
                      "tengelye +z. 1 kHz-en ωℒ ≈ R, így az induktív csatolás számít."),
        expected_behavior=L("Both loops develop induced currents whose transients are coupled "
                            "through their mutual inductance; each contributes to the other's "
                            "flux and generates its own field. The 2 × 2 inductance matrix "
                            "(symmetric, positive definite) is shown; magnetic energy and Joule "
                            "heating are tracked. Move or tilt the loops to change the coupling.",
                            "Mindkét hurokban indukált áram alakul ki, tranzienseik a kölcsönös "
                            "induktivitáson át csatoltak; mindegyik hozzájárul a másik "
                            "fluxusához és saját teret kelt. Látható a 2 × 2-es (szimmetrikus, "
                            "pozitív definit) induktivitásmátrix; a mágneses energia és a Joule-hő "
                            "követve. A hurkok mozgatásával vagy döntésével a csatolás "
                            "változtatható."),
        scene=Scene(objects=[_src_loop("src", "Source loop", 0.05, 0.0, {
            "type": "sinusoidal", "dc_A": 0.0, "peak_A": 2.0, "frequency_Hz": 1000.0,
            "phase_rad": 0.0})], domain=Domain(min_m=(-0.1, -0.1, -0.1), max_m=(0.1, 0.1, 0.1))),
        view_hint=ViewHint(mode="2d", plane="xz", probe_m=(0.0, 0.0, 0.0)),
        circuits=[_copper_loop("P1", "Upper loop", 0.04, 0.03),
                  _copper_loop("P2", "Lower loop", 0.06, -0.03)],
        time=TimeHint(start_s=0.0, end_s=0.005, step_s=1e-5, initial_s=0.0),
    ),
]

# ------------------------------------------------------- coaxial cable, TEM transmission line

_COAX_GEOMETRY = {"inner_radius_m": 0.5e-3, "shield_inner_radius_m": 1.67e-3,
                  "shield_outer_radius_m": 2.0e-3, "length_m": 2.0}
_COAX_MATERIAL = {"relative_permittivity": 2.1, "relative_permeability": 1.0}
_EQ_COAX = ["coax_e_field", "coax_h_field", "coax_inductance", "coax_capacitance",
            "coax_impedance", "coax_velocity", "coax_travelling_wave", "coax_reflection",
            "coax_poynting", "coax_power", "coax_faraday", "coax_ampere_maxwell"]
# An empty scene: the coaxial model is standalone (no point charges or current sources).
_COAX_SCENE = Scene(objects=[], domain=Domain(min_m=(-0.01, -0.01, -0.01),
                                              max_m=(0.01, 0.01, 0.01)))

_COAX = [
    Preset(
        id="coax_tem_sinusoidal", number=30, available=True, equation_ids=_EQ_COAX,
        name=L("Coaxial cable: TEM sinusoidal wave", "Koaxiális kábel: szinuszos TEM-hullám"),
        description=L("Ideal lossless coaxial cable (a = 0.50 mm, b = 1.67 mm, c = 2.00 mm, "
                      "L = 2.0 m, PTFE-like εr = 2.1) driven at z = 0 by a 1 V, 100 MHz sine "
                      "switched on at t = 0, with a matched load.",
                      "Ideális veszteségmentes koaxiális kábel (a = 0,50 mm, b = 1,67 mm, "
                      "c = 2,00 mm, L = 2,0 m, PTFE-szerű εr = 2,1), a z = 0 végen 1 V-os, "
                      "100 MHz-es, t = 0-kor bekapcsolt szinusszal gerjesztve, illesztett "
                      "lezárással."),
        expected_behavior=L("Z0 ≈ 50 Ω, vp ≈ 0.69 c, delay ≈ 9.7 ns. The wave front reaches the "
                            "load after one delay and is absorbed: V and I stay in phase "
                            "everywhere, E is radial, H azimuthal, and S = E × H points along "
                            "+z; the cross-section integral of S equals V·I.",
                            "Z0 ≈ 50 Ω, vp ≈ 0,69 c, késleltetés ≈ 9,7 ns. A hullámfront egy "
                            "késleltetés után éri el a lezárást, és elnyelődik: V és I mindenhol "
                            "fázisban van, E sugárirányú, H azimutális, S = E × H a +z irányba "
                            "mutat; S keresztmetszeti integrálja egyenlő V·I-vel."),
        scene=_COAX_SCENE, view_hint=ViewHint(mode="3d"),
        coax=CoaxSpec.model_validate({
            "geometry": _COAX_GEOMETRY, "material": _COAX_MATERIAL,
            "excitation": {"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": 100e6},
            "load": "matched", "source": "matched"}),
        time=TimeHint(start_s=0.0, end_s=20e-9, step_s=0.1e-9, initial_s=12e-9),
    ),
    Preset(
        id="coax_gaussian_reflection", number=31, available=True,
        equation_ids=[*_EQ_COAX, "telegrapher_v", "telegrapher_i"],
        name=L("Coaxial cable: Gaussian pulse and reflection",
               "Koaxiális kábel: Gauss-impulzus és reflexió"),
        description=L("Same cable as preset 30, driven by a Gaussian pulse (1 V, centre 2 ns, "
                      "σ = 0.5 ns) and left open at z = L (Γ_L = +1); matched source.",
                      "Ugyanaz a kábel, mint a 30. mintában, Gauss-impulzussal gerjesztve "
                      "(1 V, középpont 2 ns, σ = 0,5 ns), z = L-ben szakadással (Γ_L = +1); "
                      "illesztett forrás."),
        expected_behavior=L("The pulse travels to the open end (≈ 9.7 ns), where the reflected "
                            "voltage adds (V doubles at the load) and the current cancels; the "
                            "reflected pulse returns with the same voltage sign but negative "
                            "current, so S reverses to −z. Switch the load to short (Γ = −1) "
                            "or matched (Γ = 0) to compare.",
                            "Az impulzus a szakadt végig halad (≈ 9,7 ns), ahol a visszavert "
                            "feszültség hozzáadódik (V a lezárásnál kétszereződik), az áram "
                            "kioltódik; a visszavert impulzus azonos feszültség-, de negatív "
                            "áramelőjellel tér vissza, így S −z irányba fordul. A lezárás "
                            "rövidzárra (Γ = −1) vagy illesztettre (Γ = 0) állítható "
                            "összehasonlításként."),
        scene=_COAX_SCENE, view_hint=ViewHint(mode="3d"),
        coax=CoaxSpec.model_validate({
            "geometry": _COAX_GEOMETRY, "material": _COAX_MATERIAL,
            "excitation": {"type": "gaussian", "amplitude_V": 1.0, "center_s": 2e-9,
                           "width_s": 0.5e-9},
            "load": "open", "source": "matched"}),
        time=TimeHint(start_s=0.0, end_s=25e-9, step_s=0.1e-9, initial_s=7e-9),
    ),
]

PRESETS: list[Preset] = sorted(_AVAILABLE + _MAGNETIC + _COILS_AND_MAGNETS + _INDUCTION + _MOTION
                               + _CIRCUITS + _COAX + [
    Preset(id=pid, number=n, name=L(en, hu), available=False, planned_phase=phase)
    for n, pid, en, hu, phase in _PLANNED
], key=lambda p: p.number)
