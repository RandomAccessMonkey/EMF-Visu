# Running EMF-Visu on your computer

This runs the complete application (Phases 1, 2A, 2B-1 and 2B-2) in Docker. It needs no Python,
Node or database installed on your computer.

**Address once started: <http://localhost:8080>**

| Container | What it does |
|---|---|
| `frontend` | the web application (nginx), on port 8080; forwards `/api` to the API |
| `api` | physics engine and API; also on port 8000 for its documentation at `/docs` |
| `worker-analytical` | runs queued high-resolution solves |
| `redis` | job queue |
| `postgres` | saved projects, in the Docker volume `emf-visu_pgdata` |

Both ports listen on this computer only (`127.0.0.1`), not on your network.

## 1. Requirements

| | Windows 10/11 | macOS (Intel or Apple silicon) | Linux |
|---|---|---|---|
| Docker | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend (the installer's default) | [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) | [Docker Engine](https://docs.docker.com/engine/install/) with the [Compose plugin](https://docs.docker.com/compose/install/linux/) (`docker compose`, version 2) |
| Git | [Git for Windows](https://git-scm.com/download/win) | `git` (Xcode command-line tools or Homebrew) | your distribution's `git` package |
| Browser | a current Chrome, Edge, Firefox or Safari with WebGL 2 (hardware acceleration on) | | |

Also needed:

- About 4 GB of free disk space for the images.
- Internet access for the first start, which downloads base images and packages.
- Ports 8080 and 8000 free (both can be changed; see section 6).

## 2. Get the code

All commands below run in a terminal: PowerShell on Windows, Terminal on macOS, a shell on Linux.

```bash
git clone https://github.com/RandomAccessMonkey/EMF-Visu.git
```

```bash
cd EMF-Visu
```

```bash
git checkout claude/vibrant-einstein-2rhzvq
```

All later commands run in this `EMF-Visu` folder.

## 3. Start

Start Docker Desktop first (Windows, macOS) and wait until it reports that the engine is running.

**macOS / Linux:**

```bash
./scripts/start.sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

**Any system, without the helper script:**

```bash
docker compose up -d --build
```

The first start builds the images and takes about 5–10 minutes; later starts take seconds.

The helper scripts first check that Docker is installed and running and that the ports are
free. They then start everything, wait until it is healthy, and print the address. On a
problem they print the failing container's last log lines and a hint.

When it is ready:

```text
EMF-Visu is running:  http://localhost:8080
```

Open **<http://localhost:8080>** in your browser.

## 4. Stop

**macOS / Linux:**

```bash
./scripts/stop.sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

**Any system:**

```bash
docker compose down
```

Stopping keeps your saved projects. They are in the Docker volume `emf-visu_pgdata` and are
there again on the next start, after a reboot, and after updating the code.

To **delete all saved projects** (cannot be undone):

```bash
docker compose down -v
```

## 5. Status and logs

```bash
./scripts/status.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\status.ps1
```

Either one shows each container with its health (`healthy`, `starting`, `unhealthy`) and the
application's own health report. To see one container's log:

```bash
docker compose logs --tail 50 api
```

Replace `api` with `frontend`, `worker-analytical`, `postgres` or `redis` as needed.

## 6. Configuration (optional)

Nothing needs configuring. To change something, copy `.env.example` to `.env` next to
`docker-compose.yml` and edit it:

| Setting | Default | Meaning |
|---|---|---|
| `FRONTEND_PORT` | 8080 | port of the web application |
| `API_PORT` | 8000 | port of the API documentation |
| `BIND_ADDRESS` | 127.0.0.1 | `0.0.0.0` makes the app reachable from other devices on your network |
| `PYTHON_IMAGE`, `NODE_IMAGE`, `NGINX_IMAGE`, `POSTGRES_IMAGE`, `REDIS_IMAGE` | Docker Hub images | alternative registry, e.g. when Docker Hub limits downloads |

After changing `.env`, stop and start again.

## 7. Updating to a newer version

```bash
git pull
```

Then start as in section 3. The start command rebuilds what changed, and saved projects are
kept. If the page still looks old, reload it with Ctrl+F5 (Windows, Linux) or Cmd+Shift+R
(macOS).

## 8. What to try

Each step uses the panels on the right.

| Feature | How to see it |
|---|---|
| Point charges and the electric field | Presets (left) → *Electric dipole*. Drag a charge in the 2D view; **+ Charge**/**− Charge** add more; *Parameters* edits charge (nC) and position. |
| Field lines, equipotential contours | On by default. *Display* → *Field lines*, *Equipotentials*. **3D** (top) shows equipotential surfaces. |
| Divergence and curl | *Display* → *Colour map* → *Divergence ∇·E* (exactly 0 away from charges); turn on *Curl vectors* (rings = zero vector). *Probe* (top), then click the slice: *Results* shows ∇·E, ∇×E with units. Select a charge → *Place probe on the selected charge* shows the distributional (δ³) statement. |
| Flux through Gaussian surfaces | *Gauss* tab → *Guided situations* → 1 to 9. *Results* shows Φ_E, Φ_D. |
| Enclosed charge classification | *Results* → *Charges and their contributions* (inside / outside / on the surface); rings around the charges in the view. Situation 8 puts a charge exactly on the surface. |
| Surface vs volume integral | *Results* → *Volume integral ∫ ∇·E dV* and *Difference* next to Φ_E. |
| Subdivision and shared-face cancellation | Situation 5, then *Gauss* → *Subdivide into cells*, switch to **3D**. Try 4 × 3 × 3 cells: *Largest \|Φ_A + Φ_B\|* is 0 and Σ Φ_cell = Φ_outer. With 4 × 4 × 4 the charge lies on an internal plane and the cell-wise sum is marked ambiguous. |

*Advanced* (top right) adds solver details, finite-difference checks and the high-resolution
solve. *HU* switches the interface to Hungarian.

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "Docker is installed but not running" | Start Docker Desktop and wait for "Engine running". Linux: `sudo systemctl start docker`. |
| Linux: "permission denied ... docker.sock" | `sudo usermod -aG docker $USER`, then log out and in again. |
| "Port 8080 (or 8000) is already in use" | Another program uses it. Stop it, or set `FRONTEND_PORT` / `API_PORT` in `.env` (section 6). |
| First start fails while downloading (`toomanyrequests`, timeouts) | Docker Hub limits anonymous downloads, or the network blocks them. Retry later, sign in with `docker login`, or set the `*_IMAGE` mirror variables in `.env` (examples in `.env.example`). |
| First start fails with certificate errors behind a company proxy | Configure the proxy and its certificate in Docker Desktop (*Settings → Resources → Proxies*). If the build itself still fails, build the three images once with the CA as a build secret, then start with `--no-build`; see "Builds behind a TLS-inspecting proxy" below. |
| Windows: `/usr/bin/env: 'bash\r'` or odd errors in containers | The files were checked out with Windows line endings before this fix. Re-clone, or run `git add --renormalize .` and `git checkout -- .`, then start again. |
| Windows: "running scripts is disabled on this system" | Use the exact command with `-ExecutionPolicy Bypass` shown above, or the plain `docker compose` commands. |
| Start script warns "the API reports a degraded state ... password authentication failed" | `POSTGRES_PASSWORD` was changed after the first start; the database keeps its original password. Put the old value back, or delete the data with `docker compose down -v`. |
| Start script warns the worker is not healthy | Everything works except *Run high-resolution solve*. See `docker compose logs worker-analytical`. |
| Browser shows "502 Bad Gateway" or the status bar says *API offline* | The API is not running. Run the status script and `docker compose logs --tail 50 api`. |
| Page loads but the 3D view is blank or very slow | The browser lacks WebGL 2 or hardware acceleration. Enable it in the browser settings, or try Chrome or Edge. |

### Builds behind a TLS-inspecting proxy

Use this only if the normal start fails with certificate errors. `my-company-ca.pem` is your
company's root certificate:

```bash
docker build --secret id=extra_ca,src=my-company-ca.pem -f services/api/Dockerfile -t emf-visu-api .
```

```bash
docker build --secret id=extra_ca,src=my-company-ca.pem -f services/worker_analytical/Dockerfile -t emf-visu-worker-analytical .
```

```bash
docker build --secret id=extra_ca,src=my-company-ca.pem -t emf-visu-frontend frontend
```

Then start without rebuilding:

```bash
./scripts/start.sh --no-build
```

On Windows, use `scripts\start.ps1 -NoBuild` in place of `./scripts/start.sh --no-build`.

## 10. What has been verified, and where

Verified in the development environment (Linux x86_64, Docker Engine 29.9, Compose 5.6):

- `./scripts/start.sh` started all five containers healthy, including the worker's new health
  check, with both ports bound to `127.0.0.1`.
- The start script's error paths: Docker unreachable, a port already in use, a degraded
  database after a password change.
- `./scripts/stop.sh` followed by `./scripts/start.sh` kept a saved project, including its
  charges, Gaussian surface and view settings.
- The full browser test (35 checks, all features of section 8) passed twice against the started
  containers.
- Backend and frontend test suites, type checks and lint: unchanged and passing.

Not verified:

- **Your computer.** No Windows or macOS machine and no Docker Desktop were available.
- **The PowerShell scripts were not executed.** No PowerShell was available; on Windows the
  plain `docker compose` commands are the fallback.
- **The images were not built directly from Docker Hub in that environment.** It reaches the
  internet only through a proxy, so the three application images were built with the
  equivalent `docker build` commands, a registry mirror and the proxy's certificate. Postgres
  and Redis were pulled from Docker Hub normally.
- **ARM64 (Apple silicon) images.** All base images and Python wheels used are published for
  arm64, but no arm64 build was run.
