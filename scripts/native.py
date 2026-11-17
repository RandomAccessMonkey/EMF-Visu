#!/usr/bin/env python3
"""Run EMF-Visu natively, without Docker: start | stop | status.

Components and where they listen (all on this computer only):

* PostgreSQL  - a private cluster in .local/pgdata, port 5433 (EMF_PG_PORT), started and
                stopped by this script with pg_ctl. Saved projects live there.
* API         - FastAPI/uvicorn on 127.0.0.1:8000 (API_PORT).
* Frontend    - the built web app served by `vite preview` on 127.0.0.1:8080 (FRONTEND_PORT),
                forwarding /api to the API. Rebuilt automatically when its sources change.
* Worker      - the Celery solver worker (--pool solo), started ONLY when a Redis-compatible
                server answers at EMF_REDIS_URL. Without it, everything works except queued
                high-resolution solves, which the app reports as unavailable.

Run it with the project's virtual environment (the wrappers do this):
    scripts\\native.ps1 start     (macOS / Linux: ./scripts/native.sh start)
Logs: .local/logs/<component>.log.  Process records: .local/run/<component>.json.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
LOGS = LOCAL / "logs"
RUN = LOCAL / "run"
PGDATA = LOCAL / "pgdata"
FRONTEND = ROOT / "frontend"
WINDOWS = os.name == "nt"
DB_USER = DB_PASSWORD = DB_NAME = "emf"
PG_MAJOR_MIN = 14


# ------------------------------------------------------------------------- output helpers


def say(msg: str) -> None:
    print(msg, flush=True)


def ok(msg: str) -> None:
    say(f"  [ ok ] {msg}")


def note(msg: str) -> None:
    say(f"  [note] {msg}")


class Failure(Exception):
    def __init__(self, message: str, hints: list[str] | None = None, log: Path | None = None):
        super().__init__(message)
        self.hints = hints or []
        self.log = log


def tail(path: Path, lines: int = 25) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


# --------------------------------------------------------------------------- configuration


def read_env_file() -> dict[str, str]:
    """KEY=VALUE pairs from the project's .env (the same file docker compose reads)."""
    values: dict[str, str] = {}
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def setting(name: str, default: str, env_file: dict[str, str]) -> str:
    return os.environ.get(name) or env_file.get(name) or default


class Config:
    def __init__(self) -> None:
        f = read_env_file()
        self.frontend_port = int(setting("FRONTEND_PORT", "8080", f))
        self.api_port = int(setting("API_PORT", "8000", f))
        self.pg_port = int(setting("EMF_PG_PORT", "5433", f))
        self.pg_bin = setting("EMF_PG_BIN", "", f)
        self.redis_url = setting("EMF_REDIS_URL", "redis://localhost:6379/0", f)
        self.database_url = (f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@127.0.0.1:"
                             f"{self.pg_port}/{DB_NAME}")
        self.url = f"http://localhost:{self.frontend_port}"

    def service_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({
            "EMF_DATABASE_URL": self.database_url,
            "EMF_REDIS_URL": self.redis_url,
            "EMF_CORS_ORIGINS": f"http://localhost:{self.frontend_port},"
                                f"http://127.0.0.1:{self.frontend_port}",
            # 127.0.0.1, not localhost: on Windows "localhost" may resolve to ::1 first while
            # the API listens on IPv4 only.
            "EMF_API_PROXY_TARGET": f"http://127.0.0.1:{self.api_port}",
            "PYTHONUNBUFFERED": "1",
        })
        return env


