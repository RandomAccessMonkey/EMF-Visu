"""Phase 4C equations: passive circuits with induced currents (resistance, self- and mutual
inductance, the coupled circuit equations), magnetic forces on current-carrying conductors,
the dynamic sliding rod, energy accounting and the annular-band eddy-current approximation.

Appended to the one registry (``data.EQUATIONS`` / ``SYMBOLS`` and ``rules.RULES``)."""

from __future__ import annotations

from ..i18n import L, LocalizedText
from ..solvers.base import ModelContext
from .models import Equation, EquationStatus, SymbolDef

Out = tuple[EquationStatus, LocalizedText | None]
OK: Out = ("applicable", None)

_PASSIVE = L("Passive circuit: no applied voltage; the current is driven only by the change of "
             "its flux linkage (prescribed sources, motion, other passive circuits).",
             "Passzív áramkör: nincs külső feszültség; az áramot csak a fluxuskapcsolódás "
             "változása hajtja (előírt források, mozgás, más passzív áramkörök).")
_LUMPED = L("Lumped thin conductors: uniform current, no skin effect, constant conductivity "
            "(room-temperature value, no heating feedback).",
            "Koncentrált vékony vezetők: egyenletes áram, nincs szkinhatás, állandó "
            "vezetőképesség (szobahőmérsékleti érték, a melegedés nem hat vissza).")
_MQS = L("Magnetoquasistatic: no displacement current, retardation or radiation.",
         "Magnetokvázisztatikus: nincs eltolási áram, késleltetés vagy sugárzás.")
_BAND = L("Reduced-order axisymmetric approximation: concentric annular bands, each a circular "
          "loop at its mid-radius; not a continuous eddy-current solution.",
          "Redukált rendű, tengelyszimmetrikus közelítés: koncentrikus körgyűrű-sávok, mind egy "
          "középsugarú kör alakú hurok; nem folytonos örvényáram-megoldás.")

