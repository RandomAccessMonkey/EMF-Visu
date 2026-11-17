# Validation

What is checked, how, and what was actually executed. Update this file whenever tests are added
or a verification status changes.

## How to run

```bash
uv run pytest                      # physics, core, API, integration (203 tests)
uv run ruff check . && uv run mypy packages/emf_core/src packages/emf_worker/src services/api/src
cd frontend && pnpm typecheck && pnpm lint && pnpm test && pnpm build
node tests/e2e/smoke.cjs http://localhost:8080      # against a running stack
```

Integration tests need Redis and PostgreSQL; they skip themselves when a service is unreachable.
The end-to-end script needs Playwright with Chromium and a running stack.

## Physics validation (Phase 1 solver)

Reference solutions in `emf_core/verification/references.py` are written independently of the
solver. Tests are in `tests/physics/test_point_charges.py`.

| Check | Method | Tolerance |
|---|---|---|
| Single charge, \|E\| and φ | closed form, 2 charges × 3 distances, off-origin, oblique direction | 1e-12 relative |
| Direction convention | E points away from positive, toward negative charge | sign and parallelism |
| Dipole on axis and on the bisector | closed forms | 1e-12 relative |
| Dipole symmetry plane | φ = 0 exactly, no transverse E | exact |
| Dipole far field | \|E\| ∝ 1/r³ (ratio at r and 2r is 8) | 1e-5 relative |
| Superposition | E and φ of two charges equal the sums | 1e-13 relative |
| Constitutive relation | D = ε₀E in vacuum | exact |
| Gauss's law | flux through a sphere by Gauss–Legendre × uniform quadrature (48 × 96 nodes) with both, one, and no charge enclosed | 1e-6 of q/ε₀ |
| Zero divergence ≠ zero field | the no-charge sphere has zero net flux and non-zero field everywhere | asserted |
| E = −∇φ | central differences at h, h/2, h/4; error ratio ≈ 4 (second order) | ratio within 5 % |
| Curl-free, divergence-free away from charges | finite-difference Jacobian | 1e-5 of \|E\|/r |
| Singular points | masked as undefined, counted, warned | asserted |
| Constants | 1/√(ε₀μ₀) = c | 1e-9 relative |

The analytical solver has no discretization, so there is no mesh convergence study for it. The
only convergence study in Phase 1 is the finite-difference check of E = −∇φ above, which verifies
the test method's order. Mesh and grid refinement studies belong to the numerical solvers
(Phase 5).

## Physics validation added in Phase 2A

Existing tolerances were not changed. Three tests failed during development; each was
investigated instead of loosened:

- Boundary exit points did not converge with the tolerance, because the last segment was clipped
  linearly however long it was. Fixed in the integrator (exit steps are shortened first).
- Isosurfaces had cracks, because a shared lattice edge was refined in different orientations
  from different cells, and cells touching a charge were skipped. Fixed (canonical edge
  orientation; signed treatment of singular samples).
- One bound written before running the code (2e-4) was below the theoretical chord error
  (2.4e-4). It was replaced by the theoretical bound, which the code meets.

One Phase 1 test fixture was updated: a hand-built model context now also sets the new
`source_count` field, because Coulomb's law is reported as "applicable under assumptions" for a
scene with no charge.

