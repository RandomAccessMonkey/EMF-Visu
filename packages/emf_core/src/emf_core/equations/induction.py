"""Phase 4A equations: prescribed time-dependent currents, the Coulomb-gauge vector potential,
the induced electric field, magnetic flux, Faraday's and Lenz's laws and mutual induction.

Appended to the one registry (``data.EQUATIONS`` / ``SYMBOLS`` and ``rules.RULES``); statuses
are derived from the model context like every other equation."""

from __future__ import annotations

from collections.abc import Callable

from ..i18n import L, LocalizedText
from ..solvers.base import ModelContext
from .models import Equation, EquationStatus, SymbolDef

Out = tuple[EquationStatus, LocalizedText | None]
OK: Out = ("applicable", None)

_MQS = L("Magnetoquasistatic: prescribed currents in fixed geometry, displacement current "
         "neglected, no retardation or radiation, no induced-current back-reaction.",
         "Magnetokvázisztatikus: előírt áramok rögzített geometriában, az eltolási áram "
         "elhanyagolva, nincs késleltetés vagy sugárzás, nincs indukált áram visszahatása.")
_FIXED = L("Stationary sources, surfaces and paths (no motional EMF v × B).",
           "Álló források, felületek és utak (nincs mozgási EMF, v × B).")
_LINEAR = L("Linear, time-independent magnetic response.",
            "Lineáris, időben állandó mágneses viselkedés.")

SYMBOLS: dict[str, SymbolDef] = {
    "It": SymbolDef(latex=r"I(t)", unit="A",
                    meaning=L("prescribed signed source current at time t",
                              "előírt, előjeles forrásáram a t időpontban")),
    "I0": SymbolDef(latex=r"I_0", unit="A", meaning=L("constant current", "állandó áram")),
    "Idc": SymbolDef(latex=r"I_{\text{dc}}", unit="A",
                     meaning=L("DC offset", "egyenáramú eltolás")),
    "Ipk": SymbolDef(latex=r"I_{\text{peak}}", unit="A",
                     meaning=L("peak amplitude", "csúcsamplitúdó")),
    "freq": SymbolDef(latex=r"f", unit="Hz", meaning=L("frequency", "frekvencia")),
    "phase": SymbolDef(latex=r"\varphi_0", unit="rad", meaning=L("phase", "fázis")),
    "slope": SymbolDef(latex=r"s", unit="A/s", meaning=L("ramp slope", "rámpa meredeksége")),
    "tk": SymbolDef(latex=r"t_k", unit="s",
                    meaning=L("keyframe time (ramp start for a ramp)",
                              "kulcspont időpontja (rámpánál a kezdete)")),
    "Ik": SymbolDef(latex=r"I_k", unit="A", meaning=L("keyframe current", "kulcsponti áram")),
    "dIdt": SymbolDef(latex=r"\frac{dI}{dt}", unit="A/s",
                      meaning=L("rate of change of the source current (analytical)",
                                "a forrásáram változási sebessége (analitikus)")),
    "Avec": SymbolDef(latex=r"\mathbf{A}", unit="T*m",
                      meaning=L("magnetic vector potential (Coulomb gauge, ∇·A = 0)",
                                "mágneses vektorpotenciál (Coulomb-mérték, ∇·A = 0)")),
    "Eind": SymbolDef(latex=r"\mathbf{E}_{\text{ind}}", unit="V/m",
                      meaning=L("induced (nonconservative) part of the electric field; not the "
                                "electrostatic field and not the complete field",
                                "az elektromos tér indukált (nem konzervatív) része; sem a "
                                "sztatikus, sem a teljes elektromos tér")),
    "Estat": SymbolDef(latex=r"\mathbf{E}_{\text{static}}", unit="V/m",
                       meaning=L("electrostatic field of the charges, −∇φ",
                                 "a töltések elektrosztatikus tere, −∇φ")),
    "emf": SymbolDef(latex=r"\mathcal{E}", unit="V",
                     meaning=L("electromotive force around the oriented closed path",
                               "elektromotoros erő az irányított zárt görbe mentén")),
    "nS": SymbolDef(latex=r"\hat{\mathbf{n}}", unit="1",
                    meaning=L("positive surface normal (right-hand rule with the boundary "
                              "traversal)",
                              "pozitív felületi normális (jobbkéz-szabály a határ "
                              "bejárásával)")),
    "M12": SymbolDef(latex=r"M_{12}", unit="H",
                     meaning=L("mutual inductance: flux through loop 2 per ampere in loop 1",
                               "kölcsönös induktivitás: a 2. hurkon átmenő fluxus az 1. hurok "
                               "egységnyi áramára")),
    "M21": SymbolDef(latex=r"M_{21}", unit="H",
                     meaning=L("mutual inductance with the roles exchanged",
                               "kölcsönös induktivitás felcserélt szerepekkel")),
    "Phi21": SymbolDef(latex=r"\Phi_{21}", unit="Wb",
                       meaning=L("flux through loop 2 due to loop 1",
                                 "az 1. hurok által a 2. hurkon átmenő fluxus")),
    "I1": SymbolDef(latex=r"I_1", unit="A", meaning=L("current of loop 1", "az 1. hurok árama")),
}