SYMBOLS: dict[str, SymbolDef] = {
    "Rres": SymbolDef(latex=r"R", unit="ohm", meaning=L("resistance", "ellenállás")),
    "rho_e": SymbolDef(latex=r"\rho_e", unit="ohm*m", meaning=L("resistivity", "fajlagos "
                                                                 "ellenállás")),
    "sigma_c": SymbolDef(latex=r"\sigma", unit="S/m", meaning=L("conductivity",
                                                                "vezetőképesség")),
    "ell": SymbolDef(latex=r"\ell", unit="m", meaning=L("conductor length", "vezetőhossz")),
    "Acs": SymbolDef(latex=r"A", unit="m^2", meaning=L("conductor cross-section",
                                                       "vezető-keresztmetszet")),
    "Lself": SymbolDef(latex=r"\mathcal{L}", unit="H",
                       meaning=L("self-inductance (finite only for a conductor of finite "
                                 "cross-section)",
                                 "önindukció (csak véges keresztmetszetű vezetőre véges)")),
    "r_w": SymbolDef(latex=r"r_w", unit="m", meaning=L("wire radius", "huzalsugár")),
    "Lmat": SymbolDef(latex=r"\mathbf{L}", unit="H",
                      meaning=L("inductance matrix: L_ii self-inductances, L_ij mutual "
                                "inductances", "induktivitásmátrix: L_ii önindukciók, L_ij "
                                "kölcsönös induktivitások")),
    "Mij": SymbolDef(latex=r"M_{ij}", unit="H",
                     meaning=L("mutual inductance: flux through circuit i per ampere in j",
                               "kölcsönös induktivitás: az i áramkörön átmenő fluxus a j "
                               "egységnyi áramára")),
    "Iind": SymbolDef(latex=r"I_i", unit="A",
                      meaning=L("induced current of passive circuit i (solved, never prescribed)",
                                "az i passzív áramkör indukált árama (megoldott, nem előírt)")),
    "lam": SymbolDef(latex=r"\lambda_i", unit="Wb", meaning=L("total flux linkage",
                                                             "teljes fluxuskapcsolódás")),
    "Phiext": SymbolDef(latex=r"\Phi_{i,\text{ext}}", unit="Wb",
                        meaning=L("flux linkage from the prescribed sources",
                                  "az előírt forrásokból eredő fluxuskapcsolódás")),
    "Vapp": SymbolDef(latex=r"V_{\text{applied}}", unit="V",
                      meaning=L("applied voltage (zero for passive circuits)",
                                "külső feszültség (passzív áramkörnél nulla)")),
    "Wm": SymbolDef(latex=r"W_m", unit="J", meaning=L("magnetic energy of the passive circuits",
                                                     "a passzív áramkörök mágneses energiája")),
    "PR": SymbolDef(latex=r"P_R", unit="W",
                    meaning=L("Joule heating power", "Joule-hőteljesítmény")),
    "QR": SymbolDef(latex=r"Q_R", unit="J", meaning=L("accumulated Joule heat", "felhalmozott "
                                                      "Joule-hő")),
    "Fem": SymbolDef(latex=r"\mathbf{F}_{\text{em}}", unit="N",
                     meaning=L("electromagnetic force on the conductor", "a vezetőre ható "
                               "elektromágneses erő")),
    "Bext": SymbolDef(latex=r"\mathbf{B}_{\text{ext}}", unit="T",
                      meaning=L("field of every source except the conductor's own filament",
                                "minden forrás tere a vezető saját áramszálán kívül")),
    "tau": SymbolDef(latex=r"\boldsymbol{\tau}", unit="N*m",
                     meaning=L("torque", "forgatónyomaték")),
    "mmech": SymbolDef(latex=r"m", unit="kg", meaning=L("moving mass", "mozgó tömeg")),
    "bdamp": SymbolDef(latex=r"b", unit="N*s/m", meaning=L("viscous damping", "viszkózus "
                                                           "csillapítás")),
    "Jmech": SymbolDef(latex=r"J", unit="kg*m^2", meaning=L("moment of inertia",
                                                            "tehetetlenségi nyomaték")),
    "xpos": SymbolDef(latex=r"x", unit="m", meaning=L("rod position", "rúd helye")),
    "Pmech": SymbolDef(latex=r"P_{\text{mech}}", unit="W",
                       meaning=L("power delivered by the EM force to the motion",
                                 "az EM erő által a mozgásnak átadott teljesítmény")),
    "tband": SymbolDef(latex=r"t", unit="m", meaning=L("disk thickness", "korongvastagság")),
    "drk": SymbolDef(latex=r"\Delta r_k", unit="m", meaning=L("band width", "sávszélesség")),
    "rk": SymbolDef(latex=r"r_k", unit="m", meaning=L("band mid-radius", "sáv középsugara")),
    "Jphi": SymbolDef(latex=r"J_{\varphi,k}", unit="A/m^2",
                      meaning=L("approximate azimuthal current density of band k",
                                "a k. sáv közelítő azimutális áramsűrűsége")),
}


def _eq(**kw: object) -> Equation:
    return Equation.model_validate({"category": "circuits", **kw})


