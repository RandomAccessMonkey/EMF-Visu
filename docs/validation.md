# Validation

What is checked, how, and what was actually executed. Update this file whenever tests are added
or a verification status changes.

## How to run

```bash
uv run pytest                      # physics, core, API, integration (134 tests)
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
