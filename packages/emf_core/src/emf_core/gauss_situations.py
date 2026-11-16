"""Guided situations of the Gauss / Gauss–Ostrogradsky demonstration (Phase 2B-2).

Each situation is a scene plus Gaussian surfaces. The explanation shown to the user is built
from the computed flux results, so it adapts when the user changes the configuration."""

from __future__ import annotations

from pydantic import BaseModel

from .geometry.surfaces import GaussSurface
from .i18n import L, LocalizedText
from .scene.models import PointChargeSource, PointPrimitive, Role, Scene, SceneObject, Transform


class GaussSituation(BaseModel):
    id: str
    number: int
    name: LocalizedText
    description: LocalizedText
    expectation: LocalizedText
    scene: Scene
    surfaces: list[GaussSurface]


def _q(oid: str, name: str, nc: float, pos: tuple[float, float, float]) -> SceneObject:
    return SceneObject(id=oid, name=name, primitive=PointPrimitive(), role=Role.CHARGE_SOURCE,
                       source=PointChargeSource(charge_C=nc * 1e-9),
                       transform=Transform(position_m=pos))


def _s(sid: str, name: str, shape: dict[str, object], **kw: object) -> GaussSurface:
    return GaussSurface.model_validate({"id": sid, "name": name, "shape": shape, **kw})


