# EMF-Visu

An interactive electromagnetic field laboratory in which every picture is backed by a real
calculation. Build a configuration, change a parameter, see the field respond, and read which
equations govern it and under what assumptions.

**Status: Phase 1 (Foundation) of seven.** What works today:

- Ideal point charges in vacuum, solved exactly by the Python physics engine.
- The same scene in a 2D cross-section view and a 3D view: field arrows, a colour map of the
  potential φ or of |E|, a 3D arrow lattice.
- Editing: add, move (drag in 2D, gizmo in 3D, numeric input, arrow keys), rotate, scale,
  duplicate, disable and delete objects; snapping; adjustable bounds.
- A probe that returns E, φ and D at a point in 64-bit precision.
- An equation panel whose applicability statuses are computed from the active physical model.
- Presets 1–4, saved projects, English and Hungarian, beginner and advanced levels.
- High-resolution solves as cancellable jobs on a separate worker, with live progress.

Everything else in the product definition (conductors, dielectrics, magnetostatics, induction,
FEM, FDTD, circuits, field lines, flux tools) is **not implemented yet**. Such features are
disabled or refused with a reason; nothing is approximated silently. See
[docs/architecture.md](docs/architecture.md) for the full status table.

## Run with Docker

Requirements: Docker with the Compose plugin.

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

Open <http://localhost:8080>. The API is also published on <http://localhost:8000>
(interactive docs at `/docs`).

| Service | Role |
|---|---|
| `frontend` | static React build served by nginx; proxies `/api` (including WebSockets) |
| `api` | FastAPI: validation, orchestration, in-process analytical solves, persistence |
| `worker-analytical` | Celery worker for queued solves (`solver.analytical`) |
| `redis` | job queue and job results |
| `postgres` | saved projects |

If Docker Hub rate-limits you, uncomment the mirror variables at the bottom of `.env`.
Behind a TLS-inspecting proxy, pass your CA bundle as the `extra_ca` build secret.

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
- Keys: `2` / `3` switch views, arrow keys nudge the selection, `Delete` removes it, `Esc`
  deselects.
- **Advanced** level adds solver details, numerical diagnostics, the equations that do not apply
  (with reasons) and the high-resolution solve.

## Documentation

- [docs/architecture.md](docs/architecture.md): architecture, interfaces, data model, units and
  conventions, data flow, status, limitations, how to extend.
- [docs/validation.md](docs/validation.md): validation methodology and verification record.
