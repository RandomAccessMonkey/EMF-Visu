"""Phase 4B equations: rigid motion of measurement conductors, motional EMF, the generalized
Faraday law for moving circuits, the sliding-rod and rotating-coil generators, the Lorentz force
on a test charge and nonrelativistic test-particle motion.

Appended to the one registry (``data.EQUATIONS`` / ``SYMBOLS`` and ``rules.RULES``); statuses
are derived from the model context like every other equation."""

from __future__ import annotations

from ..i18n import L, LocalizedText
from ..solvers.base import ModelContext
from .models import Equation, EquationStatus, SymbolDef

Out = tuple[EquationStatus, LocalizedText | None]
OK: Out = ("applicable", None)

_RIGID = L("Rigid motion of a passive measurement conductor; the sources stay fixed.",
           "Passzív mérővezető merev mozgása; a források állnak.")
_GALILEAN = L("Nonrelativistic (|u| ≪ c): E + u × B is the force per unit charge on the "
              "conductor's carriers, measured in the laboratory frame.",
              "Nemrelativisztikus (|u| ≪ c): E + u × B a vezető töltéshordozóira ható "
              "egységnyi töltésre jutó erő a laboratóriumi rendszerben.")
_PASSIVE = L("No induced current flows and nothing acts back on the sources: the EMF is an "
             "open-circuit EMF, not a current.",
             "Nem folyik indukált áram, és semmi sem hat vissza a forrásokra: az EMF "
             "üresjárási EMF, nem áram.")
_TEST = L("Test charge: it does not change the fields; nonrelativistic; no radiation reaction "
          "or self-field.",
          "Próbatöltés: nem változtatja meg a tereket; nemrelativisztikus; nincs "
          "sugárzási visszahatás vagy saját tér.")
_UNIFORM = L("Uniform-field idealization: a reference for comparison only.",
             "Homogén tér idealizáció: csak összehasonlító referencia.")

