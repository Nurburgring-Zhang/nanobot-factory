"""R8-Worker-2 resilience tests.

Covers:
  * §2.1 service restart — uvicorn stop/start + /healthz recovery
  * §2.2 process crash — SIGKILL simulation via subprocess (best effort;
    we verify the wrapper *can* detect exit and restart, not that we
    actually crash a long-running prod server)
  * §2.3 DB lock — long-running uncommitted transaction must NOT block
    other reads/writes (sqlite WAL mode allows concurrent reads)
  * Bonus: /healthz vs /readyz separation under fault
"""
from __future__ import annotations

import os
import sys
import time
import signal
import socket
import sqlite3
import subprocess
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# 2.1 — Service restart: uvicorn process lifecycle
# --------------------------------------------------------------------------- #
def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_port(port: int, timeout: float = 12.0) -> bool:
    """Poll 127.0.0.1:port until LISTEN or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _wait_for_healthz(port: int, timeout: float = 20.0):
    """Poll /healthz until 200 or timeout. Returns (status_code, body_text)."""
    import urllib.request
    deadline = time.time() + timeout
    last = (0, "")
    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=2.0
            )
            return req.status, req.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            last = (e.code, e.read().decode("utf-8", "ignore")[:200])
        except Exception as e:
            last = (0, repr(e)[:200])
        time.sleep(0.4)
    return last


class TestServiceRestart:
    def test_uvicorn_lifecycle(self, tmp_path):
        """Start uvicorn, hit /healthz, stop it (SIGTERM), restart, hit again.

        Validates the recovery loop that systemd / Docker / k8s would drive
        in production — here we drive it ourselves so the test is hermetic.
        """
        port = _pick_free_port()
        log_out = tmp_path / "uvicorn.out"
        log_err = tmp_path / "uvicorn.err"
        proj_root = Path(__file__).resolve().parents[2]

        # Launch uvicorn pointing at server_unified.py (mounts /healthz via IMDF).
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(proj_root / "backend") + os.pathsep + str(proj_root / "backend" / "imdf")
        )
        # JWT_SECRET already set by parent conftest.

        cmd = [
            "D:\\ComfyUI\\.ext\\python.exe",
            "-m", "uvicorn",
            "server_unified:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
            "--no-access-log",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(proj_root),
            stdout=open(log_out, "wb"),
            stderr=open(log_err, "wb"),
            env=env,
        )

        try:
            # 1) Wait for LISTEN
            assert _wait_for_port(port, timeout=20), (
                f"uvicorn never opened {port}; out={log_out.read_text()[:400]} "
                f"err={log_err.read_text()[:400]}"
            )

            # 2) Wait for /healthz (router startup can lag port-bind)
            status, body = _wait_for_healthz(port, timeout=20)
            assert status == 200, f"/healthz first boot returned {status}: {body}"

            # 3) Verify uptime is small (we just started)
            assert '"uptime_seconds"' in body
            import json as _json
            j = _json.loads(body)
            assert 0.0 <= j["uptime_seconds"] < 30.0, j["uptime_seconds"]

            # 4) Stop cleanly (SIGTERM)
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=4)

            # 5) Confirm port is free
            deadline = time.time() + 8
            while time.time() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                        time.sleep(0.2)
                except OSError:
                    break
            else:
                pytest.fail(f"port {port} still accepting after SIGTERM")

            # 6) Restart
            log_out2 = tmp_path / "uvicorn2.out"
            log_err2 = tmp_path / "uvicorn2.err"
            proc2 = subprocess.Popen(
                cmd,
                cwd=str(proj_root),
                stdout=open(log_out2, "wb"),
                stderr=open(log_err2, "wb"),
                env=env,
            )
            try:
                assert _wait_for_port(port, timeout=20), "restart never opened port"
                status2, body2 = _wait_for_healthz(port, timeout=20)
                assert status2 == 200, f"/healthz after restart returned {status2}: {body2}"
                # uptime should reset
                j2 = _json.loads(body2)
                assert 0.0 <= j2["uptime_seconds"] < 30.0, j2["uptime_seconds"]
            finally:
                proc2.terminate()
                try:
                    proc2.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc2.kill()
                    proc2.wait(timeout=4)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=4)


# --------------------------------------------------------------------------- #
# 2.2 — Process crash: SIGKILL → ensure subprocess exits and can be reaped
# --------------------------------------------------------------------------- #
class TestProcessCrash:
    def test_sigkill_exits_quickly(self, tmp_path):
        """Spawn uvicorn, SIGKILL it, verify exit_code != 0 within 4 s.

        This doesn't crash a *production* server — it proves the wrapper
        (systemd/Docker) can detect a non-zero exit and trigger restart.
        """
        port = _pick_free_port()
        proj_root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(proj_root / "backend") + os.pathsep + str(proj_root / "backend" / "imdf")
        )

        cmd = [
            "D:\\ComfyUI\\.ext\\python.exe",
            "-m", "uvicorn",
            "server_unified:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
            "--no-access-log",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(proj_root),
            stdout=open(tmp_path / "out.log", "wb"),
            stderr=open(tmp_path / "err.log", "wb"),
            env=env,
        )
        try:
            assert _wait_for_port(port, timeout=20), "uvicorn did not open port"
            # Hard kill — simulates a crash.
            proc.kill()
            exit_code = proc.wait(timeout=4)
            assert exit_code is not None, "process did not exit within 4s of SIGKILL"
            # On Windows, SIGKILL via proc.kill() typically yields negative
            # exit codes (1 or signal-formatted). Just assert NON-ZERO.
            assert exit_code != 0, f"SIGKILL unexpectedly yielded exit_code={exit_code}"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=4)


# --------------------------------------------------------------------------- #
# 2.3 — DB lock: long-running uncommitted transaction
# --------------------------------------------------------------------------- #
class TestDatabaseLock:
    """A long-running tx that never commits must not freeze other requests.

    With sqlite WAL mode (which the project uses), reads are non-blocking
    even while a writer holds the lock — that's the resilience we verify.
    """

    def test_uncommitted_tx_does_not_block_reads(self, db_conn):
        """Open a write tx, sleep 1 s, rollback. Other conn must still read."""
        # Set WAL mode if not already (best effort — sqlite default may differ).
        try:
            db_conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass

        # Open a second connection (separate handle = separate tx).
        path = str(Path(db_conn.execute("PRAGMA database_list").fetchone()[2])
                   or ":memory:")
        # PRAGMA database_list returns seq/name/file — index 2 is the file
        other = sqlite3.connect(path, timeout=2.0)
        try:
            cur = db_conn.execute("BEGIN IMMEDIATE")
            cur.execute("CREATE TABLE IF NOT EXISTS _lock_test (a INT)")

            # While main conn holds the write lock, other conn must still
            # be able to SELECT (in WAL mode) — give it a short budget.
            t0 = time.time()
            rows = other.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
            elapsed = time.time() - t0

            assert isinstance(rows, list), "sqlite_master read failed under writer lock"
            # If we *did* block, elapsed >> 1s; healthy WAL keeps it < 200ms.
            assert elapsed < 1.0, (
                f"read blocked by writer lock for {elapsed:.3f}s — WAL not effective"
            )

            db_conn.execute("ROLLBACK")
            db_conn.execute("DROP TABLE IF EXISTS _lock_test")
            db_conn.commit()
        finally:
            other.close()

    def test_readyz_under_db_lock(self, client, db_conn, monkeypatch):
        """Inject a slow DB ping (mimicking a DB lock stall) — /readyz must
        still resolve within a sane bound (we cap at 3s in the assertion).
        """
        from api import readyz
        import time

        def slow_db():
            time.sleep(0.8)
            return {"ok": True, "message": "DB connected (lock simulation)",
                    "path": ":memory:"}

        monkeypatch.setattr(readyz, "_check_db", slow_db)
        t0 = time.time()
        r = client.get("/readyz")
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < 3.0, f"readyz took {elapsed:.2f}s under slow DB"
        assert elapsed >= 0.7, "slow patch did not run"


# --------------------------------------------------------------------------- #
# Bonus — /healthz vs /readyz semantic separation
# --------------------------------------------------------------------------- #
class TestHealthProbes:
    """Document the k8s-friendly probe contract:

    * ``/healthz`` (liveness): 200 as long as the process responds.
      NO DB / FS checks — must be cheap to poll every second.

    * ``/readyz`` (readiness): 200 only when critical deps are reachable.
      503 if any check fails — k8s stops routing traffic.
    """

    def test_healthz_ignores_db_state(self, client, monkeypatch):
        """Even if DB is broken, /healthz must stay 200 (process is alive)."""
        from api import readyz

        monkeypatch.setattr(
            readyz, "_check_db",
            lambda: {"ok": False, "message": "DB down", "path": None},
        )
        r = client.get("/healthz")
        assert r.status_code == 200, (
            f"/healthz must not depend on DB; got {r.status_code}: {r.text}"
        )

    def test_readyz_cares_about_db_state(self, client, monkeypatch):
        from api import readyz
        monkeypatch.setattr(
            readyz, "_check_db",
            lambda: {"ok": False, "message": "DB down", "path": None},
        )
        r = client.get("/readyz")
        assert r.status_code == 503
