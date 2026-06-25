"""Launch all 12 services + 1 gateway for load testing (P6-Fix-B-6-2).

Robust against non-ASCII paths (uses subprocess.Popen directly, no PowerShell).
Each service runs on its own port and writes to tests/load/services/<name>.log.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # D:\Hermes\生产平台\nanobot-factory
BACKEND = ROOT / "backend"
LOG_DIR = ROOT / "tests" / "load" / "services"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PY = Path(r"D:\ComfyUI\.ext\python.exe")

# Env: shared by all child processes
ENV_BASE = {
    **os.environ,
    "PYTHONPATH": str(BACKEND),
    "JWT_SECRET": "KFWonsp6d8L4zUg-UyMwFw9sIGF7yOQmBeiXWT47OCo",
    "IMDF_TEST_MODE": "1",
    "UVICORN_LOG_LEVEL": "warning",
    "RATE_LIMIT_ENABLED": "false",
    "GATEWAY_LOG_LEVEL": "WARNING",
    "IMDF_WEB_PORT": "8000",
}

SERVICES = [
    ("gateway",     8000, "gateway.main:app"),
    ("user",        8001, "services.user_service.main:app"),
    ("asset",       8002, "services.asset_service.main:app"),
    ("annotation",  8003, "services.annotation_service.main:app"),
    ("cleaning",    8004, "services.cleaning_service.main:app"),
    ("scoring",     8005, "services.scoring_service.main:app"),
    ("dataset",     8006, "services.dataset_service.main:app"),
    ("evaluation",  8007, "services.evaluation_service.main:app"),
    ("agent",       8008, "services.agent_service.main:app"),
    ("workflow",    8009, "services.workflow_service.main:app"),
    ("notification",8010, "services.notification_service.main:app"),
    ("search",      8011, "services.search_service.main:app"),
    ("collection",  8012, "services.collection_service.main:app"),
]


def _port_in_use(port: int) -> int | None:
    """Return PID listening on port, or None."""
    for conn in _list_connections():
        if conn["local_port"] == port and conn["state"] == "LISTEN":
            return conn["pid"]
    return None


def _list_connections():
    """Best-effort cross-platform port list."""
    import psutil
    out = []
    for c in psutil.net_connections(kind="inet"):
        if c.laddr:
            out.append({
                "local_port": c.laddr.port,
                "state": c.status,
                "pid": c.pid or 0,
            })
    return out


def _kill_port(port: int):
    pid = _port_in_use(port)
    if pid:
        try:
            import psutil
            p = psutil.Process(pid)
            p.kill()
            print(f"  [kill] port {port} (pid {pid})")
        except Exception as e:
            print(f"  [kill-fail] port {port} pid {pid}: {e}")


def _wait_port(port: int, timeout_s: float = 5.0) -> bool:
    """Wait until TCP connect succeeds on the port."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    print(f"ROOT: {ROOT}")
    print(f"PYTHONPATH: {BACKEND}")
    print(f"Log dir: {LOG_DIR}")
    print()

    # 1) Kill any existing services on the target ports
    print("Step 1: clearing ports 8000-8012")
    for _, port, _ in SERVICES:
        _kill_port(port)
    time.sleep(2)

    # 2) Launch each service
    print()
    print("Step 2: launching 13 services (1 gateway + 12 microservices)")
    procs: list[tuple[str, int, subprocess.Popen]] = []
    for name, port, module in SERVICES:
        log_file = LOG_DIR / f"{name}.log"
        err_file = LOG_DIR / f"{name}.err"
        log_fp = open(log_file, "wb")
        err_fp = open(err_file, "wb")
        args = [
            str(PY), "-u", "-m", "uvicorn", module,
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning", "--no-access-log",
        ]
        try:
            p = subprocess.Popen(
                args,
                cwd=str(ROOT),
                env=ENV_BASE,
                stdout=log_fp,
                stderr=err_fp,
                creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
            )
            procs.append((name, port, p))
            print(f"  [start] {name:12s} port {port:5d} pid {p.pid}")
        except Exception as e:
            print(f"  [FAIL ] {name:12s} port {port:5d} -> {e}")
        finally:
            log_fp.close()
            err_fp.close()

    # 3) Wait for services to bind ports
    print()
    print("Step 3: waiting for services to bind ports (up to 60s)")
    ready: dict[str, bool] = {}
    deadline = time.time() + 60
    while time.time() < deadline:
        all_ready = True
        for name, port, _ in procs:
            if ready.get(name):
                continue
            if _port_in_use(port):
                ready[name] = True
                print(f"  [OK ] {name:12s} :{port}")
            else:
                all_ready = False
        if all_ready and len(ready) == len(procs):
            break
        time.sleep(1)

    # 4) Final report
    print()
    print(f"Step 4: ready = {sum(ready.values())} / {len(procs)}")
    failed = [name for name, _, _ in procs if not ready.get(name)]
    if failed:
        print(f"  [FAIL] {failed}")
        for name in failed:
            err_file = LOG_DIR / f"{name}.err"
            if err_file.exists():
                lines = err_file.read_text(encoding="utf-8", errors="replace").splitlines()
                print(f"  --- {name}.err last 10 lines ---")
                for line in lines[-10:]:
                    print(f"    {line}")
    else:
        print("  [OK] all 13 services bound their ports")
        # Probe /healthz for each
        print()
        print("Step 5: /healthz probes")
        for name, port, _ in procs:
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
                    print(f"  {name:12s} :{port} /healthz -> {r.status} {r.read().decode()[:80]}")
            except Exception as e:
                print(f"  {name:12s} :{port} /healthz -> FAIL {e}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