| Check (file) | Method | Tolerance |
|---|---|---|
| Single + charge lines (`test_field_lines`) | start on the charge, straight, radial, end on the boundary; planar and spherical seeding | direction 1e-9, boundary 1e-12 |
| Single − charge lines | start on the boundary, end on the charge, stored along +E | same |
| Dipole lines | independent invariant q₁cosθ₁ + q₂cosθ₂ = const along every line; stay in plane exactly; tangent ∥ E; as many lines enter − as leave + | invariant 2e-4·q; cos > 0.999 |
| Net charge | (+2q, −q): half of the + charge's lines end on − (Gauss), none enter from outside. (+q, −2q): half of the − charge's lines come from the boundary | 0.5 ± 0.06 (line counting) |
| Zero of the field | a line aimed at the midpoint of two equal charges ends as a stagnation point there; its neighbour escapes | 1e-4 m |
| Numerical endings | forced length limit, step limit, step underflow and non-finite field are reported as `max_length` / `integration_failure` | exact |
| Weak sink in a strong field | only the line its own field dominates is captured | exact |
| Convergence | exit point error falls as the tolerance is tightened (1e-4, 1e-6, 1e-8) | error < 300 × tolerance |
| Guard radius | equals 0.5 × grid spacing; field arrays identical with and without field lines | exact |
| Domain | lines clipped to a non-cubic domain; three complete density levels (8, 16, 32) | 1e-12 |
| Contours of one charge (`test_equipotentials`) | vertices on circles of radius Kq/V; closed loops; inscribed length | 1e-7 relative |
| Contours of four charges | exact φ at every vertex equals the level; chords near-perpendicular to E | 1e-7 relative; cos < 0.15 |
| Dipole 0 V contour | lies on x = 0 | 1e-9 m |
| Contour convergence | midpoint error ratio ≈ 4 per grid doubling; below the chord-error bound (√2h)²/8r² | ratio within 35 %; bound × 1.05 |
| Singular samples | charge on a grid node: finite output, loops around it traced; sub-cell loop elsewhere missed, not invented | exact |
| Isosurface of one charge | vertices on the sphere r = Kq/V; normals radial; area converges from below | 1e-7 relative; area error < 1 % at 33³ |
| Isosurfaces of a dipole | exact φ at every vertex; 0 V surface is x = 0; closed surfaces watertight (every edge shared by exactly two triangles) | 1e-7 relative |
| Superposition terms (`test_phase2a_models`) | ΣEᵢ = E, Σφᵢ = φ; each term equals the single-charge closed form; \|E\| < Σ\|Eᵢ\| somewhere | 1e-12 relative |
| Dipole group | equals two explicit charges; follows the group transform; on-axis closed form | 1e-12 relative |
| D in vacuum | D = ε₀E per sampling | exact |
| Probe at a charge (`test_api_phase2a`) | undefined, names the charge, tolerance < 1e-10 m | exact |
| Probe near a charge | r = 1e-3 … 1e-10 m: E = Kq/r², φ = Kq/r, D = ε₀E | 1e-12 relative |
| Equation registry | statuses for 0, 1, 2 charges and zero charge; evaluated vs satisfied vs not used; other models | exact |

## Known numerical limitations (Phase 2A)

- Field-line paths carry integration error (per-step tolerance 1e-5 of the domain diagonal at
  normal quality). The field values do not.
- Line counts are rounded, so "lines ∝ |q|" holds to within one line per charge.
- Contour and surface geometry between vertices is piecewise linear.
- The fraction-of-lines tests have a counting tolerance, not a physical one.
- Performance was measured only on a 4-core CPU with software WebGL: 2D solves 55–190 ms, 3D
  solves 220–500 ms at normal quality for presets 1–4.

## Physics validation added in Phase 2B-1

Existing tolerances were not changed. Four new tests failed on first run; all four were mistakes
in the new tests, fixed in the tests: a sharpness bound measured against |E| (which cancels for a
dipole) instead of the per-charge derivative scale; a test box with a charge exactly on its face;
a 2D finite-difference comparison tolerance below the method's own error; and a component-wise
"E ≠ 0" check where a magnitude check was meant.

