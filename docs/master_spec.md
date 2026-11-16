# Electromagnetic Field Visualization & Simulation Platform — Master Prompt

> **Purpose:** Give this complete specification to a coding agent to plan and build a physically trustworthy, interactive electromagnetic laboratory. The XML-style tags organize requirements; they are part of the prompt, not executable XML.
>
> **Implementation guidance:** Use the defaults in `<open_parameters>` for the initial build. Deliver Phase 1–2 first, with extension points for later phases. Do not claim that unimplemented later-phase capabilities are working.

<project_overview>
You are a senior multidisciplinary engineering team: a computational electromagnetics engineer, a physicist specializing in classical electromagnetism, a senior frontend and 3D graphics engineer, a scientific computing and numerical methods engineer, a backend and systems architect, and a UX/UI designer specializing in advanced technical applications.

The goal is to design and build an interactive electromagnetic field visualization and simulation platform. Users should be able to build electromagnetic systems, change their parameters, see how the fields respond, look into the underlying mathematics, and understand which physical laws govern each situation. It is a real simulation platform: every visual is backed by an actual calculation.
</project_overview>

<open_parameters>
Use these defaults unless the user or execution environment provides different requirements. Do not block implementation by asking questions that can be resolved using these defaults.

- Phases to deliver in the first implementation run: Phase 1–2. Build the architecture so later phases can be added without redesigning the system.
- User accounts and authentication: no. Keep the initial application local and single-user. Design persistence interfaces so authentication can be added later.
- Deployment target: local Docker-based development and execution.
- Target browsers: latest stable Chrome, Edge, Firefox, and Safari, subject to the availability of WebGL 2.
- Minimum graphics capability: WebGL 2-compatible GPU. Provide a graceful low-performance fallback where possible.
- UI languages: English and Hungarian. Keep all UI strings externalized for localization.
- Compute available: assume a typical local developer workstation. Start with analytical solvers and lightweight calculations; make FEM/FDTD workers optional and independently deployable.
- Magnetic field controls: expose both magnetic flux density B (T) and magnetic field strength H (A/m), with clear labels and physically consistent relationships.
- If a requirement genuinely depends on unavailable hardware or an unsupported solver, identify the limitation and provide the best supported alternative rather than fabricating functionality.
</open_parameters>

<notation>
- Use SI units throughout and in every displayed value.
- ρ_free is the free charge density. ρ without a subscript is the total charge density, and it equals ρ_free in vacuum. In ∇²φ = −ρ/ε, ρ means ρ_free in a homogeneous linear medium.
- E is the electric field (V/m), D the electric displacement (C/m²), B the magnetic flux density (T), H the magnetic field strength (A/m), J the current density (A/m²), φ the electric potential (V), Φ_B the magnetic flux (Wb), S the Poynting vector (W/m²), u the energy density (J/m³).
- "Curl" and "rotation" mean the same operator, ∇×.
- "Gauss–Ostrogradsky theorem" means the divergence theorem: ∮_∂V F·dA = ∫_V ∇·F dV.
- In the Biot–Savart law, r̂ is the unit vector from the source element dℓ to the field point, and r is their distance.
- Electric field direction is explained with the positive test charge convention.
</notation>

<core_principles>
Rank these priorities in this order:
1. Physical and mathematical correctness.
2. Numerical reliability and transparent assumptions.
3. Intuitive user experience.
4. Interactive 2D and 3D visualization.
5. Performance, responsiveness, and fluid animation.
6. Extensibility and maintainable architecture.

When accuracy and visual appeal conflict, choose accuracy. Every displayed field, vector, field line, flux visualization, and animated effect corresponds either to a clearly defined physical quantity or to an element explicitly labeled as a visualization aid. Animations show only behavior that the computed fields actually have.
</core_principles>

<technology_stack>
<frontend>
- React 19 (or the latest stable compatible release), TypeScript in strict mode, Vite.
- Three.js, React Three Fiber, Drei.
- Zustand for application and simulation state. TanStack Query for API communication, caching, and simulation result management.
- Tailwind CSS, shadcn/ui, Framer Motion / Motion for subtle interface transitions.
- KaTeX or MathJax for equations. Recharts or Plotly for charts, waveforms, and numerical plots.
- Three.js WebGL 2 is the baseline renderer. Design the rendering layer so WebGPU can be added later as an optional enhancement.
- The rendering layer is independent of the physics engine.
Use stable, production-ready releases with mutually compatible pinned versions.
</frontend>

