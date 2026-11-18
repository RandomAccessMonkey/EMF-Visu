# EMF-Visu architecture

This is the technical reference for the project. It records the approved architecture plan, the
decisions taken since, and what is implemented. Keep it in step with the code: update it in the
same change as any significant architectural decision.

- **Product definition:** the master specification (the complete long-term product). It is not
  reduced by anything in this document; features that are not implemented yet are listed in
  [Implementation status](#10-implementation-status-and-roadmap) and marked unsupported in the UI.
- **Product definition file:** [master_spec.md](master_spec.md), a verbatim copy of the original
  specification.
- **Current state:** Phase 1 (Foundation), Phase 2A (point-charge electrostatics and field
  visualization), Phase 2B-1 (divergence, curl and local field analysis) and Phase 2B-2 (closed
  surfaces, flux, Gauss and Gauss–Ostrogradsky demonstrations) and Phase 3A (magnetostatic
  sources: infinite wires and circular loops, B and H, magnetic field lines) are implemented.
  Phase 3B and later are not started.

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

Decisions taken during Phase 2A are listed in [section 9a](#9a-phase-2a-point-charge-electrostatics-and-field-visualization).

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

Local preview (before Phase 3), see [local-preview.md](local-preview.md):

| Decision | Reason |
|---|---|
| Published ports bound to `127.0.0.1` by default (`BIND_ADDRESS`) | A local preview should not be reachable from the network unless asked. |
| Health check for the worker (`celery inspect ping`) | Every service now reports health; the start scripts and `docker compose ps` show it. |
| API logs database and Redis reachability at start-up | The API keeps running without them (field solving needs neither), so the log says what will not work. |
| `scripts/start|stop|status` in `.sh` and `.ps1` | One command with prerequisite checks, port checks, health waiting and diagnostics; plain `docker compose` remains equivalent. |
| `.gitattributes` keeps LF endings for shell, Python, YAML, Dockerfiles, nginx config | Windows checkouts with `core.autocrlf` would otherwise break scripts and containers. |

Native run without Docker, see [native-windows.md](native-windows.md):

| Decision | Reason |
|---|---|
| One launcher, `scripts/native.py` (start, stop, status), with thin `native.ps1` and `native.sh` wrappers that run `uv sync` first | The logic is in one cross-platform file that can be tested on any system; the Windows-only part is a few lines of PowerShell. |
| No Redis and no worker unless a Redis server is reachable at start | Redis has no official Windows build. Interactive solving runs in the API process and never needed the queue; the frontend already disables queued jobs when no worker is online. |
| Worker started with `--pool solo` when Redis is present | Celery's default prefork pool does not work on Windows. |
| PostgreSQL kept, as a private cluster in `.local/pgdata` on port 5433, managed with `initdb` and `pg_ctl` | Same database engine and schema as the Docker version, so no data-integrity trade-off; no Windows service; the port avoids a system PostgreSQL on 5432. SQLite was not used because the production schema and behaviour would then differ. |
| Unix socket disabled and TCP bound to 127.0.0.1 in that cluster's `postgresql.conf` | Local-only access; the default socket folder needs root on some Linux systems. |
| Web application served as a production build by `vite preview`, rebuilt when sources change | Matches what the Docker version serves (nginx); no nginx needed on Windows. `vite preview` uses the same `/api` proxy as the dev server. |
| Process records hold the PID, program and start time; records from before the last boot are stale | `stop` must never end an unrelated process that reused a PID. |
| `EMF_E2E_NO_WORKER=1` in the end-to-end script | The queue check then verifies that the job is reported unavailable, instead of running it. |

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
│  │  ├─ geometry/surfaces.py    Gaussian surfaces: model, meshes, validation, inside/outside
│  │  ├─ gauss_situations.py     the nine guided Gauss situations
│  │  ├─ postprocess/            field_lines.py (ODE integration), isolines.py (contours, isosurfaces),
│  │  │                          differential.py (finite-difference diagnostic, never a result)
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
| `primitive` | discriminated on `type`: `group` (container; `kind` `generic` or `dipole`), `point`, `sphere`, `box`, `cylinder`, `ring`, `plane`, `line` |
| `role` | `geometry_only` (inert, excluded from the model and reported as such), `charge_source`, `current_source`, `conductor`, `dielectric`, `magnetic_material` |
| `source` | discriminated on `type`: `point_charge {charge_C}`, `infinite_wire {current_A}` (on a `line`), `circular_loop {current_A}` (on a `ring`) (Phase 3A) |
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

`SolveRequest` = samplings (plane grid, lattice, points; each may override the quantity list) +
quantities + quality + optional derived-product requests (`field_lines`, `equipotentials`,
`isosurfaces`).
`SimulationResult` = `ResultHeader` + float64 arrays. The header carries: status, solver id,
version and kind, classification and note, assumptions, warnings, excluded (inert) object ids,
`ModelContext`, discretization and convergence (numerical solvers), sampling descriptions, compute
time, equation statuses, the derived-product tables with their method metadata, and the array
table (name, quantity, symbol, unit, kind `field` or `geometry`, shape, float64 stats).

`SolverCatalog.select()` returns the first registered solver of the request's field kind
(electric or magnetic) that supports the scene (analytical solvers are registered first) or
raises `UnsupportedSceneError` with the reasons of the solvers of that kind.

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
is computed, number of sources, evaluated equations), so statuses are computed and change with
the model. Each resolved equation also carries `usage`: *evaluated* (the solver evaluates its
formula), *satisfied* (it applies and the field obeys it, but nothing solves it), or *not used*.

### 6.5 HTTP API (`/api/v1`)

| Method and path | Purpose |
|---|---|
| `GET /health` | API, database and Redis status |
| `GET /solvers` | catalog with real availability and queue-worker liveness |
| `GET /presets` | the 20 presets; unavailable ones carry no scene |
| `POST /simulations` | synchronous solve → EMF1 container; `X-EMF-Cache: hit\|miss`; `422 unsupported` with reasons; `413` above the synchronous point limit |
| `POST /probe` | fields at one point as float64 JSON (not interpolated), each charge's contribution, and the singular state at a charge position; with current sources also a `magnetic` block (B, H, ∇·B, ∇·H, each source's Bᵢ/Hᵢ, nearest source, singular state on a filament) |
| `POST /equations/evaluate` | equations with status for the model(s) this scene resolves to (electric and/or magnetic, merged; optionally with Gaussian surfaces); `solver_ids` lists them |
| `POST /flux` | closed-surface flux (EMF1 container with a `FluxHeader`); own cache key |
| `GET /gauss/situations` | the nine guided situations (scene + surfaces) |
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
2. `sim/request.ts` builds the request from the scene's own domain and three view settings only:
   slice plane, slice offset, and 2D/3D mode. No other view setting is an input of the request.
3. `physicsKey` = scene without display-only attributes + request. It is the TanStack Query key.
4. The key is debounced (25 ms while dragging, 90 ms otherwise). While dragging, preview quality
   is used (coarser sampling, looser field-line tolerance).
5. The API validates, selects a solver, and either returns a cached container or solves
   in-process. The server cache key is `engine.physics_fingerprint`.
6. The frontend decodes the container. The render layer draws instanced arrows, a colour-mapped
   texture, and the engine's field-line, contour and isosurface vertices. Sample positions are
   recomputed from the sampling description in the header (geometry, not physics).
7. High-resolution solves go to `POST /jobs`, report progress over the WebSocket, can be cancelled,
   and replace the interactive result until the physics changes.

**What is visual-only.** Arrows are always sampled on a fixed 49 × 49 slice grid and a 13³
lattice; the displayed density is a subsample. Field lines are computed at three density levels
at once; the displayed level is a filter. E and D are both transported where vectors are drawn.
Therefore none of these triggers a physics request: visibility of vectors, field lines, contours,
isosurfaces, grid; vector and field-line density; vector field (E or D); arrow length and size;
colour map; camera, zoom and pan. A physics request is triggered by: any charge magnitude,
polarity or position, the number of charges, the domain, the slice plane or offset, and
switching between 2D and 3D (which changes the derived products requested: planar or spherical
field-line seeding, isosurfaces). Returning to a physical state that was already solved is
served from the client cache.

Quality levels:

| | preview (dragging) | normal | high (queued job) |
|---|---|---|---|
| Slice samples along the longer edge | 65 | 193 | 769 |
| Isosurface lattice per axis (3D) | 21 | 41 | 65 |
| Field-line local error tolerance / domain diagonal | 1e-4 | 1e-5 | 1e-6 |

Field values are exact at every sample at every quality level; quality changes sampling density
and the tolerance of the numerical post-processing. Display settings such as device pixel ratio
never reach the engine.

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

## 9a. Phase 2A: point-charge electrostatics and field visualization

Solver `analytical.electrostatics.point_charges` is now v1.1.0. The physical model is unchanged
(Coulomb superposition in vacuum). Added:

**Superposition terms.** `electrostatics.contributions()` returns each charge's Eᵢ and φᵢ; the
probe reports them next to the totals.

**Singularity versus safeguards.**

| | What | Size | Effect on field values |
|---|---|---|---|
| Mathematical singularity | E, φ, D undefined at a charge position | position tolerance `1e-12 × domain diagonal` (a few ulps of the coordinates) | reported as undefined (NaN in arrays, `null` in the probe) |
| Guard radius | field-line capture and maximum seed radius | `0.5 ×` slice grid spacing (so it follows the sampling resolution) | none |
| Seed radius | where field lines start around a charge | at most the guard radius, a tenth of the distance to the nearest charge, and the radius where the charge's own field is 10× the rest | none |

A probe 0.1 nm from a charge returns the true analytical value. Inside the seed radius a field
line is drawn as the straight radial segment to the charge.

**Field lines** (`postprocess/field_lines.py`). Integration of `dr/ds = ±E/|E|` with
Dormand–Prince RK5(4), adaptive per line, vectorised over lines.

- Seeds: around positive charges, integrated along +E. Around negative charges, integrated
  along −E and reversed; of these only lines that do not reach a positive charge are kept, so
  lines entering from outside the region are present and nothing is drawn twice.