# ----------------------------------------------------------------------------- processes


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def http_ok(url: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - local URL
            body = r.read()
            try:
                parsed: dict[str, Any] = json.loads(body)
                return parsed
            except ValueError:
                return {}
    except (urllib.error.URLError, OSError, ValueError):
        return None


def record_path(name: str) -> Path:
    return RUN / f"{name}.json"


def read_record(name: str) -> dict[str, Any] | None:
    try:
        rec: dict[str, Any] = json.loads(record_path(name).read_text(encoding="utf-8"))
        return rec
    except (OSError, ValueError):
        return None


def process_command(pid: int) -> str | None:
    """Command line (or image name on Windows) of a running process, None if not running."""
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, check=False).stdout
        return out.split(",")[0].strip('"').lower() if f'"{pid}"' in out else None
    proc = Path(f"/proc/{pid}/cmdline")
    if proc.exists():
        try:
            return proc.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            return None
    out = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True,
                         text=True, check=False).stdout.strip()
    return out or None


def boot_time() -> float:
    """When this computer last started (Unix time), 0 if unknown."""
    try:
        if WINDOWS:
            import ctypes

            ticks = ctypes.windll.kernel32.GetTickCount64  # type: ignore[attr-defined]
            ticks.restype = ctypes.c_uint64
            return time.time() - float(ticks()) / 1000.0
        uptime = float(Path("/proc/uptime").read_text().split()[0])
        return time.time() - uptime
    except (OSError, ValueError, AttributeError, IndexError):
        return 0.0


def alive(rec: dict[str, Any]) -> bool:
    """The recorded process still runs and is still ours. Guards against reused process IDs: a
    record from before the last restart of the computer is stale whatever runs under its PID."""
    if float(rec.get("started", 0)) < boot_time() - 5:
        return False
    cmd = process_command(int(rec["pid"]))
    if cmd is None:
        return False
    return rec["windows_image"] in cmd if WINDOWS else rec["marker"] in cmd


def spawn(name: str, args: list[str], marker: str, cwd: Path, env: dict[str, str]) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    RUN.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")  # noqa: SIM115 - handed to the child process
    log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start =====\n".encode())
    log.flush()
    kwargs: dict[str, Any] = {"cwd": cwd, "env": env, "stdout": log, "stderr": subprocess.STDOUT,
                              "stdin": subprocess.DEVNULL}
    if WINDOWS:
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                                   | subprocess.DETACHED_PROCESS)  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **kwargs)  # noqa: S603 - fixed argument lists
    image = Path(args[0]).name.lower()
    record_path(name).write_text(json.dumps({"pid": proc.pid, "started": time.time(),
                                             "marker": marker,
                                             "windows_image": image, "args": args}),
                                 encoding="utf-8")


def terminate(name: str) -> str:
    rec = read_record(name)
    if rec is None:
        return "not running"
    if not alive(rec):
        record_path(name).unlink(missing_ok=True)
        return "not running (stale record removed)"
    pid = int(rec["pid"])
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGTERM)
        for _ in range(100):
            if not alive(rec):
                break
            time.sleep(0.1)
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)
    record_path(name).unlink(missing_ok=True)
    return "stopped"


def wait_for(check: Any, seconds: float, what: str, log: Path, hints: list[str]) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.5)
    raise Failure(f"{what} did not become ready within {int(seconds)} s.", hints, log)


# ---------------------------------------------------------------------------- PostgreSQL


def find_pg_bin(cfg: Config) -> Path:
    exe = "pg_ctl.exe" if WINDOWS else "pg_ctl"
    candidates: list[Path] = []
    if cfg.pg_bin:
        candidates.append(Path(cfg.pg_bin))
    found = shutil.which("pg_ctl")
    if found:
        candidates.append(Path(found).parent)
    if WINDOWS:
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),):
            root = Path(base) / "PostgreSQL"
            if root.is_dir():
                versions = sorted((p for p in root.iterdir() if p.name.split(".")[0].isdigit()),
                                  key=lambda p: int(p.name.split(".")[0]), reverse=True)
                candidates += [v / "bin" for v in versions]
    else:
        for pattern in ("/usr/lib/postgresql/*/bin", "/opt/homebrew/opt/postgresql@*/bin",
                        "/usr/local/opt/postgresql@*/bin",
                        "/Applications/Postgres.app/Contents/Versions/*/bin"):
            candidates += sorted(Path("/").glob(pattern.lstrip("/")), reverse=True)
    for c in candidates:
        if (c / exe).is_file():
            return c
    raise Failure("PostgreSQL was not found.", [
        "Install PostgreSQL 16 (see docs/native-windows.md, step 1), or set EMF_PG_BIN to its",
        "bin folder, e.g.  EMF_PG_BIN=C:\\Program Files\\PostgreSQL\\16\\bin  in the .env file.",
    ])