def _eq(**kw: object) -> Equation:
    return Equation.model_validate({"category": "induction", **kw})


EQUATIONS: list[Equation] = [
    _eq(id="current_constant", name=L("Constant current profile", "Állandó áramprofil"),
        latex=r"I(t) = I_0,\qquad \frac{dI}{dt} = 0",
        meaning=L("A steady current: its field does not change and induces nothing.",
                  "Állandó áram: a tere nem változik, és nem indukál semmit."),
        intuition=L("Only a changing current induces.", "Csak a változó áram indukál."),
        symbols=["It", "I0", "dIdt", "t"]),
    _eq(id="current_sinusoidal", name=L("Sinusoidal current profile", "Szinuszos áramprofil"),
        latex=r"I(t) = I_{\text{dc}} + I_{\text{peak}}\sin(2\pi f t + \varphi_0),\qquad "
              r"\frac{dI}{dt} = 2\pi f I_{\text{peak}}\cos(2\pi f t + \varphi_0)",
        meaning=L("The derivative is a quarter period ahead: it is largest when the current "
                  "crosses its mean and zero at the current's peaks.",
                  "A derivált negyed periódussal előrébb jár: akkor a legnagyobb, amikor az "
                  "áram az átlagán halad át, és nulla az áram csúcsainál."),
        intuition=L("The induced EMF follows dI/dt, not I.", "Az indukált EMF dI/dt-t követi, "
                    "nem I-t."),
        symbols=["It", "Idc", "Ipk", "freq", "phase", "dIdt", "t"]),
    _eq(id="current_ramp", name=L("Linear ramp profile", "Lineáris rámpa áramprofil"),
        latex=r"I(t) = I_{\text{start}} + s\,(t - t_{\text{start}})\ \ "
              r"(t_{\text{start}} \le t \le t_{\text{end}}),\qquad \frac{dI}{dt} = s",
        meaning=L("Held at the start value before the ramp and at the end value after it (never "
                  "extrapolated); dI/dt = 0 outside, and jumps at both ends.",
                  "A rámpa előtt a kezdőértéken, utána a végértéken marad (nem extrapolálunk); "
                  "kívül dI/dt = 0, a két végén ugrik."),
        intuition=L("A constant slope gives a constant induced EMF during the ramp.",
                    "Állandó meredekség a rámpa alatt állandó indukált EMF-et ad."),
        symbols=["It", "slope", "tk", "dIdt", "t"],
        conditions=[L("At the ends of the ramp the left and right derivatives differ; the "
                      "application reports both and uses the right-hand one.",
                      "A rámpa végein a bal és jobb oldali derivált eltér; az alkalmazás "
                      "mindkettőt megadja, és a jobb oldalit használja.")]),
    _eq(id="current_piecewise", name=L("Piecewise-linear profile", "Szakaszonként lineáris "
                                       "áramprofil"),
        latex=r"I(t) = I_k + \frac{I_{k+1} - I_k}{t_{k+1} - t_k}(t - t_k),\qquad "
              r"\frac{dI}{dt} = \frac{I_{k+1} - I_k}{t_{k+1} - t_k}\ \ (t_k < t < t_{k+1})",
        meaning=L("Linear between keyframes; the first and last values are held outside; at a "
                  "keyframe dI/dt is not uniquely defined.",
                  "A kulcspontok között lineáris; azokon kívül az első és utolsó érték marad; "
                  "egy kulcspontban dI/dt nem egyértelmű."),
        intuition=L("Each segment induces a constant EMF; the EMF jumps at the keyframes.",
                    "Minden szakasz állandó EMF-et indukál; az EMF a kulcspontokban ugrik."),
        symbols=["It", "Ik", "tk", "dIdt", "t"]),
    _eq(id="vector_potential_coulomb", name=L("Vector potential of a closed current "
                                              "(Coulomb gauge)",
                                              "Zárt áram vektorpotenciálja (Coulomb-mérték)"),
        latex=r"\mathbf{A}(\mathbf{r},t) = \frac{\mu_0 I(t)}{4\pi}\oint_C "
              r"\frac{d\boldsymbol{\ell}'}{|\mathbf{r}-\mathbf{r}'|},\qquad "
              r"\nabla\cdot\mathbf{A} = 0",
        meaning=L("For a closed filament this A satisfies ∇·A = 0 (Coulomb gauge) and "
                  "∇×A = B. For a circular loop it is azimuthal and given by elliptic integrals.",
                  "Zárt áramszálra ez az A teljesíti a ∇·A = 0 feltételt (Coulomb-mérték) és "
                  "∇×A = B-t. Körvezetőre azimutális, elliptikus integrálokkal adható meg."),
        intuition=L("A runs along the current, strongest near the wire.",
                    "A az árammal párhuzamos, a vezető közelében a legerősebb."),
        symbols=["Avec", "mu0", "It", "dl", "r", "rprime"], assumptions=[_MQS, _FIXED],
        limitations=[L("Implemented for closed circular filaments (loops, solenoid and "
                       "finite-toroid turns); not for infinite wires or the ideal toroid.",
                       "Zárt kör alakú áramszálakra megvalósítva (hurkok, szolenoid és véges "
                       "toroid menetei); végtelen vezetőre és ideális toroidra nem.")]),
    _eq(id="curl_a_b", name=L("Magnetic field from the vector potential",
                              "Mágneses tér a vektorpotenciálból"),
        latex=r"\mathbf{B} = \nabla \times \mathbf{A}",
        meaning=L("B is the curl of A; checked in the tests by finite differences of A against "
                  "the solver's B.",
                  "B az A rotációja; a tesztekben A véges differenciáival ellenőrizve a megoldó "
                  "B-jével szemben."),
        intuition=L("Circulation of A around a loop equals the flux through it (Stokes).",
                    "A körintegrálja egy hurok mentén a rajta átmenő fluxus (Stokes)."),
        symbols=["B", "Avec"]),
    _eq(id="e_ind_from_a", name=L("Induced electric field", "Indukált elektromos tér"),
        latex=r"\mathbf{E}_{\text{ind}} = -\frac{\partial \mathbf{A}}{\partial t} = "
              r"-\frac{\mu_0}{4\pi}\sum_j \frac{dI_j}{dt}\oint_{C_j}"
              r"\frac{d\boldsymbol{\ell}'}{|\mathbf{r}-\mathbf{r}'|}",
        meaning=L("The nonconservative electric field produced by changing currents in fixed "
                  "geometry. It is not the electrostatic field of charges and not the complete "
                  "electric field, which would also need the scalar potential of any charges.",
                  "Rögzített geometriájú, változó áramok által keltett nem konzervatív "
                  "elektromos tér. Nem a töltések elektrosztatikus tere, és nem a teljes "
                  "elektromos tér, amelyhez a töltések skalárpotenciálja is kellene."),
        intuition=L("It circulates around the changing flux, against the change (Lenz).",
                    "A változó fluxus körül kering, a változással szemben (Lenz)."),
        symbols=["Eind", "Avec", "t", "mu0", "dIdt", "dl"], assumptions=[_MQS, _FIXED, _LINEAR]),
    _eq(id="e_decomposition", name=L("Electrostatic and induced electric field",
                                     "Elektrosztatikus és indukált elektromos tér"),
        latex=r"\mathbf{E} = \underbrace{-\nabla\varphi}_{\mathbf{E}_{\text{static}}}"
              r"\;\underbrace{-\,\partial \mathbf{A}/\partial t}_{\mathbf{E}_{\text{ind}}}",
        meaning=L("In the Coulomb gauge the electric field splits into a conservative part from "
                  "the charges and an induced part from changing currents. The application "
                  "computes the two separately and never adds them into one 'complete' field: "
                  "a time-dependent system's φ (charge redistribution) is not modelled.",
                  "Coulomb-mértékben az elektromos tér a töltésekből származó konzervatív és a "
                  "változó áramokból származó indukált részre bomlik. Az alkalmazás a kettőt "
                  "külön számítja, és nem adja össze egy 'teljes' térré: időfüggő rendszer φ-je "
                  "(töltés-átrendeződés) nincs modellezve."),
        intuition=L("Static charges: closed field lines never. Induction: closed lines possible.",
                    "Sztatikus töltések: soha nincs zárt erővonal. Indukció: lehet zárt."),
        symbols=["E", "Estat", "Eind", "phi", "Avec"], assumptions=[_MQS]),
    _eq(id="faraday_differential", name=L("Faraday's law for the induced field",
                                          "Faraday-törvény az indukált térre"),
        latex=r"\nabla \times \mathbf{E}_{\text{ind}} = -\frac{\partial \mathbf{B}}{\partial t}",
        meaning=L("Follows from E_ind = −∂A/∂t and B = ∇×A; checked in the tests by finite "
                  "differences of E_ind against the solver's ∂B/∂t.",
                  "E_ind = −∂A/∂t és B = ∇×A következménye; a tesztekben E_ind véges "
                  "differenciáival ellenőrizve a megoldó ∂B/∂t-jével szemben."),
        intuition=L("Where B changes, E_ind curls around it.", "Ahol B változik, E_ind örvénylik "
                    "körülötte."),
        symbols=["Eind", "B", "t"], assumptions=[_MQS, _FIXED]),
    _eq(id="magnetic_flux", name=L("Magnetic flux", "Mágneses fluxus"),
        latex=r"\Phi_B(t) = \int_S \mathbf{B}(\mathbf{r},t)\cdot\hat{\mathbf{n}}\,dA",
        meaning=L("Signed flux through the oriented surface; reversing the normal reverses the "
                  "sign. Computed by adaptive surface quadrature.",
                  "Előjeles fluxus az irányított felületen át; a normális megfordítása az "
                  "előjelet is megfordítja. Adaptív felületi kvadratúrával számítva."),
        intuition=L("How much B threads the surface, counted along n̂.",
                    "Mennyi B halad át a felületen, n̂ irányában számolva."),
        symbols=["PhiB", "B", "nS", "dA"]),
    _eq(id="flux_derivative", name=L("Rate of change of the flux", "A fluxus változási "
                                     "sebessége"),
        latex=r"\frac{d\Phi_B}{dt} = \int_S \frac{\partial \mathbf{B}}{\partial t}\cdot"
              r"\hat{\mathbf{n}}\,dA = \sum_j \frac{dI_j}{dt}\,\Phi_{j,1\,\mathrm{A}}",
        meaning=L("For a fixed surface and linear sources: each source's flux per ampere times "
                  "its analytical dI/dt (never a difference of two flux samples).",
                  "Rögzített felületre és lineáris forrásokra: minden forrás egységnyi áramra "
                  "jutó fluxusa szorozva analitikus dI/dt-jével (nem két fluxusminta "
                  "különbsége)."),
        intuition=L("Static sources contribute flux but no change.",
                    "Az állandó források fluxust adnak, változást nem."),
        symbols=["PhiB", "t", "B", "nS", "dA", "dIdt"], assumptions=[_FIXED, _LINEAR]),
    _eq(id="faraday_integral", name=L("Faraday's law (integral form)",
                                      "Faraday-törvény (integrális alak)"),
        latex=r"\mathcal{E} = \oint_{\partial S}\mathbf{E}_{\text{ind}}\cdot d\boldsymbol{\ell} = "
              r"-\frac{d\Phi_B}{dt}",
        meaning=L("The EMF around the boundary equals minus the rate of change of the flux "
                  "through the surface, with the boundary traversed counter-clockwise about the "
                  "surface normal.",
                  "A határ menti EMF egyenlő a felületen átmenő fluxus változási sebességének "
                  "mínusz egyszeresével; a határt a felületi normális körül az óramutatóval "
                  "ellentétesen járjuk be."),
        intuition=L("Checked: the line integral of E_ind and the surface integral of ∂B/∂t are "
                    "computed independently and compared.",
                    "Ellenőrizve: E_ind vonalintegrálját és ∂B/∂t felületi integrálját "
                    "egymástól függetlenül számítjuk és összevetjük."),
        symbols=["emf", "Eind", "dl", "PhiB", "t"], assumptions=[_MQS, _FIXED]),
    _eq(id="lenz_law", name=L("Lenz's law", "Lenz-törvény"),
        latex=r"\mathcal{E} = -\frac{d\Phi_B}{dt}",
        meaning=L("The minus sign: the induced EMF drives circulation that opposes the change "
                  "of flux, not the flux itself. Increasing flux along n̂ gives an EMF circulating "
                  "clockwise about n̂ (against the traversal).",
                  "A mínusz előjel: az indukált EMF a fluxus változásával, nem magával a "
                  "fluxussal szemben hat. n̂ irányban növekvő fluxus n̂ körül az óramutató "
                  "járásával megegyező (a bejárással ellentétes) EMF-et ad."),
        intuition=L("No closed circuit is modelled, so no induced current is shown: only the "
                    "EMF and E_ind.",
                    "Zárt áramkör nincs modellezve, ezért indukált áram sem látható: csak az EMF "
                    "és E_ind."),
        symbols=["emf", "PhiB", "t", "nS"]),
    _eq(id="mutual_inductance", name=L("Mutual inductance", "Kölcsönös induktivitás"),
        latex=r"M_{12} = \frac{\Phi_{21}}{I_1},\qquad \mathcal{E}_2 = -M_{12}\frac{dI_1}{dt}",
        meaning=L("For fixed geometry and linear media the flux through loop 2 is proportional "
                  "to the current of loop 1; computed per ampere, so independent of the current "
                  "amplitude.",
                  "Rögzített geometria és lineáris közeg esetén a 2. hurkon átmenő fluxus "
                  "arányos az 1. hurok áramával; egységnyi áramra számítva, így független az "
                  "áram amplitúdójától."),
        intuition=L("A measurement relation: no current is assumed to flow in loop 2.",
                    "Mérési összefüggés: a 2. hurokban nem feltételezünk áramot."),
        symbols=["M12", "Phi21", "I1", "emf", "dIdt"], assumptions=[_FIXED, _LINEAR]),
    _eq(id="mutual_reciprocity", name=L("Reciprocity of mutual inductance", "A kölcsönös "
                                        "induktivitás reciprocitása"),
        latex=r"M_{12} = M_{21} = \frac{\mu_0}{4\pi}\oint_{C_1}\oint_{C_2}"
              r"\frac{d\boldsymbol{\ell}_1\cdot d\boldsymbol{\ell}_2}{|\mathbf{r}_1-\mathbf{r}_2|}",
        meaning=L("Neumann's formula is symmetric; checked by computing the flux both ways with "
                  "different surfaces and fields.",
                  "A Neumann-képlet szimmetrikus; a fluxust mindkét irányban, különböző "
                  "felületekkel és terekkel számítva ellenőrizzük."),
        intuition=L("Coil 1 links coil 2 exactly as much as coil 2 links coil 1.",
                    "Az 1. tekercs pontosan annyira kapcsolódik a 2.-hoz, mint a 2. az 1.-hez."),
        symbols=["M12", "M21", "mu0", "dl"], assumptions=[_FIXED, _LINEAR]),
    _eq(id="magnetoquasistatic", name=L("Magnetoquasistatic approximation",
                                        "Magnetokvázisztatikus közelítés"),
        latex=r"\nabla\times\mathbf{H} \approx \mathbf{J},\qquad \frac{L}{c\,\tau} \ll 1",
        meaning=L("The displacement current is neglected: valid when the region L is small "
                  "compared with c times the time scale τ of the currents (1/f for a sinusoid). "
                  "The application warns when L/(cτ) > 0.01.",
                  "Az eltolási áramot elhanyagoljuk: érvényes, ha az L tartomány kicsi az "
                  "áramok τ időskálájának c-szereséhez képest (szinusznál 1/f). Az alkalmazás "
                  "figyelmeztet, ha L/(cτ) > 0,01."),
        intuition=L("Fields follow the currents instantly: no waves.",
                    "A terek azonnal követik az áramokat: nincsenek hullámok."),
        symbols=["H", "J", "t"], idealized=True),
]