- 2D mode seeds on a circle in the slice plane around charges lying in that plane; 3D mode seeds
  on a Fibonacci sphere. Lines per charge are proportional to |q|.
- Every line stores `start_reason` and `end_reason`: `positive_charge`, `negative_charge`,
  `domain_boundary`, `stagnation_point`, `max_length`, `integration_failure`. The last two are
  numerical outcomes; the UI draws such lines dashed in a warning colour and counts them.
- Capture by a charge requires being inside the guard radius *and* that charge's own field
  dominating, so a weak charge in a strong field does not swallow lines that pass it.
- A zero of the field is detected by magnitude or by a direction reversal within one step.
- A step that leaves the domain is repeated with shorter steps until linear clipping is accurate
  to the integration tolerance.

**Equipotentials** (`postprocess/isolines.py`). Marching squares on the slice grid (2D contours)
and marching tetrahedra on a lattice (3D surfaces). Every vertex is refined on its grid edge with
the Illinois method against the exact potential, to a relative tolerance of 1e-9. A sample that
coincides with a charge is treated as lying beyond every level on the side the potential diverges
to, so level sets are traced correctly around it. Surface normals are the exact `E/|E|`.
Automatic levels are a geometric ladder `K Σ|q| / L × 2^j` per sign present, plus 0 V when both
signs are present (L = domain diagonal).

**Classification.** `ResultHeader.classification` stays `exact_analytical`. Each derived product
has its own `method` block (kind, description, parameters, limitations) and repeats
`field_classification`. Arrays are tagged `field` or `geometry`.

**Schema changes (all additive; `schema_version` and `format_version` stay 1).**

| Where | Change | Compatibility |
|---|---|---|
| Scene | primitive `group` with `kind` | scenes without groups unchanged |
| Sampling | optional `quantities` | omitted = request default |
| SolveRequest | optional `field_lines`, `equipotentials`, `isosurfaces` | omitted = not computed |
| ResultHeader | optional `field_lines`, `equipotentials`, `isosurfaces`; `ArrayEntry.kind`; `ModelContext.source_count` | defaults keep old results valid |
| ProbeResponse | `contributions`, `singular_tolerance_m`, `singular_object_id` | additions only |
| EquationView | `usage`, `usage_note` | additions only |
| Equation registry | `coulomb_field` and `coulomb_potential` are now single-charge laws; new `superposition` | ids unchanged |
| Preset 3 | the dipole is a `group` with two child point charges | same physics |
| Saved view settings | arrow and lattice densities restricted to subsample-compatible values | old values mapped to the nearest on load |

**Dipole.** Two real point charges under a `group` of kind `dipole`. The UI reads q and d from
the children and writes both together; there is no separate dipole state and no ideal
point-dipole model.

**Decisions taken in Phase 2A.**

| Decision | Reason |
|---|---|
| Contours, isosurfaces and field lines are computed in the engine, not the frontend | results carry method metadata; vertices can be refined against the exact potential; testable against references |
| Own marching squares / tetrahedra instead of a library | no new dependency; about 150 lines |
| Line tables in the JSON header, vertices as float32 arrays | no change to the binary container format |
| Field-line density levels are separate complete sets, all computed per request | density becomes a display filter |
| 3D volume arrows off by default | field lines and isosurfaces already fill the 3D view |

## 9b. Phase 2B-1: divergence, curl and local field analysis

Solver version stays 1.1.0 (no change to E, φ or D). Added:

**Pointwise divergence and curl** (quantities `div_E`, `curl_E`, `div_D`, `curl_D`; units V/m²,
V/m², C/m³, C/m³). Each Coulomb term has the Jacobian K qᵢ (I − 3nnᵀ)/|r − rᵢ|³, which is
symmetric and traceless at every r ≠ rᵢ. The solver therefore returns **exact 0** for divergence
and curl wherever E is defined, and NaN ("not evaluated") exactly where E is undefined (the
Phase 2A position tolerance, 1e-12 × domain diagonal). These are analytical identities, not
rounded computations; tests check them independently against the analytical Jacobian (trace and
antisymmetric part below 1e-13 of its scale) and against finite differences.

**Distributional sources.** `ResultHeader.point_sources` lists each nonzero enabled point
charge with its world position and exact δ³ weights: qᵢ/ε₀ [V·m] for ∇·E and qᵢ [C] for ∇·D,
plus, for every plane-grid sampling, its signed distance along u × v and an in-plane flag
(|d| ≤ 1e-9 × domain diagonal, the same tolerance field-line seeding uses). There is no curl
weight: the distributional curl is zero. `electrostatics.enclosed_source_weight()` integrates
∇·E or ∇·D over a volume as the sum of enclosed weights.

**Finite-difference diagnostic** (`postprocess/differential.py`). Central differences of the
exact field at steps h and h/2, Richardson-extrapolated; uncertainty = |J(h) − J(h/2)| +
8 ε |F|max / h per Jacobian entry; h = 10⁻³ × distance to the nearest charge. Used only by the
probe, only at ordinary points, labelled "numerical approximation", always next to the exact
value.

**Probe.** Returns E, φ, D, ∇·E, ∇×E, ∇·D, ∇×D with `kind` (scalar/vector) and `status`
(`defined`, `singular` for E, φ, D at a charge, `not_evaluated` for div/curl at a charge). At a
charge it adds `distributional` (the charge, both δ weights, zero distributional curl). At
ordinary points it adds `diagnostics`.

**Rendering.**

| Layer | Data | Encoding |
|---|---|---|
| ∇·E, ∇·D, \|∇×E\|, \|∇×D\| colour maps (slice) | `arrows.*` arrays (49 × 49 vector grid) | exact 0 → a dedicated "zero" colour; NaN → "undefined" colour; nonzero (none in this model) → diverging or sequential scale; no interpolation between samples |
| Curl vectors | `arrows.curl_*`, `vol.curl_*` | exact zero vector → small ring (in the slice plane on the slice); nonzero → arrow; never rotating or animated |
| Volume scalars (3D) | `vol.*` (13³ lattice, subsampled) | small cubes in the colour-map scale |
| Source markers | `point_sources` | ring in the sign colour plus a label (name, q; for the selected charge also the δ weights). In 2D, a charge off the slice is drawn hollow at its projection with Δ along the slice normal; its own marker sphere is also drawn hollow |

The legend for divergence/curl maps states the counts: "exactly 0 at all N defined samples",
plus any nonzero or undefined samples. The 2D view shows the full 3D operators evaluated on the
slice; a test shows that the 2D-only divergence ∂Eₓ/∂x + ∂E_y/∂y of the same samples would be
−Kq/r³ instead of 0.

**Equation registry.** New: `gauss_displacement_vacuum` (∇·D = ρ), `div_E_point_charges`
(∇·E = Σ (qᵢ/ε₀)δ³), `div_D_point_charges`, `curl_E_electrostatic` (∇×E = 0, ∮E·dl = 0),
`curl_D_vacuum`. The point-charge divergence and the two curl equations are "evaluated by the
solver" (they produce displayed values); Gauss's laws and E = −∇φ are "satisfied, not solved".
Derivations (bilingual) explain the distributional interpretation. `gauss_electric_vacuum`
gained a condition explaining the distributional reading for point charges.

**Schema changes (additive; no version bumps).**

| Where | Change | Compatibility |
|---|---|---|
| `Quantity` | `div_E`, `curl_E`, `div_D`, `curl_D` | old requests unchanged |
| ResultHeader | `point_sources`, `in_plane_tolerance_m` | defaults keep old results valid |
| ProbeValue | `kind`, `status` | defaults `scalar` / `defined` |
| ProbeResponse | `distributional`, `diagnostics`, `diagnostics_method` | additions only |
| Saved view settings | `heatmap` gains div/curl options; `showCurl`, `curlField`, `showSources`, `showVolumeScalars` | unknown values are dropped on load; old projects load unchanged |

**Request size.** The vector grid now carries E, D, ∇·E, ∇×E, ∇·D, ∇×D (14 floats per sample,
49² samples) and the 3D lattice also φ (15 floats, 13³). The fine slice grid is unchanged (E, φ),
so high-resolution results did not grow. Responses are gzip-compressed and the exact-zero arrays
compress well.

## 9c. Phase 2B-2: closed surfaces, flux, Gauss and Gauss–Ostrogradsky

**Geometry subsystem** (`emf_core/geometry/surfaces.py`). `GaussSurface` = id, name, shape
(`sphere`, `cube`, `box`, `cylinder`, `mesh`), centre, rotation (R = Rx Ry Rz), orientation
(`outward` / `inward`), optional subdivision (box and cube; 1–8 cells per axis, at most 512),
and `display` (visible, opacity, normals, colour by flux — visualization only, excluded from
every cache key). Every surface becomes one closed triangle mesh, which is the authoritative
geometry for rendering, classification and integration.

| Shape | Preview mesh | Final mesh | Relation to the ideal shape |
|---|---|---|---|
| Sphere | 24 × 12 (528 triangles) | 64 × 32 (3968) | inscribed polyhedron; max deviation reported |
| Cylinder (axis = local z) | 32 × 2 + caps (192) | 96 × 8 + caps (1728) | inscribed; deviation r(1 − cos π/n) |
| Cube, box | 12 triangles | 12 triangles | exact |
| Custom mesh (engine level) | as given | as given | — |

Validation: finite coordinates; no degenerate triangle (area ≤ 1e-20 L²); every edge shared by
exactly two triangles (closed, edge-manifold); every directed edge used once (consistent
orientation); the link of every vertex is a single cycle (vertex-manifold); one connected
component; nonzero enclosed volume. Self-intersection is **not** checked. A valid mesh is
re-oriented to the requested orientation (signed volume decides its natural orientation).