<backend>
- Python 3.12+ (or the latest compatible stable release), FastAPI, Pydantic v2 for strict validation and typed models.
- NumPy and SciPy for computation and data processing.
- REST endpoints for configuration management and simulation requests. WebSockets for progress updates and real-time communication.
- Redis with a dedicated task queue for expensive simulations, which run as asynchronous jobs.
- PostgreSQL for projects, saved configurations, and user data, where persistence is in scope (see open_parameters).
</backend>

<physics_engine>
A dedicated, modular computational physics engine, fully separated from the frontend:
- DOLFINx / FEniCSx: FEM for electrostatic, magnetostatic, and appropriate quasi-static problems.
- Gmsh: 2D and 3D geometry meshing and mesh refinement.
- Meep: FDTD for time-dependent, full-wave problems.
- NumPy / SciPy: analytical solutions, numerical utilities, interpolation, post-processing.
- A lightweight analytical solver for idealized configurations (point charges, infinite line charges, parallel plates, straight wires, idealized coils). It is used wherever it applies, in place of an expensive numerical solver.

The engine selects the numerical method that fits the physical problem. Results from the analytical solver are labeled as idealized analytical models, distinct from numerical simulations. Keep the architecture modular so that new solvers and optimized Rust or C++ modules can be added later if profiling shows a need.
</physics_engine>
</technology_stack>

<architecture_requirements>
Separate the system into these components, with explicit, documented interfaces between them:
1. Frontend: interaction, geometry editing, visualization, charts, equation explanations.
2. Backend API: validation, orchestration, configuration management, communication with the engine.
3. Geometry subsystem: creation, transformation, validation, and meshing of objects.
4. Physics engine: the electromagnetic calculations.
5. Equation registry: equations, assumptions, applicability conditions, explanatory metadata.
6. Visualization subsystem: turning simulation output into visual representations.
7. Verification subsystem: analytical comparisons, convergence checks, validation tests.

All physical results shown in the frontend come from the physics engine (numerical or analytical) through these interfaces. Large simulation datasets travel in efficient binary or typed-array formats. Include Docker-based development and deployment configuration, environment variable management, automated tests, and clear setup documentation.
</architecture_requirements>

<solver_worker_architecture>
Run computational solvers as separate, independently deployable worker services rather than forcing every solver and its native dependencies into one application container.

Recommended services:
- Analytical solver worker: lightweight Python service or in-process module for fast known solutions.
- FEM worker: isolated DOLFINx/FEniCSx environment, with Gmsh available for meshing.
- FDTD worker: isolated Meep environment with its required native and numerical dependencies.
- Circuit solver: a dedicated MNA-based module or worker for lumped-element circuit analysis.
- Orchestrator: selects the appropriate solver, validates inputs, schedules jobs, tracks progress, handles cancellation, and normalizes outputs.

Use a queue for long-running jobs. Keep worker interfaces versioned and solver-agnostic. Each result must include solver identity and version, model assumptions, mesh/grid details, convergence information where available, units, and status. Do not make a solver appear available when its service is not installed or healthy.
</solver_worker_architecture>

<geometry_editor>
Users can add, remove, move, rotate, scale, and modify objects interactively, and combine several objects into complex configurations.

Primitives: points and point charges; lines and line charges; planes and charged surfaces; spheres and spherical shells; cubes and rectangular solids; cylinders and hollow cylinders; rings and circular loops; straight wires; coils and solenoids; toroids; parallel plates; arbitrary conductor shapes; custom 2D and 3D geometries.

Tools: custom dimensions and coordinates; object hierarchy and grouping; symmetry settings; cross-sectional views; snapping and alignment; adjustable spatial boundaries; optional CAD and mesh import/export (STEP, STL, OBJ, GLB, where appropriate).

Each object can be given a physical role: conductor, dielectric, magnetic material, current source, charge source, or another supported type.
</geometry_editor>

