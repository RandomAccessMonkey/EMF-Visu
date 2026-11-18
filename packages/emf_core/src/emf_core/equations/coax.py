"""Coaxial-cable TEM equations: analytical fields, transmission-line parameters, travelling
waves and reflections, the differential Maxwell laws in the dielectric (checked against
finite differences), the interface (surface) quantities, and power flow S = E × H.

Appended to the one registry (``data.EQUATIONS`` / ``SYMBOLS`` and ``rules.RULES``). When the
coaxial model is active, every other registry entry that is not one of ``GENERAL`` is reported
as not applicable to it (see ``guard``)."""

from __future__ import annotations

from ..i18n import L, LocalizedText
from ..solvers.base import ModelContext
from .models import Equation, EquationStatus, Rule, SymbolDef

Out = tuple[EquationStatus, LocalizedText | None]

_TEM = L("Ideal coaxial cable: perfectly conducting inner and outer conductors, homogeneous "
         "linear isotropic non-dispersive lossless dielectric, TEM mode only.",
         "Ideális koaxiális kábel: tökéletesen vezető belső és külső vezető, homogén, lineáris, "
         "izotróp, diszperziómentes, veszteségmentes dielektrikum, csak TEM módus.")
_DIEL = L("Valid in the dielectric a < r < b; all fields are zero inside the conductors and "
          "outside the shield.",
          "Az a < r < b dielektrikumban érvényes; a vezetők belsejében és az árnyékolón kívül "
          "minden tér nulla.")
_BOUNDARY = L("At r = a and r = b the fields jump: there the surface charge and surface current "
              "of the conductors are distributional (surface) quantities, not volume values.",
              "Az r = a és r = b felületen a terek ugranak: ott a vezetők felületi töltése és "
              "felületi árama disztribúció jellegű (felületi) mennyiség, nem térfogati érték.")

SYMBOLS: dict[str, SymbolDef] = {
    "a_cx": SymbolDef(latex=r"a", unit="m", meaning=L("inner-conductor radius",
                                                      "belső vezető sugara")),
    "b_cx": SymbolDef(latex=r"b", unit="m", meaning=L("inner radius of the outer conductor",
                                                      "a külső vezető belső sugara")),
    "r_cyl": SymbolDef(latex=r"r", unit="m", meaning=L("radial distance from the cable axis",
                                                       "sugárirányú távolság a kábel tengelyétől")),
    "Vz": SymbolDef(latex=r"V(z,t)", unit="V",
                    meaning=L("voltage of the inner conductor relative to the outer one",
                              "a belső vezető feszültsége a külsőhöz képest")),
    "Iz": SymbolDef(latex=r"I(z,t)", unit="A",
                    meaning=L("current on the inner conductor, positive along +z (the outer "
                              "conductor carries −I)",
                              "a belső vezető árama, +z irányban pozitív (a külső vezetőé −I)")),
    "Er": SymbolDef(latex=r"E_r", unit="V/m", meaning=L("radial electric field",
                                                        "sugárirányú elektromos térerősség")),
    "Hphi": SymbolDef(latex=r"H_\varphi", unit="A/m",
                      meaning=L("azimuthal magnetic field strength",
                                "azimutális mágneses térerősség")),
    "Sz": SymbolDef(latex=r"S_z", unit="W/m^2", meaning=L("axial Poynting component",
                                                          "a Poynting-vektor tengelyirányú "
                                                          "komponense")),
    "Lp": SymbolDef(latex=r"L'", unit="H/m", meaning=L("inductance per unit length",
                                                       "egységnyi hosszra eső induktivitás")),
    "Cp": SymbolDef(latex=r"C'", unit="F/m", meaning=L("capacitance per unit length",
                                                       "egységnyi hosszra eső kapacitás")),
    "Z0": SymbolDef(latex=r"Z_0", unit="ohm", meaning=L("characteristic impedance",
                                                        "hullámimpedancia")),
    "vp": SymbolDef(latex=r"v_p", unit="m/s", meaning=L("phase (propagation) velocity",
                                                        "fázis- (terjedési) sebesség")),
    "Lcab": SymbolDef(latex=r"L", unit="m", meaning=L("cable length", "kábelhossz")),
    "tdel": SymbolDef(latex=r"t_\text{delay}", unit="s", meaning=L("one-way travel time",
                                                                   "egyirányú futási idő")),
    "Vplus": SymbolDef(latex=r"V^{+},\,V^{-}", unit="V",
                       meaning=L("forward (+z) and backward (−z) voltage waves",
                                 "előre (+z) és visszafelé (−z) haladó feszültséghullám")),
    "GammaL": SymbolDef(latex=r"\Gamma_L", unit="1", meaning=L("load reflection coefficient",
                                                               "lezárási reflexiós tényező")),
    "ZL": SymbolDef(latex=r"Z_L", unit="ohm", meaning=L("load impedance",
                                                        "lezáró impedancia")),
    "rho_s": SymbolDef(latex=r"\rho_s", unit="C/m^2", meaning=L("surface charge density",
                                                                "felületi töltéssűrűség")),
    "K_s": SymbolDef(latex=r"K_z", unit="A/m", meaning=L("surface current density (axial)",
                                                         "felületi áramsűrűség (tengelyirányú)")),
    "Pz": SymbolDef(latex=r"P(z,t)", unit="W",
                    meaning=L("power through the cross-section",
                              "a keresztmetszeten átáramló teljesítmény")),
}