| Check (file) | Method | Tolerance |
|---|---|---|
| Single +, single −, dipole, four charges (`test_divergence_curl`) | ∇·E, ∇·D, ∇×E, ∇×D exactly 0 at 300 random points while \|E\| > 0; units | exact |
| Independent check of the zeros | analytical Jacobian written in the test: trace and antisymmetric part | ≤ 1e-13 × max\|J\| |
| Finite-difference diagnostic on the Coulomb fields | estimate consistent with 0 within its uncertainty; uncertainty < 1e-5 × Σ K\|qᵢ\|/rᵢ³ | as stated |
| Finite-difference method itself | known fields with div = 3 + 2x and curl = (−2xz, −2yz, 2(1 + z²)): recovered within the uncertainty; a real curl is not reported as zero; Richardson error ratio ≈ 16 per halving | ratio 16 ± 20 % |
| Near a charge | r = 1e-3 … 1e-10 m: E = Kq/r², div and curl exactly 0 | 1e-12 relative |
| At a charge | all seven quantities not evaluated (NaN), counted in the header | exact |
| Source table | weights q/ε₀ and q exactly; zero and disabled charges excluded; signed distances to xy and xz planes; in-plane flags; no curl weight | exact |
| ∫_V ∇·E dV = Q_enc/ε₀ and ∫_V ∇·D dV = Q_enc | sum of enclosed δ weights for four boxes (all, one, one other, none of three charges), compared with the outward flux of the exact field through each box face by 40 × 40 Gauss–Legendre quadrature | weights 1e-15 relative; flux 1e-4 × Σ\|q\|/ε₀ |
| Distributional curl = 0 | circulation of E around 96 circles of radius 1 mm to 0.3 m, centred on each charge or displaced off its plane | ≤ 1e-9 × \|E\| × 2πr |
| 2D slice shows 3D operators | engine ∇·E on a slice through a charge is exactly 0 at every defined sample, while the 2D divergence ∂Eₓ/∂x + ∂E_y/∂y of the same E samples is −Kq/r³ | 5e-3 relative (second-order differences) |
| Probe (`test_api_phase2b1`) | values, units, scalar/vector kinds, statuses; distributional block at a charge; diagnostics only at ordinary points | exact / as above |
| Registry (`test_phase2a_models`) | new equations present, statuses for 0 and 2 charges, full-wave, inhomogeneous and homogeneous media; usage "evaluated" vs "satisfied"; bilingual derivations; δ³ unit 1/m³ | exact |

## Physics validation added in Phase 2B-2

| Check (file) | Method | Tolerance |
|---|---|---|
| Built-in meshes (`test_gauss_surfaces`) | closed, manifold, consistently outward at both resolutions, triangle counts, rotated and translated; box/cube area and volume exact; sphere/cylinder smaller than ideal | exact / 1e-12 |
| Mesh convergence | sphere deviation and volume deficit fall as (64/24)² between preview and final; cylinder deviation = r(1 − cos π/n) | 15 % / 1e-12 |
| Reversal | reversed triangles are the original with v1, v2 swapped; signed volume negated | exact |
| Invalid meshes | hole, inconsistent orientation, collinear (zero-area) face, pinched vertex, non-manifold edge, two components: each rejected with a bilingual reason | exact |
| Invalid parameters | zero radius, negative size, subdivision on a sphere, > 8 per axis, bad indices, unknown orientation | exact |
| Classification | rotated box: inside/outside and signed distances; inside the bounding box but outside the rotated box; tolerance formula; on-face, just outside, just inside; near-boundary highlight distance; points 1e-3 … 1e-9 m from mesh vertices and edges; on a vertex and on an edge → boundary; a point on the ideal sphere above a face is outside the inscribed mesh | exact |
| Gauss's law (`test_gauss_flux`) | +q and −q in sphere, cube, box, cylinder (rotated): Φ_E = Q/ε₀ and Φ_D = Q within the reported uncertainty; volume integral = Q/ε₀ | reported uncertainty; 1e-15 |
| Several charges; cancelling charges | Φ = ΣQ_enc/ε₀; counts and partial sums; Q_enc = 0 gives Φ = 0 with local contributions of both signs | as above |
| External charges | three charges outside four shapes: each contributes 0 within 1e-12 Q/ε₀; E·n takes both signs; each external charge alone sends flux in and out | 1e-12 |
| Same charges, seven surfaces of different shape and size | flux spread < 1e-12 Q/ε₀; local E·n distributions differ by > 2× in range | 1e-12 |
| Orientation | inward = −outward for every shape, per triangle bitwise | exact |
| D vs E | Φ_D = ε₀Φ_E, per triangle and D·n = ε₀E·n | 1e-12 |
| Solid-angle formula vs direct quadrature | 40 × 40 Gauss–Legendre integration of E·n on each of the 12 box triangles | 1e-8 relative |
| Preview vs final | a charge between the two inscribed meshes: preview mesh says outside with Φ = 0, final says inside with Φ = Q/ε₀; transported triangles equal each mesh; the ideal-shape disagreement is flagged only for preview | exact |
| Geometric vs integration error | both resolutions satisfy Gauss within ~1e-9 Q/ε₀ while the mesh deviates from the sphere by > 1e-4 m | as stated |
| Near and on the surface | charge 1e-2 … 1e-10 m inside or outside a face: correct side, Gauss holds; on the face: status boundary-ambiguous, flux and volume integral undefined | reported uncertainty |
| Subdivision | on the actual face data every shared face pair sums to exactly 0; shared-face count; same triangles with opposite winding; corner order stable; Σ cell flux = outer flux; Σ cell volume integrals = parent; each cell obeys Gauss; (1,1,1) to (8,8,8) | exact / 1e-12 |
| Charge on an internal cell plane | parent unaffected; status ambiguous; 8 touching cells unassigned; no cell sum reported | exact |
| API (`test_api_gauss`) | value classes, units, mesh info, arrays; cache hit on display/name change, miss on centre, orientation, quality; boundary and invalid surfaces; unsupported scene; all nine situations; equation statuses and usage; projects with and without surfaces | exact |