<electrical_parameters>
Configurable per object: voltage, charge, charge density, current, current density, resistance, conductivity, permittivity, relative permittivity, ideal conductors, finite-conductivity conductors, insulators and dielectrics.

Voltage and current profiles: DC, AC sinusoidal, square, triangle, pulse, and custom user-defined waveforms. Adjustable: amplitude, peak and RMS values, frequency, period, phase, offset, duty cycle (where applicable), time delay, initial conditions.

Voltage, current, electric field, current density, and charge density stay distinct quantities, each with its own name, symbol, and unit in both the UI and the code.
</electrical_parameters>

<circuit_model>
Implement a dedicated circuit-simulation subsystem for lumped-element electrical networks. Keep it conceptually separate from the continuous electromagnetic field solver, while allowing carefully defined coupling in later phases.

Support:
- Ideal and supported non-ideal voltage sources.
- Ideal and supported non-ideal current sources.
- Resistors.
- Capacitors.
- Inductors.
- Switches.
- Series and parallel connections.
- Nodes, branches, ground/reference nodes, and circuit connectivity.
- Arbitrary circuit topologies within the supported component set.

Use Modified Nodal Analysis (MNA), or another documented and validated circuit-solving method.

Support analysis modes where implemented:
- DC operating-point analysis.
- Transient/time-domain analysis.
- AC frequency-domain analysis.

Display node voltages, branch currents, component voltage/current, power, and relevant waveforms. Explain sign conventions and reference directions.

Enforce circuit constraints. Do not allow independently prescribed voltage and current values to violate the circuit solution without an explicit reason. Ideal sources and field boundary conditions must be clearly distinguished from independently calculated responses.

Couple circuit results to electromagnetic simulations only when a physically defined coupling model is implemented. Clearly label uncoupled lumped-circuit and coupled field-circuit simulations.
</circuit_model>

<magnetic_parameters>
Configurable sources: permanent magnets, magnetic dipoles, magnetic field sources, current-carrying wires, circular current loops, coils, solenoids, toroids, external magnetic fields.

Adjustable: permeability, relative permeability, magnetic field strength (see open_parameters), current magnitude and direction, number of turns, coil dimensions, current waveform, frequency and phase.

Support magnetic materials and the relevant approximations, including linear magnetic materials where appropriate.
</magnetic_parameters>

<constitutive_relations>
Treat material constitutive relations as first-class physical models, separate from Maxwell's field equations.

At minimum, document and support where appropriate:

Electric displacement:
D = ε₀E + P

Linear, isotropic dielectric:
D = εE

Magnetic flux density:
B = μ₀(H + M)

Linear, isotropic magnetic material:
B = μH

Local conduction relation for an ohmic isotropic conductor:
J = σE

Support material models for:
- Vacuum.
- Linear dielectric materials.
- Linear magnetic materials.
- Conductive materials.
- Spatially varying material properties.
- Anisotropic permittivity and permeability, where the selected solver supports them.
- Frequency-dependent or dispersive material properties, where the selected solver supports them.
- Nonlinear material behavior only when a suitable model and solver are implemented and validated.

Do not silently assume ε, μ, or σ is constant. Make the selected material model and its assumptions visible. Distinguish free charge from bound/polarization charge, and distinguish B from H and D from E.

For each material model, expose the applicable parameters, units, limitations, and supported frequency/time regime. If a material model is unsupported by the active solver, mark it unsupported rather than substituting a simpler model without disclosure.
</constitutive_relations>

<environmental_conditions>
Supported external influences and conditions: external electric and magnetic fields; nearby charged objects and current-carrying conductors; conductive boundaries; dielectric regions; magnetic materials; multiple interacting sources; spatially varying material properties; temperature-dependent material properties where supported; boundary conditions; grounding; electric potential constraints; perfect electric conductor boundaries; absorbing boundaries for wave simulations; periodic boundaries where applicable.

Users can apply several influences at once, see their combined effect, and enable, disable, isolate, or compare individual sources.
</environmental_conditions>

<field_visualization>
Separate and combined visualization modes:

Electric: E vectors, field lines, electric flux, equipotential surfaces and contours, potential distribution, field magnitude and direction, divergence, curl, superposition. The UI states explicitly how field vectors, field lines, equipotential surfaces, and actual particle trajectories differ.