EQUATIONS: list[Equation] = [
    _eq(id="resistance_rho", name=L("Resistance from resistivity", "Ellenállás a fajlagos "
                                    "ellenállásból"),
        latex=r"R = \rho_e \frac{\ell}{A}",
        meaning=L("ℓ is computed from the actual circuit geometry (× turns).",
                  "ℓ a tényleges áramköri geometriából adódik (× menetszám)."),
        intuition=L("Longer and thinner conductors resist more.", "Hosszabb, vékonyabb vezető "
                    "nagyobb ellenállású."),
        symbols=["Rres", "rho_e", "ell", "Acs"], assumptions=[_LUMPED]),
    _eq(id="resistance_sigma", name=L("Resistance from conductivity", "Ellenállás a "
                                      "vezetőképességből"),
        latex=r"R = \frac{\ell}{\sigma A},\qquad \sigma = 1/\rho_e",
        meaning=L("Material presets: copper 5.8×10⁷, aluminium 3.5×10⁷, silver 6.3×10⁷ S/m "
                  "(nominal room-temperature values).",
                  "Anyagok: réz 5,8×10⁷, alumínium 3,5×10⁷, ezüst 6,3×10⁷ S/m (névleges "
                  "szobahőmérsékleti értékek)."),
        intuition=L("Better conductors give smaller R and larger induced currents.",
                    "Jobb vezető kisebb R-t és nagyobb indukált áramot ad."),
        symbols=["Rres", "ell", "sigma_c", "Acs"], assumptions=[_LUMPED]),
    _eq(id="thin_loop_inductance", name=L("Self-inductance of a thin circular loop",
                                          "Vékony körhurok önindukciója"),
        latex=r"\mathcal{L} \approx \mu_0 a\left[\ln\frac{8a}{r_w} - 2\right]",
        meaning=L("Valid for r_w ≪ a (applied only for r_w/a ≤ 0.1), current on the wire "
                  "surface (internal inductance μ₀a/4 of a uniform current not included). An "
                  "ideal filament (r_w → 0) has infinite self-inductance.",
                  "r_w ≪ a esetén érvényes (csak r_w/a ≤ 0,1-re alkalmazva), áram a huzal "
                  "felületén (egyenletes áram μ₀a/4 belső induktivitása nincs benne). Ideális "
                  "áramszál (r_w → 0) önindukciója végtelen."),
        intuition=L("Thinner wire, more self-inductance (logarithmically).",
                    "Vékonyabb huzal, nagyobb önindukció (logaritmikusan)."),
        symbols=["Lself", "mu0", "a_loop", "r_w"], idealized=True,
        limitations=[L("Circular loops only; rectangles and polygons need a user value.",
                       "Csak kör alakú hurokra; téglalaphoz és sokszöghöz felhasználói érték "
                       "kell.")]),
    _eq(id="self_magnetic_energy", name=L("Magnetic energy of one circuit", "Egy áramkör mágneses "
                                          "energiája"),
        latex=r"W_m = \tfrac12 \mathcal{L} I^2",
        meaning=L("Energy stored in the circuit's own field.", "Az áramkör saját terében tárolt "
                  "energia."),
        intuition=L("Inductance resists change of current by storing energy.",
                    "Az induktivitás energiatárolással ellenáll az áramváltozásnak."),
        symbols=["Wm", "Lself", "Iind"]),
    _eq(id="mutual_inductance_passive", name=L("Mutual inductance of passive circuits",
                                               "Passzív áramkörök kölcsönös induktivitása"),
        latex=r"M_{ij} = \frac{\Phi_{ij}}{I_j},\qquad M_{ij} = M_{ji}",
        meaning=L("Maxwell's closed form for coaxial circles; otherwise surface quadrature of "
                  "one circuit's field through the other (computed both ways where possible: "
                  "reciprocity checked, the matrix rejected if it fails).",
                  "Koaxiális körökre Maxwell zárt képlete; egyébként az egyik áramkör terének "
                  "felületi kvadratúrája a másikon át (ahol lehet, mindkét irányban: a "
                  "reciprocitás ellenőrizve, sikertelenség esetén a mátrix elutasítva)."),
        intuition=L("How strongly one circuit's current threads the other.",
                    "Mennyire fűzi át az egyik áramkör árama a másikat."),
        symbols=["Mij", "Iind"]),
    _eq(id="inductance_matrix", name=L("Inductance matrix and magnetic energy",
                                       "Induktivitásmátrix és mágneses energia"),
        latex=r"W_m = \tfrac12 \mathbf{I}^{\mathsf T}\mathbf{L}\,\mathbf{I} > 0",
        meaning=L("L must be symmetric and positive definite (positive magnetic energy); a "
                  "nonphysical matrix is rejected, never adjusted.",
                  "L-nek szimmetrikusnak és pozitív definitnek kell lennie (pozitív mágneses "
                  "energia); a nem fizikai mátrixot elutasítjuk, sosem igazítjuk."),
        intuition=L("Coupled circuits share stored energy.", "A csatolt áramkörök közösen "
                    "tárolnak energiát."),
        symbols=["Wm", "Lmat", "Iind"]),
    _eq(id="circuit_voltage_equation", name=L("Circuit equation", "Áramköri egyenlet"),
        latex=r"V_{i,\text{applied}} = R_i I_i + \frac{d\lambda_i}{dt}",
        meaning=L("The voltage law of a circuit with flux linkage λ_i. Passive circuits here have "
                  "V_applied = 0.",
                  "Fluxuskapcsolódással rendelkező áramkör feszültségtörvénye. Itt a passzív "
                  "áramkörökre V_applied = 0."),
        intuition=L("Resistive drop plus the change of linked flux.", "Ohmos esés plusz a "
                    "kapcsolt fluxus változása."),
        symbols=["Vapp", "Rres", "Iind", "lam", "t"], assumptions=[_MQS, _LUMPED]),
    _eq(id="flux_linkage", name=L("Total flux linkage", "Teljes fluxuskapcsolódás"),
        latex=r"\lambda_i = \Phi_{i,\text{ext}} + \sum_j L_{ij} I_j",
        meaning=L("External (prescribed) flux plus the self and mutual contributions of the "
                  "passive currents; the own singular filament field is represented by ℒ_i I_i.",
                  "Külső (előírt) fluxus plusz a passzív áramok saját és kölcsönös járulékai; a "
                  "saját szinguláris áramszál terét ℒ_i I_i képviseli."),
        intuition=L("Everything that threads the circuit.", "Minden, ami az áramkört átfűzi."),
        symbols=["lam", "Phiext", "Lmat", "Iind"]),
    _eq(id="passive_loop_equation", name=L("Passive circuit equation", "Passzív áramkör "
                                           "egyenlete"),
        latex=r"\mathbf{L}\frac{d\mathbf{I}}{dt} = -\mathbf{R}\mathbf{I} - "
              r"\frac{d\boldsymbol{\Phi}_{\text{ext}}}{dt} - \frac{d\mathbf{L}}{dt}\mathbf{I}",
        meaning=L("Solved with an implicit adaptive Radau method. dΦ_ext/dt = transformer part "
                  "(analytical dI_s/dt) − motional EMF ∮(u × B)·dl, each counted once; dL/dt "
                  "only for circuits moving relative to each other.",
                  "Implicit adaptív Radau-módszerrel megoldva. dΦ_ext/dt = transzformátor-rész "
                  "(analitikus dI_s/dt) − mozgási EMF ∮(u × B)·dl, mindegyik egyszer számolva; "
                  "dL/dt csak egymáshoz képest mozgó áramköröknél."),
        intuition=L("The induced current opposes every change of linked flux.",
                    "Az indukált áram minden fluxusváltozással szembeszáll."),
        symbols=["Lmat", "Iind", "t", "Rres", "Phiext"], assumptions=[_PASSIVE, _MQS, _LUMPED]),
    _eq(id="fixed_rl_equation", name=L("Single fixed RL loop", "Egyetlen rögzített RL hurok"),
        latex=r"\mathcal{L}\frac{dI}{dt} + R I = -\frac{d\Phi_{\text{ext}}}{dt},\quad "
              r"I(t) = -\frac{1}{R}\frac{d\Phi_{\text{ext}}}{dt}\left(1 - e^{-Rt/\mathcal{L}}"
              r"\right)",
        meaning=L("For a constant flux rate from I = 0; after the rate stops the current decays "
                  "with τ = ℒ/R.",
                  "Állandó fluxusváltozásra I = 0-ból; a változás megszűnése után az áram "
                  "τ = ℒ/R időállandóval lecseng."),
        intuition=L("A shorted loop first lags, then follows −(1/R) dΦ/dt.",
                    "A rövidre zárt hurok előbb késik, majd −(1/R) dΦ/dt-t követi."),
        symbols=["Lself", "Iind", "t", "Rres", "Phiext"], assumptions=[_PASSIVE]),
    _eq(id="lenz_passive", name=L("Lenz's law with a passive current", "Lenz-törvény passzív "
                                  "árammal"),
        latex=r"\operatorname{sign}\!\left(\Phi_{\text{induced}}\right) = "
              r"-\operatorname{sign}\!\left(\frac{d\Phi_{\text{ext}}}{dt}\right)\ "
              r"\text{(resistive regime)}",
        meaning=L("Shown by the computed current direction and its own field, which opposes the "
                  "change of the external flux.",
                  "A kiszámított áramirány és annak saját tere mutatja, amely a külső fluxus "
                  "változásával szembeszáll."),
        intuition=L("Nature dislikes changes of flux.", "A természet nem kedveli a "
                    "fluxusváltozást."),
        symbols=["Phiext", "Iind"], assumptions=[_PASSIVE]),
    _eq(id="transformer_induced_current", name=L("Transformer-induced current",
                                                 "Transzformátorosan indukált áram"),
        latex=r"\mathcal{E}_{\text{tr}} = -\sum_s \frac{dI_s}{dt}\Phi_{is}",
        meaning=L("Changing prescribed currents drive the passive current; the prescribed "
                  "currents themselves are unaffected (no back-reaction on sources).",
                  "A változó előírt áramok hajtják a passzív áramot; maguk az előírt áramok "
                  "nem változnak (nincs visszahatás a forrásokra)."),
        intuition=L("A changing neighbour current induces a current.",
                    "A szomszéd változó árama áramot indukál."),
        symbols=["Phiext", "Iind", "t"], assumptions=[_PASSIVE]),
    _eq(id="motional_induced_current", name=L("Motional-induced current", "Mozgással indukált "
                                              "áram"),
        latex=r"\mathcal{E}_{\text{mot}} = \oint (\mathbf{u}\times\mathbf{B})\cdot "
              r"d\boldsymbol{\ell} \;\Rightarrow\; R I + \mathcal{L}\dot I = "
              r"\mathcal{E}_{\text{mot}}",
        meaning=L("Motion through the prescribed field drives the current (Phase 4B motional "
                  "EMF).",
                  "Az előírt térben való mozgás hajtja az áramot (4B fázis mozgási EMF-je)."),
        intuition=L("Move a closed loop across field lines and a current flows.",
                    "Ha zárt hurkot mozgatunk az erővonalakon át, áram folyik."),
        symbols=["Iind", "Rres", "Lself"], assumptions=[_PASSIVE]),
    _eq(id="magnetic_force_filament", name=L("Force on a current element", "Áramelemre ható erő"),
        latex=r"d\mathbf{F} = I\, d\boldsymbol{\ell}\times\mathbf{B}_{\text{ext}}",
        meaning=L("B_ext excludes the conductor's own singular filament field.",
                  "B_ext nem tartalmazza a vezető saját szinguláris áramszálterét."),
        intuition=L("Current across field lines is pushed sideways.",
                    "Az erővonalakat keresztező áramra oldalirányú erő hat."),
        symbols=["Fem", "Iind", "dl", "Bext"]),
    _eq(id="magnetic_force_loop", name=L("Force on a current loop", "Áramhurokra ható erő"),
        latex=r"\mathbf{F} = I\oint d\boldsymbol{\ell}\times\mathbf{B}_{\text{ext}}",
        meaning=L("Integrated adaptively over the movable conductor (for the sliding rod: the rod "
                  "only; the rails are fixed).",
                  "Adaptívan integrálva a mozgatható vezetőn (csúszó rúdnál csak a rúdon; a "
                  "sínek rögzítettek)."),
        intuition=L("In a uniform field the net force on a closed loop vanishes; gradients "
                    "push it.", "Homogén térben zárt hurokra nem hat eredő erő; a gradiens "
                    "tolja."),
        symbols=["Fem", "Iind", "dl", "Bext"]),
    _eq(id="loop_torque", name=L("Torque on a current loop", "Áramhurokra ható nyomaték"),
        latex=r"\boldsymbol{\tau} = \oint (\mathbf{r}-\mathbf{c})\times\left[I\, "
              r"d\boldsymbol{\ell}\times\mathbf{B}_{\text{ext}}\right]",
        meaning=L("About the circuit's centre c.", "Az áramkör c középpontjára."),
        intuition=L("A loop turns to align its moment with B.", "A hurok momentumát B-hez "
                    "igazítva fordul."),
        symbols=["tau", "r", "Iind", "dl", "Bext"]),
    _eq(id="translational_dynamics", name=L("Equation of motion of the rod", "A rúd "
                                            "mozgásegyenlete"),
        latex=r"m\frac{d^2x}{dt^2} = F_{\text{ext}} + F_{\text{em}} - b\frac{dx}{dt}",
        meaning=L("Solved together with the circuit equation (sliding rod, one degree of "
                  "freedom; no friction, contact or bearing forces).",
                  "Az áramköri egyenlettel együtt megoldva (csúszó rúd, egy szabadsági fok; "
                  "nincs súrlódás, érintkezési vagy csapágyerő)."),
        intuition=L("The induced current's force brakes the rod.", "Az indukált áram ereje "
                    "fékezi a rudat."),
        symbols=["mmech", "xpos", "t", "Fem", "bdamp"]),
    _eq(id="rotational_dynamics", name=L("Rotational equation of motion", "Forgó mozgásegyenlet"),
        latex=r"J\frac{d^2\theta}{dt^2} = \tau_{\text{ext}} + \tau_{\text{em}} - "
              r"\beta\frac{d\theta}{dt}",
        meaning=L("Not solved in this phase: rotating circuits follow prescribed motion; the "
                  "electromagnetic torque is reported.",
                  "Ebben a fázisban nincs megoldva: a forgó áramkörök előírt mozgást követnek; "
                  "az elektromágneses nyomatékot kiírjuk."),
        intuition=L("A generator coil is braked by its own current.", "A generátortekercset "
                    "saját árama fékezi."),
        symbols=["Jmech", "tau", "t"]),
    _eq(id="electromagnetic_power", name=L("Electromagnetic mechanical power",
                                           "Elektromágneses mechanikai teljesítmény"),
        latex=r"P_{\text{mech}} = \mathbf{F}_{\text{em}}\cdot\mathbf{u}\ "
              r"(+\,\boldsymbol{\tau}_{\text{em}}\cdot\boldsymbol{\omega})",
        meaning=L("Negative when the force opposes the motion (braking).",
                  "Negatív, ha az erő a mozgással ellentétes (fékezés)."),
        intuition=L("Braking turns kinetic energy into heat.", "A fékezés a mozgási energiát "
                    "hővé alakítja."),
        symbols=["Pmech", "Fem", "tau"]),
    _eq(id="joule_heating", name=L("Joule heating", "Joule-hő"),
        latex=r"P_R = \sum_i R_i I_i^2,\qquad Q_R(t) = \int_0^t P_R\,d\tau",
        meaning=L("Integrated with the circuit equations.", "Az áramköri egyenletekkel együtt "
                  "integrálva."),
        intuition=L("Induced currents always heat the conductor.", "Az indukált áram mindig "
                    "melegíti a vezetőt."),
        symbols=["PR", "QR", "Rres", "Iind", "t"]),
    _eq(id="coupled_magnetic_energy", name=L("Energy balance of passive circuits",
                                             "Passzív áramkörök energiamérlege"),
        latex=r"P_{\text{mech}} + \frac{dW_m}{dt} + P_R = P_{\text{source}} = "
              r"\sum_i I_i\,\mathcal{E}_{\text{tr},i}",
        meaning=L("Mechanical power, change of magnetic energy and heat add up to the power "
                  "supplied through the changing prescribed flux; the residual is reported as "
                  "computed.",
                  "A mechanikai teljesítmény, a mágneses energia változása és a hő összege a "
                  "változó előírt fluxuson át betáplált teljesítmény; a maradékot kiszámított "
                  "értékként közöljük."),
        intuition=L("Energy is conserved between motion, field and heat.",
                    "Az energia megmarad a mozgás, a tér és a hő között."),
        symbols=["Pmech", "Wm", "PR", "t"], assumptions=[_PASSIVE]),
    _eq(id="energy_exchange", name=L("Mechanical work and energy exchange",
                                     "Mechanikai munka és energiacsere"),
        latex=r"\Delta K + W_{\text{damp}} - W_{\text{ext}} + \Delta W_m + Q_R - "
              r"W_{\text{source}} = 0",
        meaning=L("For the dynamic rod: kinetic energy, damping, external work, magnetic energy, "
                  "Joule heat and source work.",
                  "A dinamikus rúdra: mozgási energia, csillapítás, külső munka, mágneses "
                  "energia, Joule-hő és forrásmunka."),
        intuition=L("Kinetic energy becomes heat and field energy.", "A mozgási energia hővé és "
                    "térenergiává alakul."),
        symbols=["Wm", "QR", "mmech"]),
    _eq(id="annular_resistance", name=L("Resistance of an annular band", "Körgyűrű-sáv "
                                        "ellenállása"),
        latex=r"R_k = \frac{2\pi r_k}{\sigma t\,\Delta r_k}",
        meaning=L("Azimuthal path length over the band's cross-section t Δr_k.",
                  "Az azimutális úthossz osztva a sáv t Δr_k keresztmetszetével."),
        intuition=L("Outer bands are longer and resist more.", "A külső sávok hosszabbak, "
                    "nagyobb az ellenállásuk."),
        symbols=["Rres", "rk", "sigma_c", "tband", "drk"], assumptions=[_BAND], idealized=True),
    _eq(id="annular_current_density", name=L("Approximate azimuthal current density",
                                             "Közelítő azimutális áramsűrűség"),
        latex=r"J_{\varphi,k} \approx \frac{I_k}{t\,\Delta r_k}",
        meaning=L("Uniform within each band (an annular-band approximation, refined by "
                  "increasing N_r within its validity range Δr ≥ t/2).",
                  "Sávonként egyenletes (körgyűrű-sávos közelítés, N_r növelésével finomítva "
                  "az érvényességi tartományon belül, Δr ≥ t/2)."),
        intuition=L("Eddy currents circulate around the axis.", "Az örvényáramok a tengely "
                    "körül keringenek."),
        symbols=["Jphi", "Iind", "tband", "drk"], assumptions=[_BAND], idealized=True),
    _eq(id="coupled_band_dynamics", name=L("Coupled band dynamics", "Csatolt sávdinamika"),
        latex=r"\mathbf{L}_{\text{bands}}\frac{d\mathbf{I}}{dt} + \mathbf{R}\mathbf{I} = "
              r"-\frac{d\boldsymbol{\Phi}_{\text{ext}}}{dt}",
        meaning=L("Band self-inductances from an equivalent round wire (thin-loop formula) or "
                  "the geometric-mean-distance method; mutuals from Maxwell's formula, averaged "
                  "over the cross-sections for neighbouring bands.",
                  "A sávok önindukciója egyenértékű kör huzalból (vékony hurok képlet) vagy a "
                  "geometriai középtávolság módszeréből; a kölcsönösek Maxwell képletéből, "
                  "szomszédos sávoknál a keresztmetszetekre átlagolva."),
        intuition=L("Each ring shields the others.", "Minden gyűrű árnyékolja a többit."),
        symbols=["Lmat", "Iind", "t", "Rres", "Phiext"], assumptions=[_BAND, _PASSIVE],
        idealized=True,
        limitations=[L("Axisymmetric fields and circular disks only; no skin effect, radial "
                       "currents, temperature or thermal effects; general 3D eddy currents need "
                       "the FEM phase.",
                       "Csak tengelyszimmetrikus tér és kör alakú korong; nincs szkinhatás, "
                       "radiális áram, hőmérséklet- vagy hőhatás; általános 3D örvényáramokhoz "
                       "a VEM fázis kell.")]),
]