SYMBOLS: dict[str, SymbolDef] = {
    "u_mat": SymbolDef(latex=r"\mathbf{u}", unit="m/s",
                       meaning=L("local material velocity of the conductor (not a particle "
                                 "velocity)",
                                 "a vezető helyi anyagi sebessége (nem részecskesebesség)")),
    "Vtr": SymbolDef(latex=r"\mathbf{V}", unit="m/s",
                     meaning=L("translational velocity of the conductor's reference point",
                               "a vezető referenciapontjának haladó sebessége")),
    "omega_vec": SymbolDef(latex=r"\boldsymbol{\omega}", unit="rad/s",
                           meaning=L("angular velocity (right-hand rule)",
                                     "szögsebesség (jobbkéz-szabály)")),
    "Rmat": SymbolDef(latex=r"\mathsf{R}(t)", unit="1",
                      meaning=L("rotation matrix of the conductor's orientation",
                                "a vezető orientációjának forgatási mátrixa")),
    "cvec": SymbolDef(latex=r"\mathbf{c}(t)", unit="m",
                      meaning=L("position of the conductor's reference point (centre)",
                                "a vezető referenciapontjának (középpontjának) helye")),
    "rloc": SymbolDef(latex=r"\mathbf{r}_{\text{local}}", unit="m",
                      meaning=L("point in the conductor's own (reference) frame",
                                "pont a vezető saját (referencia-) rendszerében")),
    "Emot": SymbolDef(latex=r"\mathbf{u}\times\mathbf{B}", unit="V/m",
                      meaning=L("motional term: force per unit charge from the conductor's "
                                "motion (not an electrostatic field)",
                                "mozgási tag: a vezető mozgásából eredő, egységnyi töltésre "
                                "jutó erő (nem elektrosztatikus tér)")),
    "emf_mot": SymbolDef(latex=r"\mathcal{E}_{\text{mot}}", unit="V",
                         meaning=L("motional EMF", "mozgási EMF")),
    "emf_tr": SymbolDef(latex=r"\mathcal{E}_{\text{tr}}", unit="V",
                        meaning=L("transformer EMF ∮E_ind·dl", "transzformátor-EMF ∮E_ind·dl")),
    "emf_gen": SymbolDef(latex=r"\mathcal{E}", unit="V",
                         meaning=L("generalized EMF around the moving circuit",
                                   "általánosított EMF a mozgó áramkör mentén")),
    "S_t": SymbolDef(latex=r"S(t)", unit="m^2",
                     meaning=L("instantaneous surface bounded by the moving circuit",
                               "a mozgó áramkör által határolt pillanatnyi felület")),
    "C_t": SymbolDef(latex=r"C(t)", unit="m",
                     meaning=L("instantaneous closed conductor path", "pillanatnyi zárt "
                               "vezetőpálya")),
    "Lrod": SymbolDef(latex=r"L", unit="m", meaning=L("rod length (rail separation)",
                                                     "rúdhossz (sínek távolsága)")),
    "vrod": SymbolDef(latex=r"v", unit="m/s", meaning=L("rod speed along the rails",
                                                       "a rúd sebessége a sínek mentén")),
    "xrod": SymbolDef(latex=r"x(t)", unit="m", meaning=L("rod position along the rails",
                                                        "a rúd helye a sínek mentén")),
    "Acoil": SymbolDef(latex=r"A", unit="m^2", meaning=L("area of one turn", "egy menet "
                                                        "területe")),
    "omega_rot": SymbolDef(latex=r"\omega", unit="rad/s", meaning=L("angular speed",
                                                                    "szögsebesség")),
    "phase0": SymbolDef(latex=r"\varphi", unit="rad", meaning=L("initial angle", "kezdőszög")),
    "Nturn": SymbolDef(latex=r"N", unit="1",
                       meaning=L("number of identical series-connected turns of the measurement "
                                 "coil",
                                 "a mérőtekercs azonos, sorba kötött meneteinek száma")),
    "vpart": SymbolDef(latex=r"\mathbf{v}", unit="m/s",
                       meaning=L("laboratory-frame velocity of the test particle",
                                 "a próbarészecske laboratóriumi sebessége")),
    "mass": SymbolDef(latex=r"m", unit="kg", meaning=L("particle mass", "részecsketömeg")),
    "omega_c": SymbolDef(latex=r"\omega_c", unit="rad/s",
                         meaning=L("cyclotron angular frequency", "ciklotron-körfrekvencia")),
    "r_c": SymbolDef(latex=r"r_c", unit="m", meaning=L("cyclotron (gyro) radius",
                                                       "ciklotron- (giro-) sugár")),
    "vperp": SymbolDef(latex=r"v_\perp", unit="m/s",
                       meaning=L("velocity component perpendicular to B",
                                 "a B-re merőleges sebességkomponens")),
    "Kkin": SymbolDef(latex=r"K", unit="J", meaning=L("kinetic energy", "mozgási energia")),
    "Pow": SymbolDef(latex=r"P", unit="W", meaning=L("power delivered by the force",
                                                    "az erő teljesítménye")),
    "c0": SymbolDef(latex=r"c", unit="m/s", meaning=L("speed of light", "fénysebesség")),
    "FE": SymbolDef(latex=r"\mathbf{F}_E", unit="N", meaning=L("electric force", "elektromos "
                                                               "erő")),
    "FB": SymbolDef(latex=r"\mathbf{F}_B", unit="N", meaning=L("magnetic force", "mágneses erő")),
}


def _eq(**kw: object) -> Equation:
    return Equation.model_validate({"category": "motion", **kw})