Magnetic: B, H, field lines, magnetic flux, field vectors, magnitude, direction, divergence, interactions with current-carrying conductors.

Current: current direction, current density J, charge movement (only when a particle model is actually being simulated), conduction current, displacement current, current distribution inside conductors, skin effect (where the selected solver and frequency range support it).

Advanced: E and B superposition, energy density, Poynting vector and energy flow, wave propagation, induction, flux through arbitrary surfaces, divergence, curl, magnitude heatmaps, cross-sectional distributions, time-dependent evolution.
</field_visualization>

<visualization_modes>
2D workspace: top-down and side views, cross-sections, vector arrows, field lines, contours, equipotential lines, interactive measuring tools, coordinate axes and grids. Every 2D view states whether it is a truly two-dimensional mathematical model or a cross-section through a 3D configuration, and states any assumed invariance along the omitted dimension.

3D environment: orbit controls, zoom and pan, object selection, camera presets, cross-section and clipping planes, transparent geometry, isosurfaces, streamlines, vector field sampling, interactive spatial measurements.

The same physical system can be inspected in 2D and in 3D, keeping its configuration and parameter values.
</visualization_modes>

<faraday_and_induction>
A dedicated induction mode where users can change field strength and flux over time, move a magnet relative to a conducting loop, change loop area, orientation, and number of turns, adjust the rate of change of the field, and observe the induced electric field and the induced voltage and current in an appropriately defined circuit.

The induced electric field is shown as a potentially non-conservative, rotational field. The mode makes these points clear:
- A changing magnetic field is related to the curl of the electric field.
- The strength of the magnetic field is a different quantity from its rate of change.
- The magnitude and direction of the induced field depend on the geometry and time variation of the flux.
- The negative sign in Faraday's law expresses Lenz's law.

Users can compare an electrostatic radial field, an induced circular field, and their vector superposition. For each configuration, the mode shows and explains the actual geometry of the induced field that the solution produces.
</faraday_and_induction>

<equation_registry>
The registry determines dynamically which equations apply to the current physical configuration. Each equation includes: LaTeX expression, name, physical meaning, symbol definitions, SI units, assumptions, applicability conditions, boundary or initial conditions where relevant, limitations, links to the solver or model that uses it, a short intuitive explanation, and an optional derivation or step-by-step expansion. Clicking any displayed equation opens its explanation.

<required_equations>
Maxwell's equations (integral and differential forms where applicable):
- Gauss's law: ∇ · D = ρ_free; in vacuum ∇ · E = ρ / ε₀
- Gauss's law for magnetism: ∇ · B = 0
- Faraday's law: ∇ × E = −∂B/∂t
- Ampère–Maxwell law: ∇ × H = J_free + ∂D/∂t

Electrostatics:
- E = −∇φ
- Poisson: ∇ · (ε∇φ) = −ρ_free; for homogeneous permittivity ∇²φ = −ρ / ε
- Laplace, in charge-free regions: ∇²φ = 0
- Explain when the vacuum, homogeneous-material, and spatially varying permittivity models are appropriate.

Magnetostatics:
- Ampère's law: ∇ × H = J
- Biot–Savart: dB = (μ₀ / 4π) · I(dℓ × r̂) / r²
- Explain the assumptions behind the magnetostatic approximation and when time-dependent effects must be included.

Faraday (integral):
- ∮ E · dl = −dΦ_B/dt, with Φ_B = ∫ B · dA
- Explain how local curl relates to circulation around a closed path.

Additional:
- Continuity: ∇ · J = −∂ρ/∂t
- Lorentz force: F = q(E + v × B)
- Local Ohm's law: J = σE
- Poynting vector: S = E × H
- Energy density, for linear nondispersive media: u = ½(E · D + B · H)
</required_equations>

<applicability_logic>
- Electrostatic simulation: show the electrostatic equations and their assumptions.
- Time-varying magnetic field present: show Faraday's law.
- Current density and changing D both relevant: show the full Ampère–Maxwell law.
- Magnetostatic model: show the magnetostatic approximation.
- Spatially varying permittivity: use and display ∇ · (ε∇φ) = −ρ_free.
- Quasi-static approximation: state which terms were neglected and why.
- Full-wave simulation: use the full time-dependent Maxwell system.

