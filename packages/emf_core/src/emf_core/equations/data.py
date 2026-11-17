"""Equation and symbol tables. Add a new equation here and a rule in ``rules.py``."""

from __future__ import annotations

from ..i18n import L
from .models import Equation, SymbolDef

PC = "analytical.electrostatics.point_charges"
MS = "analytical.magnetostatics.filaments"

SYMBOLS: dict[str, SymbolDef] = {
    "E": SymbolDef(latex=r"\mathbf{E}", unit="V/m",
                   meaning=L("electric field (force per unit positive test charge)",
                             "elektromos térerősség (egységnyi pozitív próbatöltésre ható erő)")),
    "D": SymbolDef(latex=r"\mathbf{D}", unit="C/m^2",
                   meaning=L("electric displacement", "elektromos eltolás")),
    "B": SymbolDef(latex=r"\mathbf{B}", unit="T",
                   meaning=L("magnetic flux density", "mágneses indukció (fluxussűrűség)")),
    "H": SymbolDef(latex=r"\mathbf{H}", unit="A/m",
                   meaning=L("magnetic field strength", "mágneses térerősség")),
    "J": SymbolDef(latex=r"\mathbf{J}", unit="A/m^2",
                   meaning=L("current density", "áramsűrűség")),
    "P": SymbolDef(latex=r"\mathbf{P}", unit="C/m^2",
                   meaning=L("polarization (bound dipole moment per volume)",
                             "polarizáció (kötött dipólusmomentum térfogategységenként)")),
    "M": SymbolDef(latex=r"\mathbf{M}", unit="A/m",
                   meaning=L("magnetization", "mágnesezettség")),
    "S": SymbolDef(latex=r"\mathbf{S}", unit="W/m^2",
                   meaning=L("Poynting vector (energy flux density)",
                             "Poynting-vektor (energiaáram-sűrűség)")),
    "phi": SymbolDef(latex=r"\varphi", unit="V",
                     meaning=L("electric potential", "elektromos potenciál")),
    "rho": SymbolDef(latex=r"\rho", unit="C/m^3",
                     meaning=L("total charge density (equals ρ_free in vacuum)",
                               "teljes töltéssűrűség (vákuumban megegyezik ρ_free-vel)")),
    "rho_free": SymbolDef(latex=r"\rho_{\text{free}}", unit="C/m^3",
                          meaning=L("free charge density", "szabad töltéssűrűség")),
    "eps0": SymbolDef(latex=r"\varepsilon_0", unit="F/m",
                      meaning=L("vacuum permittivity", "a vákuum permittivitása")),
    "eps": SymbolDef(latex=r"\varepsilon", unit="F/m",
                     meaning=L("permittivity ε = ε₀ε_r", "permittivitás, ε = ε₀ε_r")),
    "mu0": SymbolDef(latex=r"\mu_0", unit="H/m",
                     meaning=L("vacuum permeability", "a vákuum permeabilitása")),
    "mu": SymbolDef(latex=r"\mu", unit="H/m",
                    meaning=L("permeability μ = μ₀μ_r", "permeabilitás, μ = μ₀μ_r")),
    "sigma": SymbolDef(latex=r"\sigma", unit="S/m",
                       meaning=L("electrical conductivity", "elektromos vezetőképesség")),
    "q": SymbolDef(latex=r"q", unit="C", meaning=L("electric charge", "elektromos töltés")),
    "r": SymbolDef(latex=r"\mathbf{r}", unit="m",
                   meaning=L("field point; r_i is the position of charge i",
                             "a megfigyelési pont; r_i az i-edik töltés helye")),
    "I": SymbolDef(latex=r"I", unit="A", meaning=L("electric current", "elektromos áram")),
    "dl": SymbolDef(latex=r"d\boldsymbol{\ell}", unit="m",
                    meaning=L("line element", "vonalelem")),
    "rhat": SymbolDef(latex=r"\hat{\mathbf{r}}", unit="1",
                      meaning=L("unit vector from the source element to the field point",
                                "a forráselemtől a megfigyelési pont felé mutató egységvektor")),
    "PhiB": SymbolDef(latex=r"\Phi_B", unit="Wb",
                      meaning=L("magnetic flux", "mágneses fluxus")),
    "F": SymbolDef(latex=r"\mathbf{F}", unit="N", meaning=L("force", "erő")),
    "v": SymbolDef(latex=r"\mathbf{v}", unit="m/s", meaning=L("velocity", "sebesség")),
    "u": SymbolDef(latex=r"u", unit="J/m^3",
                   meaning=L("electromagnetic energy density", "elektromágneses energiasűrűség")),
    "delta3": SymbolDef(latex=r"\delta^3(\mathbf{r}-\mathbf{r}_i)", unit="1/m^3",
                        meaning=L("three-dimensional Dirac delta distribution centred on charge i: "
                                  "zero for r ≠ rᵢ, with ∫ δ³ dV = 1 over any volume containing "
                                  "rᵢ. It has no finite value at rᵢ.",
                                  "az i-edik töltésre centrált háromdimenziós Dirac-delta "
                                  "disztribúció: r ≠ rᵢ esetén nulla, és bármely rᵢ-t tartalmazó "
                                  "térfogatra ∫ δ³ dV = 1. Az rᵢ pontban nincs véges értéke.")),
    "Qenc": SymbolDef(latex=r"Q_{\text{enc}}", unit="C",
                      meaning=L("total charge inside the volume V", "a V térfogaton belüli "
                                "összes töltés")),
    "dA": SymbolDef(latex=r"d\mathbf{A}", unit="m^2",
                    meaning=L("oriented surface element n dA (n: unit normal, outward by default)",
                              "irányított felületelem, n dA (n: egységnyi normális, alapértelmezés "
                              "szerint kifelé mutat)")),
    "PhiE": SymbolDef(latex=r"\Phi_E", unit="V*m",
                      meaning=L("electric flux of E through the surface", "E elektromos fluxusa a "
                                "felületen át")),
    "PhiD": SymbolDef(latex=r"\Phi_D", unit="C",
                      meaning=L("flux of D through the surface", "D fluxusa a felületen át")),
    "Fvec": SymbolDef(latex=r"\mathbf{F}", unit="",
                   meaning=L("any continuously differentiable vector field (or, for point "
                             "charges, a field whose divergence is a distribution)",
                             "tetszőleges folytonosan differenciálható vektormező (ponttöltéseknél "
                             "olyan mező, amelynek divergenciája disztribúció)")),
    "V": SymbolDef(latex=r"V,\ \partial V", unit="m^3",
                   meaning=L("a volume and its closed boundary surface ∂V", "egy térfogat és "
                             "annak zárt határfelülete, ∂V")),
    "t": SymbolDef(latex=r"t", unit="s", meaning=L("time", "idő")),
    "rprime": SymbolDef(latex=r"\mathbf{r}'", unit="m",
                        meaning=L("position of the current element dℓ' on the wire",
                                  "a dℓ' áramelem helye a vezetőn")),
    "rdist": SymbolDef(latex=r"r", unit="m",
                       meaning=L("distance from the current element to the field point",
                                 "az áramelem és a megfigyelési pont távolsága")),
    "rperp": SymbolDef(latex=r"r_\perp", unit="m",
                       meaning=L("shortest (perpendicular) distance from the wire axis",
                                 "a vezető tengelyétől mért legrövidebb (merőleges) távolság")),
    "phihat": SymbolDef(latex=r"\hat{\boldsymbol{\varphi}}", unit="1",
                        meaning=L("azimuthal unit vector around the wire, oriented by the "
                                  "right-hand rule with the current direction",
                                  "a vezető körüli azimutális egységvektor, az áram irányával "
                                  "a jobbkéz-szabály szerint irányítva")),
    "a_loop": SymbolDef(latex=r"a", unit="m", meaning=L("loop radius", "a körvezető sugara")),
    "z_axis": SymbolDef(latex=r"z", unit="m",
                        meaning=L("signed distance along the loop axis from its centre",
                                  "a körvezető tengelye mentén, a középponttól mért előjeles "
                                  "távolság")),
    "rho_cyl": SymbolDef(latex=r"\rho", unit="m",
                         meaning=L("distance from the loop axis", "a körvezető tengelyétől mért "
                                   "távolság")),
    "Kk": SymbolDef(latex=r"K(m),\ E(m)", unit="1",
                    meaning=L("complete elliptic integrals of the first and second kind, with "
                              "parameter m = 4aρ/((a+ρ)² + z²)",
                              "első- és másodfajú teljes elliptikus integrálok, m = "
                              "4aρ/((a+ρ)² + z²) paraméterrel")),
    "N": SymbolDef(latex=r"N", unit="1", meaning=L("number of turns", "menetszám")),
    "Lsol": SymbolDef(latex=r"L", unit="m",
                      meaning=L("winding length: distance between the first and last turn centres",
                                "tekercshossz: az első és az utolsó menet középpontjának "
                                "távolsága")),
    "zk": SymbolDef(latex=r"z_k", unit="m",
                    meaning=L("axial position of turn k", "a k-adik menet tengelyirányú helye")),
    "nturns": SymbolDef(latex=r"n", unit="1/m",
                        meaning=L("turns per unit length", "egységnyi hosszra eső menetszám")),
    "mur": SymbolDef(latex=r"\mu_r", unit="1",
                     meaning=L("relative permeability of the core", "a mag relatív "
                               "permeabilitása")),
    "Mvec": SymbolDef(latex=r"\mathbf{M}", unit="A/m",
                      meaning=L("magnetization (prescribed, uniform)", "mágnesezettség (előírt, "
                                "egyenletes)")),
    "Lmag": SymbolDef(latex=r"L", unit="m", meaning=L("magnet length", "a mágnes hossza")),
    "Jb": SymbolDef(latex=r"\mathbf{J}_b", unit="A/m^2",
                    meaning=L("bound volume current density", "kötött térfogati áramsűrűség")),
    "Kb": SymbolDef(latex=r"\mathbf{K}_b", unit="A/m",
                    meaning=L("bound surface current density", "kötött felületi áramsűrűség")),
    "nhat": SymbolDef(latex=r"\hat{\mathbf{n}}", unit="1",
                      meaning=L("outward unit normal of the surface", "a felület kifelé mutató "
                                "egységnormálisa")),
    "mmom": SymbolDef(latex=r"\mathbf{m}", unit="A*m^2",
                      meaning=L("magnetic dipole moment", "mágneses dipólusmomentum")),
    "Ienc": SymbolDef(latex=r"I_{\text{free,enc}}", unit="A",
                      meaning=L("signed free current through a surface bounded by C (bound "
                                "currents excluded)",
                                "a C által határolt felületen átfolyó előjeles szabad áram (a "
                                "kötött áramok nélkül)")),
    "Bi": SymbolDef(latex=r"\mathbf{B}_i", unit="T",
                    meaning=L("magnetic flux density of current source i alone",
                              "az i-edik áramforrás saját mágneses indukciója")),
}