EQUATIONS: list[Equation] = [
    _eq(id="rigid_body_pose", name=L("Rigid-body pose", "Merevtest-helyzet"),
        latex=r"\mathbf{r}_{\text{world}}(t) = \mathsf{R}(t)\,\mathbf{r}_{\text{local}} + "
              r"\mathbf{c}(t)",
        meaning=L("Every point of the conductor keeps its local coordinates; the rotation R(t) "
                  "and the translation c(t) place it in the world at time t.",
                  "A vezető minden pontja megtartja helyi koordinátáit; az R(t) forgatás és a "
                  "c(t) eltolás helyezi el a világban a t időpontban."),
        intuition=L("The shape never deforms; only its position and orientation change.",
                    "Az alak sosem torzul; csak a helyzete és orientációja változik."),
        symbols=["Rmat", "rloc", "cvec", "t"], assumptions=[_RIGID]),
    _eq(id="translational_velocity", name=L("Translational velocity", "Haladó sebesség"),
        latex=r"\mathbf{V}(t) = \frac{d\mathbf{c}}{dt}",
        meaning=L("Evaluated analytically from the motion profile (constant velocity, constant "
                  "acceleration, sinusoidal), never from rendered frames. At the ends of an "
                  "active window the left and right values differ.",
                  "A mozgásprofilból analitikusan számítva (állandó sebesség, állandó gyorsulás, "
                  "szinuszos), sosem a kirajzolt képkockákból. Egy aktív ablak végein a bal és "
                  "jobb oldali érték eltér."),
        intuition=L("How fast the centre moves.", "Milyen gyorsan mozog a középpont."),
        symbols=["Vtr", "cvec", "t"]),
    _eq(id="angular_velocity_rotation",
        name=L("Rotation at constant angular velocity", "Forgás állandó szögsebességgel"),
        latex=r"\mathsf{R}(t) = \mathsf{R}_{\hat{\mathbf{k}}}\!\left(\omega (t-t_0)\right)"
              r"\mathsf{R}_0,\qquad \boldsymbol{\omega} = \omega\,\hat{\mathbf{k}}",
        meaning=L("Rotation about a fixed axis k̂ through the conductor's centre with signed "
                  "angular speed ω (right-hand rule).",
                  "Forgás a vezető középpontján átmenő rögzített k̂ tengely körül, előjeles ω "
                  "szögsebességgel (jobbkéz-szabály)."),
        intuition=L("Curl the right-hand fingers in the sense of rotation: the thumb is ω.",
                    "A jobb kéz ujjai a forgás irányába görbülnek: a hüvelykujj ω."),
        symbols=["Rmat", "omega_vec", "omega_rot", "t"], assumptions=[_RIGID]),
    _eq(id="material_velocity", name=L("Local material velocity", "Helyi anyagi sebesség"),
        latex=r"\mathbf{u}(\mathbf{r},t) = \mathbf{V}(t) + \boldsymbol{\omega}(t)\times"
              r"\left[\mathbf{r}-\mathbf{c}(t)\right]",
        meaning=L("Velocity of the conductor material at a point of a rigid body. For the "
                  "sliding rod only the rod moves; the rails and the connecting segment have "
                  "u = 0.",
                  "A vezető anyagának sebessége a merev test egy pontjában. A csúszó rúdnál csak "
                  "a rúd mozog; a sínek és az összekötő szakasz sebessége u = 0."),
        intuition=L("Points far from the axis of a rotating loop move fastest.",
                    "A forgó hurok tengelytől távoli pontjai mozognak a leggyorsabban."),
        symbols=["u_mat", "Vtr", "omega_vec", "r", "cvec"], assumptions=[_RIGID]),
    _eq(id="motional_field", name=L("Motional term", "Mozgási tag"),
        latex=r"\mathbf{f}/q = \mathbf{u}\times\mathbf{B}",
        meaning=L("Magnetic force per unit charge on carriers moving with the conductor. It "
                  "drives the motional EMF but is not an electrostatic field and is never added "
                  "to E.",
                  "A vezetővel együtt mozgó töltéshordozókra ható, egységnyi töltésre jutó "
                  "mágneses erő. Ez hajtja a mozgási EMF-et, de nem elektrosztatikus tér, és "
                  "sosem adjuk hozzá E-hez."),
        intuition=L("Carry a wire across field lines and its charges are pushed along it.",
                    "Ha egy vezetőt az erővonalakon át mozgatunk, töltései a vezető mentén "
                    "elmozdulnak."),
        symbols=["Emot", "u_mat", "B"], assumptions=[_GALILEAN]),
    _eq(id="motional_emf", name=L("Motional EMF", "Mozgási EMF"),
        latex=r"\mathcal{E}_{\text{mot}} = \oint_{C(t)} (\mathbf{u}\times\mathbf{B})\cdot "
              r"d\boldsymbol{\ell}",
        meaning=L("Line integral along the actual instantaneous conductor with the actual local "
                  "velocity at every point (adaptive Gauss–Kronrod). Stationary segments "
                  "contribute nothing; tangential motion contributes nothing.",
                  "Vonalintegrál a tényleges pillanatnyi vezető mentén, minden pontban a "
                  "tényleges helyi sebességgel (adaptív Gauss–Kronrod). Az álló szakaszok és "
                  "az érintő irányú mozgás nem adnak járulékot."),
        intuition=L("Only motion across the field lines, perpendicular to the wire, counts.",
                    "Csak az erővonalakon át, a vezetőre merőleges mozgás számít."),
        symbols=["emf_mot", "C_t", "u_mat", "B", "dl"], assumptions=[_GALILEAN, _PASSIVE]),
    _eq(id="generalized_emf", name=L("Generalized EMF of a moving circuit",
                                     "Mozgó áramkör általánosított EMF-je"),
        latex=r"\mathcal{E} = \oint_{C(t)} \left[\mathbf{E} + \mathbf{u}\times\mathbf{B}\right]"
              r"\cdot d\boldsymbol{\ell} = \mathcal{E}_{\text{tr}} + \mathcal{E}_{\text{mot}}",
        meaning=L("The electrostatic part of E has a single-valued potential and integrates to "
                  "zero around a closed path; the induced part gives the transformer EMF "
                  "∮E_ind·dl. Complete only when E_ind is available for every changing source.",
                  "E elektrosztatikus része egyértékű potenciálból származik, zárt görbén nulla "
                  "az integrálja; az indukált rész adja a ∮E_ind·dl transzformátor-EMF-et. "
                  "Csak akkor teljes, ha minden változó forrásra elérhető E_ind."),
        intuition=L("Two ways to get an EMF: change B, or move the wire.",
                    "Kétféleképpen kapunk EMF-et: B változtatásával vagy a vezető mozgatásával."),
        symbols=["emf_gen", "C_t", "E", "u_mat", "B", "dl", "emf_tr", "emf_mot"],
        assumptions=[_GALILEAN, _PASSIVE]),
    _eq(id="moving_surface_flux", name=L("Flux through a moving surface",
                                         "Fluxus mozgó felületen át"),
        latex=r"\Phi_B(t) = \int_{S(t)} \mathbf{B}(\mathbf{r},t)\cdot\hat{\mathbf{n}}(t)\,dA",
        meaning=L("Integrated over the transformed physical surface at time t (adaptive "
                  "surface quadrature); the normal turns with the surface.",
                  "A t időpontbeli transzformált fizikai felületen integrálva (adaptív felületi "
                  "kvadratúra); a normális a felülettel együtt fordul."),
        intuition=L("Tilting or sliding the surface changes how much B threads it.",
                    "A felület döntése vagy elcsúsztatása megváltoztatja, mennyi B halad át "
                    "rajta."),
        symbols=["PhiB", "S_t", "B", "dA", "t"]),
    _eq(id="generalized_faraday", name=L("Faraday's law for a moving circuit",
                                         "Faraday-törvény mozgó áramkörre"),
        latex=r"\oint_{C(t)}\left[\mathbf{E}+\mathbf{u}\times\mathbf{B}\right]\cdot "
              r"d\boldsymbol{\ell} = -\frac{d}{dt}\int_{S(t)}\mathbf{B}\cdot d\mathbf{A}",
        meaning=L("Checked by computing both sides independently: the left side by line "
                  "integrals of E_ind and u × B, the right side by Richardson-extrapolated "
                  "finite differences in time of the flux through the moved surface (never from "
                  "the line integral).",
                  "Mindkét oldal független számításával ellenőrizve: a bal oldal E_ind és u × B "
                  "vonalintegráljaiból, a jobb oldal a mozgatott felületen átmenő fluxus időbeli "
                  "véges differenciáiból Richardson-extrapolációval (sosem a vonalintegrálból)."),
        intuition=L("Whether B changes or the circuit moves, the EMF opposes the change of "
                    "linked flux.",
                    "Akár B változik, akár az áramkör mozog, az EMF a kapcsolt fluxus "
                    "változásával ellentétes."),
        symbols=["C_t", "S_t", "E", "u_mat", "B", "dl", "dA", "t"],
        assumptions=[_GALILEAN, _PASSIVE]),
    _eq(id="sliding_rod_emf", name=L("Sliding-rod EMF (uniform field)",
                                     "Csúszó rúd EMF-je (homogén tér)"),
        latex=r"|\mathcal{E}| = B L v",
        meaning=L("For a uniform field perpendicular to the rails' plane. The application "
                  "integrates the actual field along the rod and shows BLv only as a labelled "
                  "reference.",
                  "A sínek síkjára merőleges homogén térre. Az alkalmazás a tényleges teret "
                  "integrálja a rúd mentén, a BLv-t csak jelölt referenciaként mutatja."),
        intuition=L("Twice the speed or twice the field gives twice the EMF.",
                    "Kétszeres sebesség vagy kétszeres tér kétszeres EMF-et ad."),
        symbols=["emf_gen", "B", "Lrod", "vrod"], assumptions=[_UNIFORM], idealized=True),
    _eq(id="flux_area_change", name=L("Flux change by area change",
                                      "Fluxusváltozás területváltozással"),
        latex=r"\Phi_B = B L x(t),\qquad \frac{d\Phi_B}{dt} = B L \frac{dx}{dt} = B L v",
        meaning=L("In a uniform perpendicular field the flux grows with the swept area; the "
                  "EMF −dΦ/dt equals the motional EMF of the rod.",
                  "Homogén, merőleges térben a fluxus a súrolt területtel nő; a −dΦ/dt EMF "
                  "megegyezik a rúd mozgási EMF-jével."),
        intuition=L("The rod sweeps new field lines into the circuit.",
                    "A rúd új erővonalakat söpör be az áramkörbe."),
        symbols=["PhiB", "B", "Lrod", "xrod", "vrod"], assumptions=[_UNIFORM], idealized=True),
    _eq(id="rotating_coil_flux", name=L("Rotating coil in a uniform field",
                                        "Forgó tekercs homogén térben"),
        latex=r"\Phi_B(t) = B A\cos(\omega t + \varphi),\qquad \mathcal{E} = -\frac{d\Phi_B}"
              r"{dt} = B A\,\omega\sin(\omega t + \varphi)",
        meaning=L("For a planar loop rotating about an axis perpendicular to a uniform B. The "
                  "application computes the actual flux and EMF and shows this waveform as a "
                  "reference with B taken at the coil's centre.",
                  "Homogén B-re merőleges tengely körül forgó sík hurokra. Az alkalmazás a "
                  "tényleges fluxust és EMF-et számítja, ezt a hullámformát referenciaként "
                  "mutatja a tekercs középpontjabeli B-vel."),
        intuition=L("The EMF is largest when the coil's plane is parallel to B (flux zero).",
                    "Az EMF akkor a legnagyobb, amikor a tekercs síkja párhuzamos B-vel (a "
                    "fluxus nulla)."),
        symbols=["PhiB", "B", "Acoil", "omega_rot", "phase0", "t", "emf_gen"],
        assumptions=[_UNIFORM], idealized=True),
    _eq(id="multi_turn_linkage", name=L("N-turn measurement coil", "N menetes mérőtekercs"),
        latex=r"\Lambda = N\Phi_B,\qquad \mathcal{E} = -\frac{d\Lambda}{dt}",
        meaning=L("Only for a coil explicitly defined with N identical, coincident, "
                  "series-connected turns: every flux and EMF is multiplied by N.",
                  "Csak kifejezetten N azonos, egybeeső, sorba kötött menettel megadott "
                  "tekercsre: minden fluxus és EMF N-szeres."),
        intuition=L("Each turn adds the same EMF in series.", "Minden menet ugyanazt az EMF-et "
                    "adja sorosan."),
        symbols=["Nturn", "PhiB", "emf_gen", "t"]),
    _eq(id="electric_force", name=L("Electric force on a test charge",
                                    "Elektromos erő próbatöltésre"),
        latex=r"\mathbf{F}_E = q\,(\mathbf{E}_{\text{static}} + \mathbf{E}_{\text{ind}})",
        meaning=L("From the electrostatic field of the charges and, for changing currents, the "
                  "induced field. Partial where E_ind is not available.",
                  "A töltések elektrosztatikus teréből és változó áramoknál az indukált térből. "
                  "Hiányos, ahol E_ind nem érhető el."),
        intuition=L("Along E for q > 0, against it for q < 0.",
                    "q > 0 esetén E irányában, q < 0 esetén ellene."),
        symbols=["FE", "q", "E"], assumptions=[_TEST]),
    _eq(id="magnetic_force", name=L("Magnetic force on a moving charge",
                                    "Mágneses erő mozgó töltésre"),
        latex=r"\mathbf{F}_B = q\,\mathbf{v}\times\mathbf{B}",
        meaning=L("v is the particle's own laboratory-frame velocity. Reversing q, v or B "
                  "reverses the force.",
                  "v a részecske saját laboratóriumi sebessége. q, v vagy B megfordítása az "
                  "erőt is megfordítja."),
        intuition=L("Right-hand rule: fingers along v, curl toward B, thumb gives F for q > 0.",
                    "Jobbkéz-szabály: ujjak v irányában, B felé görbítve; a hüvelykujj q > 0 "
                    "esetén F."),
        symbols=["FB", "q", "vpart", "B"], assumptions=[_TEST]),
    _eq(id="magnetic_force_no_work", name=L("Magnetic force does no work",
                                            "A mágneses erő nem végez munkát"),
        latex=r"P_B = q(\mathbf{v}\times\mathbf{B})\cdot\mathbf{v} = 0",
        meaning=L("F_B is perpendicular to v, so it changes the direction of motion but not the "
                  "speed; only the electric force changes the kinetic energy (P = qE·v).",
                  "F_B merőleges v-re, ezért a mozgás irányát változtatja, a sebesség nagyságát "
                  "nem; csak az elektromos erő változtatja a mozgási energiát (P = qE·v)."),
        intuition=L("A magnetic field steers, it does not speed up.",
                    "A mágneses tér terel, nem gyorsít."),
        symbols=["Pow", "q", "vpart", "B", "E"], assumptions=[_TEST]),
    _eq(id="cyclotron_frequency", name=L("Cyclotron angular frequency",
                                         "Ciklotron-körfrekvencia"),
        latex=r"\omega_c = \frac{|q| B}{m}",
        meaning=L("Angular frequency of gyration in a uniform B, independent of the speed "
                  "(nonrelativistic).",
                  "A homogén B-beli körmozgás körfrekvenciája, független a sebességtől "
                  "(nemrelativisztikus)."),
        intuition=L("Heavier particles gyrate more slowly.", "A nehezebb részecskék lassabban "
                    "keringenek."),
        symbols=["omega_c", "q", "B", "mass"], assumptions=[_TEST, _UNIFORM], idealized=True),
    _eq(id="cyclotron_radius", name=L("Cyclotron radius", "Ciklotronsugár"),
        latex=r"r_c = \frac{m v_\perp}{|q| B}",
        meaning=L("Radius of the circle (or helix) in a uniform B; the parallel velocity "
                  "component is unchanged, giving a helix.",
                  "A homogén B-beli kör (vagy csavarvonal) sugara; a párhuzamos "
                  "sebességkomponens változatlan, ezért csavarvonal alakul ki."),
        intuition=L("Faster or heavier particles make wider circles.",
                    "A gyorsabb vagy nehezebb részecskék tágabb köröket írnak le."),
        symbols=["r_c", "mass", "vperp", "q", "B"], assumptions=[_TEST, _UNIFORM],
        idealized=True),
    _eq(id="newton_lorentz", name=L("Newton–Lorentz equation of motion",
                                    "Newton–Lorentz mozgásegyenlet"),
        latex=r"m\frac{d\mathbf{v}}{dt} = q\left(\mathbf{E} + \mathbf{v}\times\mathbf{B}"
              r"\right),\qquad \frac{d\mathbf{r}}{dt} = \mathbf{v}",
        meaning=L("Integrated with the Boris scheme with time-centred fields and a step "
                  "limited by the gyrofrequency and the distance to singular regions.",
                  "Boris-sémával integrálva, időben centrált terekkel; a lépést a "
                  "girofrekvencia és a szinguláris tartományoktól mért távolság korlátozza."),
        intuition=L("The particle follows the prescribed fields; it does not change them.",
                    "A részecske követi az előírt tereket; nem változtatja meg őket."),
        symbols=["mass", "vpart", "t", "q", "E", "B", "r"], assumptions=[_TEST]),
    _eq(id="nonrelativistic_validity", name=L("Nonrelativistic validity",
                                              "Nemrelativisztikus érvényesség"),
        latex=r"|\mathbf{v}| \ll c",
        meaning=L("The force law and Newton's equation above hold for speeds well below c; the "
                  "application warns above 0.01 c and stops at c.",
                  "A fenti erőtörvény és Newton-egyenlet c-nél jóval kisebb sebességekre "
                  "érvényes; az alkalmazás 0,01 c felett figyelmeztet, c-nél leáll."),
        intuition=L("Near c the momentum is no longer mv.", "c közelében az impulzus már nem mv."),
        symbols=["vpart", "c0"], assumptions=[_TEST]),
    _eq(id="kinetic_energy", name=L("Kinetic energy", "Mozgási energia"),
        latex=r"K = \tfrac12 m |\mathbf{v}|^2,\qquad \frac{dK}{dt} = q\,\mathbf{E}\cdot\mathbf{v}",
        meaning=L("Only the electric force changes K; in a magnetic-only field K is constant "
                  "(the Boris rotation keeps |v| to rounding).",
                  "K-t csak az elektromos erő változtatja; tisztán mágneses térben K állandó (a "
                  "Boris-forgatás kerekítési pontossággal megtartja |v|-t)."),
        intuition=L("Energy comes from E, never from B.", "Az energia E-ből jön, sosem B-ből."),
        symbols=["Kkin", "mass", "vpart", "q", "E"], assumptions=[_TEST]),
]