Each equation carries one status: Applicable / Applicable under stated assumptions / Not applicable to the current model / Not evaluated by the current solver. Statuses other than "Applicable" come with a reason.
</applicability_logic>
</equation_registry>

<field_calculus_tools>
Probe: placeable anywhere. It shows E, B, H, D, J, potential, magnitudes, divergence, curl, and local energy density where supported.

Arbitrary closed surfaces and curves: compute and visualize electric flux through closed surfaces, magnetic flux through open or closed surfaces, circulation around closed paths, flux density distribution, local divergence, and local rotational behavior.

Gauss–Ostrogradsky demonstration mode: the user picks a closed surface (sphere, box, cylinder), moves positive and negative charges in and out, sees field lines entering and leaving, compares surface flux with the volume integral of divergence, and watches contributions from shared internal surfaces cancel when the volume is subdivided. The mode shows visually that zero divergence means zero net local outward flux density, while the field and the flux through individual surface elements can still be nonzero.
</field_calculus_tools>

<vector_calculus_visualization>
Provide a dedicated interactive workspace for understanding divergence and curl (rotation) in vector fields.

For each supported vector field, allow users to:
- Display the vector field itself.
- Display divergence as a signed scalar field.
- Display curl magnitude and curl direction.
- Inspect curl components and use the right-hand rule to understand direction.
- Place point probes and inspect local numerical values.
- Adjust sampling resolution.
- Select small closed paths and compare circulation with the enclosed area.
- Compare local curl with circulation per unit area in the appropriate limiting sense.

Include configurable teaching examples:
- Radial source field.
- Radial sink field.
- Uniform field.
- Rotational field.
- Divergence-free rotational field.
- A source field with an added rotational component.
- A field with nonzero divergence and nonzero curl, where a valid example is provided.

Explain that divergence measures local net outward flux per unit volume, while curl measures local circulation tendency. Distinguish field magnitude from divergence and curl magnitude. In 3D, curl is a vector; in a 2D in-plane vector field, the out-of-plane curl component is represented as a signed scalar.

Never interpret curl as energy flow. If energy transport is shown, use the Poynting vector and label its physical meaning.
</vector_calculus_visualization>

<interactive_controls>
Controls: sliders, numeric inputs, dropdowns, toggles, color-coded legends, play/pause/reset, time scrubbers, presets, side-by-side comparisons.

Adjustable: charge magnitude and sign, current magnitude and direction, voltage, frequency, phase, waveform, geometry, material properties, external sources, boundary conditions, simulation time, spatial resolution, field visualization scale, vector density, field-line density.

Every control updates the underlying physical model and triggers recalculation when needed. Use debouncing, incremental updates, caching, and selective recomputation to stay responsive.
</interactive_controls>

<visual_design>
A polished, modern scientific interface: deep dark background with luminous accents; electric blue, cyan, violet, and restrained warm highlights; subtle glow and bloom; smooth animated field lines; fluid camera movement; controlled particle and shader effects; high-quality gradients and depth cues; clean typography; minimal clutter; clear contrast between objects, fields, and annotations. Animations feel highly fluid.

Each visual style signals what kind of phenomenon it shows: a static field, a time-varying field, a propagating wave, moving charged particles, or energy flow along the Poynting vector. Motion along a path is reserved for quantities that actually travel along that path, so field-line animation never suggests that charge or energy flows along every field line.
</visual_design>

<user_experience>
Areas: main simulation canvas; geometry and object panel; physical parameter panel; field visualization panel; equations and explanations; timeline and simulation controls; results and measurement panel.

Two interface levels:
- Beginner: intuitive controls, guided explanations, presets, simplified terminology.
- Advanced: full parameters, solver settings, mathematical detail, numerical diagnostics.

Include contextual tooltips and interactive explanations so users understand both what happens and why. Support responsive layouts and keyboard accessibility.
</user_experience>

<simulation_presets>
1. Single positive point charge
2. Single negative point charge
3. Electric dipole
4. Multiple interacting point charges
5. Infinite line charge
6. Parallel plate capacitor
7. Coaxial cylindrical conductors
8. Charged conducting sphere
9. Straight current-carrying wire
10. Two parallel current-carrying wires
11. Circular current loop
12. Solenoid
13. Toroid
14. Permanent magnet
15. Changing magnetic field inside a loop
16. Faraday induction demonstration
17. Electrostatic field combined with an induced rotational electric field
18. Dielectric material inside a capacitor
19. Conductor with finite conductivity
20. Electromagnetic plane wave propagation