def _eq(**kw: object) -> Equation:
    return Equation.model_validate({"category": "coax", "assumptions": [_TEM], **kw})


EQUATIONS: list[Equation] = [
    _eq(id="coax_e_field", name=L("Radial electric field", "Sugárirányú elektromos tér"),
        latex=r"E_r(r,z,t) = \frac{V(z,t)}{r\,\ln(b/a)},\qquad "
              r"\mathbf{D} = \varepsilon\mathbf{E}",
        meaning=L("E points from the inner to the outer conductor when V > 0 and falls off as "
                  "1/r; it has no φ or z component.",
                  "V > 0 esetén E a belső vezetőtől a külső felé mutat, és 1/r szerint csökken; "
                  "nincs φ és z komponense."),
        intuition=L("The cross-section of a TEM wave looks like a charged coaxial capacitor at "
                    "voltage V(z, t).",
                    "A TEM-hullám keresztmetszete olyan, mint egy V(z, t) feszültségű töltött "
                    "koaxiális kondenzátoré."),
        symbols=["Er", "Vz", "r_cyl", "a_cx", "b_cx", "D", "eps"], limitations=[_DIEL]),
    _eq(id="coax_h_field", name=L("Azimuthal magnetic field", "Azimutális mágneses tér"),
        latex=r"H_\varphi(r,z,t) = \frac{I(z,t)}{2\pi r},\qquad \mathbf{B} = \mu\mathbf{H}",
        meaning=L("Ampère's law around the inner conductor: H circles the axis, along +φ when "
                  "I > 0 (right-hand rule about +z).",
                  "Ampère-törvény a belső vezető körül: H a tengely körül kering, I > 0 esetén "
                  "+φ irányban (jobbkéz-szabály +z körül)."),
        intuition=L("Like the field of a long straight wire, but cancelled outside by the "
                    "return current of the shield.",
                    "Mint egy hosszú egyenes vezető tere, de kívül az árnyékoló visszatérő árama "
                    "kioltja."),
        symbols=["Hphi", "Iz", "r_cyl", "B", "mu"], limitations=[_DIEL]),
    _eq(id="coax_inductance", name=L("Inductance per unit length",
                                     "Egységnyi hosszra eső induktivitás"),
        latex=r"L' = \frac{\mu}{2\pi}\ln\frac{b}{a}",
        meaning=L("Magnetic flux between the conductors per unit length and per ampere "
                  "(external inductance; the conductors are ideal, no internal inductance).",
                  "A vezetők közötti mágneses fluxus egységnyi hosszra és amperre (külső "
                  "induktivitás; a vezetők ideálisak, nincs belső induktivitás)."),
        intuition=L("A wider gap stores more magnetic energy per ampere.",
                    "Szélesebb rés amperenként több mágneses energiát tárol."),
        symbols=["Lp", "mu", "a_cx", "b_cx"]),
    _eq(id="coax_capacitance", name=L("Capacitance per unit length",
                                      "Egységnyi hosszra eső kapacitás"),
        latex=r"C' = \frac{2\pi\varepsilon}{\ln(b/a)}",
        meaning=L("Charge per unit length per volt between the conductors.",
                  "A vezetők közötti egységnyi hosszra eső töltés voltonként."),
        intuition=L("A narrower gap or a larger permittivity holds more charge per volt.",
                    "Keskenyebb rés vagy nagyobb permittivitás voltonként több töltést tart."),
        symbols=["Cp", "eps", "a_cx", "b_cx"]),
    _eq(id="coax_impedance", name=L("Characteristic impedance", "Hullámimpedancia"),
        latex=r"Z_0 = \sqrt{\frac{L'}{C'}} = \frac{1}{2\pi}\sqrt{\frac{\mu}{\varepsilon}}"
              r"\,\ln\frac{b}{a}",
        meaning=L("Ratio V⁺/I⁺ of a single travelling wave (and −V⁻/I⁻ of the backward wave).",
                  "Egyetlen haladó hullám V⁺/I⁺ aránya (a visszafelé haladóé −V⁻/I⁻)."),
        intuition=L("The resistance a wave 'sees' while travelling; no energy is dissipated.",
                    "Az az ellenállás, amelyet a haladó hullám „lát”; nincs energiaveszteség."),
        symbols=["Z0", "Lp", "Cp", "mu", "eps", "a_cx", "b_cx"]),
    _eq(id="coax_velocity", name=L("Propagation velocity and delay",
                                   "Terjedési sebesség és késleltetés"),
        latex=r"v_p = \frac{1}{\sqrt{L'C'}} = \frac{1}{\sqrt{\mu\varepsilon}},\qquad "
              r"t_\text{delay} = \frac{L}{v_p}",
        meaning=L("Independent of the radii: the TEM wave travels at the speed of light in the "
                  "dielectric.",
                  "Független a sugaraktól: a TEM-hullám a dielektrikumbeli fénysebességgel "
                  "halad."),
        intuition=L("εr = 2.1 slows the wave to about 69 % of c.",
                    "εr = 2,1 a hullámot c kb. 69 %-ára lassítja."),
        symbols=["vp", "Lp", "Cp", "mu", "eps", "tdel", "Lcab"]),
    _eq(id="coax_travelling_wave", name=L("Travelling-wave solution",
                                          "Haladóhullám-megoldás"),
        latex=r"V = V^{+}\!\left(t-\tfrac{z}{v_p}\right) + V^{-}\!\left(t+\tfrac{z}{v_p}\right),"
              r"\quad I = \frac{V^{+} - V^{-}}{Z_0}",
        meaning=L("The general solution of the lossless telegrapher equations. The backward "
                  "wave enters the current with a minus sign: it carries current (and power) "
                  "toward −z.",
                  "A veszteségmentes távíróegyenletek általános megoldása. A visszafelé haladó "
                  "hullám negatív előjellel szerepel az áramban: −z felé szállít áramot (és "
                  "teljesítményt)."),
        intuition=L("Two shapes sliding in opposite directions without changing form.",
                    "Két alak, amely alakváltozás nélkül csúszik ellentétes irányban."),
        symbols=["Vz", "Iz", "Vplus", "vp", "Z0", "t"],
        conditions=[L("z = 0 at the source, z = L at the load; the excitation is the forward "
                      "wave launched at z = 0.",
                      "z = 0 a forrásnál, z = L a lezárásnál; a gerjesztés a z = 0-ban indított "
                      "előre haladó hullám.")]),
    _eq(id="coax_reflection", name=L("Load reflection coefficient", "Lezárási reflexiós tényező"),
        latex=r"\Gamma_L = \frac{Z_L - Z_0}{Z_L + Z_0} = \frac{V^{-}}{V^{+}}\Big|_{z=L}",
        meaning=L("Matched Z_L = Z0: Γ = 0 (no reflection). Open: Γ = +1, the reflected voltage "
                  "adds and the current cancels at the load. Short: Γ = −1, the voltage cancels "
                  "and the current doubles.",
                  "Illesztett Z_L = Z0: Γ = 0 (nincs reflexió). Szakadás: Γ = +1, a visszavert "
                  "feszültség hozzáadódik, az áram a lezárásnál kioltódik. Rövidzár: Γ = −1, a "
                  "feszültség kioltódik, az áram kétszereződik."),
        intuition=L("The load sends back the part of the wave it cannot absorb.",
                    "A lezárás visszaküldi a hullám azon részét, amelyet nem tud elnyelni."),
        symbols=["GammaL", "ZL", "Z0", "Vplus"],
        conditions=[L("Re-reflections at the source use Γ_S (matched source: Γ_S = 0).",
                      "A forrásoldali újrareflexió Γ_S-sel számol (illesztett forrás: Γ_S = 0).")]),
    _eq(id="telegrapher_v", name=L("Telegrapher equation (voltage)", "Távíróegyenlet (feszültség)"),
        latex=r"\frac{\partial V}{\partial z} = -L'\frac{\partial I}{\partial t}",
        meaning=L("The line form of Faraday's law; checked numerically at the selected "
                  "cross-section.",
                  "A Faraday-törvény vonalmenti alakja; a kiválasztott keresztmetszetben "
                  "numerikusan ellenőrizve."),
        intuition=L("A changing current induces a voltage drop along the line.",
                    "A változó áram feszültségesést indukál a vonal mentén."),
        symbols=["Vz", "Iz", "Lp", "t"]),
    _eq(id="telegrapher_i", name=L("Telegrapher equation (current)", "Távíróegyenlet (áram)"),
        latex=r"\frac{\partial I}{\partial z} = -C'\frac{\partial V}{\partial t}",
        meaning=L("The line form of charge conservation (the displacement current between the "
                  "conductors).",
                  "A töltésmegmaradás vonalmenti alakja (a vezetők közötti eltolási áram)."),
        intuition=L("Current that stops along the line charges the line capacitance.",
                    "A vonal mentén megálló áram a vonal kapacitását tölti."),
        symbols=["Vz", "Iz", "Cp", "t"]),
    _eq(id="coax_faraday", name=L("Faraday's law in the dielectric",
                                  "Faraday-törvény a dielektrikumban"),
        latex=r"(\nabla\times\mathbf{E})_\varphi = \frac{\partial E_r}{\partial z} = "
              r"-\frac{\partial B_\varphi}{\partial t}",
        meaning=L("A TEM field is not curl-free: where V varies along z, ∇×E is azimuthal and "
                  "equals −∂B/∂t. Both sides are evaluated analytically and by finite "
                  "differences of the field.",
                  "A TEM-tér nem örvénymentes: ahol V változik z mentén, ∇×E azimutális és "
                  "egyenlő −∂B/∂t-vel. Mindkét oldal analitikusan és a tér véges "
                  "differenciáival is kiértékelve."),
        intuition=L("The wave's E arrows change from one cross-section to the next exactly as "
                    "fast as B changes in time.",
                    "A hullám E-nyilai keresztmetszetről keresztmetszetre pontosan olyan "
                    "gyorsan változnak, ahogy B az időben."),
        symbols=["E", "B", "Er", "t"], limitations=[_DIEL]),
    _eq(id="coax_ampere_maxwell", name=L("Ampère–Maxwell law in the dielectric",
                                         "Ampère–Maxwell-törvény a dielektrikumban"),
        latex=r"(\nabla\times\mathbf{H})_r = -\frac{\partial H_\varphi}{\partial z} = "
              r"\frac{\partial D_r}{\partial t}",
        meaning=L("No conduction current in the dielectric: the curl of H is the displacement "
                  "current density ∂D/∂t, radial between the conductors.",
                  "A dielektrikumban nincs vezetési áram: H rotációja a ∂D/∂t eltolási "
                  "áramsűrűség, sugárirányú a vezetők között."),
        intuition=L("The displacement current closes the circuit between the conductors.",
                    "Az eltolási áram zárja az áramkört a vezetők között."),
        symbols=["H", "D", "Hphi", "t"], limitations=[_DIEL]),
    _eq(id="coax_surface_charge", name=L("Surface charge on the conductors",
                                         "Felületi töltés a vezetőkön"),
        latex=r"\rho_s(a) = D_r(a^{+}) = \frac{C'V}{2\pi a},\qquad \rho_s(b) = -D_r(b^{-}) = "
              r"-\frac{C'V}{2\pi b}",
        meaning=L("Gauss's law across the interface: ∇·D is a surface (distributional) charge "
                  "there, not a finite volume density.",
                  "Gauss-törvény a határfelületen át: ott ∇·D felületi (disztribúció jellegű) "
                  "töltés, nem véges térfogati sűrűség."),
        intuition=L("Equal and opposite charge per unit length on the two conductors.",
                    "Egységnyi hosszon egyenlő és ellentétes töltés a két vezetőn."),
        symbols=["rho_s", "D", "Cp", "Vz", "a_cx", "b_cx"], limitations=[_BOUNDARY]),
    _eq(id="coax_surface_current", name=L("Surface current on the conductors",
                                          "Felületi áram a vezetőkön"),
        latex=r"K_z(a) = H_\varphi(a^{+}) = \frac{I}{2\pi a},\qquad K_z(b) = -H_\varphi(b^{-}) "
              r"= -\frac{I}{2\pi b}",
        meaning=L("The jump of tangential H at a perfect conductor is its surface current; the "
                  "curl of H there is distributional.",
                  "A tangenciális H ugrása tökéletes vezetőn a felületi áram; ott H rotációja "
                  "disztribúció jellegű."),
        intuition=L("Forward current on the inner surface, return current on the shield's "
                    "inner surface.",
                    "Előre folyó áram a belső vezető felületén, visszatérő áram az árnyékoló "
                    "belső felületén."),
        symbols=["K_s", "Hphi", "Iz", "a_cx", "b_cx"], limitations=[_BOUNDARY]),
    _eq(id="coax_poynting", name=L("Axial Poynting vector", "Tengelyirányú Poynting-vektor"),
        latex=r"S_z = E_r H_\varphi = \frac{V I}{2\pi r^2 \ln(b/a)}",
        meaning=L("S = E × H points along +z where V and I have the same sign (forward power), "
                  "along −z where a reflected wave dominates.",
                  "S = E × H +z irányú, ahol V és I előjele azonos (előre haladó "
                  "teljesítmény), −z irányú, ahol a visszavert hullám dominál."),
        intuition=L("Energy flows through the dielectric, guided by the conductors.",
                    "Az energia a dielektrikumban áramlik, a vezetők csak vezetik."),
        symbols=["Sz", "Er", "Hphi", "Vz", "Iz"], limitations=[_DIEL]),
    _eq(id="coax_power", name=L("Power through the cross-section",
                                "A keresztmetszeten átáramló teljesítmény"),
        latex=r"P(z,t) = \int_0^{2\pi}\!\!\int_a^b S_z\, r\,dr\,d\varphi = V(z,t)\,I(z,t)",
        meaning=L("The surface integral of S over the dielectric (computed by numerical "
                  "quadrature) equals the circuit power V·I.",
                  "S felületi integrálja a dielektrikumon (numerikus kvadratúrával számítva) "
                  "megegyezik a V·I áramköri teljesítménnyel."),
        intuition=L("The 'circuit' power V·I is carried by the fields between the conductors.",
                    "Az áramköri V·I teljesítményt a vezetők közötti terek szállítják."),
        symbols=["Pz", "Sz", "Vz", "Iz", "a_cx", "b_cx"]),
]