Floating-point uncertainty of the solid-angle sums observed: about 1e-12 relative for the box,
2e-12 for the sphere at the final resolution. Two first-run test failures in this phase were
test mistakes: a hole case below the schema's minimum triangle count, and absolute thresholds
for per-triangle flux on a 3968-triangle mesh (and one cell-ownership assumption).

## Other automated tests

- **Scene and solver support** (`tests/core`): rotation convention, parent transforms, eight
  classes of invalid scene rejected, inert geometry excluded and reported, disabled sources
  ignored, seven unsupported configurations refused with bilingual reasons, planned solvers
  reported unavailable, presets catalog, cache fingerprint.
- **Wire format, sampling, equations** (`tests/core`): array layouts, container round trip and
  alignment, no NaN in the header, required equations present with complete bilingual metadata,
  statuses change with the model context.
- **API contract** (`tests/api`): binary response, cache hit on a display-only change,
  unsupported and invalid requests, synchronous size limit, float64 probe, equations, honest
  solver and health reporting when Redis or the database is down, project CRUD.
- **Integration** (`tests/integration`): a real Celery worker on real Redis (job result identical
  to the in-process result, WebSocket progress, cancellation), projects in real PostgreSQL across
  app restarts.
- **Frontend unit tests**: request building, sample-point layout matching the engine, physics
  key, container decoding, display scales, dictionary parity, no hard-coded UI sentences.
- **End to end** (`tests/e2e/smoke.cjs`): twelve checks in a real browser, including "a
  visual-only change sends no simulation request".

## Verification record for the Phase 1 run

Executed in the development sandbox (Ubuntu 24.04, x86_64, 4 cores, software WebGL):

| Item | Result |
|---|---|
| Python tests | 63 passed (including integration against native Redis 7.0 and PostgreSQL 16) |
| ruff, mypy (strict) | clean |
| Frontend type-check, lint, unit tests, production build | clean; 16 tests passed |
| End-to-end script, native stack (Vite dev server, uvicorn, Celery) | 12 of 12 checks passed |
| `docker compose config` | valid |
| Container images | all three built |
| `docker compose up` | all five services started; API, frontend, PostgreSQL and Redis reported healthy |
| End-to-end script, container stack (through nginx, including the WebSocket and PostgreSQL) | 12 of 12 checks passed |