def _moving(c: ModelContext) -> Out:
    if c.moving_surfaces == 0:
        return ("not_evaluated", L("No moving measurement conductor in this configuration.",
                                   "Ebben az elrendezésben nincs mozgó mérővezető."))
    return OK


def _motional(c: ModelContext) -> Out:
    pre = _moving(c)
    if pre[0] != "applicable":
        return pre
    if not c.computes_magnetic_field:
        return ("not_evaluated", L("No magnetic field.", "Nincs mágneses tér."))
    return ("applicable_under_assumptions", L("Nonrelativistic conductor speed.",
                                              "Nemrelativisztikus vezetősebesség."))


def _generalized(c: ModelContext) -> Out:
    pre = _motional(c)
    if pre[0] == "not_evaluated":
        return pre
    if c.time_varying and not c.e_ind_available:
        return ("not_evaluated", L("A changing source has no induced field in this model: only "
                                   "the motional part is evaluated (motional-only).",
                                   "Egy változó forrásnak nincs indukált tere ebben a "
                                   "modellben: csak a mozgási rész van kiértékelve."))
    return pre


def _rod(c: ModelContext) -> Out:
    if c.sliding_rods == 0:
        return ("not_applicable", L("No sliding rod in this configuration.",
                                    "Ebben az elrendezésben nincs csúszó rúd."))
    return ("applicable_under_assumptions", L("Reference only: valid where B is uniform over "
                                              "the circuit.",
                                              "Csak referencia: ott érvényes, ahol B az "
                                              "áramkörön homogén."))


