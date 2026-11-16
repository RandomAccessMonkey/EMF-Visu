# Validation

What is checked, how, and what was actually executed. Update this file whenever tests are added
or a verification status changes.

## How to run

```bash
uv run pytest                      # physics, core, API, integration (63 tests)
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
