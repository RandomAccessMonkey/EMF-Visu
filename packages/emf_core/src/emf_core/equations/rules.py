"""Applicability rules: ModelContext -> (status, reason) for every equation.

Rules read only the model context, so they keep working as new solvers and regimes are added.
"""

from __future__ import annotations

from ..i18n import L, LocalizedText
from ..solvers.base import ModelContext
from .models import EquationStatus, Rule

Out = tuple[EquationStatus, LocalizedText | None]
OK: Out = ("applicable", None)

_NO_B = L("The active electrostatic model contains no currents and no time variation; the "
          "solver does not compute a magnetic field.",
          "Az aktív elektrosztatikus modellben nincs áram és nincs időfüggés; a megoldó nem "
          "számít mágneses mezőt.")


def _static(c: ModelContext) -> bool:
    return c.regime in ("electrostatic", "magnetostatic") and not c.time_varying


def _gauss_vacuum(c: ModelContext) -> Out:
    if c.medium == "vacuum":
        return OK
    return ("not_applicable", L("The medium is not vacuum; use ∇·D = ρ_free.",
                                "A közeg nem vákuum; a ∇·D = ρ_free alak használandó."))


def _needs_b(c: ModelContext) -> Out:
    return OK if c.computes_magnetic_field else ("not_evaluated", _NO_B)


def _faraday(c: ModelContext) -> Out:
    if c.time_varying:
        return OK
    return ("applicable_under_assumptions",
            L("Static model: ∂B/∂t = 0, so the law reduces to ∇×E = 0 (E is conservative).",
              "Sztatikus modell: ∂B/∂t = 0, így a törvény ∇×E = 0 alakra egyszerűsödik (E "
              "konzervatív)."))


def _ampere_maxwell(c: ModelContext) -> Out:
    if not c.computes_magnetic_field:
        return ("not_evaluated", _NO_B)
    if _static(c):
        return ("applicable_under_assumptions",
                L("Magnetostatic approximation: the ∂D/∂t term is neglected.",
                  "Magnetosztatikus közelítés: a ∂D/∂t tag elhanyagolva."))
    return OK


def _e_from_phi(c: ModelContext) -> Out:
    if c.regime in ("electrostatic", "magnetostatic") and not c.time_varying:
        return OK
    return ("not_applicable", L("With time-varying B the field is not purely a gradient.",
                                "Időben változó B esetén a mező nem tisztán gradiens."))


def _coulomb(c: ModelContext) -> Out:
    if c.regime == "electrostatic" and c.medium == "vacuum" and not c.has_conductors:
        if c.source_count == 0:
            return ("applicable_under_assumptions",
                    L("The scene contains no charge, so the field and the potential are zero "
                      "everywhere.",
                      "A jelenetben nincs töltés, ezért a térerősség és a potenciál mindenütt "
                      "nulla."))
        return OK
    return ("not_applicable",
            L("Requires point charges in unbounded vacuum without conductors or dielectrics.",
              "Végtelen vákuumban lévő ponttöltéseket feltételez, vezetők és dielektrikumok "
              "nélkül."))


def _superposition(c: ModelContext) -> Out:
    if c.regime != "electrostatic":
        return ("not_evaluated", _NO_E)
    if c.medium not in ("vacuum", "homogeneous_linear", "inhomogeneous_linear"):
        return ("not_applicable", L("The medium is not linear.", "A közeg nem lineáris."))
    if c.source_count == 0:
        return ("applicable_under_assumptions",
                L("No sources: every term of the sum is zero.",
                  "Nincs forrás: az összeg minden tagja nulla."))
    if c.source_count == 1:
        return ("applicable_under_assumptions",
                L("Only one charge is present, so each sum has a single term.",
                  "Csak egy töltés van jelen, így mindkét összeg egyetlen tagból áll."))
    return OK


def _gauss_d_vacuum(c: ModelContext) -> Out:
    if c.medium == "vacuum":
        return OK
    return ("not_applicable", L("The medium is not vacuum; use ∇·D = ρ_free.",
                                "A közeg nem vákuum; a ∇·D = ρ_free alak használandó."))