Qualifications on the container verification:

- Images were built with `docker build`, not `docker compose build`, because the sandbox proxy
  needs host networking and an extra CA certificate, which compose's builder would not grant
  non-interactively. The Dockerfiles and build arguments were the same ones compose uses.
- Base images came from `mirror.gcr.io` because Docker Hub rate-limited the sandbox. The default
  Docker Hub image names in the Dockerfiles were therefore pulled successfully only for
  `python:3.12-slim` (once) and `redis:7-alpine`.
- A plain `docker compose up --build` on an unrestricted network has not been executed.

Not verified anywhere:

- Browsers other than headless Chromium (Firefox, Safari, Edge).
- A real GPU: rendering performance and frame rates are unmeasured.
- Windows and macOS hosts; arm64 images.
- Touch input.

## Verification record for the Phase 2A run

Executed in the same development sandbox (4 cores, software WebGL, headless Chromium):

| Item | Result |
|---|---|
| Python tests | 108 passed (63 from Phase 1, 45 new), including integration against native Redis and PostgreSQL |
| Phase 1 test files alone | 63 passed |
| ruff, mypy (strict) | clean |
| Frontend type-check (strict), lint, production build | clean |
| Frontend unit tests | 26 passed (16 from Phase 1 with the request tests rewritten for the new request shape, plus new ones) |
| End-to-end script, native stack | 16 of 16 checks passed |
| End-to-end script, container stack rebuilt from this code | 16 of 16 checks passed, twice |

The end-to-end script asserts, by counting requests to `/simulations`, that 13 visual-only
actions send no physics request (colour map, arrow length, vector density, vector size, vector
field E/D, vectors on/off, field-line density, field lines on/off, contours on/off, grid, zoom,
isosurfaces on/off, 3D volume vectors, orbit), and that dipole separation, dipole charge, charge
magnitude, polarity, adding a charge and editing a coordinate each do. It also shows that
returning to an already-solved physical state is served from the cache.

Same qualifications as the Phase 1 record: images were built with `docker build` through a
registry mirror, not with `docker compose build`; a plain `docker compose up --build` on an
unrestricted network has not been executed. Not verified: browsers other than headless Chromium,
a real GPU, touch input, Windows/macOS hosts, arm64.

## Verification record for the Phase 2B-1 run

| Item | Result |
|---|---|
| Python tests | 134 passed (108 from earlier phases, 26 new) |
| ruff, mypy (strict) | clean |
| Frontend type-check (strict), lint, production build | clean |
| Frontend unit tests | 35 passed (26 earlier, 9 new; two request tests updated for the new request contents) |
| End-to-end script, native stack | 22 of 22 checks passed, four runs |
| End-to-end script, container stack rebuilt from this code | 22 of 22 checks passed, twice |

New end-to-end checks: probe values and units of div/curl; probe at a charge (singular,
not evaluated, δ weights, zero distributional curl); ten further visual-only actions with zero
physics requests (four divergence/curl colour maps, curl vectors and their field, source markers
off and on, volume vectors, volume scalars); off-slice ghost with Δz and its return; equations
dialog for the new equations; finite-difference diagnostics at the advanced level.

## Verification record for the Phase 2B-2 run

| Item | Result |
|---|---|
| Python tests | 203 passed (134 from earlier phases, all unchanged and passing; 69 new) |
| ruff, mypy (strict) | clean |
| Frontend type-check (strict), lint, production build | clean |
| Frontend unit tests | 43 passed (35 earlier, 8 new) |
| End-to-end script, native stack | 35 of 35 checks passed, four runs |
| End-to-end script, container stack rebuilt from this code | 35 of 35 checks passed, twice |

