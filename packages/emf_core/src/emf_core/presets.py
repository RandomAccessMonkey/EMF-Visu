"""Preset catalog. All 20 presets of the product definition are listed; a preset is only
``available`` when a solver that supports its scene exists. Unavailable presets carry no scene.
"""

from __future__ import annotations

from pydantic import BaseModel

from .i18n import L, LocalizedText
from .scene.models import PointChargeSource, PointPrimitive, Role, Scene, SceneObject, Transform


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


def _charge(oid: str, name: str, q: float, pos: tuple[float, float, float]) -> SceneObject:
    return SceneObject(id=oid, name=name, primitive=PointPrimitive(), role=Role.CHARGE_SOURCE,
                       source=PointChargeSource(charge_C=q), transform=Transform(position_m=pos))


_EQ = ["coulomb_field", "coulomb_potential", "e_from_potential", "gauss_electric_vacuum"]

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
        description=L("Charges of +1 nC and −1 nC separated by 1 m along x.",
                      "+1 nC és −1 nC töltés egymástól 1 m távolságra az x tengely mentén."),
        expected_behavior=L("The field leaves the positive charge and enters the negative one; "
                            "φ = 0 on the symmetry plane x = 0; far away |E| falls off as 1/r³.",
                            "A mező a pozitív töltésből indul és a negatívba érkezik; az x = 0 "
                            "szimmetriasíkon φ = 0; nagy távolságban |E| 1/r³ szerint csökken."),
        scene=Scene(objects=[_charge("q1", "q₊", 1e-9, (-0.5, 0, 0)),
                             _charge("q2", "q₋", -1e-9, (0.5, 0, 0))]),
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

_PLANNED: list[tuple[int, str, str, str, int]] = [
    (5, "infinite_line_charge", "Infinite line charge", "Végtelen vonaltöltés", 2),
    (6, "parallel_plate_capacitor", "Parallel plate capacitor", "Síkkondenzátor", 2),
    (7, "coaxial_conductors", "Coaxial cylindrical conductors", "Koaxiális hengeres vezetők", 2),
    (8, "charged_conducting_sphere", "Charged conducting sphere", "Töltött vezető gömb", 2),
    (9, "straight_wire", "Straight current-carrying wire", "Egyenes áramvezető", 3),
    (10, "two_parallel_wires", "Two parallel current-carrying wires",
     "Két párhuzamos áramvezető", 3),
    (11, "circular_loop", "Circular current loop", "Köráram", 3),
    (12, "solenoid", "Solenoid", "Szolenoid", 3),
    (13, "toroid", "Toroid", "Toroid", 3),
    (14, "permanent_magnet", "Permanent magnet", "Állandó mágnes", 3),
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

PRESETS: list[Preset] = _AVAILABLE + [
    Preset(id=pid, number=n, name=L(en, hu), available=False, planned_phase=phase)
    for n, pid, en, hu, phase in _PLANNED
]