def _div_point_charges(c: ModelContext) -> Out:
    if not (c.regime == "electrostatic" and c.medium == "vacuum" and not c.has_conductors):
        return ("not_applicable",
                L("Requires point charges in vacuum without conductors or dielectrics.",
                  "Vákuumbeli ponttöltéseket feltételez, vezetők és dielektrikumok nélkül."))
    if c.source_count == 0:
        return ("applicable_under_assumptions",
                L("There are no point charges, so the sum is empty and ∇·E = 0 everywhere.",
                  "Nincsenek ponttöltések, így az összeg üres és ∇·E = 0 mindenütt."))
    return OK


def _curl_e_static(c: ModelContext) -> Out:
    if c.regime in ("electrostatic", "magnetostatic") and not c.time_varying:
        return OK
    return ("not_applicable",
            L("The magnetic field changes in time, so ∇×E = −∂B/∂t (Faraday's law).",
              "A mágneses mező időben változik, ezért ∇×E = −∂B/∂t (Faraday-törvény)."))


def _curl_d_vacuum(c: ModelContext) -> Out:
    if c.time_varying or c.regime not in ("electrostatic", "magnetostatic"):
        return ("not_applicable",
                L("Not a static model.", "Nem sztatikus modell."))
    if c.medium == "inhomogeneous_linear":
        return ("not_applicable",
                L("ε varies in space, so ∇×D = ∇ε × E need not vanish.",
                  "ε helyfüggő, ezért ∇×D = ∇ε × E nem feltétlenül nulla."))
    if c.medium == "homogeneous_linear":
        return ("applicable_under_assumptions",
                L("Homogeneous medium: D = εE with constant ε.",
                  "Homogén közeg: D = εE állandó ε-nal."))
    return OK


_NO_SURFACE = L("No Gaussian surface is defined; add one to compute the flux.",
                "Nincs Gauss-felület megadva; adjon hozzá egyet a fluxus kiszámításához.")
_ON_SURFACE = L("A point charge lies on a Gaussian surface: the field is singular there and the "
                "flux through that surface is undefined.",
                "Egy ponttöltés egy Gauss-felületen fekszik: ott a mező szinguláris, és az adott "
                "felületen átmenő fluxus nem értelmezett.")
_INVALID_SURFACE = L("A Gaussian surface failed validation (not a closed, consistently oriented "
                     "surface); no flux is computed for it.",
                     "Egy Gauss-felület nem felelt meg az ellenőrzésen (nem zárt, következetesen "
                     "irányított felület); arra nem számol fluxust a program.")


def _flux_def(c: ModelContext) -> Out:
    if c.gauss_surfaces == 0:
        return ("not_evaluated", _NO_SURFACE)
    if c.gauss_boundary_ambiguous:
        return ("applicable_under_assumptions", _ON_SURFACE)
    if c.gauss_invalid:
        return ("applicable_under_assumptions", _INVALID_SURFACE)
    return OK


def _gauss_integral(c: ModelContext) -> Out:
    if c.regime != "electrostatic" or c.medium != "vacuum":
        return ("not_applicable", L("Requires electrostatics in vacuum.",
                                    "Vákuumbeli elektrosztatikát feltételez."))
    if c.gauss_surfaces == 0:
        return ("applicable_under_assumptions",
                L("Holds for every closed surface that has no charge on it; none is defined yet.",
                  "Minden olyan zárt felületre teljesül, amelyen nincs töltés; még nincs ilyen "
                  "felület megadva."))
    if c.gauss_boundary_ambiguous:
        return ("applicable_under_assumptions", _ON_SURFACE)
    return OK


def _divergence_theorem(c: ModelContext) -> Out:
    if c.regime == "electrostatic" and c.source_count > 0:
        return ("applicable_under_assumptions",
                L("The point charges make div E a distribution: the theorem holds in the "
                  "distributional sense, provided no charge lies on the surface.",
                  "A ponttöltések miatt div E disztribúció: a tétel disztribúciós értelemben "
                  "teljesül, feltéve, hogy egy töltés sem fekszik a felületen."))
    return OK


def _poisson_general(c: ModelContext) -> Out:
    if c.regime != "electrostatic":
        return ("not_applicable", L("Not an electrostatic model.", "Nem elektrosztatikus modell."))
    if c.medium == "inhomogeneous_linear":
        return OK
    return ("applicable_under_assumptions",
            L("ε is constant here, so this reduces to the homogeneous form ∇²φ = −ρ/ε.",
              "Itt ε állandó, így az egyenlet a homogén ∇²φ = −ρ/ε alakra egyszerűsödik."))


