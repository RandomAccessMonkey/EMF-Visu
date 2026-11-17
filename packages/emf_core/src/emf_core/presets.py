"""Preset catalog. All 20 presets of the product definition are listed; a preset is only
``available`` when a solver that supports its scene exists. Unavailable presets carry no scene.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .ampere import AmperePath
from .i18n import L, LocalizedText
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
    (15, "changing_b_in_loop", "Changing magnetic field inside a loop",
     "Változó mágneses mező egy hurokban", 4),
    (16, "faraday_induction", "Faraday induction demonstration",
     "Faraday-féle indukció bemutatása", 4),
    (17, "electrostatic_plus_induced", "Electrostatic field combined with an induced rotational "
     "electric field", "Elektrosztatikus mező és indukált örvényes elektromos mező együtt", 4),
    (18, "dielectric_in_capacitor", "Dielectric material inside a capacitor",
     "Dielektrikum a kondenzátorban", 5),
    (19, "finite_conductivity_conductor", "Conductor with finite conductivity",
     "Véges vezetőképességű vezető", 5),
    (20, "plane_wave", "Electromagnetic plane wave propagation",
     "Elektromágneses síkhullám terjedése", 5),
]

PRESETS: list[Preset] = sorted(_AVAILABLE + _MAGNETIC + _COILS_AND_MAGNETS + [
    Preset(id=pid, number=n, name=L(en, hu), available=False, planned_phase=phase)
    for n, pid, en, hu, phase in _PLANNED
], key=lambda p: p.number)
