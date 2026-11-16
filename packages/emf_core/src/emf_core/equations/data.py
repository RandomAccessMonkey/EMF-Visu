"""Equation and symbol tables. Add a new equation here and a rule in ``rules.py``."""

from __future__ import annotations

from ..i18n import L
from .models import Equation, SymbolDef

PC = "analytical.electrostatics.point_charges"

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
    "t": SymbolDef(latex=r"t", unit="s", meaning=L("time", "idő")),
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
        intuition=L("Magnetic field lines never begin or end.",
                    "A mágneses erővonalaknak nincs kezdetük és végük."),
        symbols=["B"],
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
                       "Gyorsan változó áramoknál az időfüggő hatásokat figyelembe kell venni.")],
    ),
    Equation(
        id="biot_savart", category="magnetostatics",
        name=L("Biot–Savart law", "Biot–Savart-törvény"),
        latex=r"d\mathbf{B} = \frac{\mu_0}{4\pi}\,\frac{I\,(d\boldsymbol{\ell}\times\hat{\mathbf{r}})}{r^2}",
        meaning=L("Magnetic field contribution of a current element.",
                  "Egy áramelem járuléka a mágneses mezőhöz."),
        intuition=L("Each piece of wire contributes a field that circles around its direction.",
                    "A vezető minden darabja a saját iránya körül örvénylő mezőt hoz létre."),
        symbols=["B", "mu0", "I", "dl", "rhat"],
        assumptions=[L("Steady current in vacuum (or a non-magnetic medium).",
                       "Stacionárius áram vákuumban (vagy nem mágneses közegben).")],
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
