# EMF-Visu architecture

This is the technical reference for the project. It records the approved architecture plan, the
decisions taken since, and what is implemented. Keep it in step with the code: update it in the
same change as any significant architectural decision.

- **Product definition:** the master specification (the complete long-term product). It is not
  reduced by anything in this document; features that are not implemented yet are listed in
  [Implementation status](#10-implementation-status-and-roadmap) and marked unsupported in the UI.
- **Current state:** Phase 1 (Foundation) is implemented. Phase 2 and later are not started.

## 1. Principles

Priorities, in order: physical and mathematical correctness; numerical reliability and transparent
assumptions; intuitive UX; interactive 2D/3D visualization; performance; extensibility.

Rules that follow from them and are enforced in code:

1. **All physics lives in the Python engine.** The frontend and shaders contain no physical
   formulas. They decide where to sample, and how to colour and draw what the engine returned.
2. **Unsupported configurations are refused, never approximated.** `Solver.supports()` returns
   reasons; the API answers `422` with them and the UI shows them in place of a result.
3. **Every result is labelled**: exact analytical solution, numerical approximation, idealized
   physical model, or visualization-only aid, together with solver id and version, assumptions,
   units and status.
4. **A solver is only reported as available when it is.** Planned solvers are listed as
   unavailable with a reason; a queue worker is "online" only if a live worker answers.
5. **Visual-only changes never trigger a solve.**

## 2. Approved decisions

| # | Decision |
|---|---|
| 1 | Phase 2 conductors are analytical-only (verified closed forms). Arbitrary conductor geometry and general boundary-value problems stay explicitly unsupported until the FEM work in Phase 5. No interim finite-difference solver. |
| 2 | All physical calculation stays in the Python engine. Responsiveness comes from debounced requests, coarser preview sampling while dragging, cached results, and selective recomputation. |
| 3 | Docker is the deployment target. Anything not actually executed in containers must be reported as unverified. (In the Phase 1 run the containers were built and run; see `docs/validation.md`.) |
| 4 | This file is the living architecture reference. |

Decisions taken during Phase 1 implementation:

| Decision | Reason |
|---|---|
| TypeScript 5.9 instead of 7.0 | `typescript-eslint` and `openapi-typescript` do not support TS 7 yet. |
| React pinned to 19.3.x | React Three Fiber 9.8 requires `react <19.4`. |
| Celery (Redis broker) as the task queue, one queue per solver kind, tasks addressed by name | Worker images need no API code; the API needs no solver code for queued solvers. |
| `uv` installed from PyPI inside images, base images overridable by build argument | Works behind registry mirrors and TLS-inspecting proxies. |
| Tables created at API start-up; no migration tool yet | One table in Phase 1. Alembic is to be added with the first schema change. |
| Recharts not installed yet | No chart exists in Phase 1; it is added with the first waveform or plot. |
| shadcn/ui used as a pattern (Tailwind + Radix primitives in `components/ui`), not via its generator | Same component model, fewer generated files. |

## 3. System overview

```
 Browser (React, R3F)                Backend API (FastAPI)                Workers (Celery)
┌───────────────────────┐  JSON     ┌──────────────────────────┐  Redis  ┌──────────────────────┐
│ scene store (zustand) │──────────▶│ validation (Pydantic)    │────────▶│ worker-analytical    │
│ sampling request      │           │ orchestrator             │  queue  │  emf_core + emf_worker│
│ query cache (TanStack)│◀──────────│  ├ solver selection      │◀────────│ (worker-fem, Phase 5)│
│ render layer (Three)  │  EMF1     │  ├ in-process fast solve │ results │ (worker-fdtd, Phase 5)│
│ panels, i18n (EN/HU)  │  binary   │  ├ result cache          │         └──────────────────────┘
└───────────────────────┘           │  └ job dispatch, WS      │
                                    │ persistence (PostgreSQL) │
                                    └────────────┬─────────────┘
                                                 │ imports
                                    ┌────────────▼─────────────┐
                                    │ emf_core (physics engine)│  scene model · solvers ·
                                    │ no web dependencies      │  equation registry · wire format
                                    └──────────────────────────┘  · verification references
```

The seven components of the specification map to code as follows:

| Component | Location |
|---|---|
| Frontend | `frontend/src` |
| Backend API | `services/api/src/emf_api` |
| Geometry subsystem | `packages/emf_core/src/emf_core/scene` (model, transforms); meshing arrives with the FEM worker |
| Physics engine | `packages/emf_core/src/emf_core/solvers`, `engine.py` |
| Equation registry | `packages/emf_core/src/emf_core/equations` |
| Visualization subsystem | `frontend/src/render` (consumes results only) |
| Verification subsystem | `packages/emf_core/src/emf_core/verification`, `tests/` |

## 4. Directory structure

```
EMF-Visu/
├─ docker-compose.yml            frontend, api, redis, postgres, worker-analytical
├─ .env.example
├─ pyproject.toml, uv.lock       uv workspace (emf-core, emf-worker, emf-api)
├─ docs/                         architecture.md (this file), validation.md
├─ packages/
│  ├─ emf_core/src/emf_core/
│  │  ├─ units.py                SI constants, quantity metadata (symbol, unit, rank)
│  │  ├─ i18n.py                 LocalizedText {en, hu} for engine-provided text
│  │  ├─ scene/                  models.py (data model), transforms.py (hierarchy)
│  │  ├─ sampling.py             plane grid, lattice, point list
│  │  ├─ solvers/                base.py (interface), catalog.py, analytical/
│  │  ├─ equations/              models.py, data.py, rules.py, registry.py
│  │  ├─ engine.py               run(): select → solve → attach equation statuses
│  │  ├─ presets.py              catalog of the 20 presets (4 available)
│  │  ├─ wire.py                 EMF1 binary container
│  │  └─ verification/           independent reference solutions
│  └─ emf_worker/src/emf_worker/ Celery app, generic task `emf.solve`, job client
├─ services/
│  ├─ api/                       Dockerfile, src/emf_api (routes, orchestrator, db)
│  └─ worker_analytical/         Dockerfile
├─ frontend/                     Dockerfile, nginx.conf, src/
│  └─ src/  api/ state/ sim/ render/ panels/ components/ i18n/ lib/
├─ scripts/export_openapi.py
└─ tests/                        physics/ core/ api/ integration/ e2e/
```

Planned additions, not created yet: `packages/emf_circuits` (MNA circuit solver),
`services/worker_fem`, `services/worker_fdtd`, `docker-compose.solvers.yml`.

## 5. Units and conventions

- SI units everywhere; every transported array carries its unit.
- Right-handed Cartesian coordinates, **z up**. Three.js is configured with the same up axis, so
  no axis conversion exists anywhere.
- Rotations: Euler angles with `R = Rx·Ry·Rz` (Three.js order `'XYZ'`). Object matrix
  `M = T·R·S`; world matrix is the product along the parent chain.
- Electric field direction follows the positive test-charge convention.
- Potential reference for the point-charge model: φ → 0 at infinity.
- Constants: CODATA 2018 (`ε₀ = 8.8541878128e-12 F/m`, `μ₀ = 1.25663706212e-6 H/m`).

## 6. Interfaces

### 6.1 Scene (geometry and material data model)

`emf_core.scene.models.Scene`, schema version 1. The one contract shared by frontend, API and
every solver. Unknown fields and non-finite numbers are rejected.

| Field | Content |
|---|---|
| `dimensionality` | `3d`, `2d_planar` or `2d_axisymmetric`. Explicit, never implied. Only `3d` is implemented. |
| `objects[]` | `id`, `name`, `primitive`, `transform`, `parent_id`, `role`, `source`, `material_id`, `enabled` |
| `primitive` | discriminated on `type`: `point`, `sphere`, `box`, `cylinder`, `ring`, `plane`, `line` |
| `role` | `geometry_only` (inert, excluded from the model and reported as such), `charge_source`, `current_source`, `conductor`, `dielectric`, `magnetic_material` |
| `source` | discriminated on `type`: `point_charge {charge_C}` |
| `materials[]` | `model` (`vacuum`, `linear_dielectric`, `linear_magnetic`, `ohmic_conductor`, `perfect_conductor`), `relative_permittivity`, `relative_permeability`, `conductivity_S_per_m` |
| `boundaries[]` | `fixed_potential`, `ground`, `pec`, `absorbing`, `periodic` (declared; no solver evaluates them yet) |
| `domain` | axis-aligned bounds, background material, potential reference |

The model describes what exists. Whether it can be solved is decided by solvers, so the data model
can run ahead of solver support without the system ever pretending.

### 6.2 Solver interface (version 1)

`emf_core.solvers.base`:

```python
class Solver(Protocol):
    id: str; version: str; kind: Literal["analytical", "fem", "fdtd", "circuit"]
    def supports(self, scene, request) -> Support            # supported + localized reasons
    def solve(self, scene, request, progress=None, cancel=None) -> SimulationResult
```

`SolveRequest` = samplings (plane grid, lattice, points) + quantities + quality.
`SimulationResult` = `ResultHeader` + float64 arrays. The header carries: status, solver id,
version and kind, classification and note, assumptions, warnings, excluded (inert) object ids,
`ModelContext`, discretization and convergence (numerical solvers), sampling descriptions, compute
time, equation statuses, and the array table (name, quantity, symbol, unit, shape, float64 stats).

`SolverCatalog.select()` returns the first registered solver that supports the scene (analytical
solvers are registered first) or raises `UnsupportedSceneError` with every reason.

### 6.3 Worker protocol (version 1)

One generic Celery task, `emf.solve`, on queue `solver.<kind>`. Payload:
`{protocol_version, scene, request}`. The worker runs `engine.run`, stores the EMF1 container in
Redis (`emf:result:<job_id>`, TTL) and returns `{status, header | failure_reason}`. Progress uses
Celery task state; cancellation is cooperative (a Redis flag checked between chunks) plus revoke
for jobs that have not started. A worker image is `emf_core + emf_worker +` the native dependencies
of its solvers and nothing else.

### 6.4 Equation registry

`Equation` (data): LaTeX (differential and integral), name, meaning, intuition, symbols with SI
units, assumptions, limitations, conditions, optional derivation, `used_by` solver ids. All text is
bilingual. `ApplicabilityRule`: `ModelContext → (status, reason)`, where status is one of
*applicable*, *applicable under stated assumptions*, *not applicable*, *not evaluated*; every
status other than *applicable* must come with a reason (enforced). `ModelContext` is produced by
the solver that ran (regime, medium, free charge, currents, conductors, time variation, whether B
is computed, evaluated equations), so statuses are computed and change with the model.

### 6.5 HTTP API (`/api/v1`)

| Method and path | Purpose |
|---|---|
| `GET /health` | API, database and Redis status |
| `GET /solvers` | catalog with real availability and queue-worker liveness |
| `GET /presets` | the 20 presets; unavailable ones carry no scene |
| `POST /simulations` | synchronous solve → EMF1 container; `X-EMF-Cache: hit\|miss`; `422 unsupported` with reasons; `413` above the synchronous point limit |
| `POST /probe` | fields at one point as float64 JSON (not interpolated) |
| `POST /equations/evaluate` | equations with status for the model this scene resolves to |
| `POST /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}`, `GET /jobs/{id}/result` | queued solves, status, cancel, result |
| `WS /ws/jobs/{id}` | job status stream until a terminal state |
| `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}` | saved scenes and view settings |

Errors use `{code, message, reasons[]}` with localized reasons. Frontend types are generated from
the OpenAPI schema (`pnpm gen:api`), so contract drift breaks the build.

### 6.6 EMF1 binary container

```
bytes 0..3   "EMF1"
bytes 4..7   uint32 LE: header length
bytes 8..    UTF-8 JSON ResultHeader (includes the array table)
padding      to a multiple of 8
payload      little-endian float32 arrays; offsets are multiples of 8
```

Fields are computed in float64 and transported as float32. Statistics needing full precision are
computed before the cast and carried in the header. Undefined samples (a sample point on a point
charge) are NaN in the payload and counted in the header; the header itself never contains NaN.
The frontend creates zero-copy `Float32Array` views.

## 7. Simulation data flow

1. An edit updates the scene store.
2. `sim/request.ts` builds the sampling request from the view (slice plane, densities, quality).
3. `physicsKey` = scene without display-only attributes + request. It is the TanStack Query key.
   Names, colour maps, arrow length mode, layer visibility and the selected tool are not in it.
4. The key is debounced (25 ms while dragging, 90 ms otherwise). While dragging, the colour-map
   grid drops to preview resolution.
5. The API validates, selects a solver, and either returns a cached container or solves
   in-process. The server cache key is `engine.physics_fingerprint`.
6. The frontend decodes the container; the render layer turns arrays into instanced arrows and a
   colour-mapped texture. Sample positions are recomputed from the sampling description in the
   header (geometry, not physics).
7. High-resolution solves go to `POST /jobs`, report progress over the WebSocket, can be cancelled,
   and replace the interactive result until the physics changes.

Quality levels: preview 64, normal 192, high 768 samples along the longer slice edge. For the
analytical solver every sample is exact, so quality changes sampling density, not accuracy; the UI
says so.

## 8. Frontend structure

| Folder | Responsibility |
|---|---|
| `api/` | generated types, fetch client, EMF1 decoder |
| `state/` | `sceneStore` (scene, selection, project), `viewStore` (view settings, tool, language, level) |
| `sim/` | request building, physics key, `useSimulation` (queries, high-resolution jobs) |
| `render/` | `Viewport`, `ArrowField` (instanced), `SceneObjects` (drag, gizmo), colour maps |
| `panels/` | objects and presets, parameters, display, equations, results, top bar, status bar, legend |
| `i18n/` | `en.json`, `hu.json`, `useT()`; a test enforces key parity and no hard-coded sentences |

The 2D view is an orthographic camera looking along the slice normal at the same 3D scene. It is a
cross-section of the 3D model, and the UI states this on every 2D view. True 2D models
(`2d_planar`, `2d_axisymmetric`) are a different `dimensionality` and are not implemented.

## 9. Physics implemented in Phase 1

Solver `analytical.electrostatics.point_charges` v1.0.0: ideal point charges at rest in unbounded
vacuum.

```
E(r)   = 1/(4πε₀) Σ qᵢ (r − rᵢ)/|r − rᵢ|³        [V/m]
φ(r)   = 1/(4πε₀) Σ qᵢ /|r − rᵢ|                 [V],  φ(∞) = 0
D(r)   = ε₀ E(r)                                  [C/m²]
```

Classification: exact analytical solution of an idealized model. Sample points closer than
`1e-12 × domain diagonal` to a charge are returned as undefined and counted.

Refused with reasons: any object with role conductor, dielectric, magnetic material or current
source; a charge source that is not a point; boundary conditions; a non-vacuum background; 2D
dimensionalities.

Traceability: equation `coulomb_field` / `coulomb_potential` (registry) →
`solvers/analytical/electrostatics.py::evaluate` → arrays `<sampling>.E`, `<sampling>.phi` →
`render/ArrowField.tsx` and the slice texture in `render/Viewport.tsx`.

## 10. Implementation status and roadmap

| Area | Phase 1 state |
|---|---|
| Application shell, panels, EN/HU, beginner/advanced levels | implemented |
| Geometry editor | add, remove, duplicate, rename, enable/disable, move/rotate/scale (numeric, 2D drag, 3D gizmo), snapping, adjustable bounds. **Not yet:** grouping UI (the data model supports `parent_id`), symmetry settings, alignment tools, cross-section clipping of geometry, CAD/mesh import and export, custom shapes |
| 2D and 3D rendering of one shared scene | implemented (arrows, slice colour map of φ or \|E\|, 3D arrow lattice) |
| State management, caching, selective recomputation | implemented |
| Analytical solver | point charges in vacuum |
| Probe | E, φ, D at a point. Divergence, curl, energy density: Phase 2 / 6 |
| Equation registry | all required equations with computed statuses; derivations are empty |
| Presets | 1–4 available; 5–20 listed as unavailable |
| Persistence | projects (scene + view settings) in PostgreSQL |
| Job queue | analytical worker, progress, cancellation |
| Waveforms, time dependence, timeline | not started (Phase 4) |
| Field lines, equipotentials, flux tools, Gauss demonstrations | not started (Phase 2) |
| Magnetostatics, induction | not started (Phases 3, 4) |
| FEM (DOLFINx, Gmsh), FDTD (Meep) | not started (Phase 5); reported as unavailable |
| Circuit subsystem (MNA) | not started; reported as unavailable |

Acceptance criteria per phase are unchanged from the approved plan:

- **Phase 2:** presets 1–8 with E, φ, equipotentials, field lines, flux and divergence;
  closed-surface flux equals Q/ε₀ within reported quadrature error; subdivided volumes sum to the
  whole; analytical conductor cases only, everything else refused.
- **Phase 3:** presets 9–14; wire, loop and solenoid against references; ∮H·dl = I; B and H both
  shown.
- **Phase 4:** presets 15–17; EMF = −N dΦ/dt; Lenz sign verified.
- **Phase 5:** FEM and FDTD workers as separate images; convergence under refinement; SI unit
  conversion for Meep; failures surfaced.
- **Phase 6:** full probe, arbitrary surfaces and curves, vector-calculus workspace, Poynting
  vector.
- **Phase 7:** full validation suite in CI, performance budgets, accessibility pass.
- **Circuits:** MNA DC, transient and AC against RC, RL and RLC closed forms; labelled uncoupled.

## 11. Known limitations

- Only ideal point charges in vacuum are solved. Everything else is refused or disabled.
- Arrow colour and colour-map ranges cover the 2nd–98th percentile and clamp beyond, because the
  field is singular at point charges. The legend states the range; probe values are exact.
- Charge markers have a display size that is not physical.
- The server result cache is in-memory and per API process.
- No authentication. Rows carry an `owner_id` so it can be added without a schema redesign.
- No database migrations yet.
- The legend overlays the lower-left corner of the viewport.
- Performance was measured only with software WebGL; there are no GPU measurements.

## 12. Extending the system

**New analytical model:** implement `Solver` in `emf_core/solvers/analytical/`, register it in
`default_catalog()`, add reference solutions to `verification/references.py` and tests in
`tests/physics/`, list the equations it evaluates in `evaluated_equation_ids`.

**New worker-based solver:** add `services/worker_<kind>/Dockerfile` (its own environment),
register a solver whose `supports()` needs no native dependency, start the worker on
`solver.<kind>`, add the service to compose. The API and frontend need no change.

**New equation:** add an `Equation` to `equations/data.py` and a rule to `equations/rules.py`. The
registry refuses to load if either is missing or if a symbol is undefined.

**New primitive, source or material:** add a model to the discriminated union in
`scene/models.py`, regenerate frontend types, add rendering in `render/SceneObjects.tsx` and
parameters in `panels/ParametersPanel.tsx`. Solvers refuse it until one supports it.

**New visualization:** add a component under `frontend/src/render` that consumes result arrays.
If it needs a new derived physical quantity, the engine must compute it.

**New UI text:** add the key to both `en.json` and `hu.json`; the parity test fails otherwise.