New end-to-end checks cover: flux results with classes and units; seven visual-only surface
actions with neither a field nor a flux request; charge movement, surface size and orientation
each triggering a flux request with the expected result; subdivision with a charge on an
internal plane (ambiguous) and with 4×3×3 cells (75 shared faces cancelling exactly); the patch
inspector; preview-mesh requests during a drag followed by a final-mesh request; a charge on the
surface; the same flux through three shapes; equation usage; project persistence; Hungarian.

## Verification record for the local preview preparation

| Item | Result |
|---|---|
| `docker compose config` | valid |
| `./scripts/start.sh --no-build` (images built beforehand) | all five containers healthy, including the new worker health check; ports bound to 127.0.0.1 |
| Error paths of `start.sh` | Docker unreachable, port 8080 in use, database password changed after first start (degraded warning): each reported with a hint |
| `stop.sh` then `start.sh` | a saved project (charge, Gaussian surface, view settings) was intact |
| End-to-end script against the started stack | 35 of 35 checks, twice |
| Python tests, ruff, mypy | 203 passed; clean |
| Frontend type-check, lint, unit tests | clean; 43 passed |
| PowerShell scripts | not executed (no PowerShell available) |

## Verification record for the native run (no Docker)

Run in the development environment (Linux x86_64, PostgreSQL 16.15, Node 22, Python 3.12), as
a normal user, with `scripts/native.py`; no Docker and, unless stated, no Redis.

| Item | Result |
|---|---|
| First start without `.local` | cluster and `emf` database created; API and web application healthy; Redis absence reported as a note |
| End-to-end script, `EMF_E2E_NO_WORKER=1` | 35 of 35 checks, three runs (the queue check verifies "disabled and reported unavailable") |
| Persistence | a project saved through the API was present after stop and start |
| Stop | all processes ended, ports freed, PostgreSQL stopped cleanly; repeated stop and status correct |
| Error paths | port 8080 in use, port 5433 in use, running as root: each reported with a hint; parts started by a failed attempt were stopped again |
| Stale process record (start time before boot) | not treated as ours; the unrelated process was not ended |
| Changed frontend source | rebuilt on the next start |
| With a Redis server present | worker started automatically; end-to-end script 35 of 35 including the high-resolution job; stop ended the worker |
| Python tests, ruff, mypy (also strict on the launcher) | 203 passed; clean |
| Frontend type-check, lint, unit tests | clean; 43 passed |
| Windows (`native.ps1`, `taskkill`, `tasklist`, PostgreSQL discovery, `initdb` on Windows) | not executed (no Windows machine available) |

## Verification record for Phase 3A (magnetostatic sources)

Development environment: Linux x86_64, Python 3.12, PostgreSQL 16.15, Node 22, Redis present.

**Analytical and numerical validation** (`tests/physics/test_magnetostatics.py`, 51 tests):