# Registry entries that also belong to the coaxial model, with their status there.
GENERAL: dict[str, Out] = {
    "gauss_electric": ("applicable_under_assumptions",
                       L("In the dielectric ρ_free = 0, so ∇·D = 0 (checked numerically); on the "
                         "conductor surfaces the free charge is a surface charge ρ_s.",
                         "A dielektrikumban ρ_free = 0, így ∇·D = 0 (numerikusan ellenőrizve); a "
                         "vezetők felületén a szabad töltés ρ_s felületi töltés.")),
    "gauss_magnetic": ("applicable", None),
    "faraday": ("applicable", None),
    "ampere_maxwell": ("applicable_under_assumptions",
                       L("In the dielectric J_free = 0; the conductor currents are surface "
                         "currents K on r = a and r = b.",
                         "A dielektrikumban J_free = 0; a vezetők árama felületi áram (K) az "
                         "r = a és r = b felületen.")),
    "constitutive_d_linear": ("applicable", None),
    "constitutive_b_linear": ("applicable", None),
    "poynting": ("applicable", None),
    "energy_density": ("applicable", None),
}

_NOT_COAX = L("Not part of the coaxial-cable TEM model.",
              "Nem része a koaxiális kábel TEM-modelljének.")
_NO_COAX = L("No coaxial-cable model is active.", "Nincs aktív koaxiális kábelmodell.")