**Classification** (inside / outside / on the boundary): unsigned distance to the mesh (exact
point–triangle distance) and ray-casting parity (Möller–Trumbore, majority of five fixed rays).
A charge with distance ≤ τ is on the boundary; τ = max(1e-12 L, 64 ε max(L, ‖r_charge‖∞,
‖r_vertex‖∞)) per surface (charges: the largest ‖·‖∞ of all charges), recorded in every result.
The near-boundary highlight (≤ max(0.01 L, 10 τ)) is a visual warning only. Zero charges are
ignored (no field, not singular).

**Surface integral** (`solvers/analytical/gauss.py`): Φ_E = Σᵢ Σ_T qᵢ/(4πε₀) Ω_T,i with the
Van Oosterom–Strackee signed solid angle Ω = 2 atan2(a·(b×c), |a||b||c| + (a·b)|c| + (a·c)|b| +
(b·c)|a|). The expression is arranged so that reversing a triangle (swapping v1 and v2) negates
Ω bitwise. Exact for the represented mesh up to floating point. The floating-point uncertainty
is the measured closure residual |Σ_T Ω − 4πw| (w ∈ {−1, 0, 1}) plus 8ε per triangle, times K|q|.

**Volume integral**: the sum of the Phase 2B-1 δ³ weights qᵢ/ε₀ (qᵢ) of the charges classified
strictly inside, via `enclosed_source_weight`. It never uses solid angles; the surface path
never uses the classification. The result reports both and their difference
(Φ − s·∫∇·E dV with s = ±1 for the orientation). A charge on the surface makes both undefined.

**Local flux density**: E·n and D·n sampled at triangle centroids (pointwise, exact values of
the field there), |E|, and a display class (|E·n| ≤ 10⁻³|E| → "≈ 0"). The integrated triangle
contribution is the solid-angle result, transported separately (`flux_E`, and per charge
`charge_flux_E`).

**Subdivision**: the box is split on a shared vertex grid; each cell face consists of the same
two triangles as its neighbour's, with opposite winding, so shared faces cancel bitwise. Each
cell gets flux per face, total flux, enclosed charge and volume integral. A charge on any cell
boundary strictly inside the parent makes the cell-wise assignment *ambiguous* (no cell owns
it; per-cell volume integrals are not summed), while the parent's volume integral is still
reported.

**Data flow**: the frontend sends `{scene, flux: {surfaces (physics fields only), quality}}` to
`/flux`. Quality is `preview` while something is dragged and `final` otherwise; the quality (and
so the mesh resolution) is part of both the client and the server cache key. The flux request is
independent of the field solve, so moving a surface never re-solves the field. Projects store
surfaces in the existing `view` JSON column under `gauss_surfaces` (no migration); the API
exposes them as `ProjectIn/Out.surfaces`, and older projects load with none.

**2D workspace**: the frontend intersects the engine's mesh with the slice plane (pure geometry)
and draws that outline; all flux values remain 3D surface integrals and are labelled so.

**Equation registry**: new `electric_flux`, `displacement_flux`, `gauss_integral_E`,
`gauss_integral_D`, `divergence_theorem`, `divergence_theorem_E`, `divergence_theorem_D`. A new
usage value `checked` marks equations whose two sides are computed independently and compared.
Statuses depend on whether surfaces exist and whether a charge lies on one.

**Schema changes (additive)**: `ModelContext` gains `gauss_surfaces`, `gauss_boundary_ambiguous`,
`gauss_invalid`, `checked_equation_ids`; `EquationView.usage` gains `checked`; `EquationsBody`,
`ProjectIn`, `ProjectOut` gain `surfaces`. `FluxHeader` is added to the OpenAPI components so
the frontend types are generated.

## 9d. Phase 3A: magnetostatic sources and magnetic field visualization

Design note written before implementation; the implementation follows it (deviations are
listed at the end of this section).

**Sources (scene model, additive).** Two new `source` types, both with role `current_source`:

| Source | Primitive | Geometry taken from the object's world transform | Positive current |
|---|---|---|---|
| `infinite_wire {current_A}` | `line` | a point on the axis = world position; direction d̂ = normalised world image of local +z | along +d̂ |
| `circular_loop {current_A}` | `ring` | centre = world position; radius a = `radius_m` × in-plane scale; normal n̂ = normalised (c_x × c_y) of the world matrix | counter-clockwise about +n̂ (right-hand rule: B along +n̂ on the axis) |

The `line` length is display-only for a wire (the model is infinite); the renderer draws the wire
across the whole region and labels it "∞". A loop whose world transform is not a similarity in
its own plane (|c_x| ≠ |c_y| or c_x ⊥̸ c_y) would be an ellipse and is refused with a reason.
A `current_source` without one of these sources, or with a mismatched primitive, is refused as
before. Old projects contain neither type and load unchanged; `schema_version` stays 1.

**Two independent field solves.** Static charges produce no B, and steady currents in
electrically neutral ideal filaments produce no E. The two static fields are therefore exactly
decoupled, and the system keeps them in separate solves:

- `SolveRequest` quantities are either electric (`E, phi, D, div_*, curl_*` of E/D) or magnetic
  (`B, H, div_B, div_H`); a request mixing both kinds is rejected by validation.
- `analytical.electrostatics.point_charges` (still v1.1.0, unchanged numbers) now ignores
  well-formed current sources instead of refusing them, and states the neutral-wire assumption.
- New `analytical.magnetostatics.filaments` (v1.0.0) supports magnetic requests; it ignores
  point charges.
- `engine.field_subscene(scene, kind)` drops the other kind's sources; every cache key (server
  `physics_fingerprint`, `flux_fingerprint`; client `physicsKey`) is computed from that
  subscene. Moving a wire never invalidates an electric result or a flux result, and moving a
  charge never invalidates a magnetic result.
- The frontend issues the electric request when the scene has charges or has no current
  sources (so existing scenes behave exactly as before), and the magnetic request when it has
  current sources. Two TanStack queries, two keys, two debounced bundles.
- High-resolution jobs queue one job per active field kind (approved decision).

**Physics** (all float64, exact closed forms, no discretization):

- Wire: B = μ₀I/(2π|r⊥|²) d̂ × r⊥, with r⊥ = (r − p) − ((r − p)·d̂)d̂.
- Loop, in local cylindrical coordinates (ρ, z) with m = 4aρ/D₊, D± = (a ± ρ)² + z²,
  1 − m = D₋/D₊ computed directly (no cancellation):
  B_z = μ₀I/(2π√D₊) [K + ((a − ρ)(a + ρ) − z²)/D₋ · E] (factored since Phase 3B.1, see 9f),
  B_ρ = μ₀I z/(2πρ√D₊) · f(m)/(2(1 − m)), f(m) = (2 − m)E − 2(1 − m)K.
  K is evaluated with `scipy.special.ellipkm1(1 − m)` (accurate as m → 1, near the wire),
  E with `ellipe(m)`.
- Near the axis f(m) loses all digits by cancellation (f ≈ (3π/16)m²). For m ≤ m_s = 0.5 the
  solver uses the exact power series f(m) = (π/2) Σ_{n≥2} f_n mⁿ, derived from the hypergeometric
  series of K and E, with all f_n > 0 (no cancellation), and writes f(m)/ρ = (4a/D₊)(π/2)
  Σ f_n m^{n−1}, which is exact at ρ = 0 (B_ρ = 0 there, B_z reduces to μ₀Ia²/(2(a²+z²)^{3/2})).
  Truncation: a fixed 80 terms (f₂…f₈₀), summed by Horner's rule. Because f_n decreases, the
  tail is bounded by f₈₀ m⁸¹/(1 − m); relative to the sum this is below 6e-28 at m = 0.5
  (tested to be below 1e-20). Transition criterion: series for m ≤ 0.5, closed form above, where
  the closed form's relative cancellation error is at most about 2ε/(0.375 m²) ≈ 5e-15.
  Continuity across the transition (a jump below 1e-11 relative between m = 0.5 ± 1e-12) and the
  exact axis limit are tested.
- H = B/μ₀ in vacuum; superposition B = Σ Bᵢ. ∇·B and ∇·H are returned as exact 0 wherever B is
  defined (analytical identity for the Biot–Savart field of a closed or infinite filament), NaN
  where undefined. Singular set: since Phase 3B.1 a source-scaled float64 tolerance (see 9f);
  originally 1e-12 × domain diagonal.
- Validation reference (tests only, never used by the solver): direct numerical Biot–Savart
  integration over the loop with the periodic trapezoidal rule (exponentially convergent for a
  smooth periodic integrand), refined until converged; for the wire, quadrature over a long
  finite segment plus its analytical tail.

**Magnetic field lines** (`postprocess/magnetic_lines.py`, reusing the Dormand–Prince
coefficients and seed helpers of the electric tracer): dr/ds = B/|B|, traced forward from each
seed; if the forward trace does not close, the backward trace from the same seed is added, so a
line that leaves the region is drawn from boundary to boundary. Seeds: on rays perpendicular to
each wire (in the slice for 2D mode, in several planes along the wire in 3D), and on radii of
each loop's disk in meridian planes (every loop field line threads the disk once). End reasons:
`closed_loop`, `domain_boundary` (truncated by the drawing region, not a physical end),
`source_singularity`, `stagnation_point`, `max_length`, `integration_failure`; only the first two
are drawn as normal lines, the others in the numerical-warning style.
Closed-loop criterion, all required: arc length travelled ≥ max(2 d₀, 20 δ), where d₀ is the
distance from the start to the nearest filament (a closed B line links a current, so it is at
least 2 d₀ long); the trace has at some point moved at least d₀ away from its start; the point
of the current step closest to the start lies inside the step and within δ of the start, with
δ = max(5 × accumulated local error estimate, 10 × atol); and the tangent there agrees with the
start tangent (cos ≥ 0.98). The step is represented by the cubic Hermite interpolant of its end
points and end tangents, scaled by the arc-length step (the integrator's own curve to fourth
order), not by the chord, whose sagitta h²/(8r) can exceed δ. The line ends at that point; the
gap is recorded (`closure_gap_m`); the polyline is never joined to its start artificially. A
seed closer than 20 atol + 0.25 guard radius to a line already drawn at the same density level
is skipped (display choice, no duplicates).