def _any(c: ModelContext) -> Out:
    if c.passive_circuits == 0:
        return ("not_evaluated", L("No passive circuit is defined.", "Nincs passzív áramkör "
                                   "megadva."))
    return ("applicable_under_assumptions", L("Lumped passive circuits, magnetoquasistatic.",
                                              "Koncentrált passzív áramkörök, "
                                              "magnetokvázisztatikus."))


def _coupled(c: ModelContext) -> Out:
    pre = _any(c)
    if pre[0] == "not_evaluated":
        return pre
    if c.passive_circuits < 2:
        return ("not_applicable", L("A single circuit: no mutual coupling.",
                                    "Egyetlen áramkör: nincs kölcsönös csatolás."))
    return OK


def _thin(c: ModelContext) -> Out:
    pre = _any(c)
    if pre[0] == "not_evaluated":
        return pre
    return ("applicable_under_assumptions", L("Circular loops with r_w/a ≤ 0.1 only.",
                                              "Csak r_w/a ≤ 0,1 kör alakú hurkokra."))


def _moving(c: ModelContext) -> Out:
    pre = _any(c)
    if pre[0] == "not_evaluated":
        return pre
    if c.moving_circuits == 0:
        return ("not_applicable", L("No moving circuit.", "Nincs mozgó áramkör."))
    return pre