def _coax_rule(c: ModelContext) -> Out:
    if not c.coax:
        return ("not_evaluated", _NO_COAX)
    return ("applicable_under_assumptions", L("Ideal lossless TEM model.",
                                              "Ideális, veszteségmentes TEM-modell."))


def _surface(c: ModelContext) -> Out:
    if not c.coax:
        return ("not_evaluated", _NO_COAX)
    return ("applicable_under_assumptions", L("Interface (distributional) quantity on r = a and "
                                              "r = b.",
                                              "Határfelületi (disztribúció jellegű) mennyiség az "
                                              "r = a és r = b felületen."))


RULES: dict[str, Rule] = {e.id: _coax_rule for e in EQUATIONS}
RULES["coax_surface_charge"] = _surface
RULES["coax_surface_current"] = _surface

EVALUATED = ["coax_e_field", "coax_h_field", "coax_inductance", "coax_capacitance",
             "coax_impedance", "coax_velocity", "coax_travelling_wave", "coax_reflection",
             "coax_surface_charge", "coax_surface_current", "coax_poynting",
             "constitutive_d_linear", "constitutive_b_linear", "poynting", "energy_density"]
CHECKED = ["coax_faraday", "coax_ampere_maxwell", "faraday", "ampere_maxwell", "gauss_electric",
           "gauss_magnetic", "telegrapher_v", "telegrapher_i", "coax_power"]
CHECKED_NOTE = L("Both sides are computed independently and compared in the Coax panel: the "
                 "analytical value from the wave derivatives against a central finite "
                 "difference of the field (for the power, the numerical cross-section integral "
                 "of S against V·I).",
                 "Mindkét oldalt függetlenül számítja a program, és a Koax panelen összeveti "
                 "őket: a hullám deriváltjaiból kapott analitikus értéket a tér centrális véges "
                 "differenciájával (a teljesítménynél S numerikus keresztmetszeti integrálját "
                 "V·I-vel).")


def guard(eid: str, rule: Rule) -> Rule:
    """Wrap an existing rule: in the coaxial model, the general entry's coax status (or not
    applicable); otherwise the original rule unchanged."""
    def wrapped(c: ModelContext) -> Out:
        if c.coax:
            return GENERAL.get(eid, ("not_applicable", _NOT_COAX))
        return rule(c)
    return wrapped