**Probe.** `/probe` keeps every electric field unchanged and adds a `magnetic` block when the
scene has current sources: B, |B|, H, |H|, ∇·B, ∇·H, the distance to the nearest current source,
each source's Bᵢ and Hᵢ, and on a wire or loop the singular state with the source identified.

**Equation registry.** New: `b_mu0_h` (B = μ₀H), `h_from_b` (H = B/μ₀), `biot_savart_integral`,
`infinite_wire_field`, `loop_axis_field`, `loop_field_elliptic`, `superposition_magnetic`,
`div_B_filaments`. `gauss_magnetic`, `biot_savart` and `ampere_static` gain explanations
(∇·B = 0 is not B = 0; Ampère is applicable but not evaluated as a local J field in 3A).
For a scene with both kinds of source, `/equations/evaluate` resolves the electric and the
magnetic model context separately and merges per equation: the most applicable status wins
(applicable > under assumptions > not evaluated > not applicable) together with its reason, and
the evaluated/checked lists are united. This is valid because the two static sub-models are
decoupled.

**Presets.** 9: wire along z through the origin, I = 10 A. 10: two wires along z at x = ±0.5 m
with three variants (same direction 10 A / 10 A; opposite 10 A / −10 A; unequal 10 A / 4 A), all
numbered 10 (approved). 11: loop of radius 0.5 m in the xy plane, I = 10 A, opening the 2D view
on the xz cross-section through its axis (new optional `Preset.view_hint`, approved).