| Check | Reference | Tolerance | Result |
|---|---|---|---|
| Infinite wire magnitude, 4 distances × 3 currents | μ₀I/(2πr) | 1e-12 relative | pass |
| Wire direction | φ̂ (right-hand rule), no radial or axial part | 1e-15 | pass |
| Arbitrary wire orientation (4 directions, 20 points each) | closed form, and numerical Biot–Savart over a ±3 m segment plus its analytical tail | 1e-12; 1e-10 | pass |
| Current reversal, doubling (wire and loop) | exact sign flip, factor 2 | bitwise; 1e-15 | pass |
| Two wires same direction / opposite / unequal (zero at x = 3/14 m) | superposed closed forms | 1e-13 | pass |
| Superposition of three sources | sum of single-source solves | 1e-14 | pass |
| Loop on the axis, 5 positions | μ₀Ia²/(2(a²+z²)^{3/2}), B_ρ exactly 0 | 1e-14 | pass |
| Loop off axis, 10 points, distance from the wire ≥ 0.01 a | numerical Biot–Savart (trapezoidal rule, refined until two levels agree to 1e-13) | ≤ 1e-8 relative vector error | pass; measured 1.6e-16 … 1.1e-14 (512–8192 nodes) |
| Loop near the wire, 0.001 a ≤ d < 0.01 a, 4 points | same, refined to 1e-12 | ≤ 1e-6 | pass; measured 5.7e-15 … 7.4e-14 (8192–65 536 nodes) |
| Convergence of the numerical reference | error decreases monotonically from > 1e-2 (64 nodes) to < 1e-12 (2048 nodes) | | pass |
| Loop orientation (3 normals) | rigidly rotated reference field | 1e-12 | pass |
| Axial and mirror symmetry | constant B_z, B_ρ over 12 azimuths, no B_φ; B_z even, B_ρ odd in z | 1e-14 | pass |
| Loop right-hand rule | B along +n inside; B circles the wire around (a, 0, 0) | sign | pass |
| Near-axis formulation | series coefficients positive and decreasing; tail bound < 1e-20; B_ρ/ρ → 3μ₀Ia²z/(4(a²+z²)^{5/2}) as ρ → 0 (10⁻¹²…10⁻⁴ m); no jump across m = 0.5; series against numerical Biot–Savart | 1e-6 (leading order); 1e-11; 1e-10 | pass |
| B = μ₀H, units T and A/m | | 1e-15 | pass |
| Singularities | NaN on a wire and on a loop; ∇·B not evaluated there; true value at 2 × the position tolerance | | pass |
| ∇·B | finite differences (Richardson) consistent with 0 at 8 random points; solver returns exact 0 at 50 points | | pass |
| Charges do not change B, wires do not change E; cache keys independent | | bitwise | pass |

**Magnetic field lines** (`tests/physics/test_magnetic_field_lines.py`, 11 tests): closed
circles around a wire, counter-clockwise for current along +z and reversed for −I, radius
constant within the integration tolerance, closure gap ≤ 1 mm; lines cut by a narrow region
reported `domain_boundary` at both ends (on the boundary) and never closed; two-wire and loop
lines follow B (cos ≥ 0.999 per segment); closed loop lines wind exactly once around a wire
crossing; 3D lines; a helix whose pitch exceeds the closure tolerance is not reported closed;
lines stopped by the step budget or by a non-finite field end as `max_length` /
`integration_failure`, never closed; closed lines meet the documented criteria at all three
qualities.

**API** (`tests/api/test_api_phase3a.py`, 11 tests): units of B, H, ∇·B, ∇·H; mixed requests
rejected; E and B in one probe with separate units, B = μ₀H, nearest source; contributions sum
to the total; singular state on a wire and on a loop with the source identified; equation
statuses for wire-only, loop-only, mixed and charge-only scenes (bilingual); presets 9–11 incl.
variants and view hint; independent electric and magnetic caches (moving a charge keeps the
magnetic result, moving a wire keeps the electric and the flux result); malformed and elliptical
sources refused with reasons; projects with currents persisted; old projects load.

| Item | Result |
|---|---|
| Python tests | 276 passed (203 earlier, unchanged except one expected count; 73 new) |
| ruff, mypy (strict) | clean |
| Frontend type-check, lint, production build | clean |
| Frontend unit tests | 50 passed (43 earlier, 7 new) |
| End-to-end script, native stack (`scripts/native.py`) with Redis and worker | 46 of 46 checks (35 earlier + 11 magnetic), including one high-resolution job per field for a charge-and-wire scene |
| End-to-end script, stack without a worker (`EMF_E2E_NO_WORKER=1`) | 45 of 45 checks (the high-resolution checks skipped as designed) |
| Magnetic high-resolution job through the worker (API) | succeeded, 769 × 769 B samples, high-quality field lines |
| Visual inspection (screenshots) | wire, two wires (same, opposite, each source separately), loop in the xz cross-section and in 3D, charge plus wire: directions follow the right-hand rule; ⊙/⊗ at the correct crossings |
| Docker images | not rebuilt in this phase (no Docker-related file changed) |
| Windows | not executed (no Windows machine); the native workflow was run on Linux |