def _need_time(c: ModelContext) -> Out | None:
    if not c.computes_magnetic_field:
        return ("not_evaluated", L("No magnetic sub-model in this scene.",
                                   "A jelenetben nincs mágneses részmodell."))
    if not c.time_varying:
        return ("not_applicable", L("No source has a time-dependent current profile.",
                                    "Egyik forrásnak sincs időfüggő áramprofilja."))
    return None


def _profile(kind: str) -> Callable[[ModelContext], Out]:
    def rule(c: ModelContext) -> Out:
        if not c.computes_magnetic_field:
            return ("not_evaluated", L("No current sources.", "Nincsenek áramforrások."))
        if kind not in c.profile_types:
            return ("not_applicable", L("No source uses this profile.",
                                        "Egyik forrás sem használja ezt a profilt."))
        return OK
    return rule


def _time(c: ModelContext) -> Out:
    return _need_time(c) or OK


def _induced(c: ModelContext) -> Out:
    pre = _need_time(c)
    if pre is not None:
        return pre
    if not c.e_ind_available:
        return ("not_evaluated", L("A source without a vector potential (infinite wire or "
                                   "ideal toroid) changes in time: E_ind is not evaluated.",
                                   "Vektorpotenciál nélküli forrás (végtelen vezető vagy "
                                   "ideális toroid) változik: E_ind nincs kiértékelve."))
    return ("applicable_under_assumptions", L("Magnetoquasistatic model, fixed geometry.",
                                              "Magnetokvázisztatikus modell, rögzített "
                                              "geometria."))