def _rotating(c: ModelContext) -> Out:
    if c.rotating_surfaces == 0:
        return ("not_applicable", L("No rotating conductor in this configuration.",
                                    "Ebben az elrendezésben nincs forgó vezető."))
    return ("applicable_under_assumptions", L("Reference only: valid where B is uniform over "
                                              "the coil.",
                                              "Csak referencia: ott érvényes, ahol B a "
                                              "tekercsen homogén."))


def _turns(c: ModelContext) -> Out:
    if c.multi_turn_surfaces == 0:
        return ("not_applicable", L("No N-turn measurement coil is defined.",
                                    "Nincs N menetes mérőtekercs megadva."))
    return OK


def _charge(c: ModelContext) -> Out:
    if not c.test_charge:
        return ("not_evaluated", L("No test charge is defined.", "Nincs próbatöltés megadva."))
    if c.time_varying and not c.e_ind_available:
        return ("applicable_under_assumptions", L(
            "E_ind is unavailable for a changing source: the electric force is partial.",
            "Változó forrásra E_ind nem érhető el: az elektromos erő hiányos."))
    return ("applicable_under_assumptions", L("Nonrelativistic test charge.",
                                              "Nemrelativisztikus próbatöltés."))


def _gyro(c: ModelContext) -> Out:
    pre = _charge(c)
    if pre[0] == "not_evaluated":
        return pre
    if not c.computes_magnetic_field:
        return ("not_applicable", L("No magnetic field.", "Nincs mágneses tér."))
    return ("applicable_under_assumptions", L("Reference for a sufficiently uniform region.",
                                              "Referencia kellően homogén tartományra."))