Each preset includes default geometry, parameter values, relevant equations, expected physical behavior, and a short guided explanation.
</simulation_presets>

<accuracy_and_validation>
Automated verification tests against known analytical solutions and trusted numerical benchmarks are part of the deliverable. They cover at least: point-charge fields, dipole fields, parallel-plate fields, infinite straight-wire magnetic fields, circular-loop fields, idealized solenoid fields, Gauss's law, the Gauss–Ostrogradsky theorem, Faraday's law, magnetic field divergence, Lorentz force direction, energy-flow calculations where supported, constitutive-relation consistency, and basic circuit checks for supported R, C, and L networks. Include convergence studies under mesh or grid refinement.

Show solver resolution and numerical uncertainty where meaningful. Every result is labeled as one of: exact analytical solution, numerical approximation, idealized physical model, or visualization-only aid. Report numerical errors and convergence problems to the user explicitly. When a solver fails, show the failure and its reason in place of a result.
</accuracy_and_validation>

<performance>
The application stays responsive while users manipulate complex geometries and many sources. Use GPU-accelerated rendering and geometry instancing where appropriate. Keep high-frequency rendering updates separate from physics recalculation, and when only a visual property changes, re-render from cached results without re-solving.

Quality levels: interactive preview, normal, high accuracy. Users control resolution and see an explanation of the accuracy versus cost trade-off. Long-running simulations show progress and can be cancelled.
</performance>

<documentation>
Cover: system, frontend, backend, and physics engine architecture; numerical methods; equation registry design; API; geometry data model; solver configuration; units and coordinate conventions; numerical assumptions; material constitutive models; circuit-solver method and sign conventions; validation methodology; known limitations; how to add new physical models, equations, and visualization types. Document every equation with its assumptions and physical regime, and keep a traceable link between the mathematical model, its numerical implementation, and the rendered visualization.
</documentation>

Build this as a working, runnable application in coherent, testable modules. Before writing implementation code, inspect the environment and available dependencies, then produce a concise design note covering the architecture, the physical model and solver interfaces, the geometry and material data models, the equation registry, and the main implementation risks and technical limitations.

Then implement in this order of milestones, limited to the phases listed in open_parameters:
- Phase 1 — Foundation: application shell, geometry editor, 2D/3D rendering, state management, basic analytical field solver.
- Phase 2 — Electrostatics: point charges, conductors, E, potential, equipotentials, flux, divergence, Gauss's law, Poisson/Laplace.
- Phase 3 — Magnetostatics: current sources, magnetic fields, Biot–Savart, Ampère's law, magnetic flux.
- Phase 4 — Induction: time-varying magnetic fields, Faraday's law, induced and rotational E fields, Lenz's law demonstrations.
- Phase 5 — Numerical simulation: Gmsh + DOLFINx for supported FEM problems, Meep for supported FDTD problems.
- Phase 6 — Advanced visualization: probes, arbitrary surfaces, flux, divergence/curl visualization, energy density, Poynting vector, advanced 3D tools.
- Phase 7 — Validation and refinement: automated physical tests, accuracy improvements, performance optimization, UX polish.
- Circuit subsystem: implement MNA-based DC, transient, and AC analysis as a separately testable module; integrate it into the UI after the core electrostatic workflow is stable. Do not claim field-circuit coupling until it is physically implemented and validated.

Deliverables: complete source code; frontend; backend API; physics engine; equation registry; presets; automated tests; Docker configuration; example environment configuration; README with setup and run instructions; architecture documentation; numerical validation documentation. Every visible control is wired to real functionality. Any feature that cannot yet be implemented accurately is clearly marked as unsupported in the UI and in the documentation.

Order of perspective: physicist first, numerical engineer second, visual designer third. The result should feel like a beautiful, interactive electromagnetic laboratory that is visually impressive, easy to explore, mathematically transparent, and trustworthy. A user changes a physical parameter, immediately sees the effect on the field, and understands which equations explain it.