def _vector_potential(c: ModelContext) -> Out:
    if not c.computes_magnetic_field:
        return ("not_evaluated", L("No current sources.", "Nincsenek áramforrások."))
    if not any(k in c.current_source_kinds for k in ("circular_loop", "solenoid",
                                                      "toroid_finite")):
        return ("not_applicable", L("No closed circular current in the scene.",
                                    "A jelenetben nincs zárt kör alakú áram."))
    return OK


def _flux(c: ModelContext) -> Out:
    if not c.computes_magnetic_field:
        return ("not_evaluated", L("No magnetic sub-model.", "Nincs mágneses részmodell."))
    if c.flux_surfaces == 0:
        return ("applicable_under_assumptions", L("Add a measurement surface to compute it.",
                                                  "Számításához adjon hozzá mérőfelületet."))
    return OK


def _faraday_integral(c: ModelContext) -> Out:
    pre = _need_time(c)
    if pre is not None and pre[0] == "not_evaluated":
        return pre
    if c.flux_surfaces == 0:
        return ("applicable_under_assumptions", L("Add a measurement surface to check it.",
                                                  "Ellenőrzéséhez adjon hozzá mérőfelületet."))
    return OK


def _mqs(c: ModelContext) -> Out:
    pre = _need_time(c)
    return pre or ("applicable_under_assumptions", L(
        "Valid while the region is small compared with c × the time scale of the currents.",
        "Érvényes, amíg a tartomány kicsi a c × áram-időskálához képest."))


RULES = {
    "current_constant": _profile("constant"),
    "current_sinusoidal": _profile("sinusoidal"),
    "current_ramp": _profile("ramp"),
    "current_piecewise": _profile("piecewise_linear"),
    "vector_potential_coulomb": _vector_potential,
    "curl_a_b": _vector_potential,
    "e_ind_from_a": _induced,
    "e_decomposition": _induced,
    "faraday_differential": _induced,
    "magnetic_flux": _flux,
    "flux_derivative": _time,
    "faraday_integral": _faraday_integral,
    "lenz_law": _time,
    "mutual_inductance": _flux,
    "mutual_reciprocity": _flux,
    "magnetoquasistatic": _mqs,
}