_LINEAR = L("Linear, isotropic material.", "Lineáris, izotrop anyag.")

EQUATIONS: list[Equation] = [
    Equation(
        id="gauss_electric", category="maxwell",
        name=L("Gauss's law", "Gauss-törvény"),
        latex=r"\nabla \cdot \mathbf{D} = \rho_{\text{free}}",
        latex_integral=r"\oint_{\partial V} \mathbf{D}\cdot d\mathbf{A} = Q_{\text{free,enc}}",
        meaning=L("Free charge is the source of the electric displacement field.",
                  "Az elektromos eltolás forrása a szabad töltés."),
        intuition=L("The net D-flux out of any closed surface equals the free charge inside it.",
                    "Bármely zárt felületen kifelé átmenő D-fluxus egyenlő a bezárt szabad "
                    "töltéssel."),
        symbols=["D", "rho_free"],
    ),
    Equation(
        id="gauss_electric_vacuum", category="maxwell",
        name=L("Gauss's law in vacuum", "Gauss-törvény vákuumban"),
        latex=r"\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}",
        latex_integral=r"\oint_{\partial V} \mathbf{E}\cdot d\mathbf{A} = \frac{Q_{\text{enc}}}{\varepsilon_0}",
        meaning=L("In vacuum, charge is the source of the electric field.",
                  "Vákuumban az elektromos mező forrása a töltés."),
        intuition=L("Field lines start on positive and end on negative charge; where there is no "
                    "charge the divergence is zero even though the field is not.",
                    "Az erővonalak pozitív töltésen erednek és negatívon végződnek; ahol nincs "
                    "töltés, ott a divergencia nulla, bár maga a mező nem az."),
        symbols=["E", "rho", "eps0", "Qenc"],
        assumptions=[L("Vacuum: D = ε₀E, so ρ is the total charge density.",
                       "Vákuum: D = ε₀E, így ρ a teljes töltéssűrűség.")],
        conditions=[L("For point charges ρ = Σ qᵢ δ³(r − rᵢ) is a distribution, not a function: "
                      "the law holds in the distributional sense, ∇·E = Σ (qᵢ/ε₀) δ³(r − rᵢ). "
                      "Away from the charges ∇·E = 0 even though E ≠ 0.",
                      "Ponttöltéseknél ρ = Σ qᵢ δ³(r − rᵢ) disztribúció, nem függvény: a törvény "
                      "disztribúciós értelemben teljesül, ∇·E = Σ (qᵢ/ε₀) δ³(r − rᵢ). A "
                      "töltéseken kívül ∇·E = 0, noha E ≠ 0.")],
    ),
    Equation(
        id="gauss_displacement_vacuum", category="maxwell",
        name=L("Gauss's law for D in vacuum", "Gauss-törvény D-re vákuumban"),
        latex=r"\nabla \cdot \mathbf{D} = \rho",
        latex_integral=r"\oint_{\partial V} \mathbf{D}\cdot d\mathbf{A} = Q_{\text{enc}}",
        meaning=L("In vacuum all charge is free charge, so the displacement field has the total "
                  "charge density as its source.",
                  "Vákuumban minden töltés szabad töltés, ezért az eltolási mező forrása a teljes "
                  "töltéssűrűség."),
        intuition=L("Same law as for E, measured in C/m² instead of V/m: D = ε₀E in vacuum.",
                    "Ugyanaz a törvény, mint E-re, csak C/m²-ben mérve V/m helyett: vákuumban "
                    "D = ε₀E."),
        symbols=["D", "rho", "Qenc"],
        assumptions=[L("Vacuum: no polarization, ρ = ρ_free.",
                       "Vákuum: nincs polarizáció, ρ = ρ_free.")],
        conditions=[L("For point charges ρ is a distribution; the law then holds in the "
                      "distributional sense (see ∇·D = Σ qᵢ δ³).",
                      "Ponttöltéseknél ρ disztribúció; a törvény ekkor disztribúciós értelemben "
                      "teljesül (lásd ∇·D = Σ qᵢ δ³).")],
    ),
    Equation(
        id="gauss_magnetic", category="maxwell",
        name=L("Gauss's law for magnetism", "A mágneses Gauss-törvény"),
        latex=r"\nabla \cdot \mathbf{B} = 0",
        latex_integral=r"\oint_{\partial V} \mathbf{B}\cdot d\mathbf{A} = 0",
        meaning=L("There are no magnetic monopoles.", "Nincsenek mágneses monopólusok."),
        intuition=L("Magnetic field lines never begin or end: they close on themselves or "
                    "continue without end. ∇·B = 0 does not mean B = 0: around a wire B is "
                    "large while its divergence is exactly zero.",
                    "A mágneses erővonalaknak nincs kezdetük és végük: önmagukba záródnak, vagy "
                    "vég nélkül folytatódnak. ∇·B = 0 nem jelenti azt, hogy B = 0: egy vezető "
                    "körül B nagy, a divergenciája mégis pontosan nulla."),
        symbols=["B"],
        conditions=[L("For ideal current filaments B is singular on the filament itself, so "
                      "there is no pointwise value there. The law still holds everywhere in the "
                      "distributional sense: current filaments are not magnetic monopoles, and "
                      "no magnetic charge exists in the model.",
                      "Ideális áramszálaknál B magán a szálon szinguláris, ott nincs pontbeli "
                      "értéke. A törvény disztribúciós értelemben mégis mindenütt teljesül: az "
                      "áramszálak nem mágneses monopólusok, és a modellben nincs mágneses "
                      "töltés.")],
    ),
    Equation(
        id="faraday", category="maxwell",
        name=L("Faraday's law", "Faraday-törvény"),
        latex=r"\nabla \times \mathbf{E} = -\frac{\partial \mathbf{B}}{\partial t}",
        latex_integral=r"\oint_{\partial S} \mathbf{E}\cdot d\boldsymbol{\ell} = -\frac{d\Phi_B}{dt},\quad \Phi_B=\int_S \mathbf{B}\cdot d\mathbf{A}",
        meaning=L("A time-varying magnetic field is accompanied by a rotational electric field.",
                  "Az időben változó mágneses mezőt örvényes elektromos mező kíséri."),
        intuition=L("The curl of E depends on the rate of change of B, not on its strength. The "
                    "minus sign expresses Lenz's law.",
                    "E rotációja B változási sebességétől függ, nem a nagyságától. A negatív "
                    "előjel a Lenz-törvényt fejezi ki."),
        symbols=["E", "B", "t", "PhiB", "dl"],
    ),
    Equation(
        id="ampere_maxwell", category="maxwell",
        name=L("Ampère–Maxwell law", "Ampère–Maxwell-törvény"),
        latex=r"\nabla \times \mathbf{H} = \mathbf{J}_{\text{free}} + \frac{\partial \mathbf{D}}{\partial t}",
        latex_integral=r"\oint_{\partial S} \mathbf{H}\cdot d\boldsymbol{\ell} = I_{\text{free,enc}} + \frac{d}{dt}\int_S \mathbf{D}\cdot d\mathbf{A}",
        meaning=L("Free current and changing electric displacement both produce circulating H.",
                  "A szabad áram és a változó elektromos eltolás egyaránt örvényes H mezőt kelt."),
        intuition=L("The displacement-current term ∂D/∂t is what allows electromagnetic waves.",
                    "Az eltolási áram (∂D/∂t) tagja teszi lehetővé az elektromágneses hullámokat."),
        symbols=["H", "J", "D", "t", "dl"],
    ),
    Equation(
        id="e_from_potential", category="electrostatics",
        name=L("Field from potential", "Térerősség a potenciálból"),
        latex=r"\mathbf{E} = -\nabla \varphi",
        meaning=L("A static electric field is the negative gradient of a scalar potential.",
                  "A sztatikus elektromos mező egy skalárpotenciál negatív gradiense."),
        intuition=L("E points 'downhill' in potential and is perpendicular to equipotentials.",
                    "E a potenciál csökkenésének irányába mutat, és merőleges az ekvipotenciális "
                    "felületekre."),
        symbols=["E", "phi"],
        assumptions=[L("Electrostatics: ∂B/∂t = 0, so ∇×E = 0 and E is conservative.",
                       "Elektrosztatika: ∂B/∂t = 0, ezért ∇×E = 0 és E konzervatív.")],
        limitations=[L("Not valid on its own when B changes in time (induced fields).",
                       "Önmagában nem érvényes, ha B időben változik (indukált mezők).")],
    ),
    Equation(
        id="coulomb_field", category="electrostatics",
        name=L("Coulomb field of a point charge", "Ponttöltés Coulomb-tere"),
        latex=r"\mathbf{E}(\mathbf{r}) = \frac{q}{4\pi\varepsilon_0}\,\frac{\mathbf{r}-\mathbf{r}_0}{|\mathbf{r}-\mathbf{r}_0|^3}",
        meaning=L("The electric field of a point charge q at r₀ is radial and falls off with the "
                  "square of the distance.",
                  "Az r₀ helyen lévő q ponttöltés elektromos tere sugárirányú, és a távolság "
                  "négyzetével csökken."),
        intuition=L("A positive charge pushes a positive test charge directly away from itself; "
                    "a negative charge pulls it in. Doubling the distance quarters the field.",
                    "A pozitív töltés egyenesen eltaszítja a pozitív próbatöltést, a negatív "
                    "vonzza. Kétszeres távolságban a térerősség a negyedére csökken."),
        symbols=["E", "q", "r", "eps0"],
        assumptions=[L("Ideal point charge at rest in unbounded vacuum.",
                       "Ideális, nyugvó ponttöltés végtelen vákuumban.")],
        limitations=[L("Singular at the charge position r = r₀, where E is undefined. Not valid "
                       "when conductors or dielectrics are present (induced and bound charges "
                       "are not included).",
                       "A töltés helyén (r = r₀) szinguláris, ott E nem értelmezett. Vezetők vagy "
                       "dielektrikumok jelenlétében nem érvényes (az influált és kötött "
                       "töltéseket nem tartalmazza).")],
        used_by=[PC],
    ),
    Equation(
        id="coulomb_potential", category="electrostatics",
        name=L("Potential of a point charge", "Ponttöltés potenciálja"),
        latex=r"\varphi(\mathbf{r}) = \frac{q}{4\pi\varepsilon_0\,|\mathbf{r}-\mathbf{r}_0|}",
        meaning=L("Scalar potential of a point charge, with zero potential at infinity.",
                  "Ponttöltés skalárpotenciálja, a végtelenben nulla potenciállal."),
        intuition=L("The potential is positive around a positive charge and negative around a "
                    "negative one; it falls off as 1/r, more slowly than the field.",
                    "A potenciál pozitív töltés körül pozitív, negatív körül negatív; 1/r szerint "
                    "csökken, lassabban, mint a térerősség."),
        symbols=["phi", "q", "r", "eps0"],
        assumptions=[L("Ideal point charge at rest in unbounded vacuum.",
                       "Ideális, nyugvó ponttöltés végtelen vákuumban.")],
        limitations=[L("Singular at the charge position r = r₀.",
                       "A töltés helyén (r = r₀) szinguláris.")],
        conditions=[L("Reference: φ → 0 as |r| → ∞.", "Vonatkoztatás: φ → 0, ha |r| → ∞.")],
        used_by=[PC],
    ),
    Equation(
        id="superposition", category="electrostatics",
        name=L("Superposition principle", "Szuperpozíció elve"),
        latex=r"\mathbf{E}_{\text{total}} = \sum_i \mathbf{E}_i,\qquad \varphi_{\text{total}} = \sum_i \varphi_i",
        meaning=L("The field of several charges is the vector sum of their individual fields; "
                  "the potential is the plain sum of their potentials.",
                  "Több töltés tere az egyes töltések tereinek vektori összege; a potenciál az "
                  "egyes potenciálok skaláris összege."),
        intuition=L("Each charge acts as if the others were not there. Vectors can cancel: |E| "
                    "of the sum is not the sum of the magnitudes.",
                    "Minden töltés úgy hat, mintha a többi ott sem volna. A vektorok ki is "
                    "olthatják egymást: az összeg |E| nagysága nem a nagyságok összege."),
        symbols=["E", "phi"],
        assumptions=[L("Linear medium (here: vacuum), so Maxwell's equations are linear in the "
                       "sources.",
                       "Lineáris közeg (itt: vákuum), így a Maxwell-egyenletek a forrásokban "
                       "lineárisak.")],
        limitations=[L("Does not hold for the field in nonlinear materials.",
                       "Nemlineáris anyagokban a mezőre nem érvényes.")],
        used_by=[PC],
    ),
    Equation(
        id="div_E_point_charges", category="electrostatics",
        name=L("Divergence of E for point charges (distributional Gauss's law)",
               "E divergenciája ponttöltésekre (disztribúciós Gauss-törvény)"),
        latex=r"\nabla \cdot \mathbf{E} = \sum_i \frac{q_i}{\varepsilon_0}\,\delta^3(\mathbf{r}-\mathbf{r}_i)",
        latex_integral=r"\int_V \nabla\cdot\mathbf{E}\,dV = \sum_{i:\,\mathbf{r}_i\in V} \frac{q_i}{\varepsilon_0} = \frac{Q_{\text{enc}}}{\varepsilon_0}",
        meaning=L("Each point charge is a delta source of divergence with weight qᵢ/ε₀ [V·m]. "
                  "Everywhere else the divergence is exactly zero.",
                  "Minden ponttöltés a divergencia delta-forrása qᵢ/ε₀ [V·m] súllyal. Minden "
                  "más pontban a divergencia pontosan nulla."),
        intuition=L("Divergence measures net outward flux per unit volume. Around a point charge "
                    "the field is strong, but every small volume that excludes the charge has as "
                    "much flux leaving as entering, so its divergence is zero. All the outward "
                    "flux comes from the charge itself.",
                    "A divergencia az egységnyi térfogatból kifelé irányuló nettó fluxus. A "
                    "ponttöltés körül a mező erős, de minden olyan kis térfogatból, amely a "
                    "töltést nem tartalmazza, ugyanannyi fluxus lép ki, mint be, így ott a "
                    "divergencia nulla. A teljes kifelé irányuló fluxus magától a töltéstől "
                    "származik."),
        symbols=["E", "q", "eps0", "delta3", "r", "Qenc"],
        assumptions=[L("Ideal point charges at rest in vacuum.",
                       "Ideális, nyugvó ponttöltések vákuumban.")],
        limitations=[L("δ³ is a distribution: it has no finite value at rᵢ, so the divergence at "
                       "a charge position is not a number. Only integrals over volumes are "
                       "meaningful there; the classical pointwise value is not evaluated.",
                       "A δ³ disztribúció: rᵢ-ben nincs véges értéke, ezért a divergencia a töltés "
                       "helyén nem szám. Ott csak térfogati integráloknak van értelmük; a klasszikus "
                       "pontbeli értéket a program nem értékeli ki."),
                     L("A charge exactly on the boundary of V has no well-defined enclosed "
                       "fraction.",
                       "A V határán pontosan rajta lévő töltéshez nem rendelhető egyértelmű "
                       "bezárt hányad.")],
        derivation=[
            L("Away from charge i: ∇·[(r − rᵢ)/|r − rᵢ|³] = 3/|r − rᵢ|³ − 3/|r − rᵢ|³ = 0. The "
              "Jacobian of each Coulomb term is traceless.",
              "Az i-edik töltésen kívül: ∇·[(r − rᵢ)/|r − rᵢ|³] = 3/|r − rᵢ|³ − 3/|r − rᵢ|³ = 0. "
              "Minden Coulomb-tag Jacobi-mátrixának nyoma nulla."),
            L("Through any sphere around rᵢ the flux of (r − rᵢ)/|r − rᵢ|³ is 4π, whatever the "
              "radius. A function that is zero everywhere except one point cannot give that, so "
              "the divergence is the distribution 4π δ³(r − rᵢ).",
              "Bármely rᵢ körüli gömbön át a (r − rᵢ)/|r − rᵢ|³ fluxusa 4π, a sugártól "
              "függetlenül. Egy pontot kivéve mindenütt nulla függvény ezt nem adhatja, ezért a "
              "divergencia a 4π δ³(r − rᵢ) disztribúció."),
            L("Multiplying by qᵢ/(4πε₀) and summing over the charges (superposition) gives "
              "∇·E = Σ (qᵢ/ε₀) δ³(r − rᵢ).",
              "qᵢ/(4πε₀)-lal szorozva és a töltésekre összegezve (szuperpozíció): "
              "∇·E = Σ (qᵢ/ε₀) δ³(r − rᵢ)."),
            L("Integrating over a volume V picks out exactly the enclosed charges: "
              "∫_V ∇·E dV = Q_enc/ε₀, which is Gauss's law.",
              "V térfogatra integrálva pontosan a bezárt töltések maradnak meg: "
              "∫_V ∇·E dV = Q_enc/ε₀, ami a Gauss-törvény."),
        ],
        used_by=[PC],
    ),
    Equation(
        id="div_D_point_charges", category="electrostatics",
        name=L("Divergence of D for point charges in vacuum",
               "D divergenciája ponttöltésekre vákuumban"),
        latex=r"\nabla \cdot \mathbf{D} = \sum_i q_i\,\delta^3(\mathbf{r}-\mathbf{r}_i)",
        latex_integral=r"\int_V \nabla\cdot\mathbf{D}\,dV = Q_{\text{enc}}",
        meaning=L("Each point charge is a delta source of ∇·D with weight qᵢ [C]; elsewhere "
                  "∇·D = 0 exactly.",
                  "Minden ponttöltés a ∇·D delta-forrása qᵢ [C] súllyal; máshol ∇·D pontosan 0."),
        intuition=L("D = ε₀E in vacuum, so this is the same statement as for E with the factor ε₀ "
                    "removed: the weight is the charge itself.",
                    "Vákuumban D = ε₀E, így ez ugyanaz az állítás, mint E-re, az ε₀ szorzó "
                    "nélkül: a súly maga a töltés."),
        symbols=["D", "q", "delta3", "r", "Qenc"],
        assumptions=[L("Ideal point charges at rest in vacuum (D = ε₀E).",
                       "Ideális, nyugvó ponttöltések vákuumban (D = ε₀E).")],
        limitations=[L("Not defined pointwise at a charge position; see the δ³ symbol.",
                       "A töltés helyén pontonként nem értelmezett; lásd a δ³ jelölést.")],
        used_by=[PC],
    ),
    Equation(
        id="curl_E_electrostatic", category="electrostatics",
        name=L("Curl of the electrostatic field", "Az elektrosztatikus tér rotációja"),
        latex=r"\nabla \times \mathbf{E} = \mathbf{0}",
        latex_integral=r"\oint_{C} \mathbf{E}\cdot d\boldsymbol{\ell} = 0",
        meaning=L("An electrostatic field has no rotational part: its circulation around every "
                  "closed path is zero, so it is conservative.",
                  "Az elektrosztatikus térnek nincs örvényes része: minden zárt görbe menti "
                  "cirkulációja nulla, tehát konzervatív."),
        intuition=L("The field can be strong and its lines can curve, yet a tiny paddle wheel "
                    "placed anywhere would not turn. Curl is a vector; here it is the zero vector.",
                    "A mező lehet erős és az erővonalai görbülhetnek, egy bárhová helyezett apró "
                    "lapátkerék mégsem fordulna el. A rotáció vektor; itt a nullvektor."),
        symbols=["E", "dl"],
        assumptions=[L("Electrostatics: ∂B/∂t = 0 (Faraday's law with no changing magnetic field).",
                       "Elektrosztatika: ∂B/∂t = 0 (Faraday-törvény változó mágneses mező "
                       "nélkül).")],
        limitations=[L("Fails when B changes in time; then ∇×E = −∂B/∂t (induction milestone).",
                       "Nem érvényes, ha B időben változik; ekkor ∇×E = −∂B/∂t (indukciós "
                       "mérföldkő).")],
        derivation=[
            L("Each Coulomb term is a gradient: E = −∇φ with φ = Σ qᵢ/(4πε₀|r − rᵢ|).",
              "Minden Coulomb-tag gradiens: E = −∇φ, ahol φ = Σ qᵢ/(4πε₀|r − rᵢ|)."),
            L("Away from the charges ∇×∇φ = 0 identically: the Jacobian of each term is symmetric.",
              "A töltéseken kívül ∇×∇φ azonosan 0: minden tag Jacobi-mátrixa szimmetrikus."),
            L("At a charge position the pointwise field is undefined, but the distributional curl "
              "is still zero: φ is single-valued, so ∮E·dl = 0 for every closed path, including "
              "paths passing arbitrarily close to the charge. A point charge is a source of "
              "divergence, never a source of rotation.",
              "A töltés helyén a pontbeli mező nem értelmezett, a disztribúciós rotáció azonban ott "
              "is nulla: φ egyértékű, ezért ∮E·dl = 0 minden zárt görbére, a töltéshez "
              "tetszőlegesen közel haladókra is. A ponttöltés a divergencia forrása, sosem a "
              "rotációé."),
        ],
        used_by=[PC],
    ),
    Equation(
        id="curl_D_vacuum", category="electrostatics",
        name=L("Curl of D in vacuum", "D rotációja vákuumban"),
        latex=r"\nabla \times \mathbf{D} = \mathbf{0}",
        latex_integral=r"\oint_{C} \mathbf{D}\cdot d\boldsymbol{\ell} = 0",
        meaning=L("In vacuum D = ε₀E with constant ε₀, so D is curl-free wherever E is, in the "
                  "distributional sense included.",
                  "Vákuumban D = ε₀E állandó ε₀-lal, ezért D ott rotációmentes, ahol E is, "
                  "disztribúciós értelemben is."),
        intuition=L("Multiplying a curl-free field by a constant keeps it curl-free.",
                    "Egy rotációmentes mező állandóval szorozva rotációmentes marad."),
        symbols=["D", "dl"],
        assumptions=[L("Electrostatics in vacuum or a homogeneous linear medium.",
                       "Elektrosztatika vákuumban vagy homogén lineáris közegben.")],
        limitations=[L("Not valid where ε varies in space: ∇×(εE) = ∇ε × E can be nonzero at "
                       "material interfaces even though ∇×E = 0.",
                       "Nem érvényes, ahol ε helyfüggő: anyaghatárokon ∇×(εE) = ∇ε × E nem nulla "
                       "lehet, noha ∇×E = 0.")],
        used_by=[PC],
    ),
    Equation(
        id="electric_flux", category="electrostatics",
        name=L("Electric flux", "Elektromos fluxus"),
        latex=r"\Phi_E = \oint_S \mathbf{E}\cdot d\mathbf{A}",
        meaning=L("The net amount of E crossing a closed surface, counted positive outward.",
                  "Az E zárt felületen átlépő nettó mennyisége, kifelé pozitív előjellel."),
        intuition=L("Only the normal component E·n crosses the surface; a strong field running along the "
                  "surface contributes nothing locally. External charges make field enter and "
                  "leave, adding positive and negative patches that cancel in the total.",
                  "Csak a normális irányú E·n komponens lép át a felületen; a felülettel párhuzamos "
                  "erős mező helyben semmit sem ad. A külső töltések miatt a mező be- és kilép, "
                  "pozitív és negatív részeket adva, amelyek az összegben kiejtik egymást."),
        symbols=["PhiE", "E", "dA"],
        assumptions=[L("S is a closed, consistently oriented surface on which E is defined.",
                       "S zárt, következetesen irányított felület, amelyen E értelmezett.")],
        limitations=[L("Undefined when a point charge lies on S: E is singular there.",
                       "Nem értelmezett, ha egy ponttöltés S-en fekszik: ott E szinguláris.")],
        derivation=[L("For a point charge and a flat triangle the integral is exact: "
                      "∫_T E·dA = q/(4πε₀) · Ω_T, with Ω_T the signed solid angle of T seen from "
                      "the charge. The application sums this over all triangles and charges.",
                      "Ponttöltésre és sík háromszögre az integrál egzakt: ∫_T E·dA = "
                      "q/(4πε₀) · Ω_T, ahol Ω_T a T töltésből látszó előjeles térszöge. A "
                      "program ezt összegzi minden háromszögre és töltésre.")],
        used_by=[PC],
    ),
    Equation(
        id="displacement_flux", category="electrostatics",
        name=L("Displacement flux", "Eltolási fluxus"),
        latex=r"\Phi_D = \oint_S \mathbf{D}\cdot d\mathbf{A}",
        meaning=L("The flux of D, measured in coulombs; in vacuum Φ_D = ε₀Φ_E.",
                  "D fluxusa, coulombban mérve; vákuumban Φ_D = ε₀Φ_E."),
        intuition=L("Through a closed surface it counts the enclosed free charge directly.",
                    "Zárt felületen át közvetlenül a bezárt szabad töltést méri."),
        symbols=["PhiD", "D", "dA"],
        assumptions=[L("Vacuum (D = ε₀E).", "Vákuum (D = ε₀E).")],
        limitations=[L("Undefined when a point charge lies on S.",
                       "Nem értelmezett, ha egy ponttöltés S-en fekszik.")],
        used_by=[PC],
    ),
    Equation(
        id="gauss_integral_E", category="maxwell",
        name=L("Gauss's law (closed surface, E)", "Gauss-törvény (zárt felület, E)"),
        latex=r"\oint_S \mathbf{E}\cdot d\mathbf{A} = \frac{Q_{\text{enc}}}{\varepsilon_0}",
        meaning=L("The net outward flux of E depends only on the charge enclosed by S.",
                  "E nettó kifelé irányuló fluxusa csak az S által bezárt töltéstől függ."),
        intuition=L("Change the shape or size of S, or move charges outside it, and the local flux "
                    "pattern changes but the total stays Q_enc/ε₀.",
                    "Ha S alakja vagy mérete változik, vagy a külső töltések mozognak, a helyi "
                    "fluxuseloszlás változik, de az összeg Q_enc/ε₀ marad."),
        symbols=["E", "dA", "Qenc", "eps0"],
        assumptions=[L("Vacuum; S closed and outward-oriented (reversed orientation flips the "
                       "sign); no charge on S.",
                       "Vákuum; S zárt és kifelé irányított (fordított irányítás az előjelet "
                       "megfordítja); nincs töltés S-en.")],
        limitations=[L("A charge exactly on S makes both sides ill-defined.",
                       "Egy S-en fekvő töltés mindkét oldalt értelmezhetetlenné teszi.")],
        used_by=[PC],
    ),
    Equation(
        id="gauss_integral_D", category="maxwell",
        name=L("Gauss's law (closed surface, D)", "Gauss-törvény (zárt felület, D)"),
        latex=r"\oint_S \mathbf{D}\cdot d\mathbf{A} = Q_{\text{enc}}",
        meaning=L("The net outward flux of D equals the enclosed (free) charge.",
                  "D nettó kifelé irányuló fluxusa egyenlő a bezárt (szabad) töltéssel."),
        intuition=L("Same law as for E without the factor ε₀.",
                    "Ugyanaz a törvény, mint E-re, az ε₀ szorzó nélkül."),
        symbols=["D", "dA", "Qenc"],
        assumptions=[L("Vacuum: all charge is free charge.", "Vákuum: minden töltés szabad.")],
        limitations=[L("A charge exactly on S makes both sides ill-defined.",
                       "Egy S-en fekvő töltés mindkét oldalt értelmezhetetlenné teszi.")],
        used_by=[PC],
    ),
    Equation(
        id="divergence_theorem", category="additional",
        name=L("Gauss–Ostrogradsky (divergence) theorem", "Gauss–Osztrogradszkij-tétel"),
        latex=r"\oint_{\partial V} \mathbf{F}\cdot d\mathbf{A} = \int_V (\nabla\cdot\mathbf{F})\,dV",
        meaning=L("The outward flux through a closed surface equals the integral of the "
                  "divergence over the enclosed volume.",
                  "Egy zárt felületen kifelé átmenő fluxus egyenlő a divergencia bezárt "
                  "térfogatra vett integráljával."),
        intuition=L("Split V into small cells: on every shared internal face the flux leaving one "
                    "cell enters its neighbour, so these cancel and only the outer boundary is "
                    "left. Each tiny cell's net outflow is its divergence times its volume.",
                    "Osszuk V-t kis cellákra: minden közös belső lapon az egyik cellából kilépő "
                    "fluxus a szomszédba lép be, így ezek kiejtik egymást, és csak a külső határ "
                    "marad. Minden kis cella nettó kiáramlása a divergencia és a térfogat "
                    "szorzata."),
        symbols=["Fvec", "dA", "V"],
        assumptions=[L("∂V closed and outward-oriented; F continuously differentiable in V, or its "
                       "divergence understood as a distribution.",
                       "∂V zárt és kifelé irányított; F folytonosan differenciálható V-ben, vagy "
                       "divergenciája disztribúcióként értendő.")],
        limitations=[L("Fails if F is singular on ∂V (a charge on the surface).",
                       "Nem érvényes, ha F szinguláris ∂V-n (töltés a felületen).")],
    ),
    Equation(
        id="divergence_theorem_E", category="electrostatics",
        name=L("Divergence theorem for E", "Divergenciatétel E-re"),
        latex=r"\oint_{\partial V} \mathbf{E}\cdot d\mathbf{A} = \int_V (\nabla\cdot\mathbf{E})\,dV = \sum_{i:\,\mathbf{r}_i\in V} \frac{q_i}{\varepsilon_0}",
        meaning=L("For point charges the volume integral of the distributional divergence is the "
                  "sum of the enclosed weights qᵢ/ε₀; it equals the surface flux.",
                  "Ponttöltésekre a disztribúciós divergencia térfogati integrálja a bezárt "
                  "qᵢ/ε₀ súlyok összege; ez egyenlő a felületi fluxussal."),
        intuition=L("The divergence is zero everywhere except at the charges, so the whole volume "
                    "integral comes from the δ³ sources inside: no grid of samples is summed.",
                    "A divergencia a töltéseken kívül mindenütt nulla, így a teljes térfogati "
                    "integrál a bent lévő δ³-forrásokból származik: nem mintapontokat összegez "
                    "a program."),
        symbols=["E", "dA", "q", "eps0", "V"],
        assumptions=[L("Point charges in vacuum; none on ∂V.",
                       "Ponttöltések vákuumban; egy sincs ∂V-n.")],
        limitations=[L("A charge on ∂V (or on an internal cell face when subdividing) has no "
                       "well-defined owner.",
                       "A ∂V-n (felosztásnál belső cellalapon) fekvő töltéshez nem rendelhető "
                       "egyértelmű cella.")],
        used_by=[PC],
    ),
    Equation(
        id="divergence_theorem_D", category="electrostatics",
        name=L("Divergence theorem for D", "Divergenciatétel D-re"),
        latex=r"\oint_{\partial V} \mathbf{D}\cdot d\mathbf{A} = \int_V (\nabla\cdot\mathbf{D})\,dV = Q_{\text{enc}}",
        meaning=L("The D form: both sides equal the enclosed charge.",
                  "A D-alak: mindkét oldal a bezárt töltéssel egyenlő."),
        intuition=L("The distributional divergence of D integrates to the enclosed charge.",
                    "D disztribúciós divergenciájának integrálja a bezárt töltés."),
        symbols=["D", "dA", "Qenc", "V"],
        assumptions=[L("Point charges in vacuum; none on ∂V.",
                       "Ponttöltések vákuumban; egy sincs ∂V-n.")],
        used_by=[PC],
    ),
    Equation(
        id="poisson_general", category="electrostatics",
        name=L("Poisson's equation (spatially varying permittivity)",
               "Poisson-egyenlet (helyfüggő permittivitás)"),
        latex=r"\nabla \cdot (\varepsilon \nabla \varphi) = -\rho_{\text{free}}",
        meaning=L("Governs the potential when ε varies in space.",
                  "A potenciált határozza meg, ha ε a hely függvénye."),
        intuition=L("Use this form whenever different materials meet; ε cannot be pulled out of "
                    "the divergence.",
                    "Ezt az alakot kell használni, ha különböző anyagok találkoznak; ε nem "
                    "emelhető ki a divergencia elé."),
        symbols=["eps", "phi", "rho_free"],
        assumptions=[_LINEAR, L("Electrostatics.", "Elektrosztatika.")],
    ),
    Equation(
        id="poisson_homogeneous", category="electrostatics",
        name=L("Poisson's equation (homogeneous medium)", "Poisson-egyenlet (homogén közeg)"),
        latex=r"\nabla^2 \varphi = -\frac{\rho}{\varepsilon}",
        meaning=L("Potential of a charge distribution in a medium with constant ε.",
                  "Töltéseloszlás potenciálja állandó ε-ú közegben."),
        intuition=L("Charge makes the potential curve: positive charge creates a local peak.",
                    "A töltés 'meggörbíti' a potenciált: a pozitív töltés helyi csúcsot hoz létre."),
        symbols=["phi", "rho", "eps"],
        assumptions=[L("Homogeneous linear isotropic medium; here ρ means ρ_free.",
                       "Homogén, lineáris, izotrop közeg; itt ρ a szabad töltéssűrűség.")],
    ),
    Equation(
        id="laplace", category="electrostatics",
        name=L("Laplace's equation", "Laplace-egyenlet"),
        latex=r"\nabla^2 \varphi = 0",
        meaning=L("In charge-free regions of a homogeneous medium the potential is harmonic.",
                  "Homogén közeg töltésmentes tartományaiban a potenciál harmonikus."),
        intuition=L("With no charge nearby, the potential has no local maxima or minima.",
                    "Ahol nincs töltés, ott a potenciálnak nincs helyi maximuma vagy minimuma."),
        symbols=["phi"],
        assumptions=[L("Charge-free region, homogeneous permittivity.",
                       "Töltésmentes tartomány, homogén permittivitás.")],
    ),
    Equation(
        id="ampere_static", category="magnetostatics",
        name=L("Ampère's law (magnetostatics)", "Ampère-törvény (magnetosztatika)"),
        latex=r"\nabla \times \mathbf{H} = \mathbf{J}",
        latex_integral=r"\oint_{\partial S} \mathbf{H}\cdot d\boldsymbol{\ell} = I_{\text{enc}}",
        meaning=L("Steady current produces circulating magnetic field.",
                  "Az állandó áram örvényes mágneses mezőt kelt."),
        intuition=L("Curl your right hand's fingers along H; the thumb points along the current.",
                    "Ha jobb kezünk ujjai H irányába hajlanak, hüvelykujjunk az áram irányába "
                    "mutat."),
        symbols=["H", "J", "dl"],
        assumptions=[L("Magnetostatic approximation: ∂D/∂t is neglected (steady currents).",
                       "Magnetosztatikus közelítés: ∂D/∂t elhanyagolva (stacionárius áramok).")],
        limitations=[L("Time-dependent effects must be included when currents change quickly.",
                       "Gyorsan változó áramoknál az időfüggő hatásokat figyelembe kell venni."),
                     L("Not evaluated in this milestone: the solver computes no local current-"
                       "density field J (ideal filaments have a line-distribution J), and the "
                       "integral form ∮H·dℓ = I and its interactive demonstration follow in "
                       "Phase 3B.",
                       "Ebben a mérföldkőben nincs kiértékelve: a megoldó nem számít helyi J "
                       "áramsűrűség-mezőt (az ideális áramszálak J-je vonal menti "
                       "disztribúció), az integrális alak (∮H·dℓ = I) és interaktív bemutatása "
                       "a 3B fázisban következik.")],
        satisfied_note=L("Applicable to magnetostatics and obeyed by the computed field, but not "
                         "evaluated: no local current-density field is computed in this "
                         "milestone, and the circulation demonstration ∮H·dℓ = I follows in "
                         "Phase 3B.",
                         "A magnetosztatikára érvényes, és a számított mező kielégíti, de nincs "
                         "kiértékelve: ebben a mérföldkőben nem számítunk helyi áramsűrűség-"
                         "mezőt, a ∮H·dℓ = I körintegrál bemutatása a 3B fázisban következik."),
        conditions=[L("Away from the filaments J = 0 and ∇×H = 0 pointwise; on an ideal filament "
                      "J is a line distribution and the law holds in the distributional sense.",
                      "Az áramszálakon kívül J = 0 és pontonként ∇×H = 0; ideális áramszálon J "
                      "vonal menti disztribúció, és a törvény disztribúciós értelemben teljesül.")],
    ),
    Equation(
        id="biot_savart", category="magnetostatics",
        name=L("Biot–Savart law (current element)", "Biot–Savart-törvény (áramelem)"),
        latex=r"d\mathbf{B} = \frac{\mu_0}{4\pi}\,\frac{I\,(d\boldsymbol{\ell}\times\hat{\mathbf{r}})}{r^2}",
        meaning=L("The source relation of magnetostatics: the magnetic field contribution of one "
                  "short current element.",
                  "A magnetosztatika forrásösszefüggése: egyetlen rövid áramelem járuléka a "
                  "mágneses mezőhöz."),
        intuition=L("dℓ points along the wire in the direction of the positive current; r̂ points "
                    "from the element to the field point. dB is perpendicular to both (right-hand "
                    "rule: dℓ × r̂) and falls off as 1/r², like an inverse-square law, but it "
                    "circles the element instead of pointing away from it. Adding the "
                    "contributions of all elements (the integral form) gives the total field.",
                    "dℓ a vezető mentén, a pozitív áram irányába mutat; r̂ az elemtől a "
                    "megfigyelési pont felé mutat. dB mindkettőre merőleges (jobbkéz-szabály: "
                    "dℓ × r̂), és 1/r² szerint csökken, mint egy négyzetes távolságtörvény, de az "
                    "elem körül kering ahelyett, hogy tőle elfelé mutatna. Az összes elem "
                    "járulékának összegzése (integrális alak) adja az eredő mezőt."),
        symbols=["B", "mu0", "I", "dl", "rhat", "rdist"],
        assumptions=[L("Steady current in vacuum (or a non-magnetic medium).",
                       "Stacionárius áram vákuumban (vagy nem mágneses közegben).")],
        limitations=[L("A single element is not a physical source on its own: steady currents "
                       "form closed circuits (or infinite wires), and only the integral over the "
                       "whole circuit is a physical field.",
                       "Egyetlen áramelem önmagában nem fizikai forrás: a stacionárius áramok "
                       "zárt áramköröket (vagy végtelen vezetőket) alkotnak, és csak a teljes "
                       "áramkörre vett integrál fizikai mező.")],
    ),
    Equation(
        id="biot_savart_integral", category="magnetostatics",
        name=L("Biot–Savart law (integral form)", "Biot–Savart-törvény (integrális alak)"),
        latex=r"\mathbf{B}(\mathbf{r}) = \frac{\mu_0}{4\pi}\int_C \frac{I\,d\boldsymbol{\ell}'\times(\mathbf{r}-\mathbf{r}')}{|\mathbf{r}-\mathbf{r}'|^3}",
        meaning=L("The total magnetic field of a current-carrying wire C: the sum of all "
                  "current-element contributions.",
                  "Egy C áramvezető teljes mágneses mezője: az összes áramelem járulékának "
                  "összege."),
        intuition=L("r − r' points from the element to the field point; dividing by |r − r'|³ is "
                    "the same as r̂/r². The closed-form wire and loop formulas are exact "
                    "solutions of this integral.",
                    "r − r' az elemtől a megfigyelési pont felé mutat; |r − r'|³-nal osztva ez "
                    "ugyanaz, mint r̂/r². Az egyenes vezető és a körvezető zárt alakú képletei "
                    "ennek az integrálnak egzakt megoldásai."),
        symbols=["B", "mu0", "I", "dl", "r", "rprime"],
        assumptions=[L("Steady current, vacuum, thin wire (filament).",
                       "Stacionárius áram, vákuum, vékony vezető (áramszál).")],
        limitations=[L("Not integrated numerically by the solver: it evaluates the closed-form "
                       "solutions. A numerical evaluation of this integral is used only in the "
                       "validation tests.",
                       "A megoldó nem integrálja numerikusan: a zárt alakú megoldásokat "
                       "értékeli ki. Ennek az integrálnak a numerikus kiértékelését csak az "
                       "ellenőrző tesztek használják.")],
        satisfied_note=L("The solver evaluates exact closed-form solutions of this integral "
                         "(straight wire, circular loop); the integral itself is not computed.",
                         "A megoldó ennek az integrálnak egzakt, zárt alakú megoldásait értékeli "
                         "ki (egyenes vezető, körvezető); magát az integrált nem számítja."),
    ),
    Equation(
        id="infinite_wire_field", category="magnetostatics",
        name=L("Field of an infinite straight wire", "Végtelen egyenes vezető tere"),
        latex=r"\mathbf{B} = \frac{\mu_0 I}{2\pi r_\perp}\,\hat{\boldsymbol{\varphi}},\qquad \mathbf{H} = \frac{I}{2\pi r_\perp}\,\hat{\boldsymbol{\varphi}}",
        meaning=L("Exact solution of the Biot–Savart integral for an infinitely long straight "
                  "filament.",
                  "A Biot–Savart-integrál egzakt megoldása végtelen hosszú egyenes áramszálra."),
        intuition=L("The field lines are circles around the wire; point the right thumb along "
                    "the current and the fingers curl along B. |B| halves when the distance "
                    "doubles.",
                    "Az erővonalak a vezető körüli körök; ha jobb hüvelykujjunk az áram irányába "
                    "mutat, ujjaink B irányába hajlanak. A távolság kétszeresére |B| a felére "
                    "csökken."),
        symbols=["B", "H", "mu0", "I", "rperp", "phihat"],
        assumptions=[L("Infinitely long, straight, zero-radius wire; steady current; vacuum.",
                       "Végtelen hosszú, egyenes, nulla sugarú vezető; stacionárius áram; "
                       "vákuum.")],
        limitations=[L("Singular on the wire axis (r⊥ = 0): the ideal filament has no "
                       "pointwise field there. A real wire of finite radius has a finite field "
                       "inside it, which is outside this model.",
                       "A vezető tengelyén (r⊥ = 0) szinguláris: az ideális áramszálnak ott "
                       "nincs pontbeli tere. Egy véges sugarú valódi vezető belsejében véges "
                       "a tér, ez azonban kívül esik ezen a modellen."),
                     L("A real wire is finite; the formula is accurate when the distance is "
                       "much smaller than the distance to its ends.",
                       "Valódi vezető véges hosszú; a képlet akkor pontos, ha a távolság jóval "
                       "kisebb a vezető végeitől mért távolságnál.")],
        used_by=[MS],
    ),
    Equation(
        id="loop_axis_field", category="magnetostatics",
        name=L("Circular loop: field on the axis", "Körvezető: a tér a tengelyen"),
        latex=r"B_z(z) = \frac{\mu_0 I a^2}{2\,(a^2 + z^2)^{3/2}}",
        meaning=L("Exact field of a thin circular loop on its symmetry axis.",
                  "Vékony körvezető egzakt tere a szimmetriatengelyén."),
        intuition=L("On the axis B points along the axis (curl the right-hand fingers with the "
                    "current: the thumb gives the direction); at the centre B = μ₀I/(2a), far "
                    "away it falls off as 1/z³ like a dipole.",
                    "A tengelyen B a tengely irányába mutat (ha jobb kezünk ujjai az áram "
                    "irányában hajlanak, hüvelykujjunk adja az irányt); a középpontban "
                    "B = μ₀I/(2a), nagy távolságban 1/z³ szerint csökken, mint egy dipólusé."),
        symbols=["B", "mu0", "I", "a_loop", "z_axis"],
        assumptions=[L("Thin (zero-radius) circular wire, steady current, vacuum.",
                       "Vékony (nulla vastagságú) kör alakú vezető, stacionárius áram, vákuum.")],
        limitations=[L("Valid only on the axis. Off the axis there is also a radial component; "
                       "the solver never uses this formula off the axis.",
                       "Csak a tengelyen érvényes. A tengelyen kívül radiális komponens is van; "
                       "a megoldó a tengelyen kívül sosem használja ezt a képletet.")],
        used_by=[MS],
    ),
    Equation(
        id="loop_field_elliptic", category="magnetostatics",
        name=L("Circular loop: field everywhere", "Körvezető: a tér mindenütt"),
        latex=r"B_z = \frac{\mu_0 I}{2\pi\sqrt{(a+\rho)^2+z^2}}\left[K(m) + \frac{a^2-\rho^2-z^2}{(a-\rho)^2+z^2}E(m)\right],\quad B_\rho = \frac{\mu_0 I\,z}{2\pi\rho\sqrt{(a+\rho)^2+z^2}}\left[-K(m) + \frac{a^2+\rho^2+z^2}{(a-\rho)^2+z^2}E(m)\right]",
        meaning=L("Exact solution of the Biot–Savart integral for a circular loop at any point, "
                  "in terms of complete elliptic integrals.",
                  "A Biot–Savart-integrál egzakt megoldása körvezetőre, tetszőleges pontban, "
                  "teljes elliptikus integrálokkal kifejezve."),
        intuition=L("The field is axially symmetric (no azimuthal component). Near the axis it "
                    "is almost axial but has a small radial part; near the wire it circles the "
                    "wire like a straight wire's field.",
                    "A mező tengelyszimmetrikus (nincs azimutális komponense). A tengely közelében "
                    "majdnem tengelyirányú, de kis radiális része is van; a vezető közelében a "
                    "vezetőt kerüli meg, mint egy egyenes vezető tere."),
        symbols=["B", "mu0", "I", "a_loop", "rho_cyl", "z_axis", "Kk"],
        assumptions=[L("Thin circular wire, steady current, vacuum.",
                       "Vékony kör alakú vezető, stacionárius áram, vákuum.")],
        limitations=[L("Singular on the wire itself. Near the axis the bracket of B_ρ cancels "
                       "to O(m²); there (m ≤ 0.5) the solver uses the exact power series of "
                       "that bracket, which has only positive terms, and on the axis B_ρ = 0.",
                       "Magán a vezetőn szinguláris. A tengely közelében B_ρ zárójeles "
                       "kifejezése O(m²)-re kiesik; ott (m ≤ 0,5) a megoldó ennek a "
                       "kifejezésnek az egzakt, csak pozitív tagokat tartalmazó hatványsorát "
                       "használja, a tengelyen pedig B_ρ = 0.")],
        used_by=[MS],
    ),
    Equation(
        id="superposition_magnetic", category="magnetostatics",
        name=L("Superposition of magnetic fields", "Mágneses mezők szuperpozíciója"),
        latex=r"\mathbf{B} = \sum_i \mathbf{B}_i,\qquad \mathbf{H} = \sum_i \mathbf{H}_i",
        meaning=L("The total field of several current sources is the vector sum of their "
                  "individual fields.",
                  "Több áramforrás eredő tere egyedi tereik vektori összege."),
        intuition=L("Where two contributions point the same way the field is reinforced; where "
                    "they point opposite ways it is weakened, and it can vanish.",
                    "Ahol két járulék azonos irányba mutat, a mező erősödik; ahol "
                    "ellentétesen, gyengül, és akár el is tűnhet."),
        symbols=["B", "Bi", "H"],
        assumptions=[L("Linear medium (vacuum).", "Lineáris közeg (vákuum).")],
        used_by=[MS],
    ),
    Equation(
        id="div_B_filaments", category="magnetostatics",
        name=L("Divergence of B of current filaments", "Áramszálak B-terének divergenciája"),
        latex=r"\nabla\cdot\mathbf{B} = 0\quad(\mathbf{r}\notin\text{filaments})",
        meaning=L("Away from the ideal filaments the computed B has exactly zero divergence; "
                  "on them only the distributional statement ∇·B = 0 applies.",
                  "Az ideális áramszálakon kívül a számított B divergenciája pontosan nulla; "
                  "rajtuk csak a ∇·B = 0 disztribúciós állítás érvényes."),
        intuition=L("Every Biot–Savart contribution is divergence-free, so the sum is too. The "
                    "colour map shows exact zeros, not small numbers.",
                    "Minden Biot–Savart-járulék divergenciamentes, így az összegük is. A "
                    "színtérkép pontos nullákat mutat, nem kis számokat."),
        symbols=["B"],
        assumptions=[L("Ideal filaments in vacuum.", "Ideális áramszálak vákuumban.")],
        used_by=[MS],
    ),
    Equation(
        id="b_mu0_h", category="constitutive",
        name=L("Magnetic flux density in vacuum", "Mágneses indukció vákuumban"),
        latex=r"\mathbf{B} = \mu_0\mathbf{H}",
        meaning=L("In vacuum B and H are proportional, with the vacuum permeability as factor.",
                  "Vákuumban B és H arányos, a szorzó a vákuum permeabilitása."),
        intuition=L("B (tesla) and H (ampere per metre) are different quantities with different "
                    "units; in vacuum they point the same way and differ by μ₀ ≈ 1.257×10⁻⁶ H/m.",
                    "B (tesla) és H (amper per méter) különböző mennyiségek különböző "
                    "mértékegységgel; vákuumban azonos irányúak, és μ₀ ≈ 1,257×10⁻⁶ H/m "
                    "szorzóban térnek el."),
        symbols=["B", "mu0", "H"],
        assumptions=[L("Vacuum (M = 0). Magnetic materials are a later milestone.",
                       "Vákuum (M = 0). A mágneses anyagok egy későbbi mérföldkő tárgyai.")],
        used_by=[MS],
    ),
    Equation(
        id="h_from_b", category="constitutive",
        name=L("Magnetic field strength in vacuum", "Mágneses térerősség vákuumban"),
        latex=r"\mathbf{H} = \frac{\mathbf{B}}{\mu_0}",
        meaning=L("How the solver obtains H from B in vacuum.",
                  "Ahogyan a megoldó vákuumban B-ből H-t kapja."),
        intuition=L("Same relation as B = μ₀H, solved for H.",
                    "Ugyanaz az összefüggés, mint B = μ₀H, H-ra kifejezve."),
        symbols=["H", "B", "mu0"],
        assumptions=[L("Vacuum (M = 0).", "Vákuum (M = 0).")],
        used_by=[MS],
    ),
    Equation(
        id="finite_solenoid_superposition", category="magnetostatics",
        name=L("Finite solenoid: sum of its turns", "Véges szolenoid: a menetek összege"),
        latex=r"\mathbf{B}_{\text{sol}}(\mathbf{r}) = \sum_{k=0}^{N-1} \mathbf{B}_{\text{loop}}(\mathbf{r};\,a,\,z_k,\,I),\qquad z_k = -\tfrac{L}{2} + k\,\tfrac{L}{N-1}",
        meaning=L("The field of a finite solenoid, computed as the sum of the exact fields of its N "
                  "circular turns.",
                  "A véges szolenoid tere, N kör alakú menete egzakt terének összegeként számítva."),
        intuition=L("Each turn's field points along the axis near the centre; inside the coil they "
                    "add up to a strong, nearly uniform field. Near the ends there are fewer turns "
                    "on one side, so the field weakens and spreads out (fringe field).",
                    "Minden menet tere a középpont közelében tengelyirányú; a tekercs belsejében "
                    "ezek erős, közel homogén térré adódnak össze. A végek közelében az egyik "
                    "oldalon kevesebb menet van, ezért a tér gyengül és szétterül (szórt tér)."),
        symbols=["B", "N", "a_loop", "I", "Lsol", "zk"],
        assumptions=[L("Discrete coaxial circular turns of zero thickness, steady current, vacuum. "
                       "Helical connections and lead wires are not modelled.",
                       "Diszkrét, koaxiális, nulla vastagságú kör alakú menetek, stacionárius áram, "
                       "vákuum. A csavarvonalas összeköttetéseket és a hozzávezetéseket nem "
                       "modellezzük.")],
        limitations=[L("Exact for the represented turns; a real helical winding differs slightly, "
                       "mostly near the turns themselves.",
                       "Az ábrázolt menetekre egzakt; egy valódi csavarvonalas tekercs kissé "
                       "eltér, főleg a menetek közvetlen közelében.")],
        used_by=[MS],
    ),
    Equation(
        id="solenoid_turn_spacing", category="magnetostatics",
        name=L("Turn spacing", "Menetköz"),
        latex=r"\Delta z = \frac{L}{N-1}\quad (N > 1)",
        meaning=L("Distance between neighbouring turn centres, derived from the winding length L "
                  "(first to last turn centre) and the number of turns.",
                  "A szomszédos menetközéppontok távolsága, a tekercshosszból (első és utolsó "
                  "menet középpontja között) és a menetszámból származtatva."),
        intuition=L("Spacing is not an independent input: changing N or L changes it.",
                    "A menetköz nem független bemenet: N vagy L módosítása megváltoztatja."),
        symbols=["Lsol", "N"],
        assumptions=[L("Evenly spaced turns; for N = 1 the single turn sits at the centre.",
                       "Egyenletesen elosztott menetek; N = 1 esetén az egyetlen menet a "
                       "középpontban van.")],
        used_by=[MS],
    ),
    Equation(
        id="solenoid_turn_density", category="magnetostatics",
        name=L("Turns per unit length", "Egységnyi hosszra eső menetszám"),
        latex=r"n = \frac{N}{L}",
        meaning=L("Winding density used by the ideal long-solenoid approximation.",
                  "Az ideális hosszú szolenoid közelítés tekercssűrűsége."),
        intuition=L("More turns per metre give a stronger field inside a long coil.",
                    "Méterenként több menet erősebb teret ad egy hosszú tekercs belsejében."),
        symbols=["nturns", "N", "Lsol"],
        idealized=True,
    ),
    Equation(
        id="ideal_solenoid_H", category="magnetostatics",
        name=L("Ideal long solenoid: H", "Ideális hosszú szolenoid: H"),
        latex=r"H \approx n I",
        meaning=L("Field strength inside an infinitely long, densely wound solenoid.",
                  "A térerősség egy végtelen hosszú, sűrűn tekercselt szolenoid belsejében."),
        intuition=L("Follows from Ampère's law on a rectangle with one side inside the coil.",
                    "Az Ampère-törvényből következik egy olyan téglalapra, amelynek egyik oldala a "
                    "tekercsen belül van."),
        symbols=["H", "nturns", "I"],
        assumptions=[L("Long coil (L ≫ a), central region far from the ends, vacuum or air core.",
                       "Hosszú tekercs (L ≫ a), a végektől távoli középső tartomány, vákuum vagy "
                       "levegő mag.")],
        limitations=[L("An idealized comparison value, never the solver's result: the finite "
                       "solenoid is always computed from its turns. Wrong near the ends and "
                       "outside the coil.",
                       "Idealizált összehasonlító érték, sosem a megoldó eredménye: a véges "
                       "szolenoidot mindig a meneteiből számítjuk. A végek közelében és a "
                       "tekercsen kívül hibás.")],
        idealized=True,
    ),
    Equation(
        id="ideal_solenoid_B", category="magnetostatics",
        name=L("Ideal long solenoid: B", "Ideális hosszú szolenoid: B"),
        latex=r"B \approx \mu_0 n I",
        meaning=L("Flux density inside an infinitely long, densely wound air-core solenoid.",
                  "Az indukció egy végtelen hosszú, sűrűn tekercselt, légmagos szolenoid "
                  "belsejében."),
        intuition=L("The finite solenoid's central field approaches this value as the coil gets "
                    "longer relative to its radius.",
                    "A véges szolenoid középponti tere ehhez az értékhez közelít, ahogy a tekercs "
                    "a sugarához képest hosszabb lesz."),
        symbols=["B", "mu0", "nturns", "I"],
        assumptions=[L("Long coil (L ≫ a), central region, vacuum.",
                       "Hosszú tekercs (L ≫ a), középső tartomány, vákuum.")],
        limitations=[L("Idealized comparison only; see the probe for where it applies.",
                       "Csak idealizált összehasonlítás; a szonda mutatja, hol alkalmazható.")],
        idealized=True,
    ),
    Equation(
        id="finite_toroid_superposition", category="magnetostatics",
        name=L("Finite-turn toroid: sum of its turns", "Véges menetszámú toroid: a menetek összege"),
        latex=r"\mathbf{B}_{\text{tor}}(\mathbf{r}) = \sum_{k=0}^{N-1}\mathbf{B}_{\text{loop},k}(\mathbf{r}),\qquad \mathbf{H}_{\text{tor}} = \mathbf{B}_{\text{tor}}/\mu_0",
        meaning=L("The field of N circular turns arranged around a toroidal centreline, each in a "
                  "meridional plane.",
                  "Egy tóruszalakú középvonal mentén elrendezett, meridiánsíkokban fekvő N kör "
                  "alakú menet tere."),
        intuition=L("Inside the winding the turns' fields add up around the ring; outside they "
                    "almost cancel, but not exactly: the discrete turns leak a little field.",
                    "A tekercselésen belül a menetek terei körben összeadódnak; kívül majdnem "
                    "kioltják egymást, de nem pontosan: a diszkrét menetekből kevés tér szivárog "
                    "ki."),
        symbols=["B", "H", "mu0", "N"],
        assumptions=[L("Thin circular turns, steady current, vacuum (no core).",
                       "Vékony kör alakú menetek, stacionárius áram, vákuum (nincs mag).")],
        used_by=[MS],
    ),
    Equation(
        id="ideal_toroid_H", category="magnetostatics",
        name=L("Ideal toroid: H in the core", "Ideális toroid: H a magban"),
        latex=r"H_\varphi = \frac{N I}{2\pi\rho}\quad\text{inside the core},\qquad \mathbf{H} = 0\ \text{outside}",
        meaning=L("Field strength of an ideal continuous toroidal winding, from Ampère's law on a "
                  "coaxial circle.",
                  "Ideális, folytonos toroid tekercselés térerőssége, egy koaxiális körre "
                  "felírt Ampère-törvényből."),
        intuition=L("A circle of radius ρ inside the core links all N turns: 2πρ H = NI.",
                    "A magon belüli ρ sugarú kör mind az N menetet körülöleli: 2πρ H = NI."),
        symbols=["H", "N", "I", "rho_cyl"],
        assumptions=[L("Continuous winding, circular core, no leakage or fringing (idealization).",
                       "Folytonos tekercselés, kör keresztmetszetű mag, szórt tér és perem nélkül "
                       "(idealizáció).")],
        limitations=[L("Not the field of a real or finite-turn toroid outside the core (there it "
                       "is not zero).",
                       "Nem egy valódi vagy véges menetszámú toroid tere a magon kívül (ott nem "
                       "nulla).")],
        used_by=[MS], idealized=True,
    ),
    Equation(
        id="ideal_toroid_B", category="magnetostatics",
        name=L("Ideal toroid: B in a linear core", "Ideális toroid: B lineáris magban"),
        latex=r"B_\varphi = \frac{\mu_0\mu_r N I}{2\pi\rho}",
        meaning=L("Flux density in a homogeneous, linear, isotropic core of the ideal toroid.",
                  "Az ideális toroid homogén, lineáris, izotrop magjában az indukció."),
        intuition=L("H is set by the current alone; the core multiplies B by μᵣ.",
                    "H-t egyedül az áram határozza meg; a mag μᵣ-szeresére növeli B-t."),
        symbols=["B", "mu0", "mur", "N", "I", "rho_cyl"],
        assumptions=[L("Linear, isotropic, time-independent core; ideal confinement.",
                       "Lineáris, izotrop, időfüggetlen mag; ideális térbezárás.")],
        used_by=[MS], idealized=True,
    ),
    Equation(
        id="magnet_sheet_field", category="magnetostatics",
        name=L("Uniformly magnetized cylinder: field of its bound current",
               "Egyenletesen mágnesezett henger: a kötött áram tere"),
        latex=r"\mathbf{B}(\mathbf{r}) = \int_{-L/2}^{L/2} M\,\mathbf{B}_{\text{loop}}(\mathbf{r};\,a,\,z',\,1\,\text{A})\,dz'",
        meaning=L("The bound surface current K = M e_φ on the side wall is a continuous stack of "
                  "circular loops carrying M dz' each; their fields are integrated numerically.",
                  "A palást K = M e_φ kötött felületi árama körhurkok folytonos halmaza, "
                  "mindegyik M dz' árammal; ezek terét numerikusan integráljuk."),
        intuition=L("A magnet's field is the field of its surface current: like a solenoid with "
                    "infinitely many, infinitely thin turns.",
                    "A mágnes tere a felületi áramának tere: mint egy szolenoid végtelen sok, "
                    "végtelenül vékony menettel."),
        symbols=["B", "Mvec", "a_loop", "Lmag"],
        assumptions=[L("Uniform axial magnetization, no other material.",
                       "Egyenletes tengelyirányú mágnesezettség, nincs más anyag.")],
        limitations=[L("Adaptive Gauss–Kronrod quadrature (stated tolerance); on the side wall "
                       "itself the tangential B has two one-sided limits.",
                       "Adaptív Gauss–Kronrod kvadratúra (megadott tűréssel); magán a palaston a "
                       "tangenciális B-nek két egyoldali határértéke van.")],
        used_by=[MS],
    ),
    Equation(
        id="h_from_b_m", category="constitutive",
        name=L("H inside a magnetized material", "H mágnesezett anyagban"),
        latex=r"\mathbf{H} = \frac{\mathbf{B}}{\mu_0} - \mathbf{M}",
        meaning=L("How the solver obtains H from B where a prescribed magnetization M exists; "
                  "outside the magnet M = 0 and H = B/μ₀.",
                  "Ahogyan a megoldó B-ből H-t kapja ott, ahol előírt M mágnesezettség van; a "
                  "mágnesen kívül M = 0 és H = B/μ₀."),
        intuition=L("Inside a bar magnet H points backwards (from N to S inside), opposite to B.",
                    "Egy rúdmágnes belsejében H visszafelé mutat (belül É-tól D felé), B-vel "
                    "ellentétesen."),
        symbols=["H", "B", "mu0", "Mvec"],
        assumptions=[L("Prescribed magnetization (no hysteresis or demagnetization curve).",
                       "Előírt mágnesezettség (nincs hiszterézis vagy lemágnesezési görbe).")],
        used_by=[MS],
    ),
    Equation(
        id="bound_currents", category="constitutive",
        name=L("Bound (magnetization) currents", "Kötött (mágnesezési) áramok"),
        latex=r"\mathbf{J}_b = \nabla\times\mathbf{M},\qquad \mathbf{K}_b = \mathbf{M}\times\hat{\mathbf{n}}",
        meaning=L("A magnetization is equivalent to bound currents: a volume current where M "
                  "varies and a surface current where it ends. For a uniform axial cylinder "
                  "J_b = 0, K_b = M e_φ on the side wall, and K_b = 0 on the end faces.",
                  "A mágnesezettség kötött áramokkal egyenértékű: térfogati áram, ahol M változik, "
                  "és felületi áram, ahol véget ér. Egyenletes, tengelyirányú hengernél J_b = 0, "
                  "a palaston K_b = M e_φ, a véglapokon K_b = 0."),
        intuition=L("Bound currents produce B like any current, but they are not free current: "
                    "they do not appear in Ampère's law for H.",
                    "A kötött áramok minden áramhoz hasonlóan B-t keltenek, de nem szabad áramok: "
                    "nem szerepelnek a H-ra vonatkozó Ampère-törvényben."),
        symbols=["Jb", "Kb", "Mvec", "nhat"],
        used_by=[MS],
    ),
    Equation(
        id="magnetic_moment", category="magnetostatics",
        name=L("Magnetic moment of the magnet", "A mágnes mágneses momentuma"),
        latex=r"\mathbf{m} = \mathbf{M}\,V = M\,\pi a^2 L\,\hat{\mathbf{e}}_{\text{axis}}",
        meaning=L("Total magnetic dipole moment of the uniformly magnetized cylinder.",
                  "Az egyenletesen mágnesezett henger teljes mágneses dipólusmomentuma."),
        intuition=L("Sets the strength of the field far away from the magnet.",
                    "Ez határozza meg a tér erősségét a mágnestől távol."),
        symbols=["mmom", "Mvec", "a_loop", "Lmag"],
        used_by=[MS],
    ),
    Equation(
        id="dipole_far_field", category="magnetostatics",
        name=L("Far field of a magnetic dipole", "Mágneses dipólus távoltere"),
        latex=r"\mathbf{B} \approx \frac{\mu_0}{4\pi r^3}\left[3(\mathbf{m}\cdot\hat{\mathbf{r}})\hat{\mathbf{r}} - \mathbf{m}\right]",
        meaning=L("At distances much larger than the magnet, its field approaches that of a point "
                  "dipole.",
                  "A mágnes méreténél jóval nagyobb távolságban a tere egy pontszerű dipólus "
                  "teréhez közelít."),
        intuition=L("Falls off as 1/r³; the probe compares it with the full result.",
                    "1/r³ szerint csökken; a szonda összeveti a teljes eredménnyel."),
        symbols=["B", "mu0", "mmom", "r"],
        assumptions=[L("r much larger than the magnet's dimensions (here: r ≥ 5 × size).",
                       "r jóval nagyobb a mágnes méreteinél (itt: r ≥ 5 × méret).")],
        limitations=[L("A labelled comparison only; the solver always uses the full surface-"
                       "current model.",
                       "Csak jelölt összehasonlítás; a megoldó mindig a teljes felületi áramos "
                       "modellt használja.")],
        idealized=True,
    ),
    Equation(
        id="ampere_integral", category="magnetostatics",
        name=L("Ampère's law (integral form)", "Ampère-törvény (integrális alak)"),
        latex=r"\oint_C \mathbf{H}\cdot d\boldsymbol{\ell} = I_{\text{free,enc}}",
        meaning=L("The circulation of H around any closed path equals the free current through "
                  "any surface bounded by it (signed by the right-hand rule).",
                  "H körintegrálja bármely zárt görbe mentén egyenlő a görbe által határolt "
                  "felületen átfolyó szabad árammal (előjel a jobbkéz-szabály szerint)."),
        intuition=L("Curl the right-hand fingers along the path: currents along the thumb count "
                    "positive. Currents outside the path, and bound currents of magnets, do not "
                    "count.",
                    "Ha jobb kezünk ujjai az út irányában hajlanak, a hüvelykujj irányába folyó "
                    "áramok pozitívak. Az úton kívüli áramok és a mágnesek kötött áramai nem "
                    "számítanak."),
        symbols=["H", "dl", "Ienc"],
        assumptions=[L("Magnetostatics: steady currents, ∂D/∂t neglected.",
                       "Magnetosztatika: stacionárius áramok, ∂D/∂t elhanyagolva.")],
        limitations=[L("Checked on the Ampère paths: the left side by adaptive numerical "
                       "integration of H from the solver, the right side independently from the "
                       "signed crossings of the current filaments with the spanning surface.",
                       "Az Ampère-utakon ellenőrizve: a bal oldal a megoldó H terének adaptív "
                       "numerikus integráljával, a jobb oldal függetlenül, az áramszálak és a "
                       "kifeszített felület előjeles metszéspontjaiból.")],
    ),
    Equation(
        id="ampere_vacuum_B", category="magnetostatics",
        name=L("Ampère's law for B in vacuum", "Ampère-törvény B-re vákuumban"),
        latex=r"\oint_C \mathbf{B}\cdot d\boldsymbol{\ell} = \mu_0 I_{\text{enc}}",
        meaning=L("Vacuum form: valid only where there is no magnetization (M = 0) along and "
                  "inside the path.",
                  "Vákuumbeli alak: csak ott érvényes, ahol az út mentén és belsejében nincs "
                  "mágnesezettség (M = 0)."),
        intuition=L("With magnets, ∮B·dl also counts their bound current; that is why the law "
                    "in matter is written for H.",
                    "Mágnesek jelenlétében ∮B·dl a kötött áramukat is beszámítja; ezért írjuk az "
                    "anyagbeli törvényt H-ra."),
        symbols=["B", "dl", "mu0", "Ienc"],
        assumptions=[L("Vacuum, M = 0.", "Vákuum, M = 0.")],
    ),
    Equation(
        id="free_bound_currents", category="magnetostatics",
        name=L("Free and bound current", "Szabad és kötött áram"),
        latex=r"\nabla\times\mathbf{B} = \mu_0\left(\mathbf{J}_{\text{free}} + \mathbf{J}_b\right),\qquad \nabla\times\mathbf{H} = \mathbf{J}_{\text{free}}",
        meaning=L("B is produced by free and bound currents together; H only 'sees' the free "
                  "current in its curl.",
                  "B-t a szabad és a kötött áramok együtt keltik; H rotációjában csak a szabad "
                  "áram jelenik meg."),
        intuition=L("A permanent magnet with no wires has ∮H·dl = 0 around every path, although "
                    "B is far from zero.",
                    "Egy vezeték nélküli állandó mágnes körül minden útra ∮H·dl = 0, noha B "
                    "korántsem nulla."),
        symbols=["B", "H", "mu0", "J", "Jb"],
    ),
    Equation(
        id="constitutive_d_general", category="constitutive",
        name=L("Electric displacement (general)", "Elektromos eltolás (általános)"),
        latex=r"\mathbf{D} = \varepsilon_0\mathbf{E} + \mathbf{P}",
        meaning=L("Defines D in terms of E and the material polarization.",
                  "D definíciója E-vel és az anyag polarizációjával."),
        intuition=L("D counts only free charge; the bound charge is absorbed into P.",
                    "D csak a szabad töltést 'látja'; a kötött töltést P tartalmazza."),
        symbols=["D", "eps0", "E", "P"],
    ),
    Equation(
        id="constitutive_d_linear", category="constitutive",
        name=L("Linear isotropic dielectric", "Lineáris, izotrop dielektrikum"),
        latex=r"\mathbf{D} = \varepsilon\mathbf{E}",
        meaning=L("Material model: polarization proportional to the field.",
                  "Anyagmodell: a polarizáció arányos a térerősséggel."),
        intuition=L("In vacuum ε = ε₀, so D and E differ only by a constant factor.",
                    "Vákuumban ε = ε₀, így D és E csak egy állandó szorzóban tér el."),
        symbols=["D", "eps", "E"], assumptions=[_LINEAR], used_by=[PC],
    ),
    Equation(
        id="constitutive_b_general", category="constitutive",
        name=L("Magnetic flux density (general)", "Mágneses indukció (általános)"),
        latex=r"\mathbf{B} = \mu_0(\mathbf{H} + \mathbf{M})",
        meaning=L("Relates B, H and the material magnetization.",
                  "B, H és az anyag mágnesezettsége közötti kapcsolat."),
        intuition=L("H is driven by free currents; M adds the material's own contribution.",
                    "H-t a szabad áramok keltik; M az anyag saját járulékát adja hozzá."),
        symbols=["B", "mu0", "H", "M"],
    ),
    Equation(
        id="constitutive_b_linear", category="constitutive",
        name=L("Linear isotropic magnetic material", "Lineáris, izotrop mágneses anyag"),
        latex=r"\mathbf{B} = \mu\mathbf{H}",
        meaning=L("Material model: magnetization proportional to H.",
                  "Anyagmodell: a mágnesezettség arányos H-val."),
        intuition=L("B and H are different quantities with different units, even in vacuum.",
                    "B és H különböző mennyiségek különböző mértékegységgel, vákuumban is."),
        symbols=["B", "mu", "H"], assumptions=[_LINEAR],
    ),
    Equation(
        id="ohm_local", category="constitutive",
        name=L("Local Ohm's law", "Differenciális Ohm-törvény"),
        latex=r"\mathbf{J} = \sigma\mathbf{E}",
        meaning=L("Conduction current density in an ohmic isotropic conductor.",
                  "Vezetési áramsűrűség ohmos, izotrop vezetőben."),
        intuition=L("The field pushes charge carriers; conductivity says how easily they move.",
                    "A mező hajtja a töltéshordozókat; a vezetőképesség megadja, milyen könnyen "
                    "mozognak."),
        symbols=["J", "sigma", "E"],
        assumptions=[L("Ohmic, isotropic conductor.", "Ohmos, izotrop vezető.")],
    ),
    Equation(
        id="continuity", category="additional",
        name=L("Continuity equation", "Kontinuitási egyenlet"),
        latex=r"\nabla \cdot \mathbf{J} = -\frac{\partial \rho}{\partial t}",
        meaning=L("Charge conservation.", "Töltésmegmaradás."),
        intuition=L("Current flowing out of a region reduces the charge inside it.",
                    "Egy tartományból kifolyó áram csökkenti a benne lévő töltést."),
        symbols=["J", "rho", "t"],
    ),
    Equation(
        id="lorentz_force", category="additional",
        name=L("Lorentz force", "Lorentz-erő"),
        latex=r"\mathbf{F} = q(\mathbf{E} + \mathbf{v}\times\mathbf{B})",
        meaning=L("Force on a point charge moving in electric and magnetic fields.",
                  "Elektromos és mágneses mezőben mozgó ponttöltésre ható erő."),
        intuition=L("E pushes along the field; B pushes sideways and does no work.",
                    "E a mező irányában hat; B oldalirányban, és nem végez munkát."),
        symbols=["F", "q", "E", "v", "B"],
    ),
    Equation(
        id="poynting", category="additional",
        name=L("Poynting vector", "Poynting-vektor"),
        latex=r"\mathbf{S} = \mathbf{E}\times\mathbf{H}",
        meaning=L("Electromagnetic energy flux density.",
                  "Az elektromágneses energiaáram sűrűsége."),
        intuition=L("Energy flows perpendicular to both E and H — not along field lines.",
                    "Az energia E-re és H-ra egyaránt merőlegesen áramlik — nem az erővonalak "
                    "mentén."),
        symbols=["S", "E", "H"],
    ),
    Equation(
        id="energy_density", category="additional",
        name=L("Energy density", "Energiasűrűség"),
        latex=r"u = \tfrac{1}{2}(\mathbf{E}\cdot\mathbf{D} + \mathbf{B}\cdot\mathbf{H})",
        meaning=L("Energy stored in the electromagnetic field per unit volume.",
                  "Az elektromágneses mezőben tárolt energia térfogategységenként."),
        intuition=L("The field itself stores energy, most densely where it is strongest.",
                    "Maga a mező tárol energiát, ott a legsűrűbben, ahol a legerősebb."),
        symbols=["u", "E", "D", "B", "H"],
        assumptions=[L("Linear, nondispersive media.", "Lineáris, nem diszperzív közeg.")],
    ),
]
