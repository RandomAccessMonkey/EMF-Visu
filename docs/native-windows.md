# Running EMF-Visu natively on Windows (no Docker)

This runs the application directly on Windows, without Docker Desktop. One command starts it and
one command stops it. The same scripts also work on macOS and Linux.

**Address once started: <http://localhost:8080>**

| Part | How it runs natively |
|---|---|
| Web application | built once, then served by Vite's preview server on port 8080; forwards `/api` to the API |
| API and physics engine | FastAPI with uvicorn on port 8000 (documentation at `/docs`) |
| Saved projects | a private PostgreSQL database in the project folder (`.local\pgdata`), port 5433, started and stopped by the scripts; no Windows service |
| Job queue (Redis) and solver worker | **not used.** Everything works except *Run high-resolution solve*, which the app shows as unavailable ("worker offline"). |

Everything listens on this computer only (`127.0.0.1`).

The physics, the API and the web application are the same code as in the Docker version. Only
the way they are started differs.

## 1. Install the prerequisites (once)

Open **PowerShell** (Start menu → "PowerShell"). A normal window is enough; administrator rights
are only needed if an installer asks for them. Run one command at a time:

| What | Command | Why |
|---|---|---|
| Git | `winget install --id Git.Git -e` | to download the code |
| uv | `winget install --id astral-sh.uv -e` | installs Python 3.12 and the Python packages for the project |
| Node.js (LTS, 22.12 or newer) | `winget install --id OpenJS.NodeJS.LTS -e` | builds and serves the web application |
| PostgreSQL 16 | `winget install --id PostgreSQL.PostgreSQL.16 -e` | the database program for saved projects |

**Close PowerShell and open a new window** so that the new programs are found. Then:

```powershell
npm.cmd install -g pnpm@10
```

Write `npm.cmd`, not `npm`. PowerShell blocks plain `npm` with "running scripts is disabled on
this system". Avoid `corepack enable` too: it writes into `C:\Program Files` and fails without
administrator rights. Afterwards, open a new PowerShell window. pnpm installs the web
application's packages on the first start.

Check that everything is found. Each command should print a version:

```powershell
git --version
```

```powershell
uv --version
```

```powershell
node --version
```

```powershell
pnpm --version
```

PostgreSQL does not need to be on `PATH`. The scripts look in `C:\Program Files\PostgreSQL\<version>\bin`
and use the newest version found.

### Notes on the PostgreSQL installer

- The PostgreSQL installer also sets up its own Windows service, a separate database on port
  5432, and may ask you for a password for it. **EMF-Visu does not use that service.** It keeps
  its own database in the project folder on port 5433, so the two do not interfere.
- If you do not want that service to run all the time, run these once in an **administrator**
  PowerShell:

  ```powershell
  Set-Service postgresql-x64-16 -StartupType Manual
  ```

  ```powershell
  Stop-Service postgresql-x64-16
  ```

- **Without the installer:** download the "zip archive" of PostgreSQL 16 for Windows x86-64 from
  <https://www.enterprisedb.com/download-postgresql-binaries>. Unzip it, for example to
  `C:\pgsql`. Then tell the scripts where it is with a `.env` file in the project folder (see
  section 6):

  ```text
  EMF_PG_BIN=C:\pgsql\bin
  ```

