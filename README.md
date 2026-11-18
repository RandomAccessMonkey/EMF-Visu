# EMF-Visu

An interactive electromagnetic field laboratory in which every picture is backed by a real
calculation. Build a configuration, change a parameter, see the field respond, and read which
equations govern it and under what assumptions.

## Licence and community use

EMF-Visu is source-available under the **PolyForm Noncommercial License 1.0.0**. It is intended
to support educational, research, and other noncommercial public-interest development.

The licence permits use, modification, and distribution for permitted noncommercial purposes.
It expressly includes use by educational institutions, charitable organizations, and public
research organizations, regardless of their funding source, subject to the licence terms.

**Commercial use is not granted.** This includes selling the software, offering it as a paid
service, or distributing a commercial product or service based on it without separate written
permission from the copyright holder.

PolyForm Noncommercial is not an OSI-approved Open Source licence because it restricts
commercial use. EMF-Visu is therefore source-available under a noncommercial licence, not
OSI-defined Open Source software. See [LICENSE](LICENSE) for the complete terms and
[CONTRIBUTING.md](CONTRIBUTING.md) for community contributions.

GitHub public repositories can be forked through GitHub's platform features. A GitHub fork does
not itself grant commercial-use rights. Please use
[GitHub Issues](https://github.com/RandomAccessMonkey/EMF-Visu/issues) for reproducible bug
reports and feedback.

**Status: Phase 1 (Foundation), Phase 2A (point-charge electrostatics), Phase 2B-1
(divergence and curl), Phase 2B-2 (Gauss's law and the divergence theorem), Phase 3A
(magnetostatic sources: wires and loops), Phase 3B (solenoids, toroids, permanent magnets and
Ampère's law), Phase 4A (magnetoquasistatic induction: Faraday's and Lenz's laws) and Phase 4B
(moving conductors, motional EMF and the Lorentz force) and Phase 4C (passive circuits,
induced currents, magnetic braking and an axisymmetric eddy-current disk) are implemented, plus
an ideal coaxial-cable TEM module.**
What works today:

- Any number of positive and negative ideal point charges in vacuum, and dipoles made of two
  point charges, solved exactly by the Python physics engine (E, φ, and D = ε₀E).
- The same scene in a 2D cross-section view and a 3D view: E or D vectors, a colour map of φ
  or |E|, field lines with direction markers, equipotential contour lines, and equipotential
  surfaces in 3D.
- Editing: add, move (drag in 2D, gizmo in 3D, numeric input, arrow keys), rotate, scale,
  duplicate, disable and delete objects; charge magnitude (slider ±100 nC, any value by
  number), polarity flip; dipole charge and separation; snapping; adjustable bounds.
- Divergence and curl of E and D: exact zeros away from the charges (shown as colour maps and
  zero-vector glyphs, while E itself is nonzero), and each charge marked as a distributional
  source with its δ³ weight. Charges off the 2D slice are drawn as projections.
- A probe that returns E, φ, D, ∇·E, ∇×E, ∇·D and ∇×D at a point in 64-bit precision, each
  charge's contribution, and on a charge the distributional statement instead of numbers.
- An equation panel whose statuses are computed from the active physical model and which says
  whether the solver evaluates an equation or the field merely satisfies it.
- Gaussian surfaces (sphere, cube, box, cylinder): flux through them computed exactly over
  the triangulated surface and compared with the enclosed charge, local flux density on the
  surface, inside/outside/boundary classification, subdivision into cells with cancelling
  internal faces, and nine guided situations (Gauss tab).
- Steady currents (Phase 3A): infinitely long straight wires and thin circular loops in any
  orientation, any number of them. B and H (separately, with their own units and legend), exact
  closed forms (elliptic integrals for the loop, with a stable near-axis series), superposition
  with each source's own contribution, magnetic field lines with detected closed loops, ⊙/⊗
  current markers, ∇·B = 0, E and B side by side in the probe, and the magnetostatic equations.
- Coils and magnets (Phase 3B): finite solenoids made of N discrete turns (turn spacing derived,
  ideal long-solenoid value shown only as a labelled comparison, field profile along the axis);
  toroids as N discrete turns in vacuum or as the ideal continuous winding on a linear core;
  uniformly magnetized cylindrical permanent magnets, computed from their bound surface current,
  with H = B/μ₀ − M inside, N/S ends, and one-sided limits on the magnet surface.
- Ampère's law (Ampère tab): circular, rectangular and polygonal closed paths; the circulation of
  H is integrated numerically along the path and compared with the free current counted
  independently from where currents cross the path's surface; the result is reported as
  verified, not converged, ambiguous, unsupported or a mismatch.
- Induction (Phase 4A, magnetoquasistatic): time-dependent source currents (constant,
  sinusoidal, ramp, piecewise linear) with time controls and continuous looping playback; B(t), ∂B/∂t
  and the induced electric field E_ind = −∂A/∂t (shown separately from the electrostatic E);
  magnetic flux through stationary measurement surfaces, the EMF ∮E_ind·dl compared with −dΦ/dt
  (Faraday tab), Lenz's-law signs, and mutual inductance with a reciprocity check. No moving
  conductors, induced currents or waves.
- Moving conductors (Phase 4B): rigid translation and rotation profiles of measurement loops, a
  sliding-rod generator and N-turn measurement coils; motional EMF ∮(u × B)·dl, transformer EMF
  and their sum compared with −dΦ/dt from the moving-surface flux (generalized Faraday law); a
  Lorentz-force probe for a test charge and nonrelativistic test-particle trajectories (Lorentz
  tab). No induced currents, moving sources or relativistic motion.
- Passive circuits (Phase 4C): shorted loops, N-turn coils, polygonal loops and the sliding rod
  with resistance and self-inductance; coupled RL dynamics through mutual inductance; the
  induced currents' own field (prescribed and induced B shown separately), forces on the
  conductors, a dynamically braked sliding rod, an axisymmetric annular-band eddy-current disk,
  and Joule heat / magnetic / kinetic energy accounting (Circuits tab).
- Coaxial cable (ideal, lossless, TEM only): analytical radial E and azimuthal H between the
  conductors, L′, C′, Z₀, v_p and delay, sinusoidal or Gaussian travelling waves with matched,
  open or short loads (closed-form reflections), the Poynting vector integrated over the
  cross-section against V·I, Maxwell and telegrapher checks, and a 2D cross-section and 3D
  cut-away view (Coax tab, presets 30–31).
- Presets 1–4, 9–16 and 21–31, saved projects, English and Hungarian, beginner and advanced levels.
- High-resolution solves as cancellable jobs on a separate worker, with live progress.

Field lines, contours and surfaces are numerical constructions on top of the exact field; the
Results panel states the method and its limits for each.

Other planned capabilities, including extended charge distributions, nonlinear or
field-dependent magnetic materials, general circuit networks with independent sources,
FEM, FDTD and open-surface flux tools, are **not implemented yet**. Such features are disabled or refused with a reason; nothing is approximated silently.
See [docs/architecture.md](docs/architecture.md) for the full status table.

## Run with Docker (local preview)

Full instructions for Windows, macOS and Linux, including troubleshooting:
**[docs/local-preview.md](docs/local-preview.md)**.

Requirements: Docker Desktop (Windows, macOS) or Docker Engine with the Compose plugin (Linux).

| | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Start | `./scripts/start.sh` | `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` |
| Stop (projects are kept) | `./scripts/stop.sh` | `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1` |
| Status | `./scripts/status.sh` | `powershell -ExecutionPolicy Bypass -File scripts\status.ps1` |

Without the scripts, on any system: `docker compose up -d --build` and `docker compose down`.

Then open **<http://localhost:8080>**. The API documentation is at <http://localhost:8000/docs>.
Both listen on this computer only. A `.env` file is optional (see `.env.example`).

| Service | Role |
|---|---|
| `frontend` | static React build served by nginx; proxies `/api` (including WebSockets) |
| `api` | FastAPI: validation, orchestration, in-process analytical solves, persistence |
| `worker-analytical` | Celery worker for queued solves (`solver.analytical`) |
| `redis` | job queue and job results |
| `postgres` | saved projects |

Saved projects live in the Docker volume `emf-visu_pgdata` and survive stopping, restarting
and updating; only `docker compose down -v` deletes them.

## Run natively without Docker (Windows, macOS, Linux)

Full instructions, including how to install the prerequisites on Windows:
**[docs/native-windows.md](docs/native-windows.md)**.

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 22.12 or newer, pnpm 10, and
PostgreSQL 14 or newer (16 recommended). No Docker and no Redis are needed.

| | Windows (PowerShell) | macOS / Linux |
|---|---|---|
| Start | `powershell -ExecutionPolicy Bypass -File scripts\native.ps1 start` | `./scripts/native.sh start` |
| Stop (projects are kept) | `powershell -ExecutionPolicy Bypass -File scripts\native.ps1 stop` | `./scripts/native.sh stop` |
| Status | `powershell -ExecutionPolicy Bypass -File scripts\native.ps1 status` | `./scripts/native.sh status` |

Then open **<http://localhost:8080>**. The scripts keep a private PostgreSQL database in
`.local/pgdata` (port 5433) and start and stop it themselves. Without a Redis server, everything
works except *Run high-resolution solve*. If a Redis server is reachable, the solver worker is
started as well.

## Run natively (development)

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22, pnpm 10, Redis,
PostgreSQL.

```bash
uv sync
```

```bash
cd frontend && pnpm install
```

Create the database once:

```bash
psql -U postgres -c "CREATE USER emf WITH PASSWORD 'emf' CREATEDB" -c "CREATE DATABASE emf OWNER emf" -c "CREATE DATABASE emf_test OWNER emf"
```

Then start three processes, each in its own terminal:

```bash
uv run uvicorn emf_api.main:app --reload --port 8000
```

```bash
uv run celery -A emf_worker.app worker -Q solver.analytical --loglevel INFO
```

```bash
cd frontend && pnpm dev
```

Open <http://localhost:5173>. The app still works without Redis or PostgreSQL: interactive
solving does not depend on them, and the status bar shows what is offline.

Configuration is by environment variable; see [.env.example](.env.example).

## Tests

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run mypy packages/emf_core/src packages/emf_worker/src services/api/src
```

```bash
cd frontend && pnpm typecheck && pnpm lint && pnpm test
```

End-to-end, against a running stack (needs Playwright with Chromium):

```bash
node tests/e2e/smoke.cjs http://localhost:8080
```

What each suite checks, the tolerances, and what has and has not been verified are in
[docs/validation.md](docs/validation.md).

## After changing the backend contract

```bash
uv run python scripts/export_openapi.py > frontend/openapi.json && (cd frontend && pnpm gen:api)
```

Frontend types are generated from the API schema, so a contract change that the frontend does not
handle fails the type-check.

## Using the app

- **2D view** is a cross-section of the 3D model, not a two-dimensional model. Drag a charge to
  move it; right-drag pans; the wheel zooms.
- **3D view**: drag to orbit; select an object to move, rotate or scale it with the gizmo.
- **Probe** (key `P`): click the slice plane to read exact field values.
- **Time bar** (time-dependent scenes): play, pause, step and set the simulation time; the
  physics is evaluated at t = start + k·Δt exactly.
- **Faraday tab**: add a measurement surface; the result compares ∮E_ind·dl with −dΦ/dt and
  explains the sign (Lenz).
- **Ampère tab**: add a circular, rectangular or polygonal path, place and orient it
  numerically; the result compares ∮H·dl with the enclosed free current.
- Keys: `2` / `3` switch views, arrow keys nudge the selection, `Delete` removes it, `Esc`
  deselects.
- **Advanced** level adds solver details, numerical diagnostics, the equations that do not apply
  (with reasons) and the high-resolution solve.

## Documentation

- [docs/architecture.md](docs/architecture.md): architecture, interfaces, data model, units and
  conventions, data flow, status, limitations, how to extend.
- [docs/validation.md](docs/validation.md): validation methodology and verification record.
- [docs/master_spec.md](docs/master_spec.md): the complete product specification.