**Frontend.** Separate encodings: electric arrows and lines keep their colours; magnetic arrows
use their own palette and legend; B/H magnetic lines are violet with direction cones. The colour
map menu gains |B|, |H| and ∇·B (its own legend). Visual toggles: B arrows, field (B or H),
magnetic lines, current sources, direction indicators (⊙/⊗ for wires crossing the 2D slice,
chevrons along wires and loops), and "contribution" (total or one source; the engine returns
each source's Bᵢ on the vector grid, so switching is visual-only). Objects panel: + wire, + loop.
Parameters: current (A, slider ±100 A plus number), reverse, direction vector (wire), axis
normal and radius (loop), reset to the preset configuration.

**Implementation notes and deviations from the design note above.**

| Item | What was done | Why |
|---|---|---|
| Solver selection | the catalog only asks solvers of the request's field kind (`field_kinds` attribute) | a refused magnetic scene should not list "this solver computes the electric field only" |
| Electric subscene | drops well-formed or disabled current sources, keeps malformed ones | a malformed current source is still refused for electric requests, as before Phase 3A |
| Electrostatic solver | assumption text changed from "no currents" to "currents, if present, are electrically neutral filaments"; field values unchanged | mixed scenes |
| Contribution colour map | with one source selected, the |Bᵢ| or |Hᵢ| map is drawn from the 49 × 49 vector grid (where the engine returns per-source fields), not the fine slice grid | per-source fields on the fine grid would multiply the payload |
| "Each source separately" | arrows of every source at the same points, each in its own colour, log length on a shared scale (vector grid only; the 3D lattice shows the total) | reinforcement and opposition become visible directly |
| Contribution limit | per-source arrays for at most 12 sources; above that a warning | bounded payload |
| Existing test changed | `tests/api/test_api.py`: number of available presets 4 → 7 | presets 9–11 are now available by design; no tolerance changed |
| Existing e2e test extended | `tests/e2e/smoke.cjs`: magnetic checks appended; existing checks unchanged | |

## 9e. Phase 3B: solenoids, toroids, permanent magnets and Ampère's law

Design note written before implementation (deviations are listed at the end of the section).

**1. Existing capabilities found (inspected in the repository).**
`scene/currents.py` turns `current_source` objects into world-space `WireSource`/`LoopSource`
filaments and reports malformed ones. `solvers/analytical/magnetostatics.py` holds the only
circular-loop field (`loop_local`: elliptic integrals, `ellipkm1` near the wire, positive power
series for m ≤ 0.5, exact axis), `loop_field` (arbitrary orientation), `source_fields`
(per-object Bᵢ), the planar/spherical seeding and the solver class.
`postprocess/magnetic_lines.py` traces B lines with Hermite-based closure detection; its
`dist_fn` serves both singular capture and the closure length scale. Electric and magnetic
requests are separated by `engine.field_subscene` (cache keys on the subscene); the
equation registry merges electric and magnetic contexts. `/flux` + `GaussLayer` +
`gauss_surfaces` in the project `view` JSON are the pattern for an independent geometric
tool with its own cache and persistence. `ampere_static` exists (applicable, "satisfied",
deferred to 3B); `constitutive_b_general` (B = μ₀(H + M)) and `constitutive_b_linear`
(B = μH) exist but are never evaluated. `Role.MAGNETIC_MATERIAL` exists in the scene model and is
refused everywhere.

**2. Required extensions (all additive).**

| Area | Extension |
|---|---|
| Scene | primitives `coil {radius_m, length_m, turns}` and `torus {major_radius_m, winding_radius_m, core_radius_m, turns, phase_rad}`; sources `solenoid {current_A}`, `toroid_finite {current_A}`, `toroid_ideal {current_A, relative_permeability}` (role `current_source`), `permanent_magnet {magnetization_A_per_m}` on the existing `cylinder` (role `magnetic_material`) |
| Sources | `current_sources()` expands solenoids and finite toroids into their turns (`LoopSource` with the owning object id), adds `MagnetSource` and `IdealToroidSource`, and validates geometry |
| Physics | one model object that evaluates B, H, ∇·B and evaluation status for all magnetic sources; magnet B by adaptive quadrature over the existing loop field; ideal toroid closed form |
| Numerics | `numerics/quadrature.py`: vectorised adaptive Gauss–Kronrod (G7/K15) used by the magnet and by the Ampère circulation |
| Ampère | `ampere.py`: path model and validation, adaptive circulation of H (and B), independent signed-crossing enclosure; `POST /ampere` with its own cache key; paths persisted under `ampere_paths` in the project `view` JSON |
| Probe | M, inside/outside, constitutive relation, nearest magnet boundary, one-sided limits on sheets and core boundaries, comparisons (ideal long solenoid, other toroid model, dipole far field) |
| Registry | solenoid, toroid, magnet and Ampère equations; usage value `approximation` for idealized comparisons |
| Presets | 12 (finite solenoid), 13 (toroid, variants finite / ideal), 14 (magnet), with domain, view hint, default probe point and default Ampère path |

**3. Physical assumptions.** Steady currents, vacuum background. Solenoid: N coaxial thin
circular turns (no helix, no leads), zₖ = −L/2 + kL/(N − 1), Δz = L/(N − 1) derived; N = 1 is a
single turn at the centre and L is ignored. Finite toroid: N thin loops in meridional planes,
φₖ = φ₀ + 2πk/N, centres R e_ρ,k, normal e_φ,k, current counter-clockwise about +e_φ,k for I > 0;
vacuum (no core). Ideal toroid: continuous winding, circular core (ρ − R)² + z² < b_core²,
H = NI/(2πρ) e_φ, B = μ₀μᵣH inside, B = H = 0 outside (ideal confinement); it is a different
model, not combined with any other magnetic source (a linear core would also respond to the
other sources, which this model cannot represent) — such scenes are refused. Magnet: solid
finite cylinder, prescribed uniform axial M (sign of M = polarity), J_b = 0, K_b = M × n on the
side wall only; B from the side-wall current sheet in vacuum; H = B/μ₀ − M inside, B/μ₀ outside;
m = M πa²L ê. Overlapping magnets are refused. Superposition of B over all filament and
magnet sources; H(r) = B(r)/μ₀ − M(r).

**4. Numerical methods.**

- *Magnet*: B(r) = M ∫_{−L/2}^{L/2} B_loop(r; a, z′, 1 A) dz′ in local cylindrical coordinates,
  using `loop_local`. Adaptive G7/K15 per point, the interval split at z′ = z (where the integrand
  peaks next to the sheet). An interval is accepted when |K15 − G7| ≤ max(rtol·|I|, atol)·(its
  share of the length); otherwise halved; at most 40 levels; points that do not converge are
  reported. rtol by use: 1e-9 for field samples (1e-11 for the probe and Ampère, 1e-7 for
  field-line tracing), atol = 1e-15·μ₀|M|.
- *Sheet tolerance*: a point within 1e-9 × domain diagonal of the side wall or the rim is "on
  the current sheet": B and H are not returned as a unique value (NaN with a boundary count);
  the probe gives one-sided limits at ±δ along the normal. On an end face B is continuous and
  returned; H is one-sided (normal H jumps by M) and marked boundary.
- *Ideal toroid*: closed form; within the same tolerance of the core surface: boundary (probe:
  inside value and 0).
- *Ampère circulation*: Γ_H = ∮ H·dl (and Γ_B = ∮ B·dl) by the same adaptive G7/K15 over the
  exact parametrisation (circle split into 8 arcs; polygon and rectangle per edge), with H from
  the solver (magnets at rtol 1e-11). Stop: total error ≤ max(rtol·|Γ|, 1e-8 A, 1e-8·I_scale),
  rtol per path (default 1e-4), I_scale = Σ |I|·turns over free sources (1 A when there is none,
  documented). Reported: integral, error estimate, subdivisions, evaluations, convergence.
- *Enclosed free current*: independent geometry. Spanning surface = the planar region bounded
  by the path (disk, rectangle, triangulable simple polygon), normal by the right-hand rule.
  Wires: plane crossing, in-region test, sign of d·n. Loops and turns: circle–plane intersection
  (0, 1 tangent, 2 points), in-region test, sign of the current tangent·n. Coplanar disjoint
  curves are unlinked (0); a crossing within tolerance of the path means the path meets a
  filament (circulation undefined); tangencies inside the region are ambiguous. Ideal toroid:
  only coaxial circles (inside the core NI·sign, otherwise 0); other paths: unsupported.
  Magnets contribute no free current. The verdict compares Γ_H with I_enc within
  max(rtol·max(|Γ|, |I|), 1e-8 A, 1e-8·I_scale).
- *Field lines*: seeds on "seed disks" (loop: its disk; solenoid and magnet: midplane disk;
  finite toroid: cross-section half-way between two turns; ideal toroid: core cross-section),
  reusing the Phase 3A loop seeding; the closure length scale also counts magnet sheets and the
  ideal core surface, while singular capture remains filaments only.

**5. Unsupported interactions (refused with a reason).** Ideal toroid together with any other
magnetic source; overlapping magnets; non-axial or non-uniform magnetization; non-uniform or
non-unit world scale of a coil, torus or magnet (dimensions are edited directly); invalid
dimensions; turns that coincide within the solver tolerance; a magnetic core in the finite-turn
model; non-planar, open or self-intersecting Ampère paths; Ampère enclosure for non-coaxial paths
in the ideal toroid model (circulation still computed, right-hand side "unsupported").

**6. Architectural decisions.** Everything stays in the magnetostatic solver and the magnetic
subscene (magnets have role `magnetic_material`, which the electric subscene now drops when
well-formed); the electric solver and its results are untouched. One circular-loop
implementation. Ampère is an independent tool like Gauss: own endpoint, own cache key
(magnetic subscene + path physics), persisted additively. Objects keep their transform for
position and orientation (axis = local +z); dimensions live in the primitive, physics in the
source, so switching the toroid model keeps both radii.

**7. Expected performance.** Cost per sample point is proportional to the number of filament
loops (each turn is one loop evaluation) plus about 30–200 loop evaluations per magnet
(adaptive). The API estimates loop evaluations per synchronous solve (points × (wires + loops +
turns + 60 × magnets)) and answers 413 above 4e7, asking for a queued job, rather than silently
reducing anything. Field lines with magnets use a looser inner quadrature (1e-7).

## 9f. Phase 3B.1: numerical audit of the near-filament field

**Question.** The loop solution clamps m = 4aρ/D₊ to ≤ 1. Does that hide the singularity or cap
near-wire values?

**Findings.**

- The NaN came from `ellipe(m)` for m rounded just above 1: within about 4e-8·a of the wire
  the exact m = 1 − q has q < 4e-16, and 4aρ/D₊ can round above 1. The clamp sets m = 1 there.
  E is continuous at m = 1 (E(1) = 1) and |E(1 − q) − 1| ≤ (q/4)(ln(16/q) + 1) < 1e-14, below
  rounding. K never uses m: it is `ellipkm1(q)` with q = D₋/D₊ formed geometrically, so its
  logarithmic divergence is resolved exactly. **The clamp is mathematically safe and caps
  nothing.**
- A separate, real precision loss was found: the B_z bracket formed a² − ρ² − z², a difference of
  nearly equal squares near ρ = a, losing about ε·a/d relative (5e-9 at d = 1e-8·a, measured
  against an independent reference). It is now (a − ρ)(a + ρ) − z² (a − ρ exact by Sterbenz's
  lemma): with exact local inputs the solution agrees with the reference to ≤ 2.5e-15 relative
  from d = 0.1·a down to d = 1e-15·a.
- From world coordinates, the remaining error is the float64 floor: the solver is backward
  stable, its result is the exact field at a point displaced by about ε·S, where S is the size
  of the local coordinates (loop: a + |p − c|; wire: |p − p₀|). The relative error is therefore
  about ε·S/d; measured 0.4–0.8·ε·a/d for loops at the origin, translated and tilted, and of
  radius 2.5 m.
- The singular tolerance `1e-12 × domain diagonal` did not scale with the source: in a domain
  much larger than a loop, valid points about 1e-10·a from the wire were declared singular; in a
  domain much smaller than a loop, points about 1e-14·a away got values with about 10 % error
  presented as ordinary.

**Method now.**

| Quantity | Rule | Justification |
|---|---|---|
| Singular (B, H undefined) | d ≤ 64·ε·S | the computed d carries ≤ ~6·ε·S rounding error: within 64·ε·S (≥ 10× margin) the point cannot be told apart from the filament |
| Precision bound per point | 8·ε·S/d (`FieldEval.precision`, probe `relative_precision_bound`) | measured error ≤ 0.056 × bound everywhere tested |
| Reported | bound > 1e-8: solve warning (count, worst bound), probe note | values are never capped or replaced |
| Magnet sheet | unchanged: 1e-9 × domain diagonal | B is bounded at a sheet; the one-sided limits differ from the value at distance δ by O(δ/a) |
| Ampère crossing "on the path" | 64·ε·S (filaments) | as above; the domain tolerance stays for planarity and coplanar loops |
| Ampère quadrature near a filament | pieces split at refined closest approaches with breakpoints d·4ʲ | the integrand varies on the scale d; each sub-interval is smooth |
| Ampère float64 floor | ε·S_path/d_min·I_scale > tolerance → not verified | path points carry ≤ ε·S_path rounding; the near stretch contributes ≤ I/2 |

**Consumers.** Solenoids and finite toroids reuse `loops_field` (same per-turn rule; one
singular turn makes only that point singular, other points and the other sources' contributions
are unaffected). The magnet's surface-current quadrature calls `loop_local` directly and benefits
from the factored bracket; near the side wall it converges at every tested distance and the
tangential jump tends to μ₀M linearly in δ. Field lines stop as `source_singularity` within a
display-scale guard radius with steps ≤ d/2, so they cannot cross a filament and the step count
stays bounded.

**Usable range** (float64, relative accuracy of |B|): about ε·S/d, i.e. 1e-8 at d ≈ 2e-8·S,
1e-4 at d ≈ 2e-12·S; singular below 64·ε·S ≈ 1.4e-14·S. Ampère paths verify down to 1e-12 m
from a wire and 1e-8 m from a loop wire (absolute tolerance 1e-8 A when Γ ≈ 0) in the tested
geometry, report `not_converged` closer, and `intersects_source` at about 1e-15 m.

## 9g. Phase 4A: electromagnetic induction (magnetoquasistatic)

**Model.** Prescribed source currents I_j(t) in fixed geometry; B follows I(t) instantly
(displacement current neglected, no retardation or radiation); linear, time-independent
response; no induced currents and no back-reaction; stationary measurement surfaces and paths
(no motional EMF v × B). The UI labels the time controls "magnetoquasistatic", and the solver
warns when L/(c·τ) > 0.01 (L: region size; τ: 1/f, ramp duration or shortest keyframe interval).

**Current profiles** (`scene/profiles.py`): constant, sinusoidal I_dc + I_peak sin(2πft + φ),
ramp (held before and after its interval, never extrapolated) and piecewise-linear (held outside
the keyframes). dI/dt is analytical. At corners both one-sided values are returned; dB/dt and
E_ind then use the right-hand value and are reported as not uniquely defined at that instant. A
profile is an optional, additive field of every current source. When it is present, `current_A`
is derived from it as I(0) (backward compatible; never a second, independent current).

**Fields at time t** (`scene/timedep.py`, magnetostatic solver). For fixed geometry the field is
linear in each current: the existing solver is evaluated with every current replaced by I_j(t)
for B and H, and by dI_j/dt (static sources removed) for ∂B/∂t. Loop fields are computed per
object at 1 A per turn and cached by geometry and sample points (`_UNIT_CACHE`), so changing t
only rescales cached unit fields. Scenes without profiles give exactly the earlier results.

**Vector potential** (Coulomb gauge, ∇·A = 0) of a closed circular filament:
A_φ = μ₀I√D₊/(2πρ) · g(m), g(m) = (1 − m/2)K(m) − E(m), with the same parameter m (not the
modulus k), the same q = D₋/D₊ (K = `ellipkm1(q)`) and the same clamp as the field. g cancels
near the axis (g ≈ πm²/32); for m ≤ 0.5 the exact positive series g_n = c_(n−1)(n−1)/(2n) is
used as A_φ = 2μ₀Ia/(π√D₊)·g(m)/m, exact on the axis. Filament singularity, precision bound and
caching are shared with the field. Implemented for loops and the turns of solenoids and finite
toroids only. E_ind = −Σ_j dI_j/dt A_j,unit. If an infinite wire or ideal toroid changes in
time, E_ind is not evaluated (NaN + reason), never shown partially. E_ind is kept separate from
the electrostatic E: no "complete" electric field is formed.

**Flux, Faraday and mutual induction** (`induction.py`). A measurement surface is the planar
region bounded by an Ampère-type path (same geometry and right-hand orientation). Unit quantities
per current object, cached by geometry (never by time or current): Φ_j = ∫B_j,unit·n dS
(adaptive 5×5 Gauss–Legendre quadtree over polar sectors or ear-clipped triangles; disks are
pre-split into rings graded around radii where filaments pass close), and C_j = ∮A_j,unit·dl
(adaptive Gauss–Kronrod split at closest approaches). At t: Φ = Σ I_jΦ_j + Φ_static,
dΦ/dt = Σ İ_jΦ_j and EMF = −Σ İ_jC_j. Verified if |EMF + dΦ/dt| ≤ rtol·max(|EMF|, |dΦ/dt|,
Σ|İ_j|·max(|Φ_j|, |C_j|)) (an absolute floor for near-zero EMFs); integration errors above it give
the "not converged" states. Lenz: flux trend steady if |dΦ/dt| ≤ 1e-9 of its largest possible
value. Mutual: M₁₂ = Φ_j; M₂₁ = flux of the boundary's own 1 A field (loop formula, or closed-form
straight-segment Biot–Savart) through the source's turn disks; reciprocity compared. Not
evaluated (reported): a filament piercing or lying in the surface (B·n singular inside), a
boundary through a filament, sources without a vector potential (EMF).

**API.** `SolveRequest.time_s`, quantities `dB_dt` (T/s) and `E_ind` (V/m) in magnetic requests,
`ResultHeader.time_sources` and `induction`, probe `time_s` with `time_values`, `POST /induction`,
`POST /profile/sample`, `AmpereRequest.time_s`, project `flux_surfaces`.

## 9h. Phase 4B: moving conductors, motional EMF and the Lorentz force