def _poisson_homog(c: ModelContext) -> Out:
    if c.regime != "electrostatic":
        return ("not_applicable", L("Not an electrostatic model.", "Nem elektrosztatikus modell."))
    if c.medium == "inhomogeneous_linear":
        return ("not_applicable", L("ε varies in space; use ∇·(ε∇φ) = −ρ_free.",
                                    "ε helyfüggő; a ∇·(ε∇φ) = −ρ_free alak használandó."))
    return OK


def _laplace(c: ModelContext) -> Out:
    if c.regime != "electrostatic" or c.medium == "inhomogeneous_linear":
        return ("not_applicable", L("Requires electrostatics in a homogeneous medium.",
                                    "Homogén közegbeli elektrosztatikát feltételez."))
    if not c.has_free_charge:
        return OK
    return ("applicable_under_assumptions",
            L("Holds everywhere except at the charge locations, where Poisson's equation "
              "applies.",
              "Mindenütt érvényes, kivéve a töltések helyét, ahol a Poisson-egyenlet érvényes."))


def _magnetostatic_only(c: ModelContext) -> Out:
    if c.regime == "magnetostatic":
        return OK
    if not c.has_free_current:
        return ("not_applicable", L("The model contains no current sources.",
                                    "A modell nem tartalmaz áramforrást."))
    return ("not_evaluated", _NO_B)


def _d_linear(c: ModelContext) -> Out:
    if c.medium == "vacuum":
        return ("applicable_under_assumptions",
                L("Vacuum: ε = ε₀ and P = 0, so D = ε₀E.", "Vákuum: ε = ε₀ és P = 0, így D = ε₀E."))
    return OK


def _ohm(c: ModelContext) -> Out:
    if c.has_conductors:
        return OK
    return ("not_applicable", L("The model contains no conducting material (σ = 0).",
                                "A modell nem tartalmaz vezető anyagot (σ = 0)."))


def _continuity(c: ModelContext) -> Out:
    if _static(c) and not c.has_free_current:
        return ("applicable_under_assumptions",
                L("Static charges: J = 0 and ∂ρ/∂t = 0, so both sides vanish.",
                  "Nyugvó töltések: J = 0 és ∂ρ/∂t = 0, így mindkét oldal nulla."))
    return OK


def _lorentz(c: ModelContext) -> Out:
    return ("not_evaluated", L("No test-particle motion is simulated by the current solver.",
                               "A jelenlegi megoldó nem szimulál próbatöltés-mozgást."))


def _poynting(c: ModelContext) -> Out:
    if c.computes_magnetic_field and _static(c):
        return ("not_evaluated",
                L("S = E × H is not computed in this milestone. In static fields its divergence "
                  "is zero, so no energy accumulates anywhere.",
                  "Az S = E × H mennyiséget ebben a mérföldkőben nem számítjuk. Sztatikus "
                  "mezőkben a divergenciája nulla, így sehol sem halmozódik fel energia."))
    if not c.computes_magnetic_field:
        return ("not_evaluated",
                L("H is not computed by the electrostatic solver (H = 0 in this model, so there "
                  "is no energy flow).",
                  "Az elektrosztatikus megoldó nem számítja H-t (ebben a modellben H = 0, tehát "
                  "nincs energiaáramlás)."))
    return OK


def _energy(c: ModelContext) -> Out:
    return ("not_evaluated", L("Energy density is not computed by the current solver yet.",
                               "Az energiasűrűséget a jelenlegi megoldó még nem számítja."))


_NO_E = L("The active model contains no charges; the electric field is not computed by this "
          "magnetostatic model.",
          "Az aktív modellben nincs töltés; ez a magnetosztatikus modell nem számít elektromos "
          "mezőt.")


def _vacuum_b(c: ModelContext) -> Out:
    if not c.computes_magnetic_field:
        return ("not_evaluated", _NO_B)
    if c.medium != "vacuum":
        return ("not_applicable", L("The medium is not vacuum; use B = μH or B = μ₀(H + M).",
                                    "A közeg nem vákuum; a B = μH vagy B = μ₀(H + M) alak "
                                    "használandó."))
    return OK