def _particle(c: ModelContext) -> Out:
    if not c.trajectory:
        return ("not_evaluated", L("No trajectory is being computed.",
                                   "Nincs pályaszámítás."))
    return ("applicable_under_assumptions", L("Nonrelativistic test particle in prescribed "
                                              "fields.",
                                              "Nemrelativisztikus próbarészecske előírt "
                                              "terekben."))


def _lorentz(c: ModelContext) -> Out:
    return _charge(c)


RULES = {
    "rigid_body_pose": _moving,
    "translational_velocity": _moving,
    "angular_velocity_rotation": _moving,
    "material_velocity": _moving,
    "motional_field": _motional,
    "motional_emf": _motional,
    "generalized_emf": _generalized,
    "moving_surface_flux": _moving,
    "generalized_faraday": _generalized,
    "sliding_rod_emf": _rod,
    "flux_area_change": _rod,
    "rotating_coil_flux": _rotating,
    "multi_turn_linkage": _turns,
    "electric_force": _charge,
    "magnetic_force": _charge,
    "magnetic_force_no_work": _charge,
    "cyclotron_frequency": _gyro,
    "cyclotron_radius": _gyro,
    "newton_lorentz": _particle,
    "nonrelativistic_validity": _charge,
    "kinetic_energy": _particle,
    "lorentz_force": _lorentz,
}