- If `winget` cannot find a package, use the installer from the program's website instead:
  [git-scm.com](https://git-scm.com/download/win),
  [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/),
  [nodejs.org](https://nodejs.org/),
  [postgresql.org/download/windows](https://www.postgresql.org/download/windows/).

## 2. Get the code

Use a folder that **OneDrive does not sync**, such as `C:\dev`. A database folder inside a
synced folder (Desktop, Documents) can be damaged by the sync.

```powershell
mkdir C:\dev
```

```powershell
cd C:\dev
```

```powershell
git clone https://github.com/RandomAccessMonkey/EMF-Visu.git
```

```powershell
cd EMF-Visu
```

```powershell
git checkout claude/vibrant-einstein-2rhzvq
```

All later commands run in this `C:\dev\EMF-Visu` folder.

## 3. Start

```powershell
powershell -ExecutionPolicy Bypass -File scripts\native.ps1 start
```

The first start needs internet access and takes a few minutes. It downloads Python 3.12 and the
Python packages (`uv sync`), installs the web packages (`pnpm install`), creates the database
folder `.local\pgdata`, and builds the web application. Later starts take about 10 seconds. The
web application is rebuilt automatically when its source files change, for example after
`git pull`.

The script checks each step and stops with a message and a hint if something is missing. When
it is ready:

```text
  [ ok ] Python 3.12.x with the project packages
  [ ok ] Node.js v22.x
  [ ok ] PostgreSQL 16 started (port 5433, data in .local/pgdata)
  [ ok ] frontend build is up to date
  [ ok ] API healthy (http://127.0.0.1:8000, database connected)
  [note] No Redis server: running without the job queue. Everything works except 'Run high-resolution solve'.
  [ ok ] frontend healthy (serving the app and forwarding /api to port 8000)

EMF-Visu is running:  http://localhost:8080
```

Open **<http://localhost:8080>**. The PowerShell window can be closed; the application keeps
running in the background until you stop it.

## 4. Stop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\native.ps1 stop
```

This stops the web server and the API, and shuts the database down cleanly (`pg_ctl stop -m fast`).
Your saved projects stay in `.local\pgdata` and are there again on the next start.

Stop before shutting down Windows if you can. If Windows shuts down while the application is
running, PostgreSQL recovers automatically on the next start; saved projects are not lost.

## 5. Status and logs

```powershell
powershell -ExecutionPolicy Bypass -File scripts\native.ps1 status
```

This shows each part as running or stopped, and the application's own health report. In that
report, `"status": "degraded"` with `"redis": {"ok": false}` is expected without the queue.

Each part writes a log file:

| File | Contents |
|---|---|
| `.local\logs\api.log` | API and physics engine |
| `.local\logs\frontend.log` | web server |
| `.local\logs\frontend-build.log` | last build of the web application |
| `.local\logs\postgres.log` | database |

To see the end of a log:

```powershell
Get-Content .local\logs\api.log -Tail 50
```

## 6. Configuration (optional)

Nothing needs configuring. To change a port, create a file named `.env` in the project folder
with any of these lines:

| Setting | Default | Meaning |
|---|---|---|
| `FRONTEND_PORT` | 8080 | port of the web application |
| `API_PORT` | 8000 | port of the API |
| `EMF_PG_PORT` | 5433 | port of the project database |
| `EMF_PG_BIN` | found automatically | folder that contains `pg_ctl.exe` |
| `EMF_REDIS_URL` | `redis://localhost:6379/0` | where to look for an optional Redis server (section 7) |

The native scripts set the database address themselves; `EMF_DATABASE_URL` in `.env` is not used
by them. The Docker version reads the same `.env` file and ignores the `EMF_PG_*` settings.

## 7. Saved projects and the queue

- **Where projects are kept:** in `.local\pgdata` inside the project folder. Git ignores this
  folder, and `git pull` does not touch it.
- **Backup:** stop the application, then copy the whole `.local\pgdata` folder.
- **Delete all saved projects** (cannot be undone): stop the application, then delete the
  `.local\pgdata` folder. The next start creates an empty one.
- **Docker and native are separate:** projects saved in the Docker version (in the volume
  `emf-visu_pgdata`) do not appear in the native version, and the other way round. Do not run
  both at the same time; they use the same ports 8080 and 8000.
- **High-resolution solves (optional):** they need a Redis-compatible server, which has no
  official Windows build. If one answers at `EMF_REDIS_URL` when you start, the script also
  starts the solver worker (Celery with `--pool solo`, the mode Celery supports on Windows), and
  the button works. Examples are Memurai, or Redis inside WSL. This is optional, and this path
  has not been tried on Windows.

## 8. Troubleshooting

| Message or symptom | Cause and fix |
|---|---|
| "running scripts is disabled on this system" | Use the exact command with `-ExecutionPolicy Bypass` shown above. |
| `npm : File ... npm.ps1 cannot be loaded because running scripts is disabled` | Use `npm.cmd` in place of `npm`, e.g. `npm.cmd install -g pnpm@10`. |
| `corepack enable` fails with `EPERM: operation not permitted` | It needs administrator rights. Use `npm.cmd install -g pnpm@10` instead. |
| "uv was not found" (or node, pnpm) right after installing | Open a new PowerShell window; installers change `PATH` only for new windows. |
| "PostgreSQL was not found." | Install it (section 1) or set `EMF_PG_BIN` in `.env` to the folder containing `pg_ctl.exe`. |
| "Port 8080 (or 8000, 5433) is already in use" | Another program uses it, for example the Docker version (`docker compose down`). Stop it, or choose another port in `.env`. |
| "The project database was created by PostgreSQL 16, but the PostgreSQL found is 17" | Several versions are installed. Set `EMF_PG_BIN` to the version-16 `bin` folder. Do not delete `.local\pgdata` to fix this; it holds your projects. |
| "PostgreSQL did not start" | The message shows the end of `.local\logs\postgres.log`. A common cause is a project folder inside OneDrive or one without write permission; see section 2. |
| "uv sync failed" or "pnpm install failed" on the first start | Usually no internet access, or a company proxy. Check the messages; behind a proxy, set `HTTPS_PROXY` before starting. |
| Status bar says *worker offline*; *Run high-resolution solve* is greyed out | Expected without Redis (section 7). Everything else works. |
| Browser shows "API offline" | Run the status command and look at `.local\logs\api.log`. |
| Page loads but the 3D view is blank or very slow | The browser lacks WebGL 2 or hardware acceleration. Enable it in the browser settings, or try Chrome or Edge. |

## 9. For developers

The native scripts serve a production build, like the Docker version. For live reloading while
editing code, start the database with the native script, and then use the development commands
from the README in separate windows, pointing them at the native database:

```powershell
$env:EMF_DATABASE_URL = "postgresql+psycopg://emf:emf@127.0.0.1:5433/emf"
```

```powershell
uv run uvicorn emf_api.main:app --reload --port 8000
```

```powershell
cd frontend; pnpm dev
```

Then open <http://localhost:5173>. Stop the native API and web server first (the stop command
stops all parts, including the database), or the ports clash.

The end-to-end test runs against the native stack with the queue check adapted:

```powershell
$env:EMF_E2E_NO_WORKER = "1"; node tests/e2e/smoke.cjs http://localhost:8080
```

How it works: `scripts\native.ps1` runs `uv sync` and then `scripts\native.py`, a Python
script using only the standard library plus `psycopg` and `redis` from the project. The script
starts each part as a background process, records its process ID in `.local\run`, waits for
the health endpoints, and on failure prints the end of the relevant log and stops what it had
started. `stop` ends each recorded process tree (`taskkill /T /F`) after checking that the
process is still the one it started (same program, started after the computer's last
restart), and stops PostgreSQL with `pg_ctl`.

## 10. What has been verified, and where

Verified in the development environment (Linux x86_64, PostgreSQL 16.15, Node 22, Python
3.12), using the same `scripts/native.py` through `scripts/native.sh`:

- A first start, with no `.local` folder, created the database folder and the `emf` database
  and brought the API and the web application up healthy, without Docker and without Redis.
- The full browser test passed against it. All 35 checks passed, with the high-resolution check
  replaced by "disabled and reported unavailable".
- A project saved through the application was still there after stop and start.
- Stop ended all processes, freed the ports, and shut PostgreSQL down cleanly. A second stop
  and the status command reported correctly.
- Error paths were each reported with a hint: port 8080 in use, port 5433 in use, and running as
  root (PostgreSQL refuses to run as root on Linux and macOS).
- A changed source file triggered a rebuild on the next start.
- With a Redis server present, the worker was started automatically. The full browser test,
  including the high-resolution job, passed 35 of 35. Stop ended the worker too.
- Backend tests (203), frontend tests (43), type checks and lint: passing.

Not verified:

- **Windows itself.** No Windows machine was available. The Windows-specific parts were
  written for Windows but not executed: `scripts\native.ps1`, process handling (`taskkill`,
  detached processes, `tasklist`), PostgreSQL discovery under `C:\Program Files`, and `initdb`
  on Windows.
- **The `winget` package IDs** in section 1 were not run.
- **Your computer.**