def _current_kind(kind: str, missing: LocalizedText) -> Rule:
    def rule(c: ModelContext) -> Out:
        if not c.computes_magnetic_field:
            return ("not_evaluated", _NO_B)
        if kind not in c.current_source_kinds:
            return ("not_applicable", missing)
        return OK
    return rule


def _loop_axis(c: ModelContext) -> Out:
    status, reason = _current_kind("circular_loop", _NO_LOOP)(c)
    if status != "applicable":
        return status, reason
    return ("applicable_under_assumptions",
            L("Only on the symmetry axis of a loop; off the axis the full elliptic-integral "
              "solution applies (and is what the solver evaluates).",
              "Csak a körvezető szimmetriatengelyén; azon kívül a teljes, elliptikus "
              "integrálos megoldás érvényes (a megoldó azt értékeli ki)."))


_NO_LOOP = L("The scene contains no circular current loop.",
             "A jelenetben nincs körvezető.")
_NO_WIRE = L("The scene contains no straight wire.", "A jelenetben nincs egyenes vezető.")


def _superposition_b(c: ModelContext) -> Out:
    if not c.computes_magnetic_field:
        return ("not_evaluated", _NO_B)
    if c.source_count == 0:
        return ("applicable_under_assumptions",
                L("No current flows: every term of the sum is zero.",
                  "Nem folyik áram: az összeg minden tagja nulla."))
    if c.source_count == 1:
        return ("applicable_under_assumptions",
                L("Only one current source is present, so the sum has a single term.",
                  "Csak egy áramforrás van jelen, így az összeg egyetlen tagból áll."))
    return OK


def _magnetostatic_source(c: ModelContext) -> Out:
    status, reason = _magnetostatic_only(c)
    if status == "applicable" and c.source_count == 0:
        return ("applicable_under_assumptions",
                L("All currents are zero, so B = 0 everywhere.",
                  "Minden áram nulla, így B = 0 mindenütt."))
    return status, reason


RULES: dict[str, Rule] = {
    "gauss_electric": lambda c: OK,
    "gauss_electric_vacuum": _gauss_vacuum,
    "gauss_displacement_vacuum": _gauss_d_vacuum,
    "div_E_point_charges": _div_point_charges,
    "div_D_point_charges": _div_point_charges,
    "curl_E_electrostatic": _curl_e_static,
    "curl_D_vacuum": _curl_d_vacuum,
    "electric_flux": _flux_def,
    "displacement_flux": _flux_def,
    "gauss_integral_E": _gauss_integral,
    "gauss_integral_D": _gauss_integral,
    "divergence_theorem": _divergence_theorem,
    "divergence_theorem_E": _gauss_integral,
    "divergence_theorem_D": _gauss_integral,
    "gauss_magnetic": _needs_b,
    "faraday": _faraday,
    "ampere_maxwell": _ampere_maxwell,
    "e_from_potential": _e_from_phi,
    "coulomb_field": _coulomb,
    "coulomb_potential": _coulomb,
    "superposition": _superposition,
    "poisson_general": _poisson_general,
    "poisson_homogeneous": _poisson_homog,
    "laplace": _laplace,
    "ampere_static": _magnetostatic_only,
    "biot_savart": _magnetostatic_source,
    "biot_savart_integral": _magnetostatic_source,
    "infinite_wire_field": _current_kind("infinite_wire", _NO_WIRE),
    "loop_axis_field": _loop_axis,
    "loop_field_elliptic": _current_kind("circular_loop", _NO_LOOP),
    "superposition_magnetic": _superposition_b,
    "div_B_filaments": lambda c: OK if c.computes_magnetic_field else ("not_evaluated", _NO_B),
    "b_mu0_h": _vacuum_b,
    "h_from_b": _vacuum_b,
    "constitutive_d_general": lambda c: OK,
    "constitutive_d_linear": _d_linear,
    "constitutive_b_general": _needs_b,
    "constitutive_b_linear": _needs_b,
    "ohm_local": _ohm,
    "continuity": _continuity,
    "lorentz_force": _lorentz,
    "poynting": _poynting,
    "energy_density": _energy,
}