**Scope.** Stationary sources (every Phase 3/4A source, currents static or following the Phase 4A
profiles) and *moving passive measurement conductors*; a test charge with the Lorentz force and
an optional nonrelativistic trajectory. Out of scope: moving sources, induced currents and
circuits, back-reaction, resistance, heating, friction, relativistic motion, self-fields.

**Motion model** (`scene/motion.py`). A conductor keeps its reference geometry in its local
frame; its pose is `r_world = R(t) r_local + c(t)` with `R(t) = R_rot(t) R0`, `c(t) = c0 + d(t)`
(reference pose = the stored centre and Euler rotation). Translations: stationary, constant
velocity, constant acceleration, sinusoidal; rotation: constant angular velocity about a world
axis through `c(t)` (signed ω, right-hand rule). Each profile may have an active window
`[t_start, t_end]`; outside it the pose is held. Velocities are analytical,
`u = V + ω × (r − c)`. At a window end the left and right velocities differ: the pose reports
both, and the request's `velocity_convention` (`undefined` | `left` | `right`) decides whether
the instantaneous motional EMF is evaluated there (`undefined` → status `motion_undefined`).

**Measurement conductors.** `FluxSurface` gained optional `motion`, `turns` (an explicitly
defined N-turn coil of identical, coincident, series-connected turns: every flux and EMF ×N)
and the `sliding_rod` shape (rails along local x at y = ±L/2, a fixed connecting segment at
x = 0, a rod at x(t) moved by `rod_motion` along the rails only). All are excluded from the
serialized form when absent, so Phase 4A surfaces and projects are byte-for-byte unchanged and
take the Phase 4A code path.

**Moving-surface computation** (`motional.py`, one field model for scenes and analytical tests:
per-source unit B and unit A columns, combined with I_j(t) and dI_j/dt):

- Φ_B(t): adaptive 5×5 Gauss–Legendre quadtree on the *posed* geometry (Phase 4A
  `surface_integrate`, ring pre-splitting near filaments), surface normal turning with the body.
- Transformer EMF ∮E_ind·dl = −Σ dI_j/dt ∮A_j·dl on the instantaneous boundary.
- Motional EMF ∮(u × B)·dl by adaptive Gauss–Kronrod on the moving pieces only (all pieces of a
  rigid body, the rod of the sliding rod), breakpoints graded at filament approaches.
- Generalized EMF = transformer + motional; the electrostatic part of E integrates to zero on a
  closed path and is counted as zero. If a changing source has no E_ind (infinite wire, ideal
  toroid) the result is `unsupported` and labelled *motional-only* (motional EMF, flux and
  dΦ/dt still shown).
- dΦ_B/dt from the flux values only: second-order central differences (one-sided three-point
  formulas at a velocity or current-profile jump, on the chosen side), Richardson-extrapolated,
  steps halved from 0.05 × the characteristic time until two extrapolations agree within 0.1 ×
  the comparison tolerance. Each stencil flux uses the *same frozen quadrature cells* (accepted
  cells of the adaptive integral at t), so the discretization is a smooth function of time.
- Tolerance: rtol × max(|EMF|, |dΦ/dt|, Σ|İ_j| max(|Φ_j|, |C_j|) + ∫|u||B||dl|): the last two
  terms are instant-independent scales, so a zero EMF (u × B ⊥ dl everywhere) is judged
  absolutely, not relatively.
- Statuses: verified, line_not_converged, surface_not_converged, derivative_not_converged,
  singular (filament pierces the surface or touches the boundary), motion_undefined,
  unsupported, invalid (e.g. rod off the rails), failed.
- Uniform-field references (labelled approximations, static fields only): sliding rod
  EMF ≈ −(B·n) L v with B at the rod midpoint; pure rotation Φ ≈ A B·n(t), EMF ≈ −A B·(ω × n)
  with B at the coil centre.

**Lorentz force and particles** (`lorentz.py`). `F_E = q(E_static + E_ind)`, `F_B = q v × B`
with v the particle's own laboratory velocity; powers qE·v and q(v × B)·v (with its rounding
bound). E_static from the Phase 2A point-charge solver, E_ind and B from the magnetostatic
solver at the instantaneous currents. Unavailable E_ind → `partial`; a point on a filament or a
charge → `singular`. Trajectories: Boris scheme (drift–kick–rotate–kick–drift, fields at the
half-step position and time), step ≤ η/ω_c, ≤ η d/|v| (d: distance to the nearest filament or
point charge, so the particle never jumps over a singular region), electric-acceleration and
current-time-scale limits, profile corners as step ends. Stops on singular or unsupported
fields, at c, or at max steps. Warnings above 0.01 c.

**API.** `InductionRequest.velocity_convention`; `SurfaceResult` adds `moving`, `turns`,
`motion` (pose, velocities, rails/rod), `emf_motional_V`, `emf_total_V`,
`generalized_complete`, `motional_samples` (u, B, u × B along the conductor),
`derivative`, `reference`, `warnings`; `POST /lorentz`, `POST /particle` (cached); equations
body `test_charge`; project `test_charge`. Equation registry: category `motion` with 21 new
equations (pose, velocities, motional term and EMF, generalized EMF and Faraday law, moving
flux, sliding-rod and rotating-coil references, N-turn linkage, electric and magnetic force,
no-work theorem, cyclotron frequency and radius, Newton–Lorentz, nonrelativistic validity,
kinetic energy); `lorentz_force` now has a context-derived status.

**Frontend.** Faraday tab: sliding-rod button, motion editor (translation, rotation, windows,
N turns), rod editor, velocity-convention selector, transformer/motional/generalized EMF rows,
derivative method and convergence, uniform-field reference, and waveforms built only from the
computed times. Viewport: moving surfaces drawn from the engine's posed polyline, normal,
velocity and u × B arrows, stationary rails vs. moving rod. Lorentz tab: test charge (species
shortcuts, q, m, position, v), force table with powers, trajectory controls and results
(ω_c, r_c, ΔK/K, kinetic-energy plot); viewport particle, force arrows, trail and the computed
sample at the simulation time (never interpolated). The time bar appears for moving surfaces
and enabled trajectories as well.

**Presets 22–25.** Sliding-rod generator (Helmholtz pair R = 0.15 m, 100 A per loop; rails
0.10 m apart, rod at 0.50 m/s, stops at 0.3 s), rotating rectangular coil (0.08 × 0.06 m,
ω = 2π rad/s about x), proton in the Helmholtz field (helix, r_c ≈ 17 mm), combined
transformer and motional induction (sinusoidal loop, axially oscillating measurement loop).

## 9i. Phase 4C: passive circuits, induced currents, magnetic braking, eddy-current disk

**Scope.** Prescribed sources (all earlier models, stationary, static or Phase 4A profiles) and
*passive* closed conductors driven only by flux change: circles, rectangles, polygons, N-turn
series coils, the sliding-rod circuit (optionally with Phase 4B motion), coupled loops, and an
axisymmetric eddy-current disk of annular bands. Out of scope: applied voltages, networks,
capacitors, RLC, nonlinear elements, skin effect, temperature, general 3D eddy currents (FEM),
radiation, rotational dynamics (rotation stays prescribed; its torque is reported).

**Circuit model** (`circuits.py`). `PassiveCircuit` = a `FluxSurface` geometry (+ motion, turns)
with `Electrical` (preset copper / aluminium / silver or custom σ or ρ_e — never both; wire
radius or cross-section; optional authoritative lumped resistance; self-inductance `thin_loop`
or `user`), an initial current and, for the sliding rod, `Mechanics` (prescribed | dynamic).
R = ℓ/(σA) with ℓ = perimeter × N; ℒ = N² μ₀a[ln(8a/r_w) − 2] for circles with r_w/a ≤ 0.1
(the external, surface-current form; the internal μ₀a/4 of a uniform current is not included),
otherwise a user value is required; an ideal filament never gets an automatic ℒ.
Measurement surfaces stay measurement surfaces: the UI converts one explicitly.

**Coupled equations.** λ_i = Φ_i,ext + Σ L_ij I_j, R_i I_i + dλ_i/dt = 0, solved as
L(t) İ = EMF_ext − RI − L̇ I with EMF_ext = EMF_tr + EMF_mot: EMF_tr = −Σ_s İ_s Φ_is (analytical
source rates × unit fluxes: Maxwell's coaxial formula where every source is a coaxial circle,
else Phase 4A surface quadrature); EMF_mot = N∮(u × B_prescribed)·dl (Phase 4B). Motion
relative to other passive circuits enters only through L̇ (central differences of the
geometric L(t)). Each contribution is counted once — tested by R I + dλ/dt = 0 on the
solution. SciPy Radau (implicit, adaptive; analytic Jacobian for fixed geometry), split at
every profile corner, events when a sliding rod leaves its rails or reaches the fixed end.
Output on the playback grid; the frontend shows the sample at or before the simulation time.

**Mutual inductance and matrix checks.** Coaxial circles: Maxwell's closed form (series for
small k). Otherwise the flux of one circuit's 1 A field (loop field / exact segment
Biot–Savart) through the other's surface; computed both ways when neither pierces the other
(reciprocity ≤ 1e-6 required), one way when one does, rejected when the circuits are linked or
their conductors touch. L must be positive definite (smallest eigenvalue > 1e-12 × largest);
a nonphysical matrix is rejected with an explanation, never adjusted.

**Field feedback.** `SolveRequest.passive` (and `ProbeBody.passive`) carries the solution sample
(geometry, I, dI/dt). The magnetostatic solver adds Σ I_j B_j,unit to B and H (arrays
`B_prescribed`, `B_passive`), Σ İ_j B_j to ∂B/∂t, −Σ İ_j A_j to E_ind (segment vector potential
`segments.py`, its curl tested against the segment field); points on a passive filament are
singular. ∂B/∂t and E_ind of a moving current-carrying circuit (∂A/∂t from motion) are reported
unavailable. Field lines follow the total field. Phase 4A/4B measurement surfaces see the
prescribed sources only.