def _dynamic(c: ModelContext) -> Out:
    if c.dynamic_circuits == 0:
        return ("not_evaluated", L("No dynamically moving rod.", "Nincs dinamikusan mozgó rúd."))
    return ("applicable_under_assumptions", L("One degree of freedom, no friction.",
                                              "Egy szabadsági fok, súrlódás nélkül."))


def _rotation(c: ModelContext) -> Out:
    return ("not_evaluated", L("Rotational dynamics is not solved in this phase (prescribed "
                               "rotation only).",
                               "A forgó dinamikát ebben a fázisban nem oldjuk meg (csak előírt "
                               "forgás)."))


def _band(c: ModelContext) -> Out:
    if c.eddy_disks == 0:
        return ("not_evaluated", L("No eddy-current disk.", "Nincs örvényáramú korong."))
    return ("applicable_under_assumptions", L("Axisymmetric annular-band approximation.",
                                              "Tengelyszimmetrikus körgyűrű-sávos közelítés."))


RULES = {
    "resistance_rho": _any,
    "resistance_sigma": _any,
    "thin_loop_inductance": _thin,
    "self_magnetic_energy": _any,
    "mutual_inductance_passive": _coupled,
    "inductance_matrix": _any,
    "circuit_voltage_equation": _any,
    "flux_linkage": _any,
    "passive_loop_equation": _any,
    "fixed_rl_equation": _any,
    "lenz_passive": _any,
    "transformer_induced_current": _any,
    "motional_induced_current": _moving,
    "magnetic_force_filament": _any,
    "magnetic_force_loop": _any,
    "loop_torque": _any,
    "translational_dynamics": _dynamic,
    "rotational_dynamics": _rotation,
    "electromagnetic_power": _moving,
    "joule_heating": _any,
    "coupled_magnetic_energy": _any,
    "energy_exchange": _dynamic,
    "annular_resistance": _band,
    "annular_current_density": _band,
    "coupled_band_dynamics": _band,
}