SITUATIONS: list[GaussSituation] = [
    GaussSituation(
        id="positive_in_sphere", number=1,
        name=L("One positive charge inside a sphere", "Egy pozitív töltés egy gömbben"),
        description=L("A +1 nC charge at the centre of a sphere of radius 1 m.",
                      "Egy +1 nC töltés egy 1 m sugarú gömb középpontjában."),
        expectation=L("Flux leaves the sphere everywhere: Φ_E = q/ε₀ ≈ 113 V·m.",
                      "A fluxus mindenütt kilép a gömbből: Φ_E = q/ε₀ ≈ 113 V·m."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0, 0, 0))]),
        surfaces=[_s("S1", "Sphere", {"type": "sphere", "radius_m": 1.0})]),
    GaussSituation(
        id="negative_in_cube", number=2,
        name=L("One negative charge inside a cube", "Egy negatív töltés egy kockában"),
        description=L("A −1 nC charge off-centre inside a cube of side 1.5 m.",
                      "Egy −1 nC töltés a középponttól eltolva egy 1,5 m élű kockában."),
        expectation=L("Flux enters through every face: Φ_E = −113 V·m, whatever the position "
                      "inside.",
                      "A fluxus minden lapon belép: Φ_E = −113 V·m, a belső helyzettől "
                      "függetlenül."),
        scene=Scene(objects=[_q("q1", "q₁", -1, (0.2, 0.3, -0.1))]),
        surfaces=[_s("S1", "Cube", {"type": "cube", "side_m": 1.5})]),
    GaussSituation(
        id="equal_and_opposite_inside", number=3,
        name=L("Equal positive and negative charges inside", "Azonos pozitív és negatív töltés "
               "belül"),
        description=L("+1 nC and −1 nC inside the same sphere.",
                      "+1 nC és −1 nC ugyanabban a gömbben."),
        expectation=L("Flux leaves near the positive charge and enters near the negative one; "
                      "the total is 0 because Q_enc = 0.",
                      "A fluxus a pozitív töltés közelében kilép, a negatív közelében belép; az "
                      "összeg 0, mert Q_enc = 0."),
        scene=Scene(objects=[_q("q1", "q₊", 1, (-0.4, 0, 0)), _q("q2", "q₋", -1, (0.4, 0, 0))]),
        surfaces=[_s("S1", "Sphere", {"type": "sphere", "radius_m": 1.2})]),
    GaussSituation(
        id="charges_outside", number=4,
        name=L("A positive and a negative charge outside", "Egy pozitív és egy negatív töltés "
               "kívül"),
        description=L("A small sphere between two external charges.",
                      "Egy kis gömb két külső töltés között."),
        expectation=L("Field lines cross the sphere, so the local flux density is far from zero, "
                      "but every line that enters also leaves: Φ_E = 0.",
                      "Az erővonalak átszelik a gömböt, így a helyi fluxussűrűség messze nem "
                      "nulla, de minden belépő vonal ki is lép: Φ_E = 0."),
        scene=Scene(objects=[_q("q1", "q₊", 1, (-1.3, 0, 0)), _q("q2", "q₋", -1, (1.3, 0, 0))]),
        surfaces=[_s("S1", "Sphere", {"type": "sphere", "radius_m": 0.6})]),
    GaussSituation(
        id="one_inside_many_outside", number=5,
        name=L("One enclosed charge plus several external charges", "Egy bezárt és több külső "
               "töltés"),
        description=L("+1 nC inside a box, three charges outside it.",
                      "+1 nC egy téglatestben, három töltés azon kívül."),
        expectation=L("The external charges reshape the flux pattern on the box, but each of "
                      "them contributes exactly zero net flux; only the +1 nC counts.",
                      "A külső töltések átrendezik a fluxuseloszlást a téglatesten, de egyenként "
                      "pontosan nulla nettó fluxust adnak; csak a +1 nC számít."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0, 0, 0)), _q("q2", "q₂", 2, (1.4, 0.5, 0)),
                             _q("q3", "q₃", -1, (-1.3, -0.8, 0.3)),
                             _q("q4", "q₄", 1, (0, 1.5, -0.5))]),
        surfaces=[_s("S1", "Box", {"type": "box", "size_m": (1.2, 1.2, 1.2)})]),
    GaussSituation(
        id="move_inside_to_outside", number=6,
        name=L("Moving a charge from inside to outside", "Töltés mozgatása belülről kifelé"),
        description=L("Drag q₁ along x until it leaves the sphere (radius 0.8 m).",
                      "Húzza q₁-et az x tengely mentén, amíg el nem hagyja a 0,8 m sugarú gömböt."),
        expectation=L("The flux stays q/ε₀ while q₁ is inside and jumps to 0 when it crosses "
                      "the surface.",
                      "A fluxus q/ε₀ marad, amíg q₁ belül van, és 0-ra ugrik, amikor átlépi a "
                      "felületet."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0.3, 0, 0))]),
        surfaces=[_s("S1", "Sphere", {"type": "sphere", "radius_m": 0.8})]),
    GaussSituation(
        id="charge_near_surface", number=7,
        name=L("A charge close to the surface", "Töltés a felület közelében"),
        description=L("A charge 2 cm inside a cube face.",
                      "Egy töltés 2 cm-rel egy kockalap belső oldalán."),
        expectation=L("The local flux density on the nearby face becomes very large, yet the "
                      "total is still exactly q/ε₀: the charge is inside.",
                      "A közeli lapon a helyi fluxussűrűség nagyon nagy lesz, az összeg mégis "
                      "pontosan q/ε₀: a töltés belül van."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0.48, 0.1, 0))]),
        surfaces=[_s("S1", "Cube", {"type": "cube", "side_m": 1.0})]),
    GaussSituation(
        id="charge_on_surface", number=8,
        name=L("A charge exactly on the surface", "Töltés pontosan a felületen"),
        description=L("A charge placed exactly on a cube face.",
                      "Egy töltés pontosan egy kockalapon."),
        expectation=L("The field is singular on the surface, so the flux is undefined: the "
                      "charge is neither inside nor outside.",
                      "A mező a felületen szinguláris, ezért a fluxus nem értelmezett: a töltés "
                      "se nem belül, se nem kívül van."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0.5, 0.1, 0.0))]),
        surfaces=[_s("S1", "Cube", {"type": "cube", "side_m": 1.0})]),
    GaussSituation(
        id="same_charges_three_shapes", number=9,
        name=L("Same enclosed charges: sphere, box and cylinder", "Ugyanazok a bezárt töltések: "
               "gömb, téglatest, henger"),
        description=L("Three different closed surfaces around the same two charges, with one "
                      "external charge.",
                      "Három különböző zárt felület ugyanazon két töltés körül, egy külső "
                      "töltéssel."),
        expectation=L("All three surfaces give the same total flux; only the local distribution "
                      "differs.",
                      "Mindhárom felület ugyanazt az összfluxust adja; csak a helyi eloszlás "
                      "különbözik."),
        scene=Scene(objects=[_q("q1", "q₁", 1, (0.1, 0, 0)),
                             _q("q2", "q₂", -0.5, (-0.2, 0.2, 0.1)),
                             _q("q3", "q₃", 2, (1.6, 0, 0))]),
        surfaces=[_s("S1", "Sphere", {"type": "sphere", "radius_m": 0.9}),
                  _s("S2", "Box", {"type": "box", "size_m": (1.4, 1.0, 1.2)},
                     display={"visible": False}),
                  _s("S3", "Cylinder", {"type": "cylinder", "radius_m": 0.7, "height_m": 1.6},
                     display={"visible": False})]),
]