**Forces and braking.** F = I N∮dl × B_ext and τ about the centre, B_ext = prescribed + other
passive circuits (own singular field excluded); for the rod only the rod segment (rails fixed).
Dynamic rod: m ẍ = F_ext + F_em − b ẋ solved with the currents; its static-field integrals
(∮dl × B_k and dΦ_k/dx per source column) are tabulated as piecewise Chebyshev series in x
verified against direct quadrature to 1e-9 (Φ_k(x) by exact integration of the series). The
braking statement is derived from the computed force and velocity.

**Eddy-current disk.** N_r equal bands; R_k = 2πr_k/(σtΔr_k); ℒ_k from an equivalent round wire
r_eq = √(tΔr/π) where r_eq/r_k ≤ 0.1, else the geometric-mean-distance method
M(r, r, 0.2235(t + Δr)); mutuals by Maxwell, averaged over 6×6 Gauss points per cross-section
for bands closer than 3t + Δr. Validity: Δr ≥ t/2 (finer bands make the matrix unreliable and
are refused); axisymmetry required (every source and other circuit coaxial, no finite toroid,
no moving circuit). J_φ ≈ I_k/(tΔr_k). Refinement 10 → 20 → 40 bands changes J by ≈ 1 % in
preset 28.

**Energy.** States integrated with the currents: Q_R = ∫ΣRI², W_src = ∫I·EMF_tr,
W_mot = ∫I·EMF_mot, W_geom = ∫½IᵀL̇I, kinetic energy from the rod's velocity, damping heat and
external work. Residual (reported as computed): without rod dynamics ΔW_m + Q_R + W_geom −
W_src − W_mot; with it ΔK + W_damp − W_ext + ΔW_m + Q_R − W_src. Instantaneous power residual
with the independently integrated force: F·u + P_R + dW_m/dt − P_src.

**API, UI, presets.** `POST /circuits` (cached), probe and simulation `passive`, equation body
`circuits`/`eddy_disks`, project `circuits`/`eddy_disks`. Circuits tab (create, convert a
measurement surface, edit electrical/mechanical/disk parameters, results at the sample, energy
table, inductance matrix, I(t)/EMF/velocity/energy plots, per-band table and J(r)); viewport
circuits coloured by current sign with direction cones; B_prescribed / B_passive as vector
fields and maps; probe sections. Equation category `circuits` (25 equations). Presets 26–29.

## 9j. Coaxial cable: ideal TEM transmission line

A standalone analytical module (`emf_core.coax`, routes `POST /coax/snapshot` and
`POST /coax/trace`). It does not use the scene's charges or currents: while it is active the
viewport shows the cable instead of the scene. Exactly what is implemented is an **ideal,
lossless, single-mode TEM model**:

- Geometry: inner conductor radius a, outer conductor inner radius b and outer radius c, length
  L; validated 0 < a < b < c, b/a ≥ 1 + 10⁻⁶, L > 0, εr > 0, μr > 0, f > 0, σ > 0, finite
  values, end > start (pydantic on the engine side, `sim/coax.ts` in the client, so an invalid
  edit never reaches the engine or the renderer).
- Assumptions: perfectly conducting conductors; homogeneous, linear, isotropic, non-dispersive,
  lossless dielectric (ε = ε₀εr, μ = μ₀μr) filling a < r < b; TEM mode only. All fields are
  zero inside the conductors and outside the shield (equal and opposite conductor currents and
  charges). The approximate TE₁₁ cutoff f_c ≈ v_p/(π(a + b)/2) is reported, with a warning when
  the excitation reaches it (Gaussian: 3/(2πσ), the 1 % point of its spectrum).
- Fields (a < r < b): E_r = V/(r ln(b/a)), D = εE, H_φ = I/(2πr), B = μH, S = E × H = S_z ẑ
  with S_z = VI/(2πr² ln(b/a)).
- Line parameters: L′ = μ ln(b/a)/(2π), C′ = 2πε/ln(b/a), Z₀ = √(L′/C′), v_p = 1/√(L′C′),
  t_delay = L/v_p (SI internally, engineering units in the UI). c enters no TEM parameter.
- Conventions: z = 0 at the source, z = L at the load; V = inner minus outer potential;
  I > 0 flows along +z on the inner conductor (−I on the shield); φ̂ = ẑ × r̂ (right-handed).
- Excitation: f(t) is the forward wave the source launches at z = 0. Sinusoid
  f = A sin(2πft) for t ≥ 0 and 0 before (switched on at t = 0, so a wave front travels down
  the cable); Gaussian f = A exp(−(t − t₀)²/(2σ²)), σ the standard deviation.
- Waves and reflections (closed form, no circuit solver): with T = t_delay,
  V_f = Σₙ(Γ_LΓ_S)ⁿ f(t − 2nT − z/v_p), V_b = Γ_L Σₙ(Γ_LΓ_S)ⁿ f(t − 2(n + 1)T + z/v_p),
  V = V_f + V_b, I = (V_f − V_b)/Z₀. Load: matched Γ_L = 0, open +1, short −1. Source end:
  matched Γ_S = 0 (default), short −1 (ideal voltage source), open +1 (ideal current source).
  The sum has one term unless both ends reflect; more than 20 000 round trips in the time range
  are refused (422).
- Snapshot (one simulation time, the playback grid point): parameters; V, I and their wave
  components at the inspected z and along the cable (241 points); cross-section arrow samples
  (4 log-spaced rings × 16 angles) and field lines (16 radial E lines; 8 H circles at
  log-spaced radii, so line density ∝ |H| ∝ 1/r); 3D station samples; the Poynting check
  (∬S_z dA by Gauss–Legendre in r (48) × midpoint in φ (64) of the pointwise E × H, against
  V·I); the arrow scale (max |V|, |I| over the playback range); interface quantities; the probe.
- Maxwell's laws, evaluated faithfully at a point of the dielectric (the probe point if it lies
  there): ∇·D and ∇·B by central finite differences (zero to round-off); (∇×E)_φ = ∂E_r/∂z
  against −∂B_φ/∂t and (∇×H)_r = −∂H_φ/∂z against ∂D_r/∂t (J_free = 0), each side both
  analytic (from the exact wave derivatives) and as an independent central finite difference
  of the field; the vanishing z components are reported, not assumed; the telegrapher
  equations likewise. The curls are nonzero wherever the wave varies. At a switched-on
  sinusoid's front the derivative jumps; the check is then reported as non-smooth.
- Interfaces (distributional, never shown as volume values): ρ_s(a) = D_r(a⁺) = C′V/(2πa),
  ρ_s(b) = −C′V/(2πb), K_z(a) = I/(2πa), K_z(b) = −I/(2πb), Q′ = C′V. A probe within 10⁻⁹ b of
  r = a or r = b reports the dielectric-side limit with these surface densities.
- Equations: category `coax` (16 entries, EN/HU) plus Gauss, Faraday, Ampère–Maxwell, the
  linear constitutive laws, the Poynting vector and the energy density with coax-specific
  statuses; every other registry entry is "not applicable" in this model (`equations/coax.py`
  wraps the existing rules; they are unchanged without the coax model).
- UI: Coax tab (geometry, dielectric, excitation, terminations, time range in ns,
  cross-section position, layer switches, parameters, V/I with wave components, the power
  check, waveforms V(z), Z₀I(z), V±(z) and V(t), Z₀I(t), V(L, t), P(t), probe, Maxwell checks,
  interface quantities); 2D true-scale cross-section with dimensions, radial E and azimuthal H
  arrows and lines, ⊙/⊗ for S; 3D cut-away cable (radial dimensions × 0.12 L/c, stated on
  screen) with V(z, t) on the dielectric's cut faces and E, H and S arrows at 65 stations.
  Arrow length ∝ |field| / its maximum over the playback range (linear `ArrowField` mode).
  Presets 30 (100 MHz sine, matched) and 31 (Gaussian pulse, open). Projects store `coax`.

## 10. Implementation status and roadmap

