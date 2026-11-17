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
  B_z = μ₀I/(2π√D₊) [K + (a² − ρ² − z²)/D₋ · E],
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
  where undefined. Singular set: distance to a wire axis or to the loop wire (√D₋) at most
  1e-12 × domain diagonal (the same position tolerance as for point charges).
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
| Presets | 1–4 and 9–11 available (10 with three variants, 11 with a view hint); the others listed as unavailable |
| Persistence | projects (scene + view settings) in PostgreSQL |
| Job queue | analytical worker, progress, cancellation |
| Waveforms, time dependence, timeline | not started (Phase 4) |
| Field lines, equipotentials | implemented for point charges (Phase 2A) |
| Divergence and curl display, distributional sources | implemented (Phase 2B-1) |
| Gaussian surfaces, closed-surface flux, Gauss and Gauss–Ostrogradsky demonstrations, subdivision | implemented (Phase 2B-2) |
| Open-surface flux, circulation tools, analytical conductor cases, presets 5–8 | not started |
| Magnetostatics (Phase 3A) | infinite straight wires and circular loops in vacuum: B, H, superposition and per-source contributions, B field lines with closed-loop detection, ∇·B, probe, equations |
| Magnetostatics (Phase 3B and later) | not started: solenoids, toroids, permanent magnets, magnetic materials, magnetic flux, Ampère circulation demonstration |
| Induction | not started (Phase 4) |
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

- Only ideal point charges and ideal current filaments (infinite straight wires, thin circular
  loops) in vacuum are solved. Everything else is refused or disabled.
- Magnetostatics: wires are infinite and of zero radius, loops are thin; B and H are singular on
  the filaments (reported as undefined, never clipped). A real wire's finite radius and internal
  field are outside the model. Wires and loops are electrically neutral (no E). Ampère's law is
  applicable but not evaluated (no local J field); its circulation demonstration is Phase 3B.
- Magnetic field lines: closure is decided numerically (tolerance δ, see 9d); where B lines are
  not closed curves (general 3D arrangements of several sources), a line that passes within δ of
  its start cannot be told apart from a closed one. Line density is a display choice (geometric
  seed radii around a single wire enclose equal flux per unit length). In a 2D slice, lines are
  only seeded by sources that cross the slice; a wire lying in the slice seeds none (its B is
  perpendicular to the slice), and the result says so.
- Elliptic integrals: K is evaluated as `ellipkm1(1 − m)` with 1 − m formed directly; far out on
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