def pg_major(bin_dir: Path) -> int:
    exe = bin_dir / ("pg_ctl.exe" if WINDOWS else "pg_ctl")
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                         check=False).stdout
    digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in out).split()
    return int(digits[0].split(".")[0]) if digits else 0


def pg(bin_dir: Path, tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    exe = bin_dir / (f"{tool}.exe" if WINDOWS else tool)
    return subprocess.run([str(exe), *args], capture_output=True, text=True, check=False)


def db_connect(cfg: Config, dbname: str = DB_NAME) -> bool:
    import psycopg

    try:
        with psycopg.connect(host="127.0.0.1", port=cfg.pg_port, user=DB_USER,
                             password=DB_PASSWORD, dbname=dbname, connect_timeout=3):
            return True
    except psycopg.Error:
        return False


PG_CONF_MARK = "# --- EMF-Visu native run (scripts/native.py) ---"


def ensure_pg_conf() -> None:
    """Local-only TCP and no Unix socket (whose default folder may need root on Linux)."""
    conf = PGDATA / "postgresql.conf"
    text = conf.read_text(encoding="utf-8")
    if PG_CONF_MARK not in text:
        conf.write_text(text.rstrip("\n") + f"\n\n{PG_CONF_MARK}\nlisten_addresses = '127.0.0.1'\n"
                        "unix_socket_directories = ''\n", encoding="utf-8")


def start_postgres(cfg: Config) -> None:
    bin_dir = find_pg_bin(cfg)
    major = pg_major(bin_dir)
    if major < PG_MAJOR_MIN:
        raise Failure(f"PostgreSQL {major} is too old; version {PG_MAJOR_MIN} or newer is needed.",
                      [f"Found in {bin_dir}. Install PostgreSQL 16 or set EMF_PG_BIN."])
    log = LOGS / "postgres.log"
    if not (PGDATA / "PG_VERSION").is_file():
        say(f"  First run: creating the project database in {PGDATA} ...")
        PGDATA.parent.mkdir(parents=True, exist_ok=True)
        pwfile = LOCAL / "pg-initial-password.txt"
        pwfile.write_text(DB_PASSWORD + "\n", encoding="utf-8")
        try:
            r = pg(bin_dir, "initdb", "-D", str(PGDATA), "-U", DB_USER, "-A", "scram-sha-256",
                   f"--pwfile={pwfile}", "-E", "UTF8", "--locale=C", "--no-instructions")
        finally:
            pwfile.unlink(missing_ok=True)
        if r.returncode != 0:
            raise Failure("Creating the database folder (initdb) failed.",
                          [line for line in (r.stdout + r.stderr).splitlines()[-8:] if line])
    else:
        data_major = int((PGDATA / "PG_VERSION").read_text().strip().split(".")[0])
        if data_major != major:
            raise Failure(
                f"The project database was created by PostgreSQL {data_major}, but the "
                f"PostgreSQL found is {major}.",
                [f"Point EMF_PG_BIN to a PostgreSQL {data_major} bin folder. Your data in "
                 f"{PGDATA} is untouched; never delete it to 'fix' this."])
    ensure_pg_conf()
    status = pg(bin_dir, "pg_ctl", "-D", str(PGDATA), "status")
    if status.returncode == 0:
        ok(f"PostgreSQL already running (port {cfg.pg_port})")
    else:
        if port_open(cfg.pg_port):
            raise Failure(f"Port {cfg.pg_port} (the project database) is used by another program.",
                          ["Set EMF_PG_PORT to a free port in the .env file."])
        LOGS.mkdir(parents=True, exist_ok=True)
        # Output to a file, not a pipe: the server inherits pg_ctl's handles, and on Windows an
        # inherited pipe would keep this call waiting for as long as the server runs.
        ctl_log = LOGS / "pg_ctl.log"
        exe = bin_dir / ("pg_ctl.exe" if WINDOWS else "pg_ctl")
        with open(ctl_log, "wb") as out:
            code = subprocess.run([str(exe), "-D", str(PGDATA), "-l", str(log), "-w", "-t", "60",
                                   "-o", f"-p {cfg.pg_port}", "start"], stdout=out,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  check=False).returncode
        if code != 0:
            raise Failure("PostgreSQL did not start.", tail(ctl_log, 6).splitlines(), log)
        ok(f"PostgreSQL {major} started (port {cfg.pg_port}, data in .local/pgdata)")
    if not db_connect(cfg):
        if not db_connect(cfg, "postgres"):
            raise Failure("Cannot connect to the project database.", [
                "The data folder exists but rejects the expected login. It was not created by",
                "this script, or its settings were changed.",
            ], log)
        import psycopg

        with psycopg.connect(host="127.0.0.1", port=cfg.pg_port, user=DB_USER,
                             password=DB_PASSWORD, dbname="postgres", autocommit=True) as c:
            c.execute(f"CREATE DATABASE {DB_NAME}")
        ok(f"database '{DB_NAME}' created")


def stop_postgres(cfg: Config) -> str:
    try:
        bin_dir = find_pg_bin(cfg)
    except Failure:
        return "PostgreSQL not found (nothing to stop)"
    if not (PGDATA / "PG_VERSION").is_file():
        return "no project database"
    if pg(bin_dir, "pg_ctl", "-D", str(PGDATA), "status").returncode != 0:
        return "not running"
    r = pg(bin_dir, "pg_ctl", "-D", str(PGDATA), "-m", "fast", "-w", "-t", "60", "stop")
    return "stopped cleanly" if r.returncode == 0 else f"stop failed: {r.stderr.strip()[:200]}"


# ------------------------------------------------------------------------ app components


def redis_available(cfg: Config) -> bool:
    import redis

    try:
        redis.Redis.from_url(cfg.redis_url, socket_connect_timeout=0.5, socket_timeout=1).ping()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def node_version(node: str) -> str:
    return subprocess.run([node, "--version"], capture_output=True, text=True,
                          check=False).stdout.strip()


def node_exe() -> str:
    node = shutil.which("node")
    if not node:
        raise Failure("Node.js was not found.", [
            "Install Node.js 22 LTS (see docs/native-windows.md, step 1) and open a new terminal.",
        ])
    version = node_version(node).lstrip("v")
    major, minor = (int(x) for x in (version.split(".") + ["0", "0"])[:2])
    if (major, minor) < (22, 12):
        raise Failure(f"Node.js {version} is too old; version 22.12 or newer is needed.",
                      ["Install the current Node.js LTS (docs/native-windows.md, step 1)."])
    return node


def ensure_frontend_deps(node: str) -> None:
    marker = FRONTEND / "node_modules" / ".modules.yaml"
    lock = FRONTEND / "pnpm-lock.yaml"
    if ((FRONTEND / "node_modules" / "vite" / "bin" / "vite.js").is_file() and marker.is_file()
            and marker.stat().st_mtime >= lock.stat().st_mtime):
        return
    pnpm = shutil.which("pnpm")
    if not pnpm:
        raise Failure("The frontend packages are not installed and pnpm was not found.", [
            "Run:  npm.cmd install -g pnpm@10   (Windows; elsewhere: npm install -g pnpm@10)",
            "then open a NEW terminal window,",
            "then run this command again.",
        ])
    say("  Installing frontend packages (pnpm install) ...")
    r = subprocess.run([pnpm, "install", "--frozen-lockfile"], cwd=FRONTEND, check=False)
    if r.returncode != 0:
        raise Failure("pnpm install failed (see the messages above).")


def frontend_stale() -> bool:
    built = FRONTEND / "dist" / "index.html"
    if not built.is_file():
        return True
    newest = 0.0
    for path in [FRONTEND / "index.html", FRONTEND / "vite.config.ts", FRONTEND / "package.json",
                 FRONTEND / "pnpm-lock.yaml"]:
        if path.exists():
            newest = max(newest, path.stat().st_mtime)
    for path in (FRONTEND / "src").rglob("*"):
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest > built.stat().st_mtime


def build_frontend(node: str, cfg: Config) -> None:
    if not frontend_stale():
        ok("frontend build is up to date")
        return
    say("  Building the frontend (about 10-30 s) ...")
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / "frontend-build.log"
    with open(log, "wb") as out:
        r = subprocess.run([node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"),
                            "build"], cwd=FRONTEND, env=cfg.service_env(), stdout=out,
                           stderr=subprocess.STDOUT, check=False)
    if r.returncode != 0:
        raise Failure("The frontend build failed.", [], log)
    ok("frontend built")


def check_port_free(port: int, name: str, setting_name: str) -> None:
    rec = read_record(name)
    if rec and alive(rec):
        return
    if port_open(port):
        raise Failure(f"Port {port} is already in use by another program.", [
            "Stop that program (for example the Docker version: docker compose down), or set",
            f"{setting_name} to a free port in the .env file.",
        ])


# ------------------------------------------------------------------------------ commands


def preflight() -> None:
    if sys.version_info < (3, 12):  # noqa: UP036 - may be started with another Python
        raise Failure(f"Python {sys.version.split()[0]} is too old; 3.12 is needed.",
                      ["Use the wrapper scripts, which run the project's own Python (uv sync)."])
    try:
        import emf_api  # noqa: F401
        import emf_worker  # noqa: F401
    except ImportError as exc:
        raise Failure("The Python packages of the project are not installed.",
                      ["Run:  uv sync   in the project folder, then run this command again."]
                      ) from exc
    if not WINDOWS and hasattr(os, "geteuid") and os.geteuid() == 0:
        raise Failure("Do not run this as root: PostgreSQL refuses to run as root.",
                      ["Run it as your normal user."])


def cmd_start(cfg: Config) -> int:
    say("Starting EMF-Visu natively (no Docker)")
    started: list[str] = []
    try:
        preflight()
        ok(f"Python {sys.version.split()[0]} with the project packages")
        node = node_exe()
        ok(f"Node.js {node_version(node)}")
        check_port_free(cfg.api_port, "api", "API_PORT")
        check_port_free(cfg.frontend_port, "frontend", "FRONTEND_PORT")
        ensure_frontend_deps(node)
        start_postgres(cfg)
        build_frontend(node, cfg)
        env = cfg.service_env()

        rec = read_record("api")
        if rec and alive(rec):
            ok(f"API already running (port {cfg.api_port})")
        else:
            spawn("api", [sys.executable, "-m", "uvicorn", "emf_api.main:app", "--host",
                          "127.0.0.1", "--port", str(cfg.api_port)], "emf_api.main:app", ROOT, env)
            started.append("api")
        health = wait_for(lambda: http_ok(f"http://127.0.0.1:{cfg.api_port}/api/v1/health"), 60,
                          "The API", LOGS / "api.log",
                          ["See the log lines below; the status command shows every part."])
        if not health.get("database", {}).get("ok"):
            raise Failure("The API is running but cannot reach the database.",
                          [str(health.get("database", {}).get("detail"))], LOGS / "api.log")
        ok(f"API healthy (http://127.0.0.1:{cfg.api_port}, database connected)")

        if redis_available(cfg):
            rec = read_record("worker")
            if rec and alive(rec):
                ok("solver worker already running")
            else:
                spawn("worker", [sys.executable, "-m", "celery", "-A", "emf_worker.app", "worker",
                                 "-Q", "solver.analytical", "--pool", "solo", "--loglevel", "INFO"],
                      "emf_worker.app", ROOT, env)
                started.append("worker")
                ok("Redis found: solver worker started (high-resolution solves available)")
        else:
            note("No Redis server: running without the job queue. Everything works except "
                 "'Run high-resolution solve'.")

        rec = read_record("frontend")
        if rec and alive(rec):
            ok(f"frontend already running (port {cfg.frontend_port})")
        else:
            spawn("frontend", [node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"),
                               "preview", "--host", "127.0.0.1", "--port", str(cfg.frontend_port),
                               "--strictPort"], "vite", FRONTEND, env)
            started.append("frontend")
        wait_for(lambda: http_ok(f"http://127.0.0.1:{cfg.frontend_port}/api/v1/health"), 60,
                 "The frontend", LOGS / "frontend.log",
                 ["The web server or its /api forwarding to the API is not working."])
        ok(f"frontend healthy (serving the app and forwarding /api to port {cfg.api_port})")
    except Failure as f:
        say("")
        say(f"ERROR: {f}")
        for h in f.hints:
            say(f"  {h}")
        if f.log:
            say(f"\n--- last lines of {f.log.relative_to(ROOT)} ---\n{tail(f.log)}")
        for name in reversed(started):
            terminate(name)
        if started:
            say("\n(Components started by this attempt were stopped again; PostgreSQL keeps "
                "running. Stop it with the stop command if you like.)")
        return 1
    say("")
    say(f"EMF-Visu is running:  {cfg.url}")
    say(f"API documentation:    http://localhost:{cfg.api_port}/docs")
    say("Saved projects:       .local/pgdata (kept when you stop)")
    say("Stop with:  scripts\\native.ps1 stop   (macOS/Linux: ./scripts/native.sh stop)")
    return 0


def cmd_stop(cfg: Config) -> int:
    say("Stopping EMF-Visu (native)")
    for name in ("frontend", "worker", "api"):
        say(f"  {name:9s} {terminate(name)}")
    say(f"  postgres  {stop_postgres(cfg)}")
    say("Saved projects are kept in .local/pgdata.")
    return 0


def cmd_status(cfg: Config) -> int:
    say("EMF-Visu native status")
    for name, port in (("api", cfg.api_port), ("frontend", cfg.frontend_port)):
        rec = read_record(name)
        state = "running" if rec and alive(rec) else "stopped"
        say(f"  {name:9s} {state:8s} port {port}   log: .local/logs/{name}.log")
    rec = read_record("worker")
    worker = "running" if rec and alive(rec) else "stopped"
    say(f"  worker    {worker:8s} (Redis {'reachable' if redis_available(cfg) else 'not found'})")
    try:
        bin_dir = find_pg_bin(cfg)
        running = (PGDATA / "PG_VERSION").is_file() and pg(
            bin_dir, "pg_ctl", "-D", str(PGDATA), "status").returncode == 0
        say(f"  postgres  {'running' if running else 'stopped':8s} port {cfg.pg_port}   "
            "log: .local/logs/postgres.log")
    except Failure:
        say("  postgres  not installed")
    health = http_ok(f"http://127.0.0.1:{cfg.frontend_port}/api/v1/health")
    shown = json.dumps(health) if health is not None else "not reachable"
    say(f"\nApp health via {cfg.url}: {shown}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["start", "stop", "status"])
    args = parser.parse_args()
    cfg = Config()
    return {"start": cmd_start, "stop": cmd_stop, "status": cmd_status}[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