| Area | Phase 1 state |
|---|---|
| Application shell, panels, EN/HU, beginner/advanced levels | implemented |
| Geometry editor | add, remove, duplicate, rename, enable/disable, move/rotate/scale (numeric, 2D drag, 3D gizmo), snapping, adjustable bounds, dipole groups. **Not yet:** general grouping UI, symmetry settings, alignment tools, cross-section clipping of geometry, CAD/mesh import and export, custom shapes |
| 2D and 3D rendering of one shared scene | implemented (E or D arrows, slice colour map of φ or \|E\|, field lines, equipotential contours, 3D equipotential surfaces, 3D arrow lattice) |
| State management, caching, selective recomputation | implemented |
| Analytical solver | point charges in vacuum |
| Probe | E, φ, D, ∇·E, ∇×E, ∇·D, ∇×D at a point, per-charge contributions, singular state with the distributional statement, finite-difference check (advanced). Energy density: later milestone |
| Equation registry | all required equations plus superposition, with computed statuses and usage; derivations are empty |
| Presets | 1–4, 9–16 and 21–31 available (22–25: moving conductors and a test particle, Phase 4B; 26–29: passive circuits, Phase 4C; 30–31: coaxial TEM cable) (10 with three variants, 13 with two, view hints incl. a default probe point, 12–14 with default Ampère paths, 15, 16, 21 with measurement surfaces and a time range); 5–8 and 17–20 listed as unavailable |
| Persistence | projects (scene incl. current profiles + view settings incl. simulation time and range + Gaussian surfaces + Ampère paths + Faraday measurement surfaces) in PostgreSQL |
| Job queue | analytical worker, progress, cancellation |
| Time-dependent currents, timeline | implemented (Phase 4A): constant, sinusoidal, ramp and piecewise-linear profiles with analytical dI/dt, deterministic playback |
| Field lines, equipotentials | implemented for point charges (Phase 2A) |
| Divergence and curl display, distributional sources | implemented (Phase 2B-1) |
| Gaussian surfaces, closed-surface flux, Gauss and Gauss–Ostrogradsky demonstrations, subdivision | implemented (Phase 2B-2) |
| Ampère circulation on closed planar paths (circle, rectangle, polygon) | implemented (Phase 3B): adaptive quadrature of H, independent signed-crossing enclosed current, verification states |
| Open-surface flux, general circulation tools, analytical conductor cases, presets 5–8 | not started |
| Magnetostatics (Phase 3A) | infinite straight wires and circular loops in vacuum: B, H, superposition and per-source contributions, B field lines with closed-loop detection, ∇·B, probe, equations |
| Magnetostatics (Phase 3B) | finite discrete-turn solenoids, finite-turn toroids (vacuum) and the ideal continuous-winding toroid (linear core), uniformly magnetized cylindrical permanent magnets (bound sheet current), B and H with material regions, sheet and core boundaries with one-sided limits, idealized comparisons (ideal long solenoid, ideal toroid, dipole far field), axis profile |
| Magnetostatics (later) | not started: nonlinear or field-dependent materials, demagnetization, magnetic flux through open surfaces, general magnetic materials |
| Induction (Phase 4A, magnetoquasistatic, stationary geometry) | B(t), ∂B/∂t, Coulomb-gauge vector potential of closed circular currents, E_ind = −∂A/∂t, magnetic flux through stationary surfaces, Faraday's law verified independently, Lenz signs, mutual inductance with reciprocity |
| Moving conductors (Phase 4B) | rigid motion profiles, sliding-rod circuit, N-turn measurement coils, motional EMF ∮(u×B)·dl, generalized Faraday law verified against finite differences of the moving-surface flux, Lorentz force probe, Boris test-particle trajectories |
| Passive circuits (Phase 4C) | induced currents of passive loops, coils and the sliding rod, coupled RL dynamics with mutual inductance, induced-current fields, forces, dynamic magnetic braking, axisymmetric annular-band eddy-current disk, energy accounting |
| Coaxial cable (TEM) | ideal lossless coaxial transmission line: analytical E, D, H, B, S; L′, C′, Z₀, v_p, delay; sinusoidal and Gaussian excitation; matched/open/short load with optional source re-reflection; Poynting power vs V·I; Maxwell and telegrapher checks; interface charges and currents; 2D cross-section and 3D cut-away |
| Induction (later) | not started: applied voltages and networks (Phase 5), moving sources, rotational dynamics, general 3D eddy currents (FEM), full-wave fields |
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

- Coaxial cable: ideal lossless single-mode TEM model only (perfect conductors, no conductor or
  dielectric losses, no skin effect, no dispersion, no higher-order modes or radiation; the
  TE₁₁ cutoff is only reported). Terminations are matched/open/short (no general load
  impedance); the source is a launched forward wave with matched/short/open re-reflection, not
  a Thevenin source with a voltage divider. Fields are only available in the module's own view
  (they are not superposed with the scene's sources). The 3D view exaggerates radial
  dimensions; the probe works in the 2D cross-section.
- Phase 4C: passive circuits only (no applied voltage, networks or capacitors); constant
  conductivity; thin-conductor (uniform current, no skin effect) model; the thin-loop ℒ omits
  the internal inductance; rectangles/polygons/rods need a given ℒ (constant, also for the rod
  whose area changes). Rotational dynamics is not solved. Prescribed sources are not affected
  by induced currents. Moving rigid circuits are slower (line integrals at every solver step).
  The eddy disk is an axisymmetric reduced-order approximation valid for Δr ≥ t/2. Phase 4A/4B
  measurement surfaces do not include passive-circuit fields. With the specified parameters of
  preset 27 the braking is weak (≈ 0.2 % speed loss) and the rod leaves the rails at t ≈ 0.40 s.

- Phase 4B: only measurement conductors move (rigidly, or the sliding rod's rod); sources stay
  fixed. The EMF is an open-circuit EMF: no current, resistance, back-reaction or force on the
  conductor. Motion is nonrelativistic (Galilean u × B). Rotation axes pass through the
  conductor's centre. A moving surface's mutual inductance is not reported. dΦ/dt of a moving
  surface is a converged finite-difference estimate with an error bound, not an analytical value.
  Test particles: nonrelativistic, no radiation reaction, self-field or interactions; the
  trajectory display shows the computed sample at or before the simulation time.

- Phase 4A induction is magnetoquasistatic and stationary: no motional EMF, no induced currents or
  circuits, no eddy currents or back-reaction, no retardation or radiation. E_ind is only the
  induced part of E; the complete electric field of a time-dependent system is not computed.
- E_ind is available for closed circular currents only; a time-varying infinite wire or ideal
  toroid makes E_ind and the EMF unavailable (B(t), ∂B/∂t and the flux remain).
- The flux through a surface that a filament pierces or lies in is not evaluated (finite for a
  transverse crossing, but the quadrature does not resolve that singularity). Linked coil pairs
  therefore need a measurement surface that avoids the turns (as in preset 21).
- The reciprocal M₂₁ is computed for loop-type sources; a measurement loop that passes through a
  source turn's disk gets M₁₂ only. The Faraday comparison's rtol must be ≥ 1e-10; the near-axis
  vector-potential reference used in the tests loses accuracy as ε·a/ρ (validated against the
  analytical axis limit instead).
- During playback, field lines are not recomputed (they are when paused); the probe, flux and
  Faraday results follow every time step.
- Only ideal point charges and ideal current filaments (infinite straight wires, thin circular
  loops) in vacuum are solved. Everything else is refused or disabled.
- Magnetostatics: wires are infinite and of zero radius, loops are thin; B and H are singular on
  the filaments (reported as undefined, never clipped). A real wire's finite radius and internal
  field are outside the model. Wires and loops are electrically neutral (no E). Ampère's law is
  checked in integral form on user paths (Phase 3B); the local form ∇×H = J is satisfied but not
  evaluated (no volume current density J field).
- Phase 3B models: solenoid turns are separate coaxial circles (no helix pitch, no lead wires,
  no wire thickness); finite toroid turns likewise, in vacuum. The ideal toroid is a
  self-contained idealization (field confined to a linear core, exactly zero outside) and is
  refused in combination with any other magnetic source. Permanent magnets are rigid, uniformly
  magnetized cylinders: M does not respond to other fields (no demagnetization, hysteresis or
  B–H curve; B_r = μ₀M is only an input parameterization); overlapping magnets are refused;
  only cylinders are supported. Coils, tori and magnets must not be scaled (refused).
- Magnet fields come from adaptive quadrature over the sheet current (rtol 1e-9 for maps, 1e-11
  for the probe and Ampère, 1e-7 for field lines); on the sheet itself (within 1e-9 of the
  domain diagonal) B and H are not defined and the one-sided limits are reported; on an end face
  B is defined and H is not. A grid point can therefore show a gap exactly on a magnet surface.
- Ampère paths must be closed, planar and simple; self-intersection is detected for polygons.
  For the ideal toroid the enclosed current is only available for paths coaxial with it
  (otherwise the status is "unsupported"). A path through a filament is reported, not
  integrated. Paths cannot be dragged in the viewport (numeric editing only).
- Synchronous solves are limited by a cost model (about 4·10⁷ loop-field evaluations; a magnet
  counts 60 per point); larger requests return 413 and must use the job queue.
- Magnetic field lines: closure is decided numerically (tolerance δ, see 9d); where B lines are
  not closed curves (general 3D arrangements of several sources), a line that passes within δ of
  its start cannot be told apart from a closed one. Line density is a display choice (geometric
  seed radii around a single wire enclose equal flux per unit length). In a 2D slice, lines are
  only seeded by sources that cross the slice; a wire lying in the slice seeds none (its B is
  perpendicular to the slice), and the result says so.
- Near-filament accuracy (Phase 3B.1, see 9f): float64 limits the relative accuracy of B and H
  to about 8·ε·S/d at distance d from an ideal filament (S: size of the source's local
  coordinates); this is reported above 1e-8, never hidden or capped. Points within 64·ε·S are
  singular. Wires keep their own scale (|p − p₀|), so a wire's singular tolerance grows with
  the distance along the wire from its reference point.
- Elliptic integrals: K is evaluated as `ellipkm1(q)` with q = D₋/D₊ formed geometrically; far out on
  the axis (z ≫ a) the B_z bracket loses about (z/a)² ε of relative accuracy; near the axis the
  B_ρ series is used (see 9d).
- The individual-contribution colour map uses the coarser vector grid.
- Field lines: in a 2D cross-section their spacing does not represent |E|. In 3D it does only
  approximately (rounded line counts, uniform seeds on a small sphere). Lines end at the edge
  of the region of interest although the physical line continues. If charges lie off the slice
  plane, the 2D view shows 3D lines projected, which can appear to cross.
- A field line that should end exactly at a zero of the field is only produced when a seed
  lies on that separatrix; neighbouring lines turn away sharply, which is correct.
- Equipotentials: chords and flat triangles deviate from the true level set by about
  cell² × curvature / 8; level-set components smaller than a grid cell are missed unless a grid
  node coincides with the charge; surfaces are cut at the region boundary. Levels are a display
  choice.
- 3D solves at normal quality take roughly 0.2–0.5 s for the presets, so the 3D view updates
  less smoothly than the 2D view after a change.
- Divergence and curl maps are sampled on the 49 × 49 vector grid, not the finer colour-map
  grid. For this model every defined sample is exactly 0, so nothing is lost; with a future model
  that has nonzero divergence or curl the resolution of these maps would matter.
- Source labels show full δ weights only for the selected charge, to avoid overlap; all weights
  are listed in the Results panel.
- The finite-difference diagnostic needs a step much smaller than the distance to the nearest
  charge; within about 1e-9 m of a charge its uncertainty is dominated by round-off.
- Gaussian surfaces: self-intersecting custom meshes are not detected; custom meshes can only
  be created through the API (no UI import); subdivision is for boxes and cubes only; surfaces
  cannot be dragged in the 2D view (numeric editing, or the 3D gizmo); the per-patch inspector
  is 3D only. While a surface is dragged, the drawn mesh lags the gizmo until the preview
  result arrives.
- Many charges: the total number of field lines is capped at 1500 per request by lowering the
  lines per charge.
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
